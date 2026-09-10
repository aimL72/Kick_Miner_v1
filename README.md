<p align="center">
  <img src="assets/logo.png" alt="Kick Channel Points Miner" width="320">
</p>

<p align="center">
  <a href="https://github.com/aimL72/Kick_Miner_v1/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/aimL72/Kick_Miner_v1?style=flat&color=black&logo=unlicense&logoColor=white"></a>
  <a href="https://github.com/aimL72/Kick_Miner_v1/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/aimL72/Kick_Miner_v1?style=flat&color=32CD32&logo=github&logoColor=white"></a>
  <a href="https://github.com/aimL72/Kick_Miner_v1/pkgs/container/kick_miner_v1"><img alt="GHCR image" src="https://img.shields.io/badge/ghcr.io-kick__miner__v1-2496ED?style=flat&logo=docker&logoColor=white"></a>
  <a href="README.de.md"><img alt="Deutsche Version" src="https://img.shields.io/badge/lang-%F0%9F%87%A9%F0%9F%87%AA%20Deutsch-white?style=flat"></a>
</p>

<h1 align="center">https://github.com/aimL72/Kick_Miner_v1</h1>

**Credits**
- Concept / feature set: [zarmstrong/Twitch-Channel-Points-Miner-v3](https://github.com/zarmstrong/Twitch-Channel-Points-Miner-v3) (GPL-3.0) — used as a conceptual template only, no source code taken
- Original Twitch idea: [gottagofaster236/Twitch-Channel-Points-Miner](https://github.com/gottagofaster236/Twitch-Channel-Points-Miner) and [Tkd-Alex/Twitch-Channel-Points-Miner-v2](https://github.com/Tkd-Alex/Twitch-Channel-Points-Miner-v2)
- Kick platform base: [Baillora/Kick_Channel_Points_Miner](https://github.com/Baillora/Kick_Channel_Points_Miner) (MIT) — Kick API endpoints, Cloudflare-bypass approach, viewer WebSocket protocol

> A simple bot that watches Kick streams for you and farms the channel points.

A pure **Kick.com** channel-points farming bot. It keeps a viewer WebSocket open
to the streamers you configure so points accrue while you're "watching", tracks
your balances in SQLite, shows everything on a Twitch-miner-style web dashboard
(with a built-in streamer editor), and can push updates to Discord and be
controlled from Telegram.

Modeled on the feature set of the Twitch channel-points miners, but Kick-only.
Predictions, watch streaks, raids and drops are **not** part of this bot – Kick
either doesn't have them or exposes no usable interface for them.

> ⚠️ **Use at your own risk.** Automating watch time violates Kick's Terms of
> Service and can get accounts restricted or banned. Only use accounts you are
> willing to lose. For educational purposes.

## Features

* **Multi-account** – each account has its own token, proxy, streamer list and
  concurrency limit.
* **Priority watching** – streamer list position = priority; when a
  higher-priority streamer goes live it displaces a lower one, capped at
  `max_concurrent`.
* **Cloudflare bypass** – one shared `curl_cffi` session per account with a
  403 re-bootstrap + retry.
* **SOCKS5 / HTTP proxy** – global or per-account.
* **Web dashboard** (`http://localhost:5000`) – Points / Config / Log tabs,
  live "now watching" strip, per-streamer point charts, and a **streamer editor**
  (add / remove / reorder, change the concurrency limit); saving restarts the
  miner automatically.
* **Points history** in `data/analytics.sqlite3` (30-day retention).
* **Discord webhook** – exact Twitch-miner message format.
* **Telegram bot** – `/status` `/balance` `/accounts` `/restart` `/language`,
  usable only by the one configured `chat_id`.
* **Auto-restart** on crashes, on Telegram `/restart`, and after a dashboard
  config edit. Clean `Ctrl+C` shutdown.
* **Self-test** – `python -m kickminer.selfcheck <channel> --account "<alias>"`
  verifies the whole read path (Cloudflare, channel, points, WS token).

## Requirements

* Python 3.10+
* A Kick **bearer token** per account (see below)

## Install

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt
cp config.example.json config.json
```

Then edit `config.json` (it is git-ignored – your token never gets committed).

## Getting your Kick token

1. Log in to **kick.com** in your browser.
2. Open DevTools (`F12`) → **Network** tab.
3. Refresh the page, click any request to `kick.com`.
4. Under **Request Headers** find `authorization: Bearer <token>`.
5. Copy the part after `Bearer ` (looks like `123456|xxxxxxxx…`) into
   `config.json` → `Accounts[].token`.

Tokens expire; if the points check starts failing, grab a fresh one.

## Configuration

`config.json` keys (see `config.example.json` for a full example):

| Key | Meaning |
| --- | --- |
| `Language` | `en` (default) or `de` |
| `Debug` | verbose console logging (the file log is always DEBUG) |
| `WebDashboard.enabled` / `.port` | web dashboard |
| `Discord.enabled` / `.webhook_url` / `.username` / `.avatar_url` | webhook notifier |
| `Discord.notify_points` / `notify_status_change` / `notify_errors` / `notify_startup` | per-event switches |
| `Discord.min_points_gain` | suppress point gains smaller than this |
| `Telegram.enabled` / `.bot_token` / `.chat_id` | control bot - `chat_id` is the single allowed user |
| `Proxy.enabled` / `.url` | global proxy (`socks5://`, `http://`) |
| `Accounts[]` | one entry per Kick account |
| `Accounts[].alias` | display name (used by the dashboard and Telegram) |
| `Accounts[].token` | Kick bearer token |
| `Accounts[].proxy` | per-account proxy, or `null` for the global one |
| `Accounts[].streamers` | ordered list – **position = priority**, index 0 highest |
| `Accounts[].max_concurrent` | how many streamers to watch at once |
| `Check_interval` | seconds between online checks |
| `Reconnect_cooldown` | after a streamer's WebSocket gives up, seconds to wait before retrying that streamer |
| `Connection_stagger_min/max` | delay range between opening connections |

The old single-account layout (`Private.token` / `Streamers` /
`Max_active_channels`) is still accepted and auto-migrated.

## Run

```bash
python main.py
```

Then open `http://localhost:5000`.

### Docker

Everything mutable (`config.json`, `logs/`, `data/`) lives in **one** mounted
directory (`/data` inside the container, `KICK_MINER_DATA`).

```bash
mkdir -p data
docker compose up -d          # pulls ghcr.io/aiml72/kick_miner_v1:latest
```

On first start it drops a `data/config.json` template — edit it (tokens,
streamers) and `docker compose restart`.

To build from this checkout instead of pulling: edit `docker-compose.yml`
(comment `image:`, uncomment `build:`), then `docker compose up -d --build`.

### ZimaOS / CasaOS

1. In the app store choose **Install a custom app** → **Import** and paste the
   contents of [`docker-compose.yml`](docker-compose.yml).
2. Change the volume line `./data:/data` to a real path on the NAS, e.g.
   `/DATA/AppData/kick-miner:/data`.
3. Start it once, then open the ZimaOS file manager, edit
   `/DATA/AppData/kick-miner/config.json` (tokens + streamers), and restart the
   app.
4. Dashboard: `http://<nas-ip>:5000`.

The image is multi-arch (amd64 + arm64) and rebuilt by GitHub Actions on every
push to `main`.

## Telegram setup

1. Talk to [@BotFather](https://t.me/BotFather), `/newbot`, copy the token into
   `Telegram.bot_token`.
2. Message [@userinfobot](https://t.me/userinfobot) to get your numeric user id,
   put it in `Telegram.chat_id` (that makes you the owner).

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full history of changes.

## Credits

See the **Credits** block at the top of this file.

## License

MIT – see [LICENSE](LICENSE).
