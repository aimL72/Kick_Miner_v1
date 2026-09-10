"""Entry point for the Kick Channel Points Miner.

Loads config, starts the multi-account mining supervisor plus the optional
dashboard / Discord / Telegram integrations, and restarts the supervisor on
crashes, on a Telegram /restart, or after a dashboard config edit. Ctrl+C
stops cleanly.
"""

from __future__ import annotations

import asyncio
import os
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
from kickminer.paths import CONFIG_PATH

_CONFIG_PATH = str(CONFIG_PATH)
_RESTART_DELAY = 5


class _RestartRequested(Exception):
    """Raised inside the supervisor when a restart was asked for on purpose."""


class _ManagerHolder:
    """Lets the long-lived dashboard thread always see the current manager
    and know whether config.json changed since that manager was built."""

    def __init__(self) -> None:
        self.current: AccountManager | None = None
        self.config_mtime: float = 0.0
        self.discord: DiscordNotifier | None = None
        self.telegram: TelegramBot | None = None

    def __call__(self) -> AccountManager | None:
        return self.current


def _make_callbacks(discord: DiscordNotifier, telegram: TelegramBot):
    def on_points_gain(alias: str, snap: dict, old: int, new: int) -> None:
        discord.points_gain(alias, snap, old, new)
        if telegram.enabled:
            asyncio.create_task(telegram.notify_points(alias, snap, old, new))

    def on_status_change(alias: str, snap: dict, action: str) -> None:
        discord.status_change(alias, snap, action)
        if not telegram.enabled:
            return
        if action in {"online", "offline"}:
            asyncio.create_task(telegram.notify_status(alias, snap, action))
        elif action == "no_points":
            asyncio.create_task(telegram.notify_no_points(alias, snap))

    return on_points_gain, on_status_change


async def _run_once(
    analytics: Analytics,
    holder: _ManagerHolder,
    restart_flag: threading.Event,
) -> None:
    cfg = load_config(_CONFIG_PATH)  # re-read: dashboard edits land here
    try:
        holder.config_mtime = os.path.getmtime(_CONFIG_PATH)
    except OSError:
        holder.config_mtime = 0.0

    # notifiers are rebuilt from the freshly-loaded config so the Restart
    # button also applies Telegram / Discord changes
    discord = DiscordNotifier(cfg.discord)
    telegram = TelegramBot(cfg.telegram, request_restart=restart_flag.set)
    holder.discord, holder.telegram = discord, telegram

    on_points_gain, on_status_change = _make_callbacks(discord, telegram)
    manager = AccountManager(
        cfg,
        analytics=analytics,
        on_points_gain=on_points_gain,
        on_status_change=on_status_change,
        discord=discord,
        telegram=telegram,
    )
    holder.current = manager
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

    await telegram.start()
    discord.startup(
        [
            {"alias": a.alias, "streamer_order": a.streamers}
            for a in cfg.accounts
        ]
    )

    async def _wait_restart() -> None:
        while not restart_flag.is_set():
            await asyncio.sleep(1)

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
        if stop.is_set():
            discord.shutdown("stopped by user")
        await asyncio.to_thread(discord.close)
        holder.current = holder.discord = holder.telegram = None
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


def _bootstrap_config() -> None:
    """First run in a container: drop a config.json template into the volume."""

    import shutil
    from pathlib import Path

    target = Path(_CONFIG_PATH)
    example = Path(__file__).with_name("config.example.json")
    if not target.exists() and example.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example, target)
        logger.warning(
            f"No config found - wrote a template to {target}. "
            "Edit it (tokens, streamers) and restart the container."
        )


def main() -> int:
    setup_logging(debug=False)
    _bootstrap_config()
    try:
        cfg = load_config(_CONFIG_PATH)
    except ConfigError as exc:
        logger.error(str(exc))
        logger.error(f"Fix {_CONFIG_PATH} and restart. Waiting 30s …")
        try:
            time.sleep(30)  # keep a container restart loop calm
        except KeyboardInterrupt:
            pass
        return 2

    setup_logging(debug=cfg.debug)
    logger.info(t("language_set", lang=load_language(cfg.language)))
    logger.info(t("app_starting"))

    restart_flag = threading.Event()
    holder = _ManagerHolder()
    analytics = Analytics()

    if cfg.web.enabled:
        try:
            from kickminer.web import start_dashboard

            start_dashboard(
                holder,
                analytics,
                cfg.web.port,
                config_path=_CONFIG_PATH,
                request_restart=restart_flag.set,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Web dashboard failed to start: {exc}")

    try:
        while True:
            try:
                asyncio.run(_run_once(analytics, holder, restart_flag))
            except _RestartRequested:
                logger.warning(t("app_restarting", seconds=1, reason="config change"))
                time.sleep(1)
                continue
            except KeyboardInterrupt:
                logger.info(t("app_stopped_by_user"))
                return 0
            except ConfigError as exc:
                logger.error(str(exc))
                return 2
            except Exception as exc:  # noqa: BLE001
                logger.exception(t("app_fatal", error=str(exc)))

            logger.warning(t("app_restarting", seconds=_RESTART_DELAY, reason="crash"))
            try:
                time.sleep(_RESTART_DELAY)
            except KeyboardInterrupt:
                return 0
    finally:
        analytics.close()


if __name__ == "__main__":
    sys.exit(main())
