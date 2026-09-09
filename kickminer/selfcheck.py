"""Connectivity self-test.

Verifies that this machine / proxy can reach Kick through the Cloudflare
bypass. Run before configuring the full miner::

    python -m kickminer.selfcheck xqc
    python -m kickminer.selfcheck xqc --account "Main Account"

With an account (token from config.json) it also checks the point balance and
the viewer WebSocket token - i.e. the full read path the miner relies on.
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from .config import ConfigError, load_config
from .http_client import KickHttpClient
from .i18n import load_language
from .kick_api import KickApi
from .logging_setup import setup_logging


def _run(slug: str, account_alias: str | None, config_path: str) -> int:
    token: str | None = None
    proxy: str | None = None

    if account_alias:
        cfg = load_config(config_path)
        match = next(
            (a for a in cfg.accounts if a.alias.lower() == account_alias.lower()),
            None,
        )
        if match is None:
            logger.error(f"Account '{account_alias}' not found in {config_path}.")
            return 2
        token, proxy = match.token, match.proxy

    http = KickHttpClient(proxy=proxy, auth_token=token)
    api = KickApi(http)
    ok = True

    logger.info(f"-> Channel lookup for '{slug}'...")
    channel = api.get_channel(slug)
    if channel is None:
        logger.error("Channel lookup FAILED (Cloudflare block or wrong slug?).")
        http.close()
        return 1

    logger.success(
        f"Channel OK: id={channel.channel_id} user={channel.user_id} "
        f"live={channel.is_live} stream_id={channel.stream_id}"
    )

    if token:
        logger.info("-> Points balance...")
        points = api.get_points(slug)
        if points is None:
            logger.error("Points lookup FAILED (token invalid/expired?).")
            ok = False
        else:
            logger.success(f"Points OK: {points}")

        logger.info("-> Viewer WebSocket token...")
        ws_token = api.get_viewer_ws_token(
            slug, channel.channel_id, channel.user_id
        )
        if ws_token:
            logger.success(f"WS token OK: {ws_token[:16]}...")
        else:
            logger.error("WS token FAILED.")
            ok = False

    http.close()
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kickminer.selfcheck")
    parser.add_argument("slug", help="Kick channel name, e.g. 'xqc'")
    parser.add_argument(
        "--account",
        help="alias from config.json - also tests points + WS token",
    )
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--lang", default="en")
    args = parser.parse_args(argv)

    setup_logging(debug=args.debug)
    load_language(args.lang)

    try:
        return _run(args.slug, args.account, args.config)
    except ConfigError as exc:
        logger.error(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
