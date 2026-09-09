"""Entry point for the Kick Channel Points Miner.

Loads config, starts the multi-account mining supervisor, and restarts it on
unexpected crashes. Ctrl+C stops cleanly.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time

from loguru import logger

from kickminer.analytics import Analytics
from kickminer.config import ConfigError, load_config
from kickminer.i18n import load_language, t
from kickminer.logging_setup import setup_logging
from kickminer.manager import AccountManager

_RESTART_DELAY = 5


async def _run_once(cfg, analytics: Analytics) -> None:
    manager = AccountManager(cfg, analytics=analytics)
    stop = asyncio.Event()

    if cfg.web.enabled:
        try:
            from kickminer.web import start_dashboard

            start_dashboard(manager, analytics, cfg.web.port)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Web dashboard failed to start: {exc}")

    loop = asyncio.get_running_loop()
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass  # Windows / non-main thread - KeyboardInterrupt handles it

    run_task = asyncio.create_task(manager.run(), name="manager")
    stop_task = asyncio.create_task(stop.wait(), name="stop")

    try:
        await asyncio.wait(
            {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        stop_task.cancel()
        await manager.stop()
        if not run_task.done():
            run_task.cancel()
        try:
            await run_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

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

    analytics = Analytics()
    try:
        while True:
            try:
                asyncio.run(_run_once(cfg, analytics))
            except KeyboardInterrupt:
                logger.info(t("app_stopped_by_user"))
                return 0
            except Exception as exc:  # noqa: BLE001
                logger.exception(t("app_fatal", error=str(exc)))

            logger.warning(
                t("app_restarting", seconds=_RESTART_DELAY, reason="crash")
            )
            try:
                time.sleep(_RESTART_DELAY)
            except KeyboardInterrupt:
                return 0
    finally:
        analytics.close()


if __name__ == "__main__":
    sys.exit(main())
