"""Per-account orchestration: online checks, priority rebalance, watch sessions.

One :class:`AccountWorker` owns one Kick token, its own HTTP client (so proxy
and auth are isolated) and N possible :class:`ViewerWebSocket` sessions, capped
at ``max_concurrent``.

The HTTP layer (curl_cffi) is synchronous; every call is pushed to a worker
thread via :func:`asyncio.to_thread` so the event loop keeps running.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from loguru import logger

from .config import AccountConfig
from .entities import AccountState, StreamerState
from .http_client import KickHttpClient
from .i18n import t
from .kick_api import KickApi
from .viewer_ws import ViewerWebSocket

_POINTS_POLL_EVERY = (120.0, 180.0)
_ONLINE_CHECK_GAP = (1.0, 2.5)  # between per-streamer checks within one sweep


def select_active(order: list[str], online: set[str], max_concurrent: int) -> list[str]:
    """The streamers that *should* be watched right now, highest priority first.

    ``order`` is the configured list (index = priority); a streamer is eligible
    only if it is in ``online``. At most ``max_concurrent`` are returned.
    """

    eligible = [name for name in order if name in online]
    return eligible[: max(0, max_concurrent)]


class AccountWorker:
    def __init__(
        self,
        cfg: AccountConfig,
        *,
        check_interval: float = 120.0,
        stagger_min: float = 3.0,
        stagger_max: float = 8.0,
        on_points_gain=None,
        on_status_change=None,
        analytics=None,
        discord=None,
    ) -> None:
        self.cfg = cfg
        self.check_interval = check_interval
        self.stagger_min = stagger_min
        self.stagger_max = stagger_max
        self._on_points_gain = on_points_gain
        self._on_status_change = on_status_change
        self._analytics = analytics
        self._discord = discord
        self._token_check_counter = 0

        self.state = AccountState(
            alias=cfg.alias,
            proxy=cfg.proxy,
            max_concurrent=cfg.max_concurrent,
            order=list(cfg.streamers),
        )
        for idx, name in enumerate(cfg.streamers):
            self.state.streamers[name] = StreamerState(name=name, priority=idx)

        self._http = KickHttpClient(proxy=cfg.proxy, auth_token=cfg.token)
        self._api = KickApi(self._http)
        self._ws: dict[str, ViewerWebSocket] = {}
        self._running = False
        self._stopped = False
        self._rebalance_lock = asyncio.Lock()

    # ------------------------------------------------------------------ #

    async def run(self) -> None:
        self._running = True
        logger.info(
            t(
                "worker_start",
                alias=self.cfg.alias,
                streamers=len(self.state.streamers),
                limit=self.cfg.max_concurrent,
                proxy=t("yes") if self.cfg.proxy else t("no"),
            )
        )
        try:
            await self._check_token()
            await self._check_all_online()
            await self._rebalance()
            while self._running:
                await asyncio.sleep(
                    random.uniform(
                        self.check_interval * 0.8, self.check_interval * 1.2
                    )
                )
                self._token_check_counter += 1
                if self._token_check_counter >= 5:  # ~ every 5 online sweeps
                    self._token_check_counter = 0
                    await self._check_token()
                await self._check_all_online()
                await self._rebalance()
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"[{self.cfg.alias}] worker crashed: {exc}")
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._running = False
        for name in list(self._ws):
            await self._stop_watching(name, reason="shutdown")
        await asyncio.to_thread(self._http.close)
        logger.info(t("worker_stopped", alias=self.cfg.alias))

    # ------------------------------------------------------------------ #

    async def _check_all_online(self) -> None:
        for name in self.state.order:
            if not self._running:
                return
            st = self.state.streamers[name]
            try:
                channel = await asyncio.to_thread(self._api.get_channel, name)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{self.cfg.alias}] online check {name}: {exc}")
                continue
            if channel is None:
                continue

            st.channel_id = channel.channel_id
            st.user_id = channel.user_id
            was_online = st.is_online
            st.is_online = channel.is_live
            st.stream_id = channel.stream_id

            if channel.is_live and not was_online:
                logger.info(t("streamer_online", alias=self.cfg.alias, streamer=name))
                self._emit_status(name, "online")
            elif not channel.is_live and was_online:
                logger.info(t("streamer_offline", alias=self.cfg.alias, streamer=name))
                self._emit_status(name, "offline")

            await asyncio.sleep(random.uniform(*_ONLINE_CHECK_GAP))

    async def _rebalance(self) -> None:
        async with self._rebalance_lock:
            online = {n for n in self.state.order if self.state.streamers[n].is_online}
            desired = set(
                select_active(self.state.order, online, self.cfg.max_concurrent)
            )
            current = set(self._ws)

            for name in current - desired:
                reason = (
                    t("streamer_went_offline")
                    if not self.state.streamers[name].is_online
                    else t("streamer_displaced")
                )
                await self._stop_watching(name, reason=reason)
                if reason == t("streamer_displaced"):
                    self._emit_status(name, "displaced")

            for name in desired - current:
                await self._start_watching(name)
                self._emit_status(name, "watching")
                await asyncio.sleep(
                    random.uniform(self.stagger_min, self.stagger_max)
                )

            if desired:
                logger.debug(
                    f"[{self.cfg.alias}] watching {sorted(desired)} "
                    f"({len(desired)}/{self.cfg.max_concurrent})"
                )

    # ------------------------------------------------------------------ #

    async def _start_watching(self, name: str) -> None:
        st = self.state.streamers[name]
        try:
            if not st.channel_id or not st.user_id:
                channel = await asyncio.to_thread(self._api.get_channel, name)
                if channel is None:
                    raise RuntimeError("channel lookup failed")
                st.channel_id, st.user_id = channel.channel_id, channel.user_id
                st.stream_id = channel.stream_id

            ws_token = await asyncio.to_thread(
                self._api.get_viewer_ws_token, name, st.channel_id, st.user_id
            )
            if not ws_token:
                raise RuntimeError("no viewer WS token")

            balance = await asyncio.to_thread(self._api.get_points, name)
            if balance is not None:
                st.points = balance
                self._record_points(name, balance)
            st.points_start = st.points

            async def _on_closed(streamer: str = name) -> None:
                self.state.streamers[streamer].is_watching = False

            ws = ViewerWebSocket(
                ws_token=ws_token,
                channel_id=st.channel_id,
                stream_id=st.stream_id or 0,
                label=f"{self.cfg.alias}/{name}",
                proxy=self.cfg.proxy,
                on_closed=_on_closed,
            )
            self._ws[name] = ws
            st.is_watching = True
            st.error_count = 0
            st.ws_task = asyncio.create_task(ws.run(), name=f"ws:{name}")
            st.points_task = asyncio.create_task(
                self._points_loop(name), name=f"points:{name}"
            )
            logger.info(
                t(
                    "streamer_watch_start",
                    alias=self.cfg.alias,
                    streamer=name,
                    priority=st.priority,
                )
            )
        except Exception as exc:  # noqa: BLE001
            st.is_watching = False
            st.error_count += 1
            st.last_error = str(exc)
            self._ws.pop(name, None)
            logger.error(f"[{self.cfg.alias}] start {name} failed: {exc}")

    async def _stop_watching(self, name: str, *, reason: str) -> None:
        st = self.state.streamers[name]
        ws = self._ws.pop(name, None)
        logger.info(
            t("streamer_watch_stop", alias=self.cfg.alias, streamer=name, reason=reason)
        )
        for task in (st.ws_task, st.points_task):
            if task is not None and not task.done():
                task.cancel()
        if ws is not None:
            try:
                await ws.stop()
            except Exception:  # noqa: BLE001
                pass
        for task in (st.ws_task, st.points_task):
            if task is not None:
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        st.ws_task = st.points_task = None
        st.is_watching = False

    async def _points_loop(self, name: str) -> None:
        st = self.state.streamers[name]
        try:
            while self._running and st.is_watching:
                await asyncio.sleep(random.uniform(*_POINTS_POLL_EVERY))
                if not st.is_watching:
                    break
                amount = await asyncio.to_thread(self._api.get_points, name)
                if amount is None:
                    continue
                old = st.points
                st.points = amount
                st.last_points_update = datetime.now(timezone.utc)
                self._record_points(name, amount)
                if amount > old:
                    gain = amount - old
                    logger.success(
                        t(
                            "points_gain",
                            alias=self.cfg.alias,
                            streamer=name,
                            gain=gain,
                            total=amount,
                        )
                    )
                    if self._on_points_gain is not None:
                        self._on_points_gain(self.cfg.alias, st.snapshot(), old, amount)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{self.cfg.alias}] points loop {name}: {exc}")

    # ------------------------------------------------------------------ #

    async def _check_token(self) -> None:
        try:
            ident = await asyncio.to_thread(self._api.token_identity)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[{self.cfg.alias}] token check failed: {exc}")
            return
        was = self.state.token_valid
        self.state.token_valid = ident.valid
        self.state.token_username = ident.username
        self.state.token_checked_at = datetime.now(timezone.utc)

        if ident.valid and was is not True:
            logger.info(
                f"[{self.cfg.alias}] Kick token OK (user: {ident.username})."
            )
        elif not ident.valid and was is not False:
            logger.error(
                f"[{self.cfg.alias}] Kick token is invalid or expired - "
                f"update it in the dashboard Config tab."
            )
            if self._discord is not None:
                self._discord.token_expired(self.cfg.alias)

    def _record_points(self, name: str, balance: int) -> None:
        if self._analytics is not None:
            self._analytics.record(self.cfg.alias, name, balance)

    def _emit_status(self, name: str, action: str) -> None:
        if self._on_status_change is not None:
            self._on_status_change(
                self.cfg.alias, self.state.streamers[name].snapshot(), action
            )

    def snapshot(self) -> dict:
        return self.state.snapshot()
