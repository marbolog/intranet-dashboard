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
