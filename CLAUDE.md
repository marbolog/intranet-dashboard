# CLAUDE.md

## Project: intranet-dashboard

Web dashboard showing all home lab services on Raspberry Pi (192.168.50.13) and Zimaboard (192.168.50.12), with health checks, per-service uptime history, and links to open web apps.

> **Removed 2026-09-01** (unused — see `docs/superpowers/specs/2026-09-01-revamp-design.md`):
> Ollama, Transmission, autobrr, Prowlarr, Samba, and the Magnetize Stack
> (bitmagnet + Postgres + Jackett + FlareSolverr). ~33 GB / ~1.5 GB RAM reclaimed.

### Stack
- **Python 3.11**, managed by **uv**
- **Flask** — serves the single-page UI and the status API
- **requests** — HTTP health checks for web services
- **PyYAML** — service config
- **SQLite** (stdlib `sqlite3`) — status-history store (`dashboard.db`), sampled every 60 s
- **pytest** (dev group) — `uv run pytest`
- Vanilla JS (no build step) — polls `/api/status` every 30 s, draws inline-SVG sparklines

### Running
```bash
# Dev:
uv run python app.py

# Production (systemd):
sudo cp systemd/intranet-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now intranet-dashboard.service
```

Dashboard is at: **http://192.168.50.13:8888**

### Files
| File | Purpose |
|---|---|
| `app.py` | Flask app — serves `/`, `/api/services`, `/api/status`; boots the DB + sampler |
| `config.py` | Loads `config.yaml`; computes `service_id`; `iter_services()` |
| `checks.py` | Health checks: `check_http` / `check_systemd` / `check_docker` / `check_file_fresh` |
| `store.py` | SQLite: schema, `record()`, `prune()`, `status_summary()` (uptime %, sparkline) |
| `sampler.py` | Daemon thread — samples every service every `sample_interval_seconds`, prunes hourly |
| `config.yaml` | Service definitions + `sample_interval_seconds` / `history_retention_days` |
| `static/index.html` | Single-page dashboard (vanilla JS, inline-SVG sparklines) |
| `dashboard.db` | Status-history SQLite DB (gitignored, created on first run) |
| `tests/` | pytest suite (`uv run pytest`) |
| `systemd/intranet-dashboard.service` | Systemd unit (runs as user marcello) |

### Adding / editing services
Edit `config.yaml` and restart the service. Each service entry supports:
- `name` — display name (required)
- `description` — shown in card (optional)
- `url` — web URL; enables the Open button and HTTP health check
- `systemd_unit` — check via `systemctl show` (`ActiveState=active`); background services with no URL
- `docker_container` — check via `docker inspect` (background Docker services)
- `file_fresh` — `{path, max_age_minutes}`; up if the file was modified within the window (cron jobs)

Health check priority: `url` > `docker_container` > `systemd_unit` > `file_fresh`.

HTTP checks count `<400` and `401`/`403` (auth wall) as up; everything else is down. One retry on transport failure.

### Service groups (hosts in config.yaml)
`config.yaml` uses host entries as visual sections in the dashboard. Multiple entries can share the same IP to create logical groupings — e.g. **Raspberry Pi 5 — Background** is a separate host entry for `192.168.50.13` that groups the daemons.

| Host entry | IP | Purpose |
|---|---|---|
| Raspberry Pi 5 | 192.168.50.13 | Web apps: PiGallery2, qBittorrent, TG Downloader, Jellyfin, RSS Media Review, Static Files |
| Raspberry Pi 5 — Background | 192.168.50.13 | Daemons: TG Listener (Docker), RSS Feed Reader (cron/`file_fresh`), Power Monitor, Reverse Tunnel, Tailscale |
| Zimaboard 2 | 192.168.50.12 | ZimaOS, ttyd, MiniDLNA |

**Static file server (nginx):** nginx serves `/srv/www` on port 80 (`http://192.168.50.13/`).
Drop files into `/srv/www` (owned by `marcello`, writable without sudo); folders without an
`index.html` get an automatic directory listing (`autoindex on`). Site config lives at
`/etc/nginx/sites-available/static-files`; the stock `default` site is disabled. Reload after
config changes with `sudo nginx -t && sudo systemctl reload nginx`.

### Status history
`sampler.py` runs as a daemon thread inside the Flask process. Every
`sample_interval_seconds` (default 60) it checks every service and writes one
row per service to `dashboard.db` (`samples` table, WAL mode). Once an hour it
deletes rows older than `history_retention_days` (default 30).

`/api/status` never runs a live check — it returns the latest stored sample per
service plus derived figures: `uptime_24h`, `uptime_7d`, `last_seen_ts`, and a
24-bucket hourly `sparkline` (oldest first). The UI polls it every 30 s.

To reset history: stop the service, `rm dashboard.db*`, start it again.

### Docker health checks
`marcello` is in the `docker` group (gid 991), so `docker inspect` works without
sudo. The only `docker_container` check now is `tg-downloader` (TG Listener).



You are a human software engineer. Assume all code will be written and maintained by humans. Optimize for reasoning, regeneration, and debugging — with an eye on human readability.

Your goal: produce code that is predictable, debuggable, and easy for future LLMs to rewrite or extend.

## Workflow

- Work in discrete steps. Break complex tasks into smaller subtasks and complete them one at a time.
- Use `mcp__context7` or equivalent documentation tools to read relevant docs for any language, framework, or library before writing code. Never assume your training knowledge is current — always verify.
- Check your work before returning control to the user. Run tests if available, verify builds, lint. Never return incomplete or unverified work.
- Each time you complete a task or learn important project information, update this `CLAUDE.md` file to reflect new knowledge or required changes.

## Mandatory Coding Principles

1. **Structure**
   - Use a consistent, predictable project layout.
   - Group code by feature/screen; keep shared utilities minimal.
   - Create simple, obvious entry points.
   - Before scaffolding multiple files, identify shared structure first. Use framework-native composition patterns (layouts, base templates, providers, shared components) for elements that appear across pages. Duplication that requires the same fix in multiple places is a code smell, not a pattern to preserve.

2. **Architecture**
   - Prefer flat, explicit code over abstractions or deep hierarchies.
   - Avoid clever patterns, metaprogramming, and unnecessary indirection.
   - Minimize coupling so files can be safely regenerated.

3. **Functions and Modules**
   - Keep control flow linear and simple.
   - Use small-to-medium functions; avoid deeply nested logic.
   - Pass state explicitly; avoid globals.

4. **Naming and Comments**
   - Use descriptive-but-simple names.
   - Comment only to note invariants, assumptions, or external requirements.

5. **Logging and Errors**
   - Emit detailed, structured logs at key boundaries.
   - Make errors explicit and informative.

6. **Regenerability**
   - Write code so any file/module can be rewritten from scratch without breaking the system.
   - Prefer clear, declarative configuration (JSON/YAML/etc.).

7. **Platform Use**
   - Use platform conventions directly and simply without over-abstracting.

8. **Modifications**
   - When extending/refactoring, follow existing patterns.
   - Prefer full-file rewrites over micro-edits unless told otherwise.

9. **Quality**
   - Favor deterministic, testable behavior.
   - Keep tests simple and focused on verifying observable behavior.

