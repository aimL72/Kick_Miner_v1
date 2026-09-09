"""Discord webhook notifier.

Message format matches the Twitch Channel Points Miner: a plain ``content``
string wrapped in backticks (a single pair for one-liners, a triple-backtick
fence for multi-line), posted with a configurable ``username`` / ``avatar_url``.
No embeds. The event wording mirrors the Twitch miner's log lines:

    +10 -> gaules (230 points) - Reason: WATCH.
    gaules (230 points) is Online!
    gaules (230 points) is Offline!

Sends run on a daemon queue-thread so the async mining loop never blocks;
1 request/second self-limit with a single retry on HTTP 429.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from textwrap import dedent

from curl_cffi import requests
from loguru import logger

from ..utils import millify

_DEFAULT_USERNAME = "Kick Channel Points Miner"


def _fence(message: str) -> str:
    """Replicate the Twitch miner's backtick-fencing of the webhook content."""

    message = dedent(message).strip()
    max_run = run = 0
    for ch in message:
        run = run + 1 if ch == "`" else 0
        max_run = max(max_run, run)

    if "\n" in message:
        fence = "`" * max(3, max_run + 1)
        return f"{fence}\n{message}\n{fence}"
    if max_run:
        fence = "`" * (max_run + 1)
        return f"{fence} {message} {fence}"
    return f"`{message}`"


class DiscordNotifier:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.enabled = bool(cfg.enabled and cfg.webhook_url)
        self.username = cfg.username or _DEFAULT_USERNAME
        self._q: queue.Queue[str | None] = queue.Queue()
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
            f"Kick Channel Points Miner started - "
            f"{len(accounts)} account(s), {total} streamers."
        )

    def shutdown(self, reason: str) -> None:
        if self.enabled:
            self._enqueue(f"Kick Channel Points Miner stopped - {reason}.")

    def points_gain(self, alias: str, streamer: str, old: int, new: int) -> None:
        if not self._on("notify_points"):
            return
        gain = new - old
        if gain < max(1, self.cfg.min_points_gain):
            return
        self._enqueue(
            f"+{gain} -> {streamer} ({millify(new)} points) - Reason: WATCH."
        )

    def status_change(self, alias: str, streamer: str, priority: int, action: str) -> None:
        if not self._on("notify_status_change"):
            return
        if action == "online":
            self._enqueue(f"{streamer} is Online!")
        elif action == "offline":
            self._enqueue(f"{streamer} is Offline!")

    def error(self, alias: str, streamer: str, message: str) -> None:
        if not self._on("notify_errors"):
            return
        target = f"{alias}/{streamer}" if streamer else alias
        self._enqueue(f"Error on {target}: {str(message)[:400]}")

    def close(self) -> None:
        if self._worker is not None:
            self._q.put(None)
            self._worker.join(timeout=5)

    # ------------------------------------------------------------------ #

    def _on(self, flag: str) -> bool:
        return self.enabled and bool(getattr(self.cfg, flag, True))

    def _enqueue(self, message: str) -> None:
        self._q.put(_fence(message))

    def _run(self) -> None:
        while True:
            content = self._q.get()
            if content is None:
                return
            self._send(content)

    def _payload(self, content: str) -> dict:
        payload: dict[str, str] = {"content": content, "username": self.username}
        if self.cfg.avatar_url:
            payload["avatar_url"] = self.cfg.avatar_url
        return payload

    def _send(self, content: str) -> None:
        gap = time.time() - self._last_send
        if gap < 1.0:
            time.sleep(1.0 - gap)
        body = json.dumps(self._payload(content))
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
