# intranet-dashboard

A lightweight home lab dashboard that lists every service running on your local machines, shows current health status with per-service uptime history, and gives you one-click access to each web UI.

## How it works

The dashboard reads a `config.yaml` file that describes your hosts and services. A
background thread samples every service on a fixed interval (default 60 s) and stores
the result in a local SQLite database (`dashboard.db`). The page reads the stored
samples — it never triggers a live check on load — and shows, per service, current
status, a 24-hour uptime sparkline, and an uptime percentage.

- **Web services** — HTTP GET; up if the response is `< 400` or an auth wall (401/403).
- **Systemd services** — `systemctl show` locally (`ActiveState=active`).
- **Docker containers** — `docker inspect` locally.
- **Cron jobs** — `file_fresh`: up if a named file changed within `max_age_minutes`.

Services with no probe configured show as *unknown*.

## Requirements

- Python 3.11+ with [uv](https://docs.astral.sh/uv/)

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure

Edit `config.yaml` directly to describe your hosts and services (see [Configuration](#configuration) below).

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
  title: Home Lab             # page title and header text
  port: 8888                  # port to listen on
  sample_interval_seconds: 60 # how often the background sampler checks every service
  history_retention_days: 30  # how long samples are kept in dashboard.db

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

      # Cron job — up if the log file changed recently
      - name: Nightly Backup
        description: Runs at 03:00 via cron
        file_fresh:
          path: /var/log/backup.log
          max_age_minutes: 1500

      # No check — always shown as unknown
      - name: Cron Job
        description: Runs every hour via cron
```

### Health check priority

The first key present wins: `url` > `docker_container` > `systemd_unit` > `file_fresh`.
`docker_container` / `systemd_unit` / `file_fresh` only work on the machine running the
dashboard; remote hosts support HTTP checks only.

| Key | Type | Effect |
|---|---|---|
| `url` | string | Enables the Open button; HTTP check — up if `<400` or `401`/`403` |
| `docker_container` | string | `docker inspect` check (local host only) |
| `systemd_unit` | string | `systemctl show` → `ActiveState=active` (local host only) |
| `file_fresh` | mapping | `{path, max_age_minutes}` — up if the file's mtime is within the window |

## File layout

```
app.py                              Flask routes; boots the DB + sampler
config.py                           Config loading + service IDs
checks.py                           Health-check functions
store.py                            SQLite: samples table, aggregate queries
sampler.py                          Background sampling thread
config.yaml                         Service definitions
dashboard.db                        Status-history SQLite DB (created on first run)
static/index.html                   Single-page dashboard UI
tests/                              pytest suite
systemd/intranet-dashboard.service  Systemd unit template
```

## API

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/services` | Service list from config (computed IDs + `sample_interval_seconds`) |
| `GET /api/status` | Latest stored sample per service plus uptime % and 24h sparkline |
