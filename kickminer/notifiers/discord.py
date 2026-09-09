"""Discord webhook notifier.

Message *text* follows the Twitch Channel Points Miner wording (an emoji plus
the ``Streamer(username=…, channel_id=…, channel_points=…)`` repr); Discord
wraps it in an embed so it gets the coloured left border:

    ┃ 🚀  +10 → Streamer(username=die_schlager_camper, channel_id=9623471, channel_points=10) - Reason: WATCH.   (green)
    ┃ 🥳  Streamer(username=gaules, channel_id=668, channel_points=1.24M) is Online!                              (green)
    ┃ 😴  Streamer(username=gaules, channel_id=668, channel_points=9.4k) is Offline!                              (grey)
    ┃ 🎁  Claiming the bonus for Streamer(username=gaules, channel_id=668, channel_points=10)!                    (green)
    ┃ 🟢  Kick Channel Points Miner started - 2 account(s), 5 streamers.                                          (green)
    ┃ 🔴  Kick Channel Points Miner stopped - user stopped.                                                       (red)

(Telegram uses its own shorter two-line wording - see notifiers/telegram.py.)

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

from .base import EMOJI, streamer_repr

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


def _sr(snap: dict, points=None) -> str:
    pts = snap.get("points") if points is None else points
    return streamer_repr(snap.get("name"), snap.get("channel_id"), pts)


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
        if not self._on("notify_startup"):
            return
        total = len({s for a in accounts for s in a.get("streamer_order", [])})
        self._enqueue(
            f"{EMOJI['start']}  Kick Channel Points Miner started - "
            f"{len(accounts)} account(s), {total} streamers.",
            "start",
        )

    def shutdown(self, reason: str) -> None:
        if self.enabled:
            self._enqueue(
                f"{EMOJI['stop']}  Kick Channel Points Miner stopped - {reason}.",
                "stop",
            )

    def points_gain(self, alias: str, snap: dict, old: int, new: int) -> None:
        if not self._on("notify_points"):
            return
        gain = new - old
        if gain < max(1, self.cfg.min_points_gain):
            return
        self._enqueue(
            f"{EMOJI['gain']}  +{gain} → {_sr(snap, new)} - Reason: WATCH.", "gain"
        )

    def bonus_claim(self, alias: str, snap: dict) -> None:
        if self._on("notify_points"):
            self._enqueue(
                f"{EMOJI['claim']}  Claiming the bonus for {_sr(snap)}!", "claim"
            )

    def status_change(self, alias: str, snap: dict, action: str) -> None:
        if not (self._on("notify_status_change") and action in ("online", "offline")):
            return
        word = "Online" if action == "online" else "Offline"
        self._enqueue(f"{EMOJI[action]}  {_sr(snap)} is {word}!", action)

    def error(self, alias: str, streamer: str, message: str) -> None:
        if not self._on("notify_errors"):
            return
        target = f"{alias}/{streamer}" if streamer else alias
        self._enqueue(
            f"{EMOJI['error']}  Error on {target}: {str(message)[:400]}", "error"
        )

    def token_expired(self, alias: str) -> None:
        if not self._on("notify_errors"):
            return
        self._enqueue(
            f"{EMOJI['error']}  Account {alias}: Kick token is invalid or expired "
            "- update it in the dashboard Config tab.",
            "error",
        )

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
