# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Because the Docker image is published as a rolling `latest` tag on every push to
`main`, entries are grouped by date rather than by release tag. The short commit
hash is given for each change.

## [Unreleased]

### Added
- **Auto-skip channels that award no points.** Some Kick channels give no channel
  points at all. If a watched streamer earns nothing for
  `No_points_grace_minutes` straight (default 30, `0` disables, otherwise 10–240),
  the miner flags it "no points", moves to the next streamer, and re-checks it
  once every 6 hours. Shown as a red "no pts" badge on the dashboard card and
  pushed to Discord / Telegram (gated by the "errors" toggle). Configurable from
  the dashboard Watch-mode section.
- Project logo (`assets/logo.png`), a credits header at the top of both READMEs
  (in the style of the Twitch miner) and a `CHANGELOG.md`.
- **Hover help throughout the dashboard** (`a2a8bc0`) — a small `?` bubble next to
  every label shows a tooltip explaining the control (watch mode, cycle interval,
  max concurrent, token, streamer list, add-account, all Notification fields,
  stat tiles, the now-watching strip and the account cards). Buttons and the tab
  bar carry plain `title=` tooltips.

### Changed
- Dark styling for the `<select>` dropdown and native number/text inputs so the
  watch-mode picker no longer renders white (`5bb713b`).

## 2026-09-10

### Added
- **Cycle watch mode** (`9f32791`) — a new `"Cycle"` config block. When enabled,
  each account rotates through its streamer list in groups of `max_concurrent`,
  one group per interval (5–120 min, default 15), wrapping around, so every
  streamer gets watched in turn. When disabled the miner keeps the original
  priority behaviour: the highest live streamers are watched until they go
  offline. Selectable from the dashboard, with a live "cycle 2/3, switch in
  4m12s" status on the Points tab.
- **Notifications tab in the dashboard** (`ed696e0`) — enter the Telegram bot
  token / owner chat id and the Discord webhook URL from the browser. Secrets are
  masked on read and only overwritten when re-typed, so nothing sensitive lives
  in the repo or image.
- **Explicit Restart button** (`ed696e0`) — configuration edits are saved
  immediately but only take effect when you press Restart. The button glows and a
  banner appears while there are saved-but-not-applied changes.
- Docker deployment: a single `/data` volume, first-run `config.json` bootstrap
  from the example, and a GitHub Actions workflow that publishes a multi-arch
  (amd64 + arm64) image to GHCR on every push to `main` (`e7d7bcd`).

### Changed
- Notifications tab reworked into collapsible sections; Telegram gained the same
  per-event toggles and minimum-points-gain threshold as Discord (`0fdffd9`).
- Restart now also rebuilds the Telegram and Discord notifiers, so token edits
  from the dashboard apply on Restart instead of needing a container restart
  (`f6cd028`).
- Telegram is single-user only now — `allowed_users` was removed everywhere; the
  owner is the one `chat_id`, claimed on first `/start` if unset (`649e036`).
- Config editor accepts channel names with hyphens and dots and up to 40
  characters (e.g. `los-ratones`); `/`, `\` and `..` are still rejected
  (`a10e24a`).

## 2026-09-09

### Added
- Initial build of the Kick channel-points farmer.
  - Project scaffold, `config.json` loader/validator, loguru logging, and the
    Kick read layer (channel / livestream / points / WebSocket-token endpoints)
    with curl_cffi TLS impersonation for the Cloudflare bypass (`3be84f1`).
  - Mining core: the viewer WebSocket that sends `watch.livestream` events,
    the per-account worker with live-status polling and `select_active`
    rebalancing, and the manager that runs all accounts (`c8b90a7`).
  - SQLite points history (30-day retention) and a web dashboard with a
    dependency-free SVG chart (`23d265f`).
  - Discord webhook notifications and a Telegram control bot
    (`/status` `/balance` `/accounts` `/restart` `/language`) (`e9bfd59`).
  - Dashboard v2 in the style of the Twitch miner: navy/coral palette, tabbed
    layout, now-watching strip, per-account cards, and a Config tab that edits
    the streamer list (add / remove / reorder, `max_concurrent`) via an atomic
    config writer (`195f48c`).
  - Multi-account support with staggered connection start.
  - Packaging, README (English + German), and a slim Dockerfile (`c1355b6`).
  - Kick bearer-token validity check with a green/red badge on the dashboard and
    a Discord alert when a token goes invalid; token editable from the Config tab
    (`cf0e88a`).
  - `Reconnect_cooldown` wired up — a streamer whose WebSocket gives up is parked
    for the cooldown period instead of being retried immediately (`4ac3431`).
  - Drag-to-reorder streamers (SortableJS, vendored) and add/remove whole Kick
    accounts from the dashboard (`057bed3`).

### Fixed
- **Silent crash after ~17 minutes on multi-account runs** (`ff88941`) — the
  curl_cffi sync `Session` is not multi-thread-safe, and `asyncio.to_thread`
  handed calls to arbitrary pool threads, causing a native segfault with no
  traceback. Each HTTP client now owns a single dedicated worker thread for the
  life of its session. Validated by a clean 90-minute two-account run.
- **403 reconnect loop** (`7e40d52`) — viewer WebSocket tokens expire after
  ~15–30 minutes and the old code cached the token from construction, so any
  mid-session reconnect looped on HTTP 403. Every reconnect now fetches a fresh
  token first.
- Telegram `getUpdates` `Conflict` (a second poller) is logged as a clean
  warning instead of a traceback (`a49400d`).
- `kick_api`: a 200 response with no `points` field (a viewer who never earned on
  that channel) is treated as a balance of 0 (`ca52359`).

### Notes on notification formatting
The Discord and Telegram message formats were iterated several times on
2026-09-09 (`7ea6672`, `2c24f6f`, `22eb641`, `9bbfb0a`, `d7fb019`, `7adcc91`,
`c079bda`, `7ccaa70`, `2c68a09`, `fc44fa2`). The settled result: Discord sends a
coloured embed (green for online/gain/start, grey for offline, red for
stop/error) with a two-line body, and Telegram uses the same emoji set with its
own wording.
