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
