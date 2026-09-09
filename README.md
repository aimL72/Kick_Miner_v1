# Kick Channel Points Miner

A pure **Kick.com** channel-points farming bot. It keeps a viewer WebSocket open
to the streamers you configure so points accrue while you're "watching", tracks
your balance, and shows everything on a small web dashboard.

Modeled on the feature set of the Twitch channel-points miners, but Kick-only.
Predictions, watch streaks, raids and drops are **not** part of this bot – Kick
either doesn't have them or exposes no usable interface for them.

> ⚠️ **Use at your own risk.** Automating watch time violates Kick's Terms of
> Service and can get accounts restricted or banned. Only use accounts you are
> willing to lose. For educational purposes.

## Status

Work in progress. Phase 1 (configuration, logging, Kick read layer) is done and
verifiable today:

```bash
python -m kickminer.selfcheck <channel>                      # public reachability
python -m kickminer.selfcheck <channel> --account "<alias>"  # + points + WS token
```

The mining supervisor, dashboard and notifiers follow in the next phases.

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

Tokens expire; if the self-test's points check starts failing, grab a fresh one.

## Configuration

`config.json` keys (see `config.example.json` for a full example):

| Key | Meaning |
| --- | --- |
| `Language` | `en` (default) or `de` |
| `Debug` | verbose logging |
| `WebDashboard.enabled` / `.port` | Flask dashboard (phase 3) |
| `Discord` | webhook notifications (phase 4) |
| `Telegram` | control bot (phase 4) |
| `Proxy.enabled` / `.url` | global proxy (`socks5://`, `http://`) |
| `Accounts[]` | one entry per Kick account |
| `Accounts[].streamers` | ordered list – **position = priority**, index 0 highest |
| `Accounts[].max_concurrent` | how many streamers to watch at once |
| `Check_interval` | seconds between online checks |
| `Reconnect_cooldown` | seconds before a reconnect attempt |
| `Connection_stagger_min/max` | delay range between opening connections |

The old single-account layout (`Private.token` / `Streamers` /
`Max_active_channels`) is still accepted and auto-migrated.

## Run

```bash
python main.py
```

Or with Docker:

```bash
docker compose up -d --build
```

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## Credits

* [Baillora/Kick_Channel_Points_Miner](https://github.com/Baillora/Kick_Channel_Points_Miner)
  (MIT) – Kick API endpoints, Cloudflare-bypass approach, viewer WebSocket protocol.
* [zarmstrong/Twitch-Channel-Points-Miner-v3](https://github.com/zarmstrong/Twitch-Channel-Points-Miner-v3)
  (GPL-3.0) – conceptual template for architecture and feature scope. No source code was taken.

## License

MIT – see [LICENSE](LICENSE).
