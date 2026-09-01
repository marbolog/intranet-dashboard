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
    ident = host.get("ip") or host.get("name", "")
    return f"{slugify(ident)}_{slugify(svc['name'])}"


def iter_services(cfg: dict) -> Iterator[tuple[str, dict, dict]]:
    """Yield (service_id, host, svc) for every service in every host."""
    for host in cfg.get("hosts", []):
        for svc in host.get("services", []):
            yield service_id(host, svc), host, svc
