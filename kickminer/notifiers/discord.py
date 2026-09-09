"""Discord webhook notifier.

Fire-and-forget: every send runs on a tiny single-thread pool so the async
mining loop never blocks on Discord. Honors a 1 req/s self-imposed rate limit
and retries once on HTTP 429.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime, timezone

from curl_cffi import requests
from loguru import logger

_COLOR = {
    "success": 0x34D168,
    "info": 0x5865F2,
    "warning": 0xFAA61A,
    "error": 0xF04747,
}


class DiscordNotifier:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.enabled = bool(cfg.enabled and cfg.webhook_url)
        self._q: queue.Queue[dict | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._last_send = 0.0
        if self.enabled:
            self._worker = threading.Thread(
                target=self._run, name="discord", daemon=True
            )
            self._worker.start()
            logger.info("Discord webhook enabled.")

    # ------------------------------------------------------------------ #
    # public API (called from the async loop – never blocks)

    def startup(self, accounts: list[dict]) -> None:
        if not self._on("notify_startup"):
            return
        fields = []
        for a in accounts:
            names = a.get("streamer_order", [])
            preview = ", ".join(names[:6]) + (f" +{len(names) - 6}" if len(names) > 6 else "")
            fields.append(
                {
                    "name": f"👤 {a.get('alias')}",
                    "value": f"{'proxy' if a.get('proxy') else 'direct'} · "
                    f"limit {a.get('max_concurrent')}\n`{preview or '-'}`",
                    "inline": False,
                }
            )
        self._enqueue(
            "🚀 KickMiner started",
            f"**{len(accounts)}** account(s) loaded",
            "success",
            fields=fields,
        )

    def shutdown(self, reason: str) -> None:
        if not self.enabled:
            return
        self._enqueue("⏹ KickMiner stopping", f"Reason: {reason}", "warning")

    def points_gain(self, alias: str, streamer: str, old: int, new: int) -> None:
        if not self._on("notify_points"):
            return
        gain = new - old
        if gain < max(1, self.cfg.min_points_gain):
            return
        self._enqueue(
            "💰 Points earned",
            None,
            "success",
            url=f"https://kick.com/{streamer}",
            fields=[
                {"name": "Streamer", "value": streamer, "inline": True},
                {"name": "Gained", "value": f"+{gain:,}", "inline": True},
                {"name": "Total", "value": f"{new:,}", "inline": True},
                {"name": "Account", "value": alias, "inline": True},
            ],
        )

    def status_change(self, alias: str, streamer: str, priority: int, action: str) -> None:
        if not self._on("notify_status_change"):
            return
        titles = {
            "online": ("🟢 Streamer online", "info"),
            "offline": ("🔴 Streamer offline", "warning"),
            "watching": ("▶️ Now watching", "success"),
            "displaced": ("⏸ Displaced by higher priority", "warning"),
        }
        title, color = titles.get(action, (f"📡 {action}", "info"))
        self._enqueue(
            title,
            f"[{streamer}](https://kick.com/{streamer})",
            color,
            fields=[
                {"name": "Account", "value": alias, "inline": True},
                {"name": "Priority", "value": f"#{priority}", "inline": True},
            ],
        )

    def error(self, alias: str, streamer: str, message: str) -> None:
        if not self._on("notify_errors"):
            return
        self._enqueue(
            "❌ Error",
            f"```\n{str(message)[:400]}\n```",
            "error",
            fields=[
                {"name": "Account", "value": alias, "inline": True},
                {"name": "Streamer", "value": streamer or "-", "inline": True},
            ],
        )

    def close(self) -> None:
        if self._worker is not None:
            self._q.put(None)
            self._worker.join(timeout=5)

    # ------------------------------------------------------------------ #

    def _on(self, flag: str) -> bool:
        return self.enabled and bool(getattr(self.cfg, flag, True))

    def _enqueue(self, title, description, color, *, url=None, fields=None) -> None:
        embed = {
            "title": title,
            "color": _COLOR.get(color, _COLOR["info"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if description:
            embed["description"] = description
        if url:
            embed["url"] = url
        if fields:
            embed["fields"] = fields
        payload = {"embeds": [embed]}
        if self.cfg.username:
            payload["username"] = self.cfg.username
        if self.cfg.avatar_url:
            payload["avatar_url"] = self.cfg.avatar_url
        self._q.put(payload)

    def _run(self) -> None:
        while True:
            payload = self._q.get()
            if payload is None:
                return
            self._send(payload)

    def _send(self, payload: dict) -> None:
        gap = time.time() - self._last_send
        if gap < 1.0:
            time.sleep(1.0 - gap)
        try:
            resp = requests.post(
                self.cfg.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10,
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
                    self.cfg.webhook_url,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
            elif resp.status_code >= 300:
                logger.debug(f"Discord webhook HTTP {resp.status_code}")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Discord webhook error: {exc}")
