"""SQLite persistence for status samples and aggregate queries."""

import logging
import sqlite3
import time
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
