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
        monkeypatch.setattr(checks.http_requests, "get",
                            lambda *a, _c=code, **k: FakeResp(_c))
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
