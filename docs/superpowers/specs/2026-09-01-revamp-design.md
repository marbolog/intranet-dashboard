# Revamp — Design Spec

**Date:** 2026-09-01
**Project:** intranet-dashboard
**Status:** Approved
**Supersedes:** `2026-05-07-ui-redesign-design.md` (sidebar layout — never implemented, dropped)

## Overview

Two sub-projects:

- **A — Decommission runbook.** A one-time operation on the Raspberry Pi (192.168.50.13)
  that removes six unused services plus one Docker stack, reclaiming ~33 GB of disk and
  ~1.5 GB of RAM.
- **B — Dashboard revamp.** In this repo: prune `config.yaml`, rebuild the front-end as a
  single-scroll page, add a status-history subsystem (60 s in-process sampler → SQLite →
  uptime % + sparkline per service), and fix known health-check bugs.

A runs first so the new config reflects reality from the start.

---

# Sub-project A — Decommission runbook

## Rationale

Assessment on 2026-09-01 (mining the persistent journal back to May 2026 plus each
service's own logs) found the following with zero or near-zero measured use:

| Service | Evidence |
|---|---|
| Ollama | 0 inference calls since May; last API hit (model-management only) 2026-06-29. `tg-downloader` RAG uses the Claude API, not Ollama. |
| Transmission | 0 torrents, empty stats, 0 web requests since July. Fully redundant with qBittorrent. |
| autobrr | 0 releases ever grabbed, 0 download actions configured. Only activity: polling 3 Prowlarr RSS feeds. |
| Prowlarr | 144 searches/day — all of them autobrr's feed refreshes. No `*arr`, no human searches. Its only consumer does nothing. |
| Samba (smbd + nmbd) | 0 connections in 4 months. The RSS pipeline uses the local filesystem, not SMB. |
| Magnetize Stack (bitmagnet + Postgres + Jackett + FlareSolverr) | 26 GB DB, constant ~6 % CPU + ~1 GB RAM crawling the DHT. 0 human GraphQL/torznab queries in 90 days of logs. |

`torrent-cli` (`~/devel-with-claude/torrent-cli`) targets Transmission + Prowlarr + autobrr
but is not installed, has no config, and shows no traffic. Decision: remove the services
anyway; the repo stays on disk, non-functional.

**Kept:** Jellyfin (marginal but wanted), PiGallery2 (unused but wanted), nginx + `/srv/www`
(low use, left as-is), reverse-tunnel (**active — the current remote-access path**),
Tailscale.

## Method

Full removal — purge packages, `docker compose down --rmi all`, delete data directories.
No staged/reversible pass. You accepted that A has no rollback.

### Safety net (before any removal)

Create `~/decommission-2026-09-01-backup.tar.gz` containing:
- all affected systemd unit files (`/etc/systemd/system/{ollama,prowlarr,reverse-tunnel}.service`,
  `~/.config/systemd/user/autobrr.service`)
- text configs: `~/.config/autobrr/config.toml`, `/etc/samba/smb.conf`,
  `~/devel-with-grok/mgzns-downloader/*.yml` + `.env`, `/etc/transmission-daemon/settings.json`
- **not** the large data (Ollama models, autobrr DB, bitmagnet Postgres)

Also capture plain-text snapshots: `dpkg -l`, `systemctl list-unit-files --state=enabled`,
`ss -tlnp`, `docker ps -a`, `df -h`, `free -h`.

### Removal order (lowest risk first)

| # | Service | Commands |
|---|---|---|
| 1 | **Ollama** | `sudo systemctl disable --now ollama.service`<br>`sudo rm /etc/systemd/system/ollama.service && sudo systemctl daemon-reload`<br>`sudo rm /usr/local/bin/ollama`<br>`sudo rm -rf /usr/share/ollama` (6.1 GB)<br>`sudo userdel ollama` |
| 2 | **Transmission** | `sudo systemctl disable --now transmission-daemon`<br>`sudo apt purge -y transmission-daemon transmission-cli transmission-common`<br>`sudo rm -rf /var/lib/transmission-daemon /etc/transmission-daemon` |
| 3 | **autobrr** | `systemctl --user disable --now autobrr.service`<br>`rm ~/.config/systemd/user/autobrr.service && systemctl --user daemon-reload`<br>`sudo rm /usr/bin/autobrr`<br>`rm -rf ~/.config/autobrr` (218 MB) |
| 4 | **Prowlarr** | `sudo systemctl disable --now prowlarr.service`<br>`sudo rm /etc/systemd/system/prowlarr.service && sudo systemctl daemon-reload`<br>`sudo rm -rf /opt/Prowlarr /var/lib/prowlarr`<br>`sudo userdel prowlarr` |
| 5 | **Samba** | `sudo systemctl disable --now smbd nmbd`<br>`sudo apt purge -y samba samba-common-bin` (verified dry-run: removes only those two, no cascade)<br>`sudo apt autoremove -y`<br>`sudo rm -rf /etc/samba /var/lib/samba /var/cache/samba` |
| 6 | **Magnetize Stack** | `cd ~/devel-with-grok/mgzns-downloader`<br>`docker compose down --rmi all --remove-orphans`<br>`docker image prune -f`<br>`rm -rf ~/devel-with-grok/mgzns-downloader/config` (26 GB — all bind mounts, no named volumes)<br>keep the 88 KB compose repo for reference |

After each group: `systemctl --failed`, `docker ps`, and a `ss -tlnp` / `df -h` / `free -h` check.

### Expected end state

- Disk freed: ~33 GB. RAM freed: ~1.5 GB.
- Ports closed: 445, 139, 9091, 9696, 7474, 11434, 8192, 3333, 3334.
- Untouched: `tg-downloader` / `tg-webui` / `tg-autoheal` / `pigallery2` containers;
  `reverse-tunnel`, `tailscaled`, `nginx`, `jellyfin`, `qbittorrent-nox`, `intranet-dashboard`,
  `power-monitor`, `rss-review` services.

### Out of band

Router port-forwards for the removed services (if any) are a manual check on the router —
not visible from the Pi.

---

# Sub-project B — Dashboard revamp

## B1. Config cleanup

After A, 14 services in 3 host groups. The `Torrent Stack` and `Magnetize Stack` groups
disappear. The Pi's remaining services split into two same-IP groups (the pattern the old
`Torrent Stack` used) for a cleaner single scroll.

```yaml
dashboard:
  title: Home Lab
  port: 8888
  sample_interval_seconds: 60      # NEW — sampler cadence
  history_retention_days: 30       # NEW — sample retention

hosts:
  - name: Raspberry Pi 5
    ip: 192.168.50.13
    services:
      - name: PiGallery2
        url: http://192.168.50.13:3010/
        description: Self-hosted photo gallery
      - name: qBittorrent
        url: http://192.168.50.13:8080/
        description: BitTorrent client web UI
      - name: TG Downloader
        url: http://192.168.50.13:8090/
        description: Telegram channel media downloader and file browser
      - name: Jellyfin
        url: http://192.168.50.13:8096/
        description: Media server — movies, TV shows, music
      - name: RSS Media Review
        url: http://192.168.50.13:8765/
        description: Keep/discard review UI for RSS feed downloads
      - name: Static Files
        url: http://192.168.50.13/
        description: nginx static file server — serves /srv/www (autoindex on)

  - name: Raspberry Pi 5 — Background
    ip: 192.168.50.13
    services:
      - name: TG Listener
        description: Background Telegram media download listener (Docker)
        docker_container: tg-downloader
      - name: RSS Feed Reader
        description: RSS feed poller (cron, every 2 h)
        file_fresh:
          path: /home/marcello/devel-with-claude/rss-feed-reader/cron.log
          max_age_minutes: 150
      - name: Power Monitor
        description: Power outage and under-voltage notifier
        systemd_unit: power-monitor.service
      - name: Reverse Tunnel
        description: SSH reverse tunnel to relay VPS (remote access path)
        systemd_unit: reverse-tunnel.service
      - name: Tailscale
        description: WireGuard mesh VPN node agent
        systemd_unit: tailscaled.service

  - name: Zimaboard 2
    ip: 192.168.50.12
    services:
      - name: ZimaOS
        url: http://192.168.50.12/
        description: Home server OS and app store
      - name: ttyd
        url: http://192.168.50.12:7681/
        description: Web-based terminal
      - name: MiniDLNA
        url: http://192.168.50.12:8200/
        description: DLNA media server
```

Service-entry schema is otherwise unchanged: `name` / `description` / `url` /
`systemd_unit` / `docker_container` / `file_fresh`.

## B2. Module layout (chosen: "modest split")

| File | Interface | Depends on |
|---|---|---|
| `config.py` | `load_config() -> dict`, `iter_services(cfg) -> Iterator[(service_id, host, svc)]`, `service_id(host, svc) -> str` | `config.yaml` |
| `checks.py` | `check_service(svc) -> {"status": str, "latency_ms": int \| None}` — pure, logged | none |
| `store.py` | `init_db()`, `record(results: dict[str, dict], ts: int)`, `prune(before_ts: int)`, `status_summary() -> dict[str, dict]` | `sqlite3` |
| `sampler.py` | `start(cfg) -> None` — spawn daemon thread | `checks`, `store`, `config` |
| `app.py` | Flask routes; calls `store.init_db()` + `sampler.start(cfg)` on boot | all of the above |

`slugify` / `service_id` move from `app.py` into `config.py` unchanged.

## B3. Database — `dashboard.db`

SQLite, stdlib only, in the repo directory, gitignored (`dashboard.db`, `dashboard.db-wal`,
`dashboard.db-shm`).

```sql
CREATE TABLE IF NOT EXISTS samples (
  service_id TEXT    NOT NULL,
  ts         INTEGER NOT NULL,      -- unix epoch seconds
  status     TEXT    NOT NULL,      -- 'up' | 'down' | 'unknown'
  latency_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_samples_service_ts ON samples (service_id, ts);
```

- `PRAGMA journal_mode=WAL` set once in `init_db()`.
- Every `store` function opens its own short-lived `sqlite3.connect(DB, timeout=5)`.
- One writer (sampler thread), several readers (Flask request threads), one process.
- Steady state ≈ 605k rows (14 × 1440/day × 30 days).

### `store.status_summary()` return shape (per `service_id`)

```json
{
  "status": "down",
  "latency_ms": null,
  "uptime_24h": 0.87,
  "uptime_7d": 0.99,
  "last_seen_ts": 1756712400,
  "sparkline": [1.0, 1.0, 0.5, null, 1.0, "...24 entries"]
}
```

- `status`, `latency_ms` — from the most recent `samples` row for that service.
- `uptime_24h` / `uptime_7d` — `count(status='up') / count(*)` within the window; `null` if no samples.
- `last_seen_ts` — `max(ts)` where `status='up'`; `null` if never. UI shows it only when currently down.
- `sparkline` — 24 hourly buckets covering the last 24 h, oldest first (`sparkline[0]` =
  24 h ago, `sparkline[23]` = the current hour), each the fraction of `up` samples in that
  hour, or `null` for an hour with no samples. Computed in SQL.

## B4. Sampler

Daemon thread, started once in `app.py` at boot, guarded against the Werkzeug reloader
(the production unit runs with `debug=False`, so the guard is belt-and-braces). Each cycle:

1. `load_config()` → run every check in parallel via `ThreadPoolExecutor(max_workers=16)`.
2. `store.record(results, now)`.
3. Once per hour: `store.prune(now - history_retention_days * 86400)`.
4. Structured log: `action=sample count=14 up=12 down=1 unknown=1 duration_ms=340`.
5. `sleep(sample_interval_seconds)`.

The first sample runs immediately on boot so the UI is never empty.

## B5. API — two endpoints, both read-only from the DB

### `GET /api/services`

Unchanged output plus `sample_interval_seconds` (so the front-end can align its poll).

```json
{
  "title": "Home Lab",
  "sample_interval_seconds": 60,
  "hosts": [ { "name": "...", "ip": "...", "services": [ {"id": "...", "name": "...", "description": "...", "url": "..."} ] } ]
}
```

### `GET /api/status`

Returns `store.status_summary()` verbatim — `{ service_id: {status, latency_ms, uptime_24h,
uptime_7d, last_seen_ts, sparkline} }`. Never triggers a live check. Freshness is bounded
by `sample_interval_seconds`.

No `/api/history` endpoint — the sparkline and percentages are the whole "uptime % +
sparkline" feature.

## B6. Health-check fixes (`checks.py`)

Scope: fix obvious bugs. No new status states, no per-service expected-status config.

### `check_http`

- Transport error (timeout / connection refused / DNS) → `down`, logged with the specific cause.
- Response received → `up` if `status < 400` **or** `status in (401, 403)` (auth wall = reachable);
  any other status → `down`. The actual status code is always logged.
- One retry on *transport* failure only: `sleep(0.5)` then one more attempt. HTTP error
  statuses are not retried. Keeps a single dropped packet from painting a red sparkline bar.
- `allow_redirects=True` retained; timeout 3 s retained.

### `check_systemd`

- `systemctl is-active <unit>`: `active` → up, anything else → down.
- `SubState` captured into the log line.
- Subprocess failure → `unknown` (logged).
- **Known gap, not fixed:** confirms the unit's process is alive, not that it works — the
  reason reverse-tunnel read "active" through its Aug 21–28 flapping. A proper fix (a
  `tcp_probe` check against the VPS's forwarded port) needs new config and is deferred.

### `check_docker`

Logic unchanged; logging added; non-zero `docker inspect` exit → `unknown` (logged).

### `check_file_fresh` (new)

`file_fresh: {path, max_age_minutes}`. File missing → `down`; `mtime` within window → `up`;
older → `down`. The file's actual age is logged each call.

### Priority in `check_service`

`url` > `docker_container` > `systemd_unit` > `file_fresh` > `{"status": "unknown"}`.

### Every check

One structured log line per invocation, e.g.
`action=check type=http target=http://192.168.50.13:8096/ result=up latency_ms=45`.

### Out of scope

`degraded` state, per-service `expect_status`, response-body matching, the reverse-tunnel
reachability probe.

## B7. Front-end (`static/index.html`)

Evolution of the current file, not a rewrite. Single HTML file, vanilla JS, no build step.

**Kept:** sticky header, stacked host sections, responsive `auto-fill` card grid, the
`renderHosts()` (build once) + `applyStatus()` (patch in place) pattern, ~30 s auto-refresh,
loading/error states.

**Adopted from the 2026-05-07 spec:** 3 px left-border status cards (green / red / grey),
its colour tokens, latency shown in the card header.

**Dropped from that spec:** the sidebar, host-switching, and the separate desktop/mobile
layouts. One layout at every width.

### Card

```
┌─┬─────────────────────────────┐
│ │ Jellyfin             45ms   │   name (bold) + latency / "down"
│ │ Media server — movies…      │   description, muted, 1-line clamp
│ │ ▁▂▁█▁▁▂▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁    │   24 h sparkline (inline SVG)
│ │ 87% · 24h        [ Open ↗ ] │   uptime % + Open button (Open only if url)
└─┴─────────────────────────────┘
   ↑ 3 px left border = current status
```

When `status == "down"`, the bottom line leads with `last seen 2h ago` (from `last_seen_ts`,
humanised) instead of the plain percentage.

### Sparkline

Inline SVG, 24 thin bars (one per hour, last 24 h). Bar height ∝ `sparkline[i]` (fraction-up).
Colour: `>= 0.99` green, `>= 0.5` amber, `< 0.5` red; `null` → faint grey stub. ~72 px wide.
`role="img"` + `aria-label="uptime 87% over last 24 hours"`. Re-rendered on each status patch.

### Header & groups

- Header gains an overall `12 / 14 up` summary beside the last-checked timestamp.
- Group heading: uppercase name + monospace IP as now, but a repeated consecutive IP is
  suppressed (so "Raspberry Pi 5 — Background" does not restate `192.168.50.13`).

### Refresh

Poll `/api/status` every 30 s. It is a cheap DB read now, so this is far lighter than
today's live-check-per-poll.

## B8. Testing

First tests in the project. Add `pytest` as a dev dependency via `uv`.

| Target | Tests |
|---|---|
| `checks.py` | `check_http` (mocked `requests`): 200/302 → up, 401/403 → up, 404/500 → down, timeout → down + one retry fired, connection error → down. `check_file_fresh` (`tmp_path` + set mtime): fresh → up, stale → down, missing → down. `check_systemd` / `check_docker` (mocked `subprocess.run`): status mapping. |
| `store.py` | `tmp_path` DB. `record()` → `status_summary()` current = latest sample. Uptime math over a known up/down mix → exact `uptime_24h` / `uptime_7d`. Sparkline bucketing across hours → 24 buckets, right fraction-up, `null` for empty hours. `prune()` drops only rows older than the cutoff. `last_seen_ts` correct when currently down. |
| `config.py` | Sample config → `iter_services` yields expected ids; `service_id` slug stable. |
| `sampler.py` | One cycle with monkeypatched checks + tmp DB → rows written. The sleep loop is not tested. |
| Front-end | No automated tests. Manual checklist. |

**Manual verification before "done":**
1. `uv run pytest` green.
2. `uv run python app.py`; eyeball `/api/services` and `/api/status` JSON.
3. Browser: all 14 services render; sparklines draw; a deliberately-stopped service shows
   `down` + `last seen`; uptime numbers sane after a few sample cycles.
4. On the Pi: journal shows `action=sample` lines; `dashboard.db` grows then prunes.

## B9. Sequencing & deploy

1. **Sub-project A** — execute the decommission runbook on the Pi.
2. **Sub-project B** on branch `revamp` off `master`: build the modules, refactor `app.py`,
   rewrite `index.html`, tests green, update `CLAUDE.md` + `README.md`, mark
   `2026-05-07-ui-redesign-design.md` superseded (pointer to this spec), add `dashboard.db*`
   to `.gitignore`.
3. **Deploy:** `git pull` on the Pi (repo at `/home/marcello/devel-with-claude/intranet-dashboard`,
   which the running service uses) → `uv sync` (runtime deps unchanged: Flask / requests /
   PyYAML; SQLite is stdlib) → `sudo systemctl restart intranet-dashboard.service` → verify
   journal + DB. Check whether the systemd unit needs `ReadWritePaths` for `dashboard.db`
   (expected not — runs as `marcello`, writes into the repo dir).
4. **No data migration** — `dashboard.db` starts empty on first boot; history accrues from zero.

**Rollback:** A has none by design (full removal). B: redeploy the previous commit and delete
`dashboard.db`.

## Non-goals

- Authentication on the dashboard (LAN-only, unchanged).
- Monitoring/alerting on the collected history (no notifications, no thresholds).
- A dedicated per-service history page or incident list.
- Any change to the services that are kept.
- Fixing the Zimaboard's missing SSH key (blocks unit-level checks for its services — they
  stay `url`-checked).
