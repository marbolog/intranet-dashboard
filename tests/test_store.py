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
    store.record({"s": {"status": "up"}}, ts=now - 60, db_path=db)          # current hour
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
