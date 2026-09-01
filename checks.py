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
