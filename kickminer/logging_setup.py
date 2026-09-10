"""Central logging configuration built on loguru.

* console: colored, level depends on ``debug``
* file:    ``logs/kickminer.log`` with rotation + compression, always DEBUG
"""

from __future__ import annotations

import sys

from loguru import logger

from .paths import LOG_DIR as _LOG_DIR

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
    "<level>{level: <8}</level> "
    "<cyan>{name}</cyan> - <level>{message}</level>"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{name}:{function}:{line} - {message}"
)


def setup_logging(debug: bool = False) -> None:
    """(Re)configure all sinks. Safe to call more than once."""

    logger.remove()

    logger.add(
        sys.stderr,
        level="DEBUG" if debug else "INFO",
        format=_CONSOLE_FORMAT,
        colorize=True,
        backtrace=False,
        diagnose=False,
    )

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(
        _LOG_DIR / "kickminer.log",
        level="DEBUG",
        format=_FILE_FORMAT,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
