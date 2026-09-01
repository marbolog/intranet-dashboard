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
