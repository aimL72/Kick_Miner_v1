"""Top-level orchestration across all configured accounts."""

from __future__ import annotations

import asyncio
import random

from loguru import logger

from .account_worker import AccountWorker
from .config import Config

_ACCOUNT_START_GAP = (5.0, 15.0)


class AccountManager:
    def __init__(
        self,
        config: Config,
        *,
        on_points_gain=None,
        on_status_change=None,
        analytics=None,
        discord=None,
        telegram=None,
    ):
        self.config = config
        self.analytics = analytics
        self.workers: list[AccountWorker] = [
            AccountWorker(
                acc,
                check_interval=config.check_interval,
                reconnect_cooldown=config.reconnect_cooldown,
                stagger_min=config.stagger_min,
                stagger_max=config.stagger_max,
                cycle_enabled=config.cycle_enabled,
                cycle_interval_minutes=config.cycle_interval_minutes,
                no_points_grace_minutes=config.no_points_grace_minutes,
                on_points_gain=on_points_gain,
                on_status_change=on_status_change,
                analytics=analytics,
                discord=discord,
                telegram=telegram,
            )
            for acc in config.accounts
        ]
        self._tasks: list[asyncio.Task] = []

    async def run(self) -> None:
        for i, worker in enumerate(self.workers):
            if i > 0:
                delay = random.uniform(*_ACCOUNT_START_GAP)
                logger.info(f"staggering {delay:.0f}s before account [{worker.cfg.alias}]")
                await asyncio.sleep(delay)
            self._tasks.append(
                asyncio.create_task(worker.run(), name=f"account:{worker.cfg.alias}")
            )
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*(w.stop() for w in self.workers), return_exceptions=True)
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #

    def snapshot(self) -> list[dict]:
        return [w.snapshot() for w in self.workers]

    def unique_streamers(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for w in self.workers:
            for name in w.state.order:
                if name not in seen:
                    seen.add(name)
                    out.append(name)
        return out
