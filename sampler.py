"""Background thread: sample all services on an interval, persist, prune."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import checks
import config
import store

log = logging.getLogger("dashboard.sampler")

PRUNE_EVERY_S = 3600


def sample_once(cfg: dict, now: int | None = None) -> dict[str, dict]:
    now = int(time.time()) if now is None else now
    tasks = [(sid, svc) for sid, _host, svc in config.iter_services(cfg)]
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = {ex.submit(checks.check_service, svc): sid for sid, svc in tasks}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                results[sid] = fut.result()
            except Exception:
                log.exception("action=check result=unknown service_id=%s", sid)
                results[sid] = {"status": "unknown"}
    store.record(results, now)
    return results


def _counts(results: dict[str, dict]) -> dict[str, int]:
    c = {"up": 0, "down": 0, "unknown": 0}
    for r in results.values():
        key = r.get("status", "unknown")
        c[key] = c.get(key, 0) + 1
    return c


def _loop(interval_s: int, retention_days: int) -> None:
    last_prune = 0.0
    while True:
        started = time.monotonic()
        try:
            results = sample_once(config.load_config())
            c = _counts(results)
            log.info("action=sample count=%d up=%d down=%d unknown=%d duration_ms=%d",
                     len(results), c["up"], c["down"], c["unknown"],
                     round((time.monotonic() - started) * 1000))
            if time.monotonic() - last_prune > PRUNE_EVERY_S:
                store.prune(int(time.time()) - retention_days * 86_400)
                last_prune = time.monotonic()
        except Exception:
            log.exception("action=sample result=error")
        time.sleep(max(1.0, interval_s - (time.monotonic() - started)))


def start(cfg: dict) -> None:
    dash = cfg.get("dashboard", {})
    interval_s = dash.get("sample_interval_seconds", 60)
    retention_days = dash.get("history_retention_days", 30)
    threading.Thread(
        target=_loop, args=(interval_s, retention_days),
        daemon=True, name="sampler",
    ).start()
    log.info("action=sampler_start interval_s=%d retention_days=%d",
             interval_s, retention_days)
