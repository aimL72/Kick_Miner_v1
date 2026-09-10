"""Load, validate and normalize ``config.json``.

Supports the multi-account format and transparently migrates the old
single-account layout (``Private.token`` / ``Streamers`` / ``Max_active_channels``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from .i18n import t


class ConfigError(Exception):
    """Fatal configuration problem - the bot cannot start."""


@dataclass(slots=True)
class AccountConfig:
    alias: str
    token: str
    streamers: list[str]
    max_concurrent: int = 2
    proxy: str | None = None


@dataclass(slots=True)
class DiscordConfig:
    enabled: bool = False
    webhook_url: str = ""
    username: str = "KickMiner"
    avatar_url: str = ""
    notify_points: bool = True
    notify_status_change: bool = True
    notify_errors: bool = True
    notify_startup: bool = True
    min_points_gain: int = 10


@dataclass(slots=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""  # the single owner
    notify_points: bool = True
    notify_status_change: bool = True
    notify_errors: bool = True
    notify_startup: bool = True
    min_points_gain: int = 1


@dataclass(slots=True)
class WebConfig:
    enabled: bool = True
    port: int = 5000


@dataclass(slots=True)
class Config:
    language: str = "en"
    debug: bool = False
    check_interval: int = 120
    reconnect_cooldown: int = 600
    stagger_min: float = 3.0
    stagger_max: float = 8.0
    cycle_enabled: bool = False
    cycle_interval_minutes: int = 15
    no_points_grace_minutes: int = 30  # 0 = never auto-skip
    global_proxy: str | None = None
    accounts: list[AccountConfig] = field(default_factory=list)
    web: WebConfig = field(default_factory=WebConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)

    @property
    def total_streamers(self) -> int:
        seen: set[str] = set()
        for acc in self.accounts:
            seen.update(s.lower() for s in acc.streamers)
        return len(seen)


# ---------------------------------------------------------------------- #


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _clean_streamers(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        name = str(item).strip().lower().lstrip("@")
        if name and name not in out:
            out.append(name)
    return out


def _migrate_legacy(raw: dict[str, Any]) -> list[dict[str, Any]]:
    token = str(raw.get("Private", {}).get("token", "")).strip()
    streamers = raw.get("Streamers", [])
    if not token or not streamers:
        return []
    logger.warning(t("config_legacy_migrated"))
    return [
        {
            "alias": "Default",
            "token": token,
            "streamers": streamers,
            "max_concurrent": raw.get("Max_active_channels", 5),
        }
    ]


def _parse_accounts(raw: dict[str, Any]) -> list[AccountConfig]:
    entries = raw.get("Accounts")
    if not isinstance(entries, list) or not entries:
        entries = _migrate_legacy(raw)

    accounts: list[AccountConfig] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        alias = str(entry.get("alias") or f"Account {idx + 1}").strip()
        token = str(entry.get("token") or "").strip()
        streamers = _clean_streamers(entry.get("streamers"))

        if not token:
            logger.warning(t("config_account_no_token", alias=alias))
            continue
        if not streamers:
            logger.warning(t("config_account_no_streamers", alias=alias))
            continue

        try:
            max_concurrent = max(1, int(entry.get("max_concurrent", 2)))
        except (TypeError, ValueError):
            max_concurrent = 2

        proxy = entry.get("proxy")
        accounts.append(
            AccountConfig(
                alias=alias,
                token=token,
                streamers=streamers,
                max_concurrent=max_concurrent,
                proxy=str(proxy).strip() if proxy else None,
            )
        )
    return accounts


def _parse_discord(raw: dict[str, Any]) -> DiscordConfig:
    d = raw.get("Discord", {}) or {}
    cfg = DiscordConfig(
        enabled=_as_bool(d.get("enabled")),
        webhook_url=str(d.get("webhook_url", "")).strip(),
        username=str(d.get("username", "")),
        avatar_url=str(d.get("avatar_url", "")),
        notify_points=_as_bool(d.get("notify_points"), True),
        notify_status_change=_as_bool(d.get("notify_status_change"), True),
        notify_errors=_as_bool(d.get("notify_errors"), True),
        notify_startup=_as_bool(d.get("notify_startup"), True),
        min_points_gain=int(d.get("min_points_gain", 10) or 0),
    )
    if cfg.enabled and not cfg.webhook_url:
        logger.warning("Discord enabled but webhook_url missing - disabling Discord.")
        cfg.enabled = False
    return cfg


def _parse_telegram(raw: dict[str, Any]) -> TelegramConfig:
    tg = raw.get("Telegram", {}) or {}
    cfg = TelegramConfig(
        enabled=_as_bool(tg.get("enabled")),
        bot_token=str(tg.get("bot_token", "")).strip(),
        chat_id=str(tg.get("chat_id", "")).strip(),
        notify_points=_as_bool(tg.get("notify_points"), True),
        notify_status_change=_as_bool(tg.get("notify_status_change"), True),
        notify_errors=_as_bool(tg.get("notify_errors"), True),
        notify_startup=_as_bool(tg.get("notify_startup"), True),
        min_points_gain=int(tg.get("min_points_gain", 1) or 0),
    )
    if cfg.enabled and not cfg.bot_token:
        logger.warning("Telegram enabled but bot_token missing - disabling Telegram.")
        cfg.enabled = False
    return cfg


def load_config(path: str | Path = "config.json") -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(t("config_not_found", path=str(path)))

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(t("config_invalid_json", error=str(exc))) from exc

    if not isinstance(raw, dict):
        raise ConfigError(t("config_invalid_json", error="root is not an object"))

    proxy_cfg = raw.get("Proxy", {}) or {}
    global_proxy = (
        str(proxy_cfg.get("url", "")).strip()
        if _as_bool(proxy_cfg.get("enabled"))
        else None
    )

    web_cfg = raw.get("WebDashboard", {}) or {}

    def _num(key: str, default: float) -> float:
        try:
            return float(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    accounts = _parse_accounts(raw)
    # apply global proxy where the account did not set its own
    if global_proxy:
        logger.info(t("config_proxy_global"))
        for acc in accounts:
            if acc.proxy is None:
                acc.proxy = global_proxy

    if not accounts:
        raise ConfigError(t("config_no_accounts"))

    cfg = Config(
        language=str(raw.get("Language", "en")).lower().strip() or "en",
        debug=_as_bool(raw.get("Debug")),
        check_interval=int(_num("Check_interval", 120)),
        reconnect_cooldown=int(_num("Reconnect_cooldown", 600)),
        stagger_min=_num("Connection_stagger_min", 3.0),
        stagger_max=_num("Connection_stagger_max", 8.0),
        cycle_enabled=_as_bool((raw.get("Cycle", {}) or {}).get("enabled")),
        cycle_interval_minutes=max(
            1, int((raw.get("Cycle", {}) or {}).get("interval_minutes", 15) or 15)
        ),
        no_points_grace_minutes=max(0, int(_num("No_points_grace_minutes", 30))),
        global_proxy=global_proxy,
        accounts=accounts,
        web=WebConfig(
            enabled=_as_bool(web_cfg.get("enabled"), True),
            port=int(web_cfg.get("port", 5000) or 5000),
        ),
        discord=_parse_discord(raw),
        telegram=_parse_telegram(raw),
    )

    logger.info(
        t(
            "config_loaded",
            accounts=len(cfg.accounts),
            streamers=cfg.total_streamers,
        )
    )
    return cfg
