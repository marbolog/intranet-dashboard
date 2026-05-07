# UI Redesign — Design Spec

**Date:** 2026-05-07
**Project:** intranet-dashboard
**Status:** Approved

## Overview

Redesign the dashboard from a flat card grid to a sidebar + main-area app layout. The sidebar lists hosts; the main area shows the selected host's services. On mobile the sidebar is replaced by a sticky header and hosts stack vertically.

---

## Layout

### Desktop (≥ 768px)

```
┌────────────────┬──────────────────────────────────────────┐
│   Sidebar      │   Main area                              │
│   220px fixed  │   scrollable                             │
│                │                                          │
│  🏠 Home Lab   │  Raspberry Pi 5  192.168.50.13           │
│  ─────────     │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  ▶ Pi 5        │  │ Jellyfin │ │qBittorr..│ │ Rclone   │ │
│    ●10 ●1      │  │          │ │          │ │          │ │
│  Zimaboard     │  └──────────┘ └──────────┘ └──────────┘ │
│    ●3          │                                          │
│  ─────────     │                                          │
│  13/14 up      │                                          │
└────────────────┴──────────────────────────────────────────┘
```

- Sidebar is `position: fixed`, full viewport height, does not scroll
- Main area has `margin-left: 220px`, scrolls independently
- No top header bar on desktop

### Mobile (< 768px)

```
┌──────────────────────────────┐
│  🏠 Home Lab      13/14 up   │  ← sticky blue header
├──────────────────────────────┤
│  RASPBERRY PI 5              │
│  192.168.50.13               │
│  ┌────────────────────────┐  │
│  │ Jellyfin          Open │  │
│  ├────────────────────────┤  │
│  │ qBittorrent       Open │  │
│  └────────────────────────┘  │
│  ZIMABOARD                   │
│  192.168.50.12               │
│  ┌────────────────────────┐  │
│  │ ZimaOS            Open │  │
│  └────────────────────────┘  │
└──────────────────────────────┘
```

- Sidebar is hidden on mobile
- Blue sticky header: brand name left, "N/M up" summary right
- All hosts rendered as stacked sections; no host switching — just scroll

---

## Color System

| Token | Value | Usage |
|---|---|---|
| `--sidebar-bg` | `#1d4ed8` | Sidebar background |
| `--sidebar-active` | `rgba(255,255,255,0.15)` | Selected host highlight |
| `--sidebar-border` | `rgba(255,255,255,0.12)` | Divider lines in sidebar |
| `--main-bg` | `#ffffff` | Main content background |
| `--page-bg` | `#f8fafc` | Page / card background |
| `--card-bg` | `#ffffff` | Card surface |
| `--border` | `#e2e8f0` | Card borders |
| `--text` | `#1e293b` | Primary text |
| `--muted` | `#94a3b8` | Secondary text, descriptions |
| `--up` | `#22c55e` | Status up — left border + counter |
| `--down` | `#ef4444` | Status down — left border + counter + latency label |
| `--unknown` | `#cbd5e1` | Status unknown — left border |
| `--btn-bg` | `#1d4ed8` | Open button background |

---

## Sidebar (desktop)

- Fixed, 220px wide, full viewport height, `overflow-y: auto`
- **Brand:** "🏠 Home Lab" — white, bold, top of sidebar with padding
- **Host list:** one row per host
  - Host name (white, semibold)
  - Status counters on the next line: `● N` in green for up services, `● N` in red for down services (only shown if count > 0)
  - Selected host: `rgba(white, 0.15)` background + `2px solid white` left border
  - Click switches the main area (no page reload)
- **Footer:** thin divider line, then two rows:
  - Row 1: "↺" refresh button (left) + "N / M up" summary (right) — both in muted white (`rgba(white, 0.55)`)
  - Row 2: last-checked timestamp, e.g. "Checked 11:42" — `rgba(white, 0.4)`, smaller font

---

## Main Area (desktop)

- `margin-left: 220px`, `min-height: 100vh`, `background: #f8fafc`
- **Host heading:** host name (bold, 1.1rem) + IP address (monospace, muted) — top of content, padding 24px
- **Card grid:** `display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; padding: 0 24px 24px`

---

## Service Cards

### Desktop card (vertical layout)

```
┌─╔══════════════════════════╗
│ ║  Jellyfin                ║  ← name, bold
│ ║  45ms                    ║  ← latency, muted
│ ║  Media server — movies.. ║  ← description, muted, 1 line clamp
│ ║                          ║
│ ║  [ Open ↗ ]              ║  ← only if URL present
╚═╚══════════════════════════╝
  ↑ left border: green / red / gray
```

- `background: #fff`, `border: 1px solid #e2e8f0`, `border-radius: 10px`
- `border-left: 3px solid <status-color>`
- Latency: `0.75rem`, `--muted`; "down" shown in `--down` red; "—" for unknown
- Description: `0.8rem`, `--muted`, `overflow: hidden; display: -webkit-box; -webkit-line-clamp: 1`
- Open button: blue (`--btn-bg`), `border-radius: 6px`, `padding: 8px 14px`, `touch-action: manipulation`, `min-height: 38px`

### Mobile card (horizontal row)

```
┌─╔══════════════════════════════╗
│ ║  Jellyfin       [ Open ↗ ]  ║
│ ║  45ms · Media server        ║
╚═╚══════════════════════════════╝
```

- Name + Open button on the same line (flex row, space-between)
- Latency + description merged on a second line, separated by " · "
- Open button: smaller (`padding: 6px 12px`), vertically centered

---

## Status Rendering

| State | Left border | Latency label | Color |
|---|---|---|---|
| up | `--up` green | `45ms` or `up` | `--muted` |
| down | `--down` red | `down` | `--down` red |
| unknown | `--unknown` gray | `—` | `--muted` |

Sidebar counters: only show green counter if any services are up; only show red counter if any are down. Unknown services are not counted in the sidebar.

---

## Interactivity

- **Host switching (desktop):** clicking a sidebar host re-renders the main area with that host's services. No full page reload. URL does not change.
- **Auto-refresh:** `/api/status` polled every 30 seconds. Status updates are applied in-place (no full re-render) — only the left border color and latency label update, plus sidebar counters.
- **Refresh button (desktop only):** small "↺" icon button in sidebar footer, triggers an immediate status refresh. No manual refresh on mobile — auto-refresh every 30s is sufficient.
- **Initial load:** `/api/services` and `/api/status` fetched in parallel. Services list is cached; only status is re-fetched on subsequent refreshes.

---

## Responsive Breakpoints

| Breakpoint | Behavior |
|---|---|
| ≥ 768px | Sidebar visible, main area offset by 220px, card grid |
| < 768px | Sidebar hidden, sticky blue header, stacked sections, horizontal card rows |
| < 480px | Card rows stack vertically (same as desktop card but single column) |

---

## Files Changed

Only `static/index.html` is modified. `app.py` and `config.yaml` are unchanged — the API contract stays the same.
