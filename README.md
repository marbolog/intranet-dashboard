# intranet-dashboard

A lightweight home lab dashboard that lists every service running on your local machines, shows live health status, and gives you one-click access to each web UI.

## How it works

The dashboard reads a `config.yaml` file that describes your hosts and services. On each page load (and every 30 seconds automatically) it probes each service and reports whether it is reachable:

- **Web services** — an HTTP GET to the service URL; up if the response is < 500.
- **Systemd services** — `systemctl is-active <unit>` run locally.
- **Docker containers** — `docker inspect` checked locally.

Services with no probe configured (e.g. cron jobs) show as *unknown*.

## Requirements

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure

```bash
cp config.yaml.example config.yaml   # or edit config.yaml directly
```

Edit `config.yaml` to describe your hosts and services (see [Configuration](#configuration) below).

### 3. Run

```bash
uv run python app.py
```

The dashboard is served at `http://<host-ip>:<port>` (default port **8888**).

### 4. Run as a systemd service (optional)

```bash
sudo cp systemd/intranet-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now intranet-dashboard.service
```

The unit runs as the `marcello` user. Edit the `User=` and `WorkingDirectory=` lines if your setup differs.

> **Docker health checks**: if the user running the service is not in the `docker` group, docker-based checks will return *unknown*. Fix with `sudo usermod -aG docker <user>` and re-login.

## Configuration

```yaml
dashboard:
  title: Home Lab      # page title and header text
  port: 8888           # port to listen on

hosts:
  - name: My Server
    ip: 192.168.1.10
    services:
      # Web app — HTTP health check + "Open" link
      - name: Jellyfin
        url: http://192.168.1.10:8096/
        description: Media server

      # Background service — systemd health check, no link
      - name: Power Monitor
        description: Power outage and under-voltage notifier
        systemd_unit: power-monitor.service

      # Docker container — docker inspect health check, no link
      - name: My Worker
        description: Background task processor
        docker_container: my-worker

      # No check — always shown as unknown
      - name: Cron Job
        description: Runs every hour via cron
```

### Health check priority

If a service has a `url`, that is always used for the health check (HTTP). `docker_container` and `systemd_unit` are only used when there is no `url` — typically for background services with no web interface.

| Key | Type | Effect |
|---|---|---|
| `url` | string | Enables the Open button; HTTP health check |
| `systemd_unit` | string | `systemctl is-active` check (local host only) |
| `docker_container` | string | `docker inspect` check (local host only) |

Remote hosts (not the machine running the dashboard) support only HTTP checks.

## File layout

```
app.py                          Flask app — serves / and /api/*
config.yaml                     Service definitions
static/index.html               Single-page dashboard UI
systemd/intranet-dashboard.service  Systemd unit template
```

## API

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/services` | Full service list from config (includes computed IDs) |
| `GET /api/status` | Health check results keyed by service ID |
