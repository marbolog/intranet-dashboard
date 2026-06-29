# CLAUDE.md

## Project: intranet-dashboard

Web dashboard showing all home lab services on Raspberry Pi (192.168.50.13) and Zimaboard (192.168.50.12), with live health checks and links to open web apps.

### Stack
- **Python 3.11**, managed by **uv**
- **Flask** — serves the single-page UI and health-check API
- **requests** — HTTP health checks for web services
- **PyYAML** — service config
- Vanilla JS (no build step) — auto-refreshes status every 30 s

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
| `app.py` | Flask app — serves `/`, `/api/services`, `/api/status` |
| `config.yaml` | Service definitions (hosts, names, URLs, check types) |
| `static/index.html` | Single-page dashboard (vanilla JS) |
| `systemd/intranet-dashboard.service` | Systemd unit (runs as user marcello) |

### Adding / editing services
Edit `config.yaml` and restart the service. Each service entry supports:
- `name` — display name (required)
- `description` — shown in card (optional)
- `url` — web URL; enables the Open button and HTTP health check
- `systemd_unit` — check via `systemctl is-active` (background services with no URL)
- `docker_container` — check via `docker inspect` (background Docker services)

Health check priority: `url` > `docker_container` > `systemd_unit`.

### Service groups (hosts in config.yaml)
`config.yaml` uses host entries as visual sections in the dashboard. Multiple entries can share the same IP to create logical groupings — e.g. **Torrent Stack** is a separate host entry for `192.168.50.13` that groups Prowlarr, autobrr, and Transmission together.

| Host entry | IP | Purpose |
|---|---|---|
| Raspberry Pi 5 | 192.168.50.13 | General services + background daemons (Ollama, Samba, Tailscale, power monitor, reverse tunnel) + nginx static file server (port 80) |
| Torrent Stack | 192.168.50.13 | Prowlarr (9696), autobrr (7474), Transmission (9091) |
| Magnetize Stack | 192.168.50.13 | bitmagnet (3333 web / 3334 DHT), Jackett (9118), FlareSolverr, Postgres — Docker compose stack at `~/devel-with-grok/mgzns-downloader` |
| Zimaboard 2 | 192.168.50.12 | ZimaOS, ttyd, MiniDLNA |

**Ollama** runs locally (`127.0.0.1:11434`, models `mistral:7b` + `phi3:mini`); it is bound to localhost so it has no `url` (no Open button) and is health-checked via `systemd_unit`.

**Static file server (nginx):** nginx serves `/srv/www` on port 80 (`http://192.168.50.13/`).
Drop files into `/srv/www` (owned by `marcello`, writable without sudo); folders without an
`index.html` get an automatic directory listing (`autoindex on`). Site config lives at
`/etc/nginx/sites-available/static-files`; the stock `default` site is disabled. Reload after
config changes with `sudo nginx -t && sudo systemctl reload nginx`.

### Docker health checks (resolved)
`marcello` is now in the `docker` group (gid 991), so `docker inspect` works without
sudo and all `docker_container` checks (`tg-downloader`, `mgzns-flaresolverr`,
`mgzns-bitmagnet-postgres`) report correctly. The previous `usermod -aG docker marcello`
fix has been applied — no action needed.



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

