#!/usr/bin/env python3
"""Intranet service dashboard — serves / and health-check API."""

import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests as http_requests
import yaml
from flask import Flask, jsonify, send_from_directory

CONFIG_PATH = Path(__file__).parent / "config.yaml"
STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__)


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def service_id(host: dict, svc: dict) -> str:
    ip = host.get("ip", host.get("name", "")).replace(".", "_")
    return f"{ip}_{slugify(svc['name'])}"


def check_http(url: str) -> dict:
    try:
        start = time.monotonic()
        r = http_requests.get(url, timeout=3, allow_redirects=True)
        latency = round((time.monotonic() - start) * 1000)
        return {"status": "up" if r.status_code < 500 else "down", "latency_ms": latency}
    except Exception:
        return {"status": "down"}


def check_systemd(unit: str) -> dict:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=3,
        )
        return {"status": "up" if result.stdout.strip() == "active" else "down"}
    except Exception:
        return {"status": "unknown"}


def check_docker(container: str) -> dict:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {"status": "unknown"}
        return {"status": "up" if result.stdout.strip().lower() == "true" else "down"}
    except Exception:
        return {"status": "unknown"}


def check_service(svc: dict) -> dict:
    # URL check is preferred — tests actual web reachability for web apps.
    # Docker/systemd are used for background services that have no web UI.
    if "url" in svc:
        return check_http(svc["url"])
    if "docker_container" in svc:
        return check_docker(svc["docker_container"])
    if "systemd_unit" in svc:
        return check_systemd(svc["systemd_unit"])
    return {"status": "unknown"}


def enrich_hosts(hosts: list) -> list:
    return [
        {
            **host,
            "services": [
                {**svc, "id": service_id(host, svc)}
                for svc in host.get("services", [])
            ],
        }
        for host in hosts
    ]


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/services")
def api_services():
    config = load_config()
    return jsonify({
        "title": config.get("dashboard", {}).get("title", "Home Lab"),
        "hosts": enrich_hosts(config.get("hosts", [])),
    })


@app.get("/api/status")
def api_status():
    config = load_config()
    tasks = [
        (service_id(host, svc), svc)
        for host in config.get("hosts", [])
        for svc in host.get("services", [])
    ]

    results = {}
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(check_service, svc): svc_id for svc_id, svc in tasks}
        for future in as_completed(futures):
            svc_id = futures[future]
            try:
                results[svc_id] = future.result()
            except Exception:
                results[svc_id] = {"status": "unknown"}

    return jsonify(results)


if __name__ == "__main__":
    config = load_config()
    port = config.get("dashboard", {}).get("port", 8888)
    app.run(host="0.0.0.0", port=port)
