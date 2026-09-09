"""Discord webhook notifier.

The message *text* is the same two-line wording the Telegram bot uses (one
shared vocabulary in ``notifiers.base``); Discord wraps it in an embed so it
gets the coloured left border:

    ┃ Account aimL72
    ┃ 🥳 gaules is online          (green)
    ┃ Account aimL72
    ┃ 😴 gaules is offline         (grey)
    ┃ Account aimL72
    ┃ 🚀 gaules +12 → 3,412 Points (green)
    ┃ 🔴 Kick Miner stopped — user stopped   (red)

Sends run on a daemon queue-thread so the async mining loop never blocks;
1 request/second self-limit with a single retry on HTTP 429.
"""

from __future__ import annotations

import json
import queue
import threading
import time

from curl_cffi import requests
from loguru import logger

from . import base

_DEFAULT_USERNAME = "Kick Channel Points Miner"

_GREEN, _GREY, _RED, _BLUE = 0x53FC18, 0x8B8FA3, 0xF04747, 0x5865F2
_COLOR = {
    "online": _GREEN,
    "gain": _GREEN,
    "start": _GREEN,
    "claim": _GREEN,
    "offline": _GREY,
    "stop": _RED,
    "error": _RED,
    "info": _BLUE,
}


class DiscordNotifier:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.enabled = bool(cfg.enabled and cfg.webhook_url)
        self.username = cfg.username or _DEFAULT_USERNAME
        self._q: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._last_send = 0.0
        if self.enabled:
            self._worker = threading.Thread(
                target=self._run, name="discord", daemon=True
            )
            self._worker.start()
            logger.info("Discord webhook enabled.")

    # ------------------------------------------------------------------ #
    # public API - called from the async loop, never blocks

    def startup(self, accounts: list[dict]) -> None:
        if self._on("notify_startup"):
            self._enqueue(base.msg_startup(accounts), "start")

    def shutdown(self, reason: str) -> None:
        if self.enabled:
            self._enqueue(base.msg_shutdown(reason), "stop")

    def points_gain(self, alias: str, snap: dict, old: int, new: int) -> None:
        if not self._on("notify_points"):
            return
        if new - old < max(1, self.cfg.min_points_gain):
            return
        self._enqueue(base.msg_points(alias, snap, old, new), "gain")

    def bonus_claim(self, alias: str, snap: dict) -> None:
        if self._on("notify_points"):
            self._enqueue(base.msg_claim(alias, snap), "claim")

    def status_change(self, alias: str, snap: dict, action: str) -> None:
        if self._on("notify_status_change") and action in ("online", "offline"):
            self._enqueue(base.msg_status(alias, snap, action), action)

    def error(self, alias: str, streamer: str, message: str) -> None:
        if self._on("notify_errors"):
            self._enqueue(base.msg_error(alias, streamer, message), "error")

    def token_expired(self, alias: str) -> None:
        if self._on("notify_errors"):
            self._enqueue(base.msg_token_expired(alias), "error")

    def close(self) -> None:
        if self._worker is not None:
            self._q.put(None)
            self._worker.join(timeout=5)

    # ------------------------------------------------------------------ #

    def _on(self, flag: str) -> bool:
        return self.enabled and bool(getattr(self.cfg, flag, True))

    def _enqueue(self, message: str, kind: str = "info") -> None:
        self._q.put((message, kind))

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            self._send(*item)

    def _payload(self, message: str, kind: str) -> dict:
        payload: dict = {
            "username": self.username,
            "embeds": [{"description": message, "color": _COLOR.get(kind, _BLUE)}],
        }
        if self.cfg.avatar_url:
            payload["avatar_url"] = self.cfg.avatar_url
        return payload

    def _send(self, message: str, kind: str) -> None:
        gap = time.time() - self._last_send
        if gap < 1.0:
            time.sleep(1.0 - gap)
        body = json.dumps(self._payload(message, kind))
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(
                self.cfg.webhook_url, data=body, headers=headers, timeout=10
            )
            self._last_send = time.time()
            if resp.status_code == 429:
                retry = 3.0
                try:
                    retry = float(resp.json().get("retry_after", 3))
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(min(retry, 15))
                requests.post(
                    self.cfg.webhook_url, data=body, headers=headers, timeout=10
                )
            elif resp.status_code >= 300:
                logger.debug(f"Discord webhook HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Discord webhook error: {exc}")
