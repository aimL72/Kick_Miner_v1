"""Entry point for the Kick Channel Points Miner.

Phase 1 status: configuration, logging and the Kick read layer are in place.
The mining supervisor (WebSocket watch loop + multi-account manager) lands in
phase 2. Until then this file just validates the setup and points you at the
self-test.
"""

from __future__ import annotations

import sys

from loguru import logger

from kickminer.config import ConfigError, load_config
from kickminer.i18n import load_language, t
from kickminer.logging_setup import setup_logging


def main() -> int:
    setup_logging(debug=False)
    try:
        cfg = load_config("config.json")
    except ConfigError as exc:
        logger.error(str(exc))
        return 2

    setup_logging(debug=cfg.debug)
    active = load_language(cfg.language)
    logger.info(t("language_set", lang=active))
    logger.info(t("app_starting"))

    for acc in cfg.accounts:
        logger.info(
            t(
                "worker_start",
                alias=acc.alias,
                streamers=len(acc.streamers),
                limit=acc.max_concurrent,
                proxy=t("yes") if acc.proxy else t("no"),
            )
        )

    logger.warning(
        "Mining loop not implemented yet (phase 2). "
        "Run  python -m kickminer.selfcheck <channel> --account \"<alias>\"  "
        "to verify Kick connectivity."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
