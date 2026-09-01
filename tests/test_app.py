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
    monkeypatch.setattr(app_module.config, "load_config", lambda: {"hosts": []})
    client = app_module.app.test_client()
    body = client.get("/api/services").get_json()
    assert body["sample_interval_seconds"] == 60
    assert body["title"] == "Home Lab"


def test_api_status_returns_store_summary(monkeypatch):
    monkeypatch.setattr(app_module.store, "status_summary",
                        lambda: {"x": {"status": "up", "sparkline": []}})
    client = app_module.app.test_client()
    assert client.get("/api/status").get_json() == {"x": {"status": "up", "sparkline": []}}
