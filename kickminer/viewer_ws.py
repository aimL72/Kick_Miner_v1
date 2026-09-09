"""Viewer WebSocket - the thing that actually earns points.

Kick accrues channel points server-side while a viewer session is "watching".
That session is a WebSocket to ``websockets.kick.com`` on which the client
periodically emits ``tracking.user.watch.livestream`` events. No official docs
exist; the protocol below is what the web player does.

Verified against live Kick (2026-09): the upgrade request must carry an
``Origin: https://kick.com`` header or ``ws_connect`` hangs.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable

from curl_cffi.requests import AsyncSession
from loguru import logger

from .i18n import t

WS_CONNECT_URL = "wss://websockets.kick.com/viewer/v1/connect"

_WATCH_EVENT_EVERY = (9.5, 12.5)      # seconds between watch pings
_KEEPALIVE_EVERY = (25.0, 35.0)      # seconds between handshake + ping
_MAX_RECONNECTS = 6
_CONNECT_TIMEOUT = 25.0


class ViewerWebSocket:
    def __init__(
        self,
        *,
        ws_token: str,
        channel_id: int,
        stream_id: int,
        label: str = "",
        proxy: str | None = None,
        impersonate: str = "chrome124",
        on_closed: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.ws_token = ws_token
        self.channel_id = int(channel_id)
        self.stream_id = int(stream_id or 0)
        self.label = label or str(channel_id)
        self.proxy = proxy
        self.impersonate = impersonate
        self.on_closed = on_closed

        self._running = False
        self._connected = False
        self._reconnects = 0
        self._session: AsyncSession | None = None
        self._ws = None
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        """Connect and keep the watch session alive until stopped or given up."""

        self._running = True
        try:
            while self._running:
                ok = await self._connect_once()
                if not ok:
                    if not await self._backoff():
                        break
                    continue

                self._reconnects = 0
                await self._serve()  # returns when the connection drops

                if not self._running:
                    break
                if not await self._backoff():
                    break
        finally:
            await self._teardown()
            if self.on_closed is not None:
                await self.on_closed()

    async def stop(self) -> None:
        self._running = False
        await self._teardown()

    # ------------------------------------------------------------------ #

    async def _connect_once(self) -> bool:
        headers = {
            "Origin": "https://kick.com",
            "Referer": "https://kick.com/",
        }
        url = f"{WS_CONNECT_URL}?token={self.ws_token}"
        try:
            self._session = AsyncSession(
                impersonate=self.impersonate,
                proxy=self.proxy,
            )
            logger.debug(t("ws_connecting", channel_id=self.channel_id))
            self._ws = await asyncio.wait_for(
                self._session.ws_connect(url, headers=headers),
                timeout=_CONNECT_TIMEOUT,
            )
            self._connected = True
            logger.info(t("ws_connected") + f" [{self.label}]")
            await self._send_handshake()
            await self._send(json.dumps({"type": "ping"}))
            await self._send_watch_event()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(t("ws_error", error=f"{type(exc).__name__}: {exc}"))
            await self._teardown()
            return False

    async def _serve(self) -> None:
        self._tasks = [
            asyncio.create_task(self._watch_loop(), name=f"watch:{self.label}"),
            asyncio.create_task(self._keepalive_loop(), name=f"ka:{self.label}"),
        ]
        try:
            await self._read_loop()
        finally:
            for task in self._tasks:
                task.cancel()
            for task in self._tasks:
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            self._tasks = []
            self._connected = False

    async def _read_loop(self) -> None:
        assert self._ws is not None
        while self._running and self._connected:
            try:
                raw = await self._ws.recv()
            except Exception as exc:  # noqa: BLE001 - normal on disconnect
                logger.debug(t("ws_disconnected") + f" [{self.label}] ({exc})")
                return
            await self._handle(raw)

    async def _handle(self, raw: object) -> None:
        if isinstance(raw, tuple):
            raw = raw[0]
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "ignore")
        if not isinstance(raw, str) or not raw.strip():
            return
        if raw.strip() == "ping":
            await self._send("pong")
            return
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        mtype = msg.get("type")
        if mtype == "ping":
            await self._send(json.dumps({"type": "pong"}))
        elif mtype == "error":
            err = msg.get("data", {})
            err = err.get("message") if isinstance(err, dict) else err
            logger.warning(t("ws_error", error=err) + f" [{self.label}]")

    # ------------------------------------------------------------------ #

    async def _watch_loop(self) -> None:
        while self._running and self._connected:
            await asyncio.sleep(random.uniform(*_WATCH_EVENT_EVERY))
            await self._send_watch_event()

    async def _keepalive_loop(self) -> None:
        while self._running and self._connected:
            await asyncio.sleep(random.uniform(*_KEEPALIVE_EVERY))
            await self._send_handshake()
            await self._send(json.dumps({"type": "ping"}))

    async def _send_handshake(self) -> None:
        await self._send(
            json.dumps(
                {
                    "type": "channel_handshake",
                    "data": {"message": {"channelId": self.channel_id}},
                }
            )
        )

    async def _send_watch_event(self) -> None:
        await self._send(
            json.dumps(
                {
                    "type": "user_event",
                    "data": {
                        "message": {
                            "name": "tracking.user.watch.livestream",
                            "channel_id": self.channel_id,
                            "livestream_id": self.stream_id,
                        }
                    },
                }
            )
        )

    async def _send(self, payload: str) -> None:
        if not self._connected or self._ws is None:
            return
        try:
            await self._ws.send_str(payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug(t("ws_error", error=str(exc)) + f" [{self.label}]")
            self._connected = False

    # ------------------------------------------------------------------ #

    async def _backoff(self) -> bool:
        """Sleep before the next reconnect. Returns False once we give up."""

        self._reconnects += 1
        if self._reconnects > _MAX_RECONNECTS:
            logger.error(t("ws_reconnect_giveup", streamer=self.label))
            return False
        delay = min(5 * (2 ** (self._reconnects - 1)), 120)
        logger.info(
            t(
                "ws_reconnect",
                attempt=self._reconnects,
                max=_MAX_RECONNECTS,
                delay=delay,
            )
            + f" [{self.label}]"
        )
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return False
        return self._running

    async def _teardown(self) -> None:
        self._connected = False
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:  # noqa: BLE001
                pass
            self._session = None
