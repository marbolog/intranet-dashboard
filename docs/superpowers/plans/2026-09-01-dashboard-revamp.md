# Dashboard Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the intranet dashboard around a SQLite status-history subsystem — a 60-second in-process sampler feeding per-service uptime % and 24h sparklines — with a pruned config, a single-scroll UI, and fixed health-check semantics.

**Architecture:** Split the single `app.py` into five focused modules (`config`, `checks`, `store`, `sampler`, `app`). A daemon thread samples every service on an interval and writes rows to `dashboard.db`; both API endpoints become read-only DB queries. The front-end stays one static HTML file with vanilla JS, gaining inline-SVG sparklines and uptime figures.

**Tech Stack:** Python 3.11, Flask, requests, PyYAML, `sqlite3` (stdlib), pytest (dev). Vanilla JS, no build step.

**Spec:** `docs/superpowers/specs/2026-09-01-revamp-design.md` (sub-project B only; sub-project A, the decommission runbook, is executed separately and is not part of this plan)

## Global Constraints

- Python `>=3.11`.
- Runtime dependencies unchanged: `flask>=3.0`, `requests>=2.0`, `pyyaml>=6.0`. No new runtime deps. Persistence is stdlib `sqlite3` only — no ORM, no connection pool.
- `pytest>=8` is the only new dependency, dev-group only.
- No JavaScript build step. One static file: `static/index.html`. Vanilla JS, inline SVG.
- Health checks are pure functions with one structured log line per invocation, e.g. `action=check type=http target=http://192.168.50.13:8096/ result=up latency_ms=45`.
- Status states are exactly `up` / `down` / `unknown`. No `degraded`, no per-service expected-status config.
- Health-check priority in `check_service`: `url` > `docker_container` > `systemd_unit` > `file_fresh` > `unknown`.
- `dashboard.db` (+ `-wal`, `-shm`) lives in the repo directory and is gitignored.
- The systemd unit runs `.venv/bin/python app.py` as user `marcello` with `WorkingDirectory` = repo root. Do not change it.
- TDD: failing test first, minimal implementation, passing test, commit. One logical change per commit.
- Commit message trailer on every commit:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN
  ```

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `config.py` | create | Load `config.yaml`; compute stable `service_id`; enumerate services. |
| `checks.py` | create | `check_http` / `check_systemd` / `check_docker` / `check_file_fresh` / `check_service` — pure, logged. |
| `store.py` | create | SQLite schema, `init_db`, `record`, `prune`, `status_summary` (+ private aggregate helpers). |
| `sampler.py` | create | `sample_once` (one pass → DB) and `start` (daemon thread loop). |
| `app.py` | rewrite | Flask routes only; boots `store.init_db()` + `sampler.start()`; both `/api/*` endpoints read from `store`/`config`. |
| `config.yaml` | rewrite | Pruned to 14 services in 3 host groups; new `sample_interval_seconds` / `history_retention_days` keys; `file_fresh` for the RSS cron. |
| `static/index.html` | rewrite | Single-scroll layout, left-border status cards, inline-SVG sparklines, uptime figures. |
| `pyproject.toml` | modify | Add `pytest` dev group; `py-modules`; pytest config. |
| `.gitignore` | modify | Add `dashboard.db*`. |
| `tests/test_config.py` | create | `config` behaviour. |
| `tests/test_checks.py` | create | `checks` behaviour (mocked I/O). |
| `tests/test_store.py` | create | `store` behaviour (`tmp_path` DB). |
| `tests/test_sampler.py` | create | `sampler.sample_once` writes rows. |
| `tests/test_app.py` | create | Flask endpoints (test client). |
| `CLAUDE.md` | modify | New module list, health-check table, status-history section, pruned host table. |
| `README.md` | modify | New architecture description, endpoints, `file_fresh`. |
| `docs/superpowers/specs/2026-05-07-ui-redesign-design.md` | modify | Add "Superseded" banner. |

---

## Task 1: `config.py` + test scaffolding

**Files:**
- Create: `config.py`
- Modify: `pyproject.toml`
- Create: `tests/test_config.py`
- Create: `tests/__init__.py` (empty)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `config.load_config(path: pathlib.Path | None = None) -> dict` — reads `config.yaml` (or `path`).
  - `config.slugify(text: str) -> str`
  - `config.service_id(host: dict, svc: dict) -> str` — `"{ip_with_underscores}_{slug(name)}"`.
  - `config.iter_services(cfg: dict) -> Iterator[tuple[str, dict, dict]]` — yields `(service_id, host, svc)`.
  - `config.CONFIG_PATH: pathlib.Path`

- [ ] **Step 1: Add pytest dev dependency and config to `pyproject.toml`**

Append/modify so the file reads:

```toml
[project]
name = "intranet-dashboard"
version = "0.1.0"
description = "Home lab service dashboard with live health checks"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.0",
    "requests>=2.0",
    "pyyaml>=6.0",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
py-modules = ["app", "config", "checks", "store", "sampler"]

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Sync**

Run: `uv sync`
Expected: resolves and installs `pytest`.

- [ ] **Step 3: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 4: Write the failing test — `tests/test_config.py`**

```python
import textwrap

import config


def test_service_id_is_stable_and_slugified():
    host = {"ip": "192.168.50.13"}
    svc = {"name": "RSS Media Review"}
    assert config.service_id(host, svc) == "192_168_50_13_rss_media_review"


def test_service_id_falls_back_to_host_name_when_no_ip():
    assert config.service_id({"name": "Box"}, {"name": "S"}) == "box_s"


def test_iter_services_yields_every_service_with_id(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(textwrap.dedent("""
        hosts:
          - name: A
            ip: 10.0.0.1
            services:
              - name: One
                url: http://x/
              - name: Two
                systemd_unit: two.service
          - name: B
            ip: 10.0.0.2
            services:
              - name: Three
                docker_container: three
    """))
    cfg = config.load_config(cfg_file)
    ids = [sid for sid, _host, _svc in config.iter_services(cfg)]
    assert ids == ["10_0_0_1_one", "10_0_0_1_two", "10_0_0_2_three"]


def test_iter_services_empty_config():
    assert list(config.iter_services({})) == []
```

- [ ] **Step 5: Run — expect failure**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`.

- [ ] **Step 6: Implement `config.py`**

```python
"""Load config.yaml and enumerate services with stable IDs."""

import re
from pathlib import Path
from typing import Iterator

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    with open(path or CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def service_id(host: dict, svc: dict) -> str:
    ip = host.get("ip", host.get("name", "")).replace(".", "_")
    return f"{ip}_{slugify(svc['name'])}"


def iter_services(cfg: dict) -> Iterator[tuple[str, dict, dict]]:
    """Yield (service_id, host, svc) for every service in every host."""
    for host in cfg.get("hosts", []):
        for svc in host.get("services", []):
            yield service_id(host, svc), host, svc
```

- [ ] **Step 7: Run — expect pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml config.py tests/__init__.py tests/test_config.py uv.lock
git commit -m "Add config module and pytest scaffolding

Extracts config loading + service_id from app.py into config.py, adds
iter_services(). Introduces pytest as a dev-group dependency.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 2: `checks.py`

**Files:**
- Create: `checks.py`
- Create: `tests/test_checks.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `checks.check_http(url: str) -> dict` — `{"status": "up", "latency_ms": int}` or `{"status": "down"}`. `up` iff response status `< 400` or in `{401, 403}`. One retry on transport failure only.
  - `checks.check_systemd(unit: str) -> dict` — `{"status": "up"|"down"}`, or `{"status": "unknown"}` on subprocess error.
  - `checks.check_docker(container: str) -> dict` — `{"status": "up"|"down"}`, or `{"status": "unknown"}` on non-zero exit / error.
  - `checks.check_file_fresh(spec: dict) -> dict` — `spec` = `{"path": str, "max_age_minutes": int}`. `{"status": "up"|"down"}`.
  - `checks.check_service(svc: dict) -> dict` — dispatches by key priority.
  - Module attributes `checks.http_requests` (the `requests` module) and `checks.time` are used by tests via monkeypatch.

- [ ] **Step 1: Write the failing test — `tests/test_checks.py`**

```python
import os
import subprocess
import time

import checks


class FakeResp:
    def __init__(self, code):
        self.status_code = code


def test_http_200_is_up(monkeypatch):
    monkeypatch.setattr(checks.http_requests, "get", lambda *a, **k: FakeResp(200))
    result = checks.check_http("http://x/")
    assert result["status"] == "up"
    assert "latency_ms" in result


def test_http_302_is_up(monkeypatch):
    monkeypatch.setattr(checks.http_requests, "get", lambda *a, **k: FakeResp(302))
    assert checks.check_http("http://x/")["status"] == "up"


def test_http_401_and_403_are_up(monkeypatch):
    for code in (401, 403):
        monkeypatch.setattr(checks.http_requests, "get", lambda *a, **k: FakeResp(code))
        assert checks.check_http("http://x/")["status"] == "up"


def test_http_404_is_down(monkeypatch):
    monkeypatch.setattr(checks.http_requests, "get", lambda *a, **k: FakeResp(404))
    assert checks.check_http("http://x/")["status"] == "down"


def test_http_500_is_down(monkeypatch):
    monkeypatch.setattr(checks.http_requests, "get", lambda *a, **k: FakeResp(500))
    assert checks.check_http("http://x/")["status"] == "down"


def test_http_transport_error_retries_once_then_down(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise checks.http_requests.ConnectionError()

    monkeypatch.setattr(checks.http_requests, "get", boom)
    monkeypatch.setattr(checks.time, "sleep", lambda s: None)
    assert checks.check_http("http://x/")["status"] == "down"
    assert len(calls) == 2  # initial + one retry


def test_http_recovers_on_retry(monkeypatch):
    seq = [checks.http_requests.Timeout(), FakeResp(200)]

    def flaky(*a, **k):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(checks.http_requests, "get", flaky)
    monkeypatch.setattr(checks.time, "sleep", lambda s: None)
    assert checks.check_http("http://x/")["status"] == "up"


def _fake_run(stdout="", returncode=0):
    def run(*a, **k):
        return subprocess.CompletedProcess(a[0], returncode, stdout, "")
    return run


def test_systemd_active_is_up(monkeypatch):
    monkeypatch.setattr(checks.subprocess, "run",
                        _fake_run("ActiveState=active\nSubState=running\n"))
    assert checks.check_systemd("x.service")["status"] == "up"


def test_systemd_inactive_is_down(monkeypatch):
    monkeypatch.setattr(checks.subprocess, "run",
                        _fake_run("ActiveState=failed\nSubState=failed\n"))
    assert checks.check_systemd("x.service")["status"] == "down"


def test_systemd_subprocess_error_is_unknown(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(checks.subprocess, "run", boom)
    assert checks.check_systemd("x.service")["status"] == "unknown"


def test_docker_running_is_up(monkeypatch):
    monkeypatch.setattr(checks.subprocess, "run", _fake_run("true\n", 0))
    assert checks.check_docker("c")["status"] == "up"


def test_docker_stopped_is_down(monkeypatch):
    monkeypatch.setattr(checks.subprocess, "run", _fake_run("false\n", 0))
    assert checks.check_docker("c")["status"] == "down"


def test_docker_missing_container_is_unknown(monkeypatch):
    monkeypatch.setattr(checks.subprocess, "run", _fake_run("", 1))
    assert checks.check_docker("c")["status"] == "unknown"


def test_file_fresh_recent_is_up(tmp_path):
    f = tmp_path / "cron.log"
    f.write_text("run")
    assert checks.check_file_fresh({"path": str(f), "max_age_minutes": 60})["status"] == "up"


def test_file_fresh_stale_is_down(tmp_path):
    f = tmp_path / "cron.log"
    f.write_text("run")
    old = time.time() - 7200
    os.utime(f, (old, old))
    assert checks.check_file_fresh({"path": str(f), "max_age_minutes": 60})["status"] == "down"


def test_file_fresh_missing_is_down(tmp_path):
    spec = {"path": str(tmp_path / "nope.log"), "max_age_minutes": 60}
    assert checks.check_file_fresh(spec)["status"] == "down"


def test_check_service_priority(monkeypatch):
    monkeypatch.setattr(checks, "check_http", lambda url: {"status": "up", "src": "http"})
    monkeypatch.setattr(checks, "check_docker", lambda c: {"status": "up", "src": "docker"})
    monkeypatch.setattr(checks, "check_systemd", lambda u: {"status": "up", "src": "systemd"})
    svc = {"url": "http://x/", "docker_container": "c", "systemd_unit": "u"}
    assert checks.check_service(svc)["src"] == "http"
    assert checks.check_service({"docker_container": "c", "systemd_unit": "u"})["src"] == "docker"
    assert checks.check_service({"systemd_unit": "u"})["src"] == "systemd"
    assert checks.check_service({})["status"] == "unknown"
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_checks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'checks'`.

- [ ] **Step 3: Implement `checks.py`**

```python
"""Health checks for services. Pure functions — no persistence."""

import logging
import subprocess
import time
from pathlib import Path

import requests as http_requests

log = logging.getLogger("dashboard.checks")

HTTP_TIMEOUT_S = 3
HTTP_RETRY_DELAY_S = 0.5
REACHABLE_ERROR_CODES = {401, 403}  # server answered, just wants auth


def check_http(url: str) -> dict:
    """GET url; up iff status < 400 or an auth-wall code. Retry once on transport failure."""
    for attempt in (1, 2):
        try:
            start = time.monotonic()
            r = http_requests.get(url, timeout=HTTP_TIMEOUT_S, allow_redirects=True)
            latency = round((time.monotonic() - start) * 1000)
            up = r.status_code < 400 or r.status_code in REACHABLE_ERROR_CODES
            log.info("action=check type=http target=%s result=%s status=%s latency_ms=%d",
                     url, "up" if up else "down", r.status_code, latency)
            return {"status": "up", "latency_ms": latency} if up else {"status": "down"}
        except http_requests.RequestException as e:
            if attempt == 1:
                time.sleep(HTTP_RETRY_DELAY_S)
                continue
            log.warning("action=check type=http target=%s result=down error=%s",
                        url, type(e).__name__)
            return {"status": "down"}


def check_systemd(unit: str) -> dict:
    try:
        result = subprocess.run(
            ["systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState"],
            capture_output=True, text=True, timeout=3,
        )
        props = dict(
            line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
        )
        active = props.get("ActiveState", "")
        sub = props.get("SubState", "")
        up = active == "active"
        log.info("action=check type=systemd target=%s result=%s active=%s sub=%s",
                 unit, "up" if up else "down", active, sub)
        return {"status": "up"} if up else {"status": "down"}
    except Exception as e:
        log.warning("action=check type=systemd target=%s result=unknown error=%s",
                    unit, type(e).__name__)
        return {"status": "unknown"}


def check_docker(container: str) -> dict:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            log.warning("action=check type=docker target=%s result=unknown rc=%d",
                        container, result.returncode)
            return {"status": "unknown"}
        running = result.stdout.strip().lower() == "true"
        log.info("action=check type=docker target=%s result=%s",
                 container, "up" if running else "down")
        return {"status": "up"} if running else {"status": "down"}
    except Exception as e:
        log.warning("action=check type=docker target=%s result=unknown error=%s",
                    container, type(e).__name__)
        return {"status": "unknown"}


def check_file_fresh(spec: dict) -> dict:
    path = Path(spec["path"])
    max_age_s = spec["max_age_minutes"] * 60
    try:
        age_s = time.time() - path.stat().st_mtime
    except OSError:
        log.warning("action=check type=file_fresh target=%s result=down error=missing", path)
        return {"status": "down"}
    up = age_s <= max_age_s
    log.info("action=check type=file_fresh target=%s result=%s age_s=%d",
             path, "up" if up else "down", int(age_s))
    return {"status": "up"} if up else {"status": "down"}


def check_service(svc: dict) -> dict:
    if "url" in svc:
        return check_http(svc["url"])
    if "docker_container" in svc:
        return check_docker(svc["docker_container"])
    if "systemd_unit" in svc:
        return check_systemd(svc["systemd_unit"])
    if "file_fresh" in svc:
        return check_file_fresh(svc["file_fresh"])
    return {"status": "unknown"}
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_checks.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add checks.py tests/test_checks.py
git commit -m "Add checks module with fixed HTTP semantics and file_fresh

check_http now treats <400 and 401/403 as up (everything else down),
retries once on transport failure. New check_file_fresh for cron jobs.
Every check emits one structured log line.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 3: `store.py` — schema, `record`, `prune`

**Files:**
- Create: `store.py`
- Modify: `.gitignore`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `store.DB_PATH: pathlib.Path` — module-level, read at call time (never a bound default).
  - `store.init_db(db_path: Path | None = None) -> None` — creates table + index, sets WAL.
  - `store.record(results: dict[str, dict], ts: int, db_path: Path | None = None) -> None` — inserts one row per service. Each result dict has `status` (required) and optional `latency_ms`.
  - `store.prune(before_ts: int, db_path: Path | None = None) -> int` — deletes rows with `ts < before_ts`, returns count.
  - `store._connect(db_path) -> sqlite3.Connection` — `row_factory = sqlite3.Row`.

- [ ] **Step 1: Add `dashboard.db*` to `.gitignore`**

`.gitignore` becomes:

```
.venv/
__pycache__/
*.egg-info/
*.pyc
.superpowers/
dashboard.db
dashboard.db-wal
dashboard.db-shm
```

- [ ] **Step 2: Write the failing test — `tests/test_store.py`**

```python
import store


def test_init_db_is_idempotent(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    store.init_db(db)  # must not raise
    assert db.exists()


def test_record_inserts_one_row_per_service(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    store.record({"a": {"status": "up", "latency_ms": 12},
                  "b": {"status": "down"}}, ts=1000, db_path=db)
    with store._connect(db) as conn:
        rows = conn.execute("SELECT service_id, ts, status, latency_ms "
                            "FROM samples ORDER BY service_id").fetchall()
    assert [tuple(r) for r in rows] == [
        ("a", 1000, "up", 12),
        ("b", 1000, "down", None),
    ]


def test_prune_deletes_only_old_rows(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    store.record({"s": {"status": "up"}}, ts=1000, db_path=db)
    store.record({"s": {"status": "up"}}, ts=50_000, db_path=db)
    deleted = store.prune(before_ts=10_000, db_path=db)
    assert deleted == 1
    with store._connect(db) as conn:
        remaining = conn.execute("SELECT ts FROM samples").fetchall()
    assert [r["ts"] for r in remaining] == [50_000]
```

- [ ] **Step 3: Run — expect failure**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'store'`.

- [ ] **Step 4: Implement `store.py` (schema + record + prune only)**

```python
"""SQLite persistence for status samples and aggregate queries."""

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("dashboard.store")

DB_PATH = Path(__file__).parent / "dashboard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  service_id TEXT    NOT NULL,
  ts         INTEGER NOT NULL,
  status     TEXT    NOT NULL,
  latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_samples_service_ts ON samples (service_id, ts);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
    log.info("action=init_db path=%s", db_path or DB_PATH)


def record(results: dict[str, dict], ts: int, db_path: Path | None = None) -> None:
    rows = [
        (sid, ts, r.get("status", "unknown"), r.get("latency_ms"))
        for sid, r in results.items()
    ]
    with _connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO samples (service_id, ts, status, latency_ms) VALUES (?, ?, ?, ?)",
            rows,
        )


def prune(before_ts: int, db_path: Path | None = None) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM samples WHERE ts < ?", (before_ts,))
        deleted = cur.rowcount
    log.info("action=prune before_ts=%d deleted=%d", before_ts, deleted)
    return deleted
```

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add store.py .gitignore tests/test_store.py
git commit -m "Add store module: SQLite schema, record, prune

WAL-mode samples table (service_id, ts, status, latency_ms). One row per
service per sample; prune() drops rows past the retention cutoff.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 4: `store.py` — `status_summary`

**Files:**
- Modify: `store.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Consumes: `store._connect`, the `samples` table.
- Produces:
  - `store.status_summary(db_path: Path | None = None, now: int | None = None) -> dict[str, dict]` — keyed by `service_id`, each value:
    ```python
    {
      "status": str,            # latest sample's status
      "latency_ms": int | None, # latest sample's latency
      "uptime_24h": float | None,  # fraction up in last 24h, rounded to 4dp; None if no samples
      "uptime_7d": float | None,
      "last_seen_ts": int | None,  # max ts where status == 'up'
      "sparkline": list,        # 24 entries, oldest first; float fraction-up or None per hour
    }
    ```
  - `store.SPARKLINE_HOURS = 24`
  - Private helpers `store._uptime(conn, sid, start_ts, end_ts)` and `store._sparkline(conn, sid, start_ts, end_ts)`.

- [ ] **Step 1: Add failing tests to `tests/test_store.py`**

```python
def test_status_summary_reports_latest_status(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    store.record({"s": {"status": "up", "latency_ms": 10}}, ts=1000, db_path=db)
    store.record({"s": {"status": "down"}}, ts=1060, db_path=db)
    summ = store.status_summary(db_path=db, now=1100)
    assert summ["s"]["status"] == "down"
    assert summ["s"]["latency_ms"] is None


def test_status_summary_uptime_fraction(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    now = 100_000
    for i in range(10):                       # 8 up, 2 down, one per minute
        status = "up" if i < 8 else "down"
        store.record({"s": {"status": status}}, ts=now - i * 60, db_path=db)
    summ = store.status_summary(db_path=db, now=now)
    assert summ["s"]["uptime_24h"] == 0.8
    assert summ["s"]["uptime_7d"] == 0.8


def test_status_summary_uptime_none_when_no_samples_in_window(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    now = 10_000_000
    store.record({"s": {"status": "up"}}, ts=1000, db_path=db)  # far outside 7d
    summ = store.status_summary(db_path=db, now=now)
    assert summ["s"]["uptime_24h"] is None
    assert summ["s"]["uptime_7d"] is None


def test_status_summary_sparkline_buckets(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    now = 24 * 3600
    store.record({"s": {"status": "up"}}, ts=now - 60, db_path=db)         # current hour
    store.record({"s": {"status": "down"}}, ts=now - 5 * 3600, db_path=db)  # ~5h ago
    spark = store.status_summary(db_path=db, now=now)["s"]["sparkline"]
    assert len(spark) == 24
    assert spark[23] == 1.0      # current hour: all up
    assert spark[19] == 0.0      # 5h ago: all down  (bucket = (19*3600)/3600)
    assert spark[0] is None      # 24h ago: no data


def test_status_summary_last_seen_ts_when_down(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    store.record({"s": {"status": "up"}}, ts=1000, db_path=db)
    store.record({"s": {"status": "down"}}, ts=2000, db_path=db)
    assert store.status_summary(db_path=db, now=3000)["s"]["last_seen_ts"] == 1000


def test_status_summary_empty_db(tmp_path):
    db = tmp_path / "d.db"
    store.init_db(db)
    assert store.status_summary(db_path=db, now=1000) == {}
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'status_summary'`.

- [ ] **Step 3: Implement — append to `store.py`**

```python
import time

SPARKLINE_HOURS = 24


def status_summary(db_path: Path | None = None, now: int | None = None) -> dict[str, dict]:
    now = int(time.time()) if now is None else now
    day_ago = now - 86_400
    week_ago = now - 7 * 86_400
    spark_start = now - SPARKLINE_HOURS * 3600

    out: dict[str, dict] = {}
    with _connect(db_path) as conn:
        service_ids = [r["service_id"] for r in
                       conn.execute("SELECT DISTINCT service_id FROM samples")]
        for sid in service_ids:
            latest = conn.execute(
                "SELECT status, latency_ms FROM samples "
                "WHERE service_id = ? ORDER BY ts DESC LIMIT 1", (sid,)
            ).fetchone()
            last_up = conn.execute(
                "SELECT MAX(ts) AS ts FROM samples WHERE service_id = ? AND status = 'up'",
                (sid,)
            ).fetchone()["ts"]
            out[sid] = {
                "status": latest["status"],
                "latency_ms": latest["latency_ms"],
                "uptime_24h": _uptime(conn, sid, day_ago, now),
                "uptime_7d": _uptime(conn, sid, week_ago, now),
                "last_seen_ts": last_up,
                "sparkline": _sparkline(conn, sid, spark_start, now),
            }
    return out


def _uptime(conn, sid, start_ts, end_ts):
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'up' THEN 1 ELSE 0 END) AS up "
        "FROM samples WHERE service_id = ? AND ts >= ? AND ts <= ?",
        (sid, start_ts, end_ts),
    ).fetchone()
    if not row["total"]:
        return None
    return round(row["up"] / row["total"], 4)


def _sparkline(conn, sid, start_ts, end_ts):
    """24 hourly buckets, index 0 = oldest hour, 23 = current hour."""
    rows = conn.execute(
        "SELECT CAST((ts - ?) / 3600 AS INTEGER) AS bucket, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'up' THEN 1 ELSE 0 END) AS up "
        "FROM samples WHERE service_id = ? AND ts >= ? AND ts <= ? "
        "GROUP BY bucket",
        (start_ts, sid, start_ts, end_ts),
    )
    buckets: list = [None] * SPARKLINE_HOURS
    for r in rows:
        b = r["bucket"]
        if 0 <= b < SPARKLINE_HOURS and r["total"]:
            buckets[b] = round(r["up"] / r["total"], 4)
    return buckets
```

Move the `import time` to the top of the file with the other imports rather than leaving it mid-file.

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (9 tests total in the file).

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "Add store.status_summary: current status, uptime %, sparkline

Per service: latest status/latency, 24h and 7d uptime fractions,
last_seen_ts, and 24 hourly sparkline buckets (oldest first). All
aggregation in SQL.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 5: `sampler.py`

**Files:**
- Create: `sampler.py`
- Create: `tests/test_sampler.py`

**Interfaces:**
- Consumes: `config.load_config`, `config.iter_services`, `checks.check_service`, `store.record`, `store.prune`.
- Produces:
  - `sampler.sample_once(cfg: dict, now: int | None = None) -> dict[str, dict]` — runs every check in parallel, calls `store.record(results, now)`, returns the results.
  - `sampler.start(cfg: dict) -> None` — reads `cfg["dashboard"]["sample_interval_seconds"]` (default 60) and `["history_retention_days"]` (default 30), starts a daemon thread running the sample/prune loop.
  - `sampler.PRUNE_EVERY_S = 3600`
  - Module references `sampler.checks` and `sampler.store` (used by tests via monkeypatch).

- [ ] **Step 1: Write the failing test — `tests/test_sampler.py`**

```python
import sampler
import store


def test_sample_once_runs_checks_and_records(tmp_path, monkeypatch):
    db = tmp_path / "d.db"
    store.init_db(db)
    monkeypatch.setattr(store, "DB_PATH", db)
    monkeypatch.setattr(sampler.checks, "check_service",
                        lambda svc: {"status": "up", "latency_ms": 1})
    cfg = {"hosts": [{"name": "H", "ip": "10.0.0.1",
                      "services": [{"name": "S", "url": "http://x/"},
                                   {"name": "T", "systemd_unit": "t.service"}]}]}

    results = sampler.sample_once(cfg, now=5000)

    assert results["10_0_0_1_s"]["status"] == "up"
    assert results["10_0_0_1_t"]["status"] == "up"
    summ = store.status_summary(db_path=db, now=5001)
    assert set(summ) == {"10_0_0_1_s", "10_0_0_1_t"}


def test_sample_once_survives_a_failing_check(tmp_path, monkeypatch):
    db = tmp_path / "d.db"
    store.init_db(db)
    monkeypatch.setattr(store, "DB_PATH", db)

    def sometimes_boom(svc):
        if svc["name"] == "bad":
            raise RuntimeError("boom")
        return {"status": "up"}

    monkeypatch.setattr(sampler.checks, "check_service", sometimes_boom)
    cfg = {"hosts": [{"name": "H", "ip": "10.0.0.1",
                      "services": [{"name": "good", "url": "http://x/"},
                                   {"name": "bad", "url": "http://y/"}]}]}

    results = sampler.sample_once(cfg, now=5000)
    assert results["10_0_0_1_good"]["status"] == "up"
    assert results["10_0_0_1_bad"]["status"] == "unknown"
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_sampler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sampler'`.

- [ ] **Step 3: Implement `sampler.py`**

```python
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
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_sampler.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add sampler.py tests/test_sampler.py
git commit -m "Add sampler: parallel check pass + daemon-thread loop

sample_once() checks every service in a thread pool and records the batch;
start() spawns a daemon thread that samples on the configured interval and
prunes hourly. A failing check degrades to 'unknown', never crashes the pass.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 6: `app.py` rewrite

**Files:**
- Rewrite: `app.py`
- Create: `tests/test_app.py`

**Interfaces:**
- Consumes: `config.load_config`, `config.service_id`, `sampler.start`, `store.init_db`, `store.status_summary`.
- Produces:
  - `GET /` → `static/index.html`.
  - `GET /api/services` → `{"title": str, "sample_interval_seconds": int, "hosts": [...]}` where each service dict gains `"id"`.
  - `GET /api/status` → `store.status_summary()` verbatim.
  - `app.app` — the Flask instance (for the test client).
  - `app.main()` — boots DB + sampler, then `app.run(...)`.

- [ ] **Step 1: Write the failing test — `tests/test_app.py`**

```python
import app as app_module


def _cfg():
    return {
        "dashboard": {"title": "T", "port": 8888, "sample_interval_seconds": 45},
        "hosts": [{
            "name": "H", "ip": "10.0.0.1",
            "services": [{"name": "S", "url": "http://x/", "description": "d"}],
        }],
    }


def test_api_services_shape(monkeypatch):
    monkeypatch.setattr(app_module.config, "load_config", _cfg)
    client = app_module.app.test_client()
    body = client.get("/api/services").get_json()
    assert body["title"] == "T"
    assert body["sample_interval_seconds"] == 45
    svc = body["hosts"][0]["services"][0]
    assert svc["id"] == "10_0_0_1_s"
    assert svc["url"] == "http://x/"


def test_api_services_defaults_interval(monkeypatch):
    monkeypatch.setattr(app_module.config, "load_config",
                        lambda: {"hosts": []})
    client = app_module.app.test_client()
    body = client.get("/api/services").get_json()
    assert body["sample_interval_seconds"] == 60
    assert body["title"] == "Home Lab"


def test_api_status_returns_store_summary(monkeypatch):
    monkeypatch.setattr(app_module.store, "status_summary",
                        lambda: {"x": {"status": "up", "sparkline": []}})
    client = app_module.app.test_client()
    assert client.get("/api/status").get_json() == {"x": {"status": "up", "sparkline": []}}
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL — current `app.py` has no `sample_interval_seconds`, `/api/status` still does live checks, imports differ.

- [ ] **Step 3: Rewrite `app.py`**

```python
#!/usr/bin/env python3
"""Intranet service dashboard — serves / and a read-only status API."""

import logging
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

import config
import sampler
import store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__)


def _enrich_hosts(cfg: dict) -> list:
    return [
        {
            **host,
            "services": [
                {**svc, "id": config.service_id(host, svc)}
                for svc in host.get("services", [])
            ],
        }
        for host in cfg.get("hosts", [])
    ]


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/services")
def api_services():
    cfg = config.load_config()
    dash = cfg.get("dashboard", {})
    return jsonify({
        "title": dash.get("title", "Home Lab"),
        "sample_interval_seconds": dash.get("sample_interval_seconds", 60),
        "hosts": _enrich_hosts(cfg),
    })


@app.get("/api/status")
def api_status():
    return jsonify(store.status_summary())


def main() -> None:
    cfg = config.load_config()
    store.init_db()
    sampler.start(cfg)
    port = cfg.get("dashboard", {}).get("port", 8888)
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_app.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS (all tests across all files).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Rewrite app.py: thin routes over config/store/sampler

/api/status is now a read-only store.status_summary() call; /api/services
echoes sample_interval_seconds. main() boots the DB and the sampler thread.
Check/config logic moved to their own modules.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 7: Prune and regroup `config.yaml`

**Files:**
- Rewrite: `config.yaml`

**Interfaces:**
- Consumes: nothing.
- Produces: a config with `dashboard.sample_interval_seconds`, `dashboard.history_retention_days`, and 14 services across 3 host groups. Group 2 (`Raspberry Pi 5 — Background`) contains `RSS Feed Reader` with a `file_fresh` block.

- [ ] **Step 1: Write the new `config.yaml`**

```yaml
dashboard:
  title: Home Lab
  port: 8888
  sample_interval_seconds: 60
  history_retention_days: 30

hosts:
  - name: Raspberry Pi 5
    ip: 192.168.50.13
    services:
      - name: PiGallery2
        url: http://192.168.50.13:3010/
        description: Self-hosted photo gallery

      - name: qBittorrent
        url: http://192.168.50.13:8080/
        description: BitTorrent client web UI

      - name: TG Downloader
        url: http://192.168.50.13:8090/
        description: Telegram channel media downloader and file browser

      - name: Jellyfin
        url: http://192.168.50.13:8096/
        description: Media server — movies, TV shows, music

      - name: RSS Media Review
        url: http://192.168.50.13:8765/
        description: Keep/discard review UI for RSS feed downloads

      - name: Static Files
        url: http://192.168.50.13/
        description: nginx static file server — serves /srv/www (autoindex on)

  - name: Raspberry Pi 5 — Background
    ip: 192.168.50.13
    services:
      - name: TG Listener
        description: Background Telegram media download listener (Docker)
        docker_container: tg-downloader

      - name: RSS Feed Reader
        description: RSS feed poller (cron, every 2 h)
        file_fresh:
          path: /home/marcello/devel-with-claude/rss-feed-reader/cron.log
          max_age_minutes: 150

      - name: Power Monitor
        description: Power outage and under-voltage notifier
        systemd_unit: power-monitor.service

      - name: Reverse Tunnel
        description: SSH reverse tunnel to relay VPS (remote access path)
        systemd_unit: reverse-tunnel.service

      - name: Tailscale
        description: WireGuard mesh VPN node agent
        systemd_unit: tailscaled.service

  - name: Zimaboard 2
    ip: 192.168.50.12
    services:
      - name: ZimaOS
        url: http://192.168.50.12/
        description: Home server OS and app store

      - name: ttyd
        url: http://192.168.50.12:7681/
        description: Web-based terminal

      - name: MiniDLNA
        url: http://192.168.50.12:8200/
        description: DLNA media server
```

- [ ] **Step 2: Validate it loads and enumerates 14 services**

Run:
```bash
uv run python -c "import config; c = config.load_config(); print(sum(1 for _ in config.iter_services(c)), 'services'); print([h['name'] for h in c['hosts']])"
```
Expected: `14 services` and `['Raspberry Pi 5', 'Raspberry Pi 5 — Background', 'Zimaboard 2']`.

- [ ] **Step 3: Smoke-test the API**

Run:
```bash
uv run python -c "
import app, json
app.store.init_db()
c = app.app.test_client()
print(json.dumps(c.get('/api/services').get_json(), indent=2)[:600])
"
```
Expected: JSON with `sample_interval_seconds: 60` and the three host groups; each service has an `id`. Delete the stray `dashboard.db*` this creates in the repo dir afterwards (`rm -f dashboard.db dashboard.db-*`).

- [ ] **Step 4: Commit**

```bash
git add config.yaml
git commit -m "Prune config to 14 services; add history + file_fresh keys

Drops the decommissioned services (Ollama, Samba, Prowlarr, autobrr,
Transmission, Magnetize Stack). Splits the Pi into apps vs background
groups. Adds sample_interval_seconds / history_retention_days and a
file_fresh check for the RSS cron job.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 8: Rewrite `static/index.html`

**Files:**
- Rewrite: `static/index.html`

**Interfaces:**
- Consumes: `GET /api/services` (`title`, `sample_interval_seconds`, `hosts[].services[]` with `id` / `name` / `description` / `url`) and `GET /api/status` (`{id: {status, latency_ms, uptime_24h, uptime_7d, last_seen_ts, sparkline}}`).
- Produces: the rendered dashboard. No module exports.

This task has no unit tests (vanilla JS, no build). It ends with the manual verification in Step 3.

- [ ] **Step 1: Write the full file**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Home Lab</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --accent:   #2563eb;
      --bg:       #f1f5f9;
      --surface:  #ffffff;
      --border:   #e2e8f0;
      --text:     #1e293b;
      --muted:    #64748b;
      --shadow:   0 1px 3px rgba(0,0,0,.10), 0 1px 2px rgba(0,0,0,.06);
      --up:       #16a34a;
      --down:     #dc2626;
      --amber:    #d97706;
      --unknown:  #94a3b8;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }

    .header {
      position: sticky; top: 0; z-index: 100;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 10px 16px;
      display: flex; align-items: center; justify-content: space-between;
      gap: 10px;
    }
    .brand { font-weight: 700; font-size: 1.05rem; color: var(--accent); white-space: nowrap; }
    .header-right { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .summary { font-size: .85rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
    .last-checked {
      font-size: .78rem; color: var(--muted);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .btn-refresh {
      padding: 9px 14px; border: 1px solid var(--border); border-radius: 6px;
      background: var(--surface); font-size: .8rem; cursor: pointer;
      font-family: inherit; color: var(--text);
      white-space: nowrap; flex-shrink: 0; touch-action: manipulation;
    }
    .btn-refresh:hover { background: var(--bg); }
    .btn-refresh.spinning { opacity: .5; pointer-events: none; }

    @media (max-width: 460px) {
      .last-checked { display: none; }
    }

    .main { padding: 20px 16px; max-width: 1200px; margin: 0 auto; }
    @media (max-width: 480px) { .main { padding: 14px 10px; } }

    .host { margin-bottom: 28px; }
    .host-label {
      font-size: .7rem; font-weight: 700; letter-spacing: .1em;
      text-transform: uppercase; color: var(--muted);
      margin-bottom: 10px;
      display: flex; align-items: baseline; gap: 8px;
    }
    .host-ip {
      font-size: .75rem; font-weight: 400; letter-spacing: 0;
      text-transform: none; color: var(--unknown);
      font-family: ui-monospace, monospace;
    }

    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 10px;
    }
    @media (max-width: 480px) { .cards { grid-template-columns: 1fr; gap: 8px; } }

    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 3px solid var(--unknown);
      border-radius: 10px;
      padding: 14px 16px;
      box-shadow: var(--shadow);
      display: flex; flex-direction: column; gap: 6px;
      transition: border-left-color .3s;
    }
    .card.up   { border-left-color: var(--up); }
    .card.down { border-left-color: var(--down); }

    .card-top { display: flex; align-items: baseline; gap: 8px; }
    .card-name {
      font-weight: 600; font-size: .9rem; flex: 1; min-width: 0;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .card-latency { font-size: .72rem; color: var(--muted); white-space: nowrap; flex-shrink: 0; }
    .card-latency.down { color: var(--down); }

    .card-desc {
      font-size: .8rem; color: var(--muted); line-height: 1.4;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }

    .spark { display: block; width: 100%; height: 22px; }

    .card-foot {
      display: flex; align-items: center; justify-content: space-between; gap: 8px;
      margin-top: 2px;
    }
    .uptime { font-size: .72rem; color: var(--muted); }
    .uptime.down { color: var(--down); }

    .card-open {
      display: inline-flex; align-items: center; justify-content: center; gap: 4px;
      padding: 8px 12px;
      background: var(--accent); color: #fff;
      border-radius: 7px; text-decoration: none;
      font-size: .8rem; font-weight: 500;
      touch-action: manipulation;
    }
    .card-open:hover { opacity: .85; }

    .loading { color: var(--muted); font-size: .9rem; padding: 40px 0; text-align: center; }
  </style>
</head>
<body>

<header class="header">
  <span class="brand" id="brand">Home Lab</span>
  <div class="header-right">
    <span class="summary" id="summary"></span>
    <span class="last-checked" id="last-checked"></span>
    <button class="btn-refresh" id="btn-refresh">↺ Refresh</button>
  </div>
</header>

<main class="main" id="main">
  <p class="loading">Loading…</p>
</main>

<script>
  const mainEl    = document.getElementById('main');
  const brandEl   = document.getElementById('brand');
  const summaryEl = document.getElementById('summary');
  const checkedEl = document.getElementById('last-checked');
  const refreshBtn = document.getElementById('btn-refresh');

  let hostsData = [];
  let refreshMs = 30_000;

  function statusClass(s) {
    if (!s) return '';
    return s.status === 'up' ? 'up' : s.status === 'down' ? 'down' : '';
  }

  function latencyLabel(s) {
    if (!s) return '';
    if (s.status === 'up')   return s.latency_ms != null ? `${s.latency_ms}ms` : 'up';
    if (s.status === 'down') return 'down';
    return '';
  }

  function ago(ts) {
    if (ts == null) return 'never';
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (sec < 90)      return `${sec}s ago`;
    if (sec < 5400)    return `${Math.round(sec / 60)}m ago`;
    if (sec < 172800)  return `${Math.round(sec / 3600)}h ago`;
    return `${Math.round(sec / 86400)}d ago`;
  }

  function uptimeLabel(s) {
    if (!s) return '';
    if (s.status === 'down') return `last seen ${ago(s.last_seen_ts)}`;
    if (s.uptime_24h == null) return 'no history yet';
    return `${Math.round(s.uptime_24h * 100)}% · 24h`;
  }

  // 24 bars; height ∝ fraction-up, colour by value, faint stub for null.
  function sparkSvg(spark) {
    const pts = Array.isArray(spark) ? spark : [];
    const n = 24, w = 4, gap = 1, h = 22;
    const bars = [];
    for (let i = 0; i < n; i++) {
      const v = pts[i];
      const x = i * (w + gap);
      if (v == null) {
        bars.push(`<rect x="${x}" y="${h - 2}" width="${w}" height="2" fill="var(--border)"/>`);
        continue;
      }
      const bh = Math.max(2, Math.round(v * h));
      const colour = v >= 0.99 ? 'var(--up)' : v >= 0.5 ? 'var(--amber)' : 'var(--down)';
      bars.push(`<rect x="${x}" y="${h - bh}" width="${w}" height="${bh}" fill="${colour}"/>`);
    }
    const vw = n * (w + gap);
    return `<svg class="spark" viewBox="0 0 ${vw} ${h}" preserveAspectRatio="none"
              role="img" aria-label="uptime history, last 24 hours">${bars.join('')}</svg>`;
  }

  function renderHosts(hosts, status) {
    mainEl.innerHTML = '';
    let lastIp = null;
    for (const host of hosts) {
      const section = document.createElement('section');
      section.className = 'host';
      const ipHtml = host.ip && host.ip !== lastIp ? `<span class="host-ip">${host.ip}</span>` : '';
      lastIp = host.ip;
      section.innerHTML = `
        <div class="host-label">${host.name} ${ipHtml}</div>
        <div class="cards"></div>
      `;
      mainEl.appendChild(section);

      const cardsEl = section.querySelector('.cards');
      for (const svc of (host.services || [])) {
        const s = status[svc.id] || {};
        const card = document.createElement('div');
        card.className = `card ${statusClass(s)}`;
        card.dataset.id = svc.id;
        card.innerHTML = `
          <div class="card-top">
            <span class="card-name">${svc.name}</span>
            <span class="card-latency ${s.status === 'down' ? 'down' : ''}">${latencyLabel(s)}</span>
          </div>
          <div class="card-desc">${svc.description || ''}</div>
          <div class="spark-wrap">${sparkSvg(s.sparkline)}</div>
          <div class="card-foot">
            <span class="uptime ${s.status === 'down' ? 'down' : ''}">${uptimeLabel(s)}</span>
            ${svc.url ? `<a class="card-open" href="${svc.url}" target="_blank" rel="noopener">Open ↗</a>` : ''}
          </div>
        `;
        cardsEl.appendChild(card);
      }
    }
  }

  function applyStatus(status) {
    let up = 0, total = 0;
    for (const host of hostsData) {
      for (const svc of (host.services || [])) {
        total++;
        const s = status[svc.id] || {};
        if (s.status === 'up') up++;
        const card = mainEl.querySelector(`[data-id="${svc.id}"]`);
        if (!card) continue;
        card.className = `card ${statusClass(s)}`;
        const lat = card.querySelector('.card-latency');
        lat.textContent = latencyLabel(s);
        lat.className = `card-latency ${s.status === 'down' ? 'down' : ''}`;
        card.querySelector('.spark-wrap').innerHTML = sparkSvg(s.sparkline);
        const up_ = card.querySelector('.uptime');
        up_.textContent = uptimeLabel(s);
        up_.className = `uptime ${s.status === 'down' ? 'down' : ''}`;
      }
    }
    summaryEl.textContent = `${up} / ${total} up`;
  }

  async function loadAll() {
    const [cfgRes, stRes] = await Promise.all([fetch('/api/services'), fetch('/api/status')]);
    const cfg = await cfgRes.json();
    const status = await stRes.json();

    document.title = cfg.title || 'Home Lab';
    brandEl.textContent = cfg.title || 'Home Lab';
    hostsData = cfg.hosts || [];
    if (cfg.sample_interval_seconds) refreshMs = cfg.sample_interval_seconds * 1000 / 2;

    renderHosts(hostsData, status);
    applyStatus(status);
    checkedEl.textContent = `Checked ${new Date().toLocaleTimeString()}`;
  }

  async function refreshStatus() {
    if (!hostsData.length) { await loadAll(); return; }
    const status = await (await fetch('/api/status')).json();
    applyStatus(status);
    checkedEl.textContent = `Checked ${new Date().toLocaleTimeString()}`;
  }

  async function refresh() {
    refreshBtn.classList.add('spinning');
    try { await refreshStatus(); }
    finally { refreshBtn.classList.remove('spinning'); }
  }

  refreshBtn.addEventListener('click', refresh);

  loadAll().catch(err => {
    mainEl.innerHTML = `<p class="loading">Failed to load: ${err.message}</p>`;
  });

  setInterval(refreshStatus, 30_000);
</script>
</body>
</html>
```

- [ ] **Step 2: Start the app**

Run: `uv run python app.py` (leave it running in a second shell)

- [ ] **Step 3: Manual verification**

1. Open `http://localhost:8888` (or the Pi IP). All 14 services render across the 3 groups; the second group does not repeat `192.168.50.13`.
2. Header shows `N / 14 up`.
3. Each card has a sparkline (mostly empty stubs on first run) and an uptime line reading `no history yet` while `up`.
4. Wait ~3 minutes (3+ sample cycles). Sparkline bars begin filling from the right; uptime shows `100% · 24h` for healthy services.
5. Stop one service (e.g. `sudo systemctl stop power-monitor`); within ~2 minutes its card border turns red, latency shows `down`, and the uptime line switches to `last seen …`. Restart it afterwards.
6. Resize to a narrow width — cards go single-column, layout holds, no horizontal scroll.
7. `curl -s localhost:8888/api/status | python3 -m json.tool` — every service id present with `status` / `uptime_24h` / `sparkline` (24 entries).

- [ ] **Step 4: Stop the app, clean the dev DB**

```bash
rm -f dashboard.db dashboard.db-wal dashboard.db-shm
```

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "Rewrite dashboard UI: single scroll, left-border cards, sparklines

One layout at all widths (no sidebar). Each card shows a 24h uptime
sparkline (inline SVG), a 24h uptime %, and 'last seen' when down.
Header gains an N/M up summary; repeated host IPs are suppressed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Task 9: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-07-ui-redesign-design.md`

**Interfaces:**
- Consumes: nothing.
- Produces: docs consistent with the shipped code.

- [ ] **Step 1: Update `CLAUDE.md`**

Make these changes:

1. **Stack section** — add a bullet: `- **SQLite** (stdlib \`sqlite3\`) — status-history store (\`dashboard.db\`), sampled every 60 s`.
2. **Files table** — replace with:

   | File | Purpose |
   |---|---|
   | `app.py` | Flask app — serves `/`, `/api/services`, `/api/status`; boots the DB + sampler |
   | `config.py` | Loads `config.yaml`; computes `service_id`; `iter_services()` |
   | `checks.py` | Health checks: `check_http` / `check_systemd` / `check_docker` / `check_file_fresh` |
   | `store.py` | SQLite: schema, `record()`, `prune()`, `status_summary()` (uptime %, sparkline) |
   | `sampler.py` | Daemon thread — samples every service every `sample_interval_seconds`, prunes hourly |
   | `config.yaml` | Service definitions + `sample_interval_seconds` / `history_retention_days` |
   | `static/index.html` | Single-page dashboard (vanilla JS, inline-SVG sparklines) |
   | `dashboard.db` | Status-history SQLite DB (gitignored, created on first run) |
   | `systemd/intranet-dashboard.service` | Systemd unit (runs as user marcello) |

3. **Adding / editing services** — add to the bullet list:
   `- \`file_fresh\` — \`{path, max_age_minutes}\`; up if the file was modified within the window (cron jobs)`
   and update the priority line to:
   `Health check priority: \`url\` > \`docker_container\` > \`systemd_unit\` > \`file_fresh\`.`

4. **Service groups table** — remove the `Torrent Stack` and `Magnetize Stack` rows. Change the `Raspberry Pi 5` row to two rows:

   | Host entry | IP | Purpose |
   |---|---|---|
   | Raspberry Pi 5 | 192.168.50.13 | Web apps: PiGallery2, qBittorrent, TG Downloader, Jellyfin, RSS Media Review, Static Files |
   | Raspberry Pi 5 — Background | 192.168.50.13 | Daemons: TG Listener (Docker), RSS Feed Reader (cron/`file_fresh`), Power Monitor, Reverse Tunnel, Tailscale |
   | Zimaboard 2 | 192.168.50.12 | ZimaOS, ttyd, MiniDLNA |

5. **Delete** the "Ollama runs locally…" paragraph, the "Docker health checks (resolved)" paragraph's reference to `mgzns-flaresolverr` / `mgzns-bitmagnet-postgres` (change it to mention only `tg-downloader`), and the **Static file server (nginx)** paragraph stays (nginx is kept).

6. **Add** a new section after "Service groups":

   ```markdown
   ### Status history

   `sampler.py` runs as a daemon thread inside the Flask process. Every
   `sample_interval_seconds` (default 60) it checks every service and writes one
   row per service to `dashboard.db` (`samples` table, WAL mode). Once an hour it
   deletes rows older than `history_retention_days` (default 30).

   `/api/status` never runs a live check — it returns the latest stored sample per
   service plus derived figures: `uptime_24h`, `uptime_7d`, `last_seen_ts`, and a
   24-bucket hourly `sparkline` (oldest first). The UI polls it every 30 s.

   To reset history: stop the service, `rm dashboard.db*`, start it again.
   ```

7. **Decommissioned (2026-09-01)** — add a short note under the intro so future sessions know these are gone deliberately:

   ```markdown
   > **Removed 2026-09-01** (unused — see `docs/superpowers/specs/2026-09-01-revamp-design.md`):
   > Ollama, Transmission, autobrr, Prowlarr, Samba, and the Magnetize Stack
   > (bitmagnet + Postgres + Jackett + FlareSolverr). ~33 GB / ~1.5 GB RAM reclaimed.
   ```

- [ ] **Step 2: Update `README.md`**

1. **How it works** — replace the bullet list and the "every 30 seconds it probes" sentence with:

   ```markdown
   A background thread samples every service on a fixed interval (default 60 s) and
   stores the result in a local SQLite database (`dashboard.db`). The page reads
   the stored samples — it never triggers a live check on load — and shows, per
   service, current status, a 24-hour uptime sparkline, and an uptime percentage.

   - **Web services** — HTTP GET; up if the response is `< 400` or an auth wall (401/403).
   - **Systemd services** — `systemctl show` locally (`ActiveState=active`).
   - **Docker containers** — `docker inspect` locally.
   - **Cron jobs** — `file_fresh`: up if a named file changed within `max_age_minutes`.
   ```

2. **Configuration** — add `sample_interval_seconds` and `history_retention_days` to the `dashboard:` block, and add a `file_fresh` example service and a table row:

   | `file_fresh` | mapping | `{path, max_age_minutes}` — up if the file's mtime is within the window |

   Update the priority sentence to include `file_fresh` last.

3. **File layout** — list the new modules (`config.py`, `checks.py`, `store.py`, `sampler.py`) and `dashboard.db`.

4. **API** — update `/api/status` row: `Latest stored sample per service plus uptime % and 24h sparkline`. Add a note that `/api/services` now includes `sample_interval_seconds`.

5. Remove the `cp config.yaml.example` line (there is no example file) — replace with "Edit `config.yaml` directly".

- [ ] **Step 3: Mark the old spec superseded**

At the very top of `docs/superpowers/specs/2026-05-07-ui-redesign-design.md`, immediately after the `# UI Redesign — Design Spec` heading, insert:

```markdown
> **SUPERSEDED (2026-09-01)** — this sidebar layout was approved but never
> implemented. The revamp in `2026-09-01-revamp-design.md` keeps this document's
> visual language (status colours, left-border cards, latency) but drops the
> sidebar and host-switching in favour of a single scrolling page.
```

- [ ] **Step 4: Full suite + final check**

Run: `uv run pytest -v`
Expected: PASS (all tests).

Run: `git status`
Expected: only the three doc files modified.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md docs/superpowers/specs/2026-05-07-ui-redesign-design.md
git commit -m "Update docs for the revamp

CLAUDE.md: new module list, health-check priority with file_fresh,
status-history section, pruned host table, decommission note. README:
DB-backed sampling model, file_fresh, new endpoints. Mark the 2026-05-07
sidebar spec superseded.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UDFDdypYSP8uj7dUFQXWDN"
```

---

## Deploy (after the branch merges to `master` and sub-project A is done)

Not a plan task — run by hand on the Pi:

```bash
cd /home/marcello/devel-with-claude/intranet-dashboard
git pull
uv sync
sudo systemctl restart intranet-dashboard.service
journalctl -u intranet-dashboard -f      # expect: action=init_db, action=sampler_start, action=sample …
```

Verify `http://192.168.50.13:8888` renders and `dashboard.db` appears in the repo dir. No systemd-unit change is needed (runs as `marcello`, `WorkingDirectory` is the repo, `dashboard.db` is written there).

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| B1 config cleanup | Task 7 |
| B2 module layout | Tasks 1, 2, 3–4, 5, 6 |
| B3 DB schema + `status_summary` shape | Tasks 3, 4 |
| B4 sampler (interval, prune hourly, first sample on boot, structured log) | Task 5 (+ Task 6 wires boot) |
| B5 API (`/api/services` + interval, `/api/status` DB-backed, no `/api/history`) | Task 6 |
| B6 health-check fixes (http mapping, retry, systemd SubState, docker logging, `file_fresh`, priority) | Task 2 |
| B7 front-end (single scroll, left-border cards, sparkline spec, header summary, IP suppression, 30 s poll) | Task 8 |
| B8 testing (pytest dev dep, per-module tests, manual checklist) | Tasks 1–6, 8 |
| B9 sequencing & deploy | Deploy section |
| Non-goals (no auth, no alerting, no history page, no Zimaboard SSH) | Respected — nothing in the plan adds them |

**Placeholder scan:** No TBD/TODO. Every code step has complete code. Manual-only steps (Task 8) are spelled out as numbered checks.

**Type consistency:** `service_id` signature `(host, svc)` consistent across `config.py`, `app.py`, tests. `check_service(svc) -> dict` consistent. `store.record(results, ts, db_path=None)` / `store.status_summary(db_path=None, now=None)` consistent between Tasks 3, 4, 5, 6 and tests. `status_summary` return keys (`status`, `latency_ms`, `uptime_24h`, `uptime_7d`, `last_seen_ts`, `sparkline`) match between Task 4 implementation, Task 8 consumer, and the spec. `sparkline` is 24 entries oldest-first in both the SQL (`bucket 0 = oldest`) and the JS (`pts[i]`, bar `x = i*(w+gap)`).

**Known deferrals (from spec, intentionally not tasks):** reverse-tunnel reachability probe; Zimaboard unit checks; any alerting.
