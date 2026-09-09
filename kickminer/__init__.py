"""Kick Channel Points Miner - a pure Kick point-farming bot.

Split into clearly separated layers:

* ``http_client``  - one Cloudflare-capable HTTP session (curl_cffi)
* ``kick_api``     - Kick's REST endpoints (channel, livestream, points, WS token)
* ``viewer_ws``    - viewer WebSocket that keeps the "watching" state (phase 2)
* ``entities``     - dataclasses for account / streamer state
* ``account_worker`` / ``manager`` - orchestration of multiple accounts
* ``analytics``    - points history in SQLite
* ``notifiers``    - Discord webhook, Telegram bot
* ``web``          - Flask dashboard
"""

__version__ = "0.1.0"
