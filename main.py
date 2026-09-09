"""Entry point for the Kick Channel Points Miner.

Loads config, starts the multi-account mining supervisor plus the optional
dashboard / Discord / Telegram integrations, and restarts the supervisor on
unexpected crashes. Ctrl+C stops cleanly; Telegram /restart cycles it.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import threading
import time

from loguru import logger

from kickminer.analytics import Analytics
from kickminer.config import ConfigError, load_config
from kickminer.i18n import load_language, t
from kickminer.logging_setup import setup_logging
from kickminer.manager import AccountManager
from kickminer.notifiers import DiscordNotifier, TelegramBot

_RESTART_DELAY = 5


class _RestartRequested(Exception):
    """Raised inside the supervisor when a restart was asked for on purpose."""


def _make_callbacks(discord: DiscordNotifier, telegram: TelegramBot):
    def on_points_gain(alias: str, streamer: str, old: int, new: int) -> None:
        discord.points_gain(alias, streamer, old, new)
        if telegram.enabled:
            asyncio.create_task(telegram.notify_points(alias, streamer, old, new))

    def on_status_change(alias: str, streamer: str, priority: int, action: str) -> None:
        discord.status_change(alias, streamer, priority, action)
        if telegram.enabled and action in {"online", "offline"}:
            asyncio.create_task(telegram.notify_status(alias, streamer, action))

    return on_points_gain, on_status_change


async def _run_once(
    cfg,
    analytics: Analytics,
    discord: DiscordNotifier,
    telegram: TelegramBot,
    restart_flag: threading.Event,
) -> None:
    on_points_gain, on_status_change = _make_callbacks(discord, telegram)
    manager = AccountManager(
        cfg,
        analytics=analytics,
        on_points_gain=on_points_gain,
        on_status_change=on_status_change,
    )
    telegram.bind(manager)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass  # Windows / non-main thread - KeyboardInterrupt handles it

    if cfg.web.enabled:
        try:
            from kickminer.web import start_dashboard

            start_dashboard(manager, analytics, cfg.web.port)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Web dashboard failed to start: {exc}")

    await telegram.start()
    discord.startup(
        [
            {
                "alias": a.alias,
                "proxy": a.proxy,
                "max_concurrent": a.max_concurrent,
                "streamer_order": a.streamers,
            }
            for a in cfg.accounts
        ]
    )

    async def _wait_restart() -> str:
        while not restart_flag.is_set():
            await asyncio.sleep(1)
        return "restart"

    run_task = asyncio.create_task(manager.run(), name="manager")
    stop_task = asyncio.create_task(stop.wait(), name="stop")
    restart_task = asyncio.create_task(_wait_restart(), name="restart")

    try:
        await asyncio.wait(
            {run_task, stop_task, restart_task}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        for task in (stop_task, restart_task):
            task.cancel()
        await manager.stop()
        await telegram.stop()
        if not run_task.done():
            run_task.cancel()
        try:
            await run_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    if restart_flag.is_set():
        restart_flag.clear()
        raise _RestartRequested
    if stop.is_set():
        raise KeyboardInterrupt


def main() -> int:
    setup_logging(debug=False)
    try:
        cfg = load_config("config.json")
    except ConfigError as exc:
        logger.error(str(exc))
        return 2

    setup_logging(debug=cfg.debug)
    logger.info(t("language_set", lang=load_language(cfg.language)))
    logger.info(t("app_starting"))

    restart_flag = threading.Event()
    analytics = Analytics()
    discord = DiscordNotifier(cfg.discord)
    telegram = TelegramBot(cfg.telegram, request_restart=restart_flag.set)

    try:
        while True:
            try:
                asyncio.run(
                    _run_once(cfg, analytics, discord, telegram, restart_flag)
                )
            except _RestartRequested:
                logger.warning(
                    t("app_restarting", seconds=1, reason="telegram /restart")
                )
                time.sleep(1)
                continue
            except KeyboardInterrupt:
                logger.info(t("app_stopped_by_user"))
                discord.shutdown("user stopped")
                return 0
            except Exception as exc:  # noqa: BLE001
                logger.exception(t("app_fatal", error=str(exc)))
                discord.error("system", "", str(exc))

            logger.warning(
                t("app_restarting", seconds=_RESTART_DELAY, reason="crash")
            )
            try:
                time.sleep(_RESTART_DELAY)
            except KeyboardInterrupt:
                return 0
    finally:
        discord.close()
        analytics.close()


if __name__ == "__main__":
    sys.exit(main())
