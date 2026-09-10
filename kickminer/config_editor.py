"""Safe, atomic edits to ``config.json`` from the web dashboard.

Only the streamer lists and ``max_concurrent`` are editable; everything else in
the file is preserved byte-for-byte (we reload, mutate, and rewrite the parsed
JSON). After a successful edit the caller restarts the supervisor so the new
streamer set takes effect.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path

# Kick channel slug: letters/digits plus _ . - (some channels use hyphens or
# dots). Starts and ends alphanumeric; up to ~40 chars. Path separators and
# ".." stay blocked because the slug is interpolated into API URLs.
STREAMER_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,38}[a-z0-9])?$")
TOKEN_RE = re.compile(r"^\d+\|[A-Za-z0-9]{16,}$")
_LOCK = threading.Lock()


class ConfigEditError(Exception):
    """A rejected dashboard edit (bad input, unknown account, ...)."""


def _clean_name(raw: str) -> str:
    name = str(raw or "").strip().lower().lstrip("@")
    if ".." in name or "/" in name or "\\" in name or not STREAMER_RE.match(name):
        raise ConfigEditError(
            f"'{raw}' is not a valid Kick channel name. Use the name from the "
            "channel URL (kick.com/<name>) - letters, digits, _ . -"
        )
    return name


def _accounts(raw: dict) -> list[dict]:
    accts = raw.get("Accounts")
    if not isinstance(accts, list) or not accts:
        raise ConfigEditError("config.json has no editable 'Accounts' list.")
    return accts


def _find(raw: dict, alias: str) -> dict:
    for acc in _accounts(raw):
        if str(acc.get("alias")) == alias:
            return acc
    raise ConfigEditError(f"Unknown account: {alias!r}")


TELEGRAM_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")
_DISCORD_HOSTS = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
    "https://canary.discord.com/api/webhooks/",
    "https://ptb.discord.com/api/webhooks/",
)


def _token_hint(token: str) -> str:
    token = str(token or "")
    if "|" not in token:
        return "…" + token[-4:] if token else ""
    prefix, _, secret = token.partition("|")
    return f"{prefix}|…{secret[-4:]}" if secret else f"{prefix}|…"


def _secret_hint(value: str) -> str:
    value = str(value or "")
    return f"…{value[-6:]}" if len(value) > 6 else ("set" if value else "")


def read_editable(path: str | Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for acc in raw.get("Accounts", []) or []:
        streamers = [
            str(s).strip().lower()
            for s in acc.get("streamers", [])
            if str(s).strip()
        ]
        token = str(acc.get("token") or "")
        out.append(
            {
                "alias": acc.get("alias"),
                "streamers": streamers,
                "max_concurrent": int(acc.get("max_concurrent", 2) or 2),
                "proxy": bool(acc.get("proxy")),
                "has_token": bool(token),
                "token_hint": _token_hint(token),  # never the full secret
            }
        )

    tg = raw.get("Telegram", {}) or {}
    dc = raw.get("Discord", {}) or {}
    def _notify_block(d: dict, secret_key: str, hint_key: str, has_key: str) -> dict:
        return {
            "enabled": bool(d.get("enabled")),
            "notify_points": bool(d.get("notify_points", True)),
            "notify_status_change": bool(d.get("notify_status_change", True)),
            "notify_errors": bool(d.get("notify_errors", True)),
            "notify_startup": bool(d.get("notify_startup", True)),
            "min_points_gain": int(d.get("min_points_gain", 1) or 0),
            has_key: bool(d.get(secret_key)),
            hint_key: _secret_hint(d.get(secret_key)),
        }

    cy = raw.get("Cycle", {}) or {}
    return {
        "accounts": out,
        "cycle": {
            "enabled": bool(cy.get("enabled")),
            "interval_minutes": int(cy.get("interval_minutes", 15) or 15),
            "no_points_grace_minutes": max(
                0, int(raw.get("No_points_grace_minutes", 30) or 0)
            ),
        },
        "telegram": {
            **_notify_block(tg, "bot_token", "token_hint", "has_token"),
            "chat_id": str(tg.get("chat_id", "")),
        },
        "discord": _notify_block(dc, "webhook_url", "webhook_hint", "has_webhook"),
    }


def _validate_token(raw: str) -> str:
    tok = str(raw or "").strip()
    if not TOKEN_RE.match(tok):
        raise ConfigEditError(
            "That does not look like a Kick bearer token "
            "(expected '123456|abcdef...')."
        )
    return tok


def apply_action(path: str | Path, action: dict) -> dict:
    path = Path(path)
    kind = action.get("action")
    alias = action.get("account")

    with _LOCK:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.setdefault("Accounts", [])

        # ---- account-level actions (no existing account to look up) ----
        if kind == "add_account":
            new_alias = str(action.get("alias") or "").strip()
            if not new_alias:
                raise ConfigEditError("Account name must not be empty.")
            if any(str(a.get("alias")) == new_alias for a in raw["Accounts"]):
                raise ConfigEditError(f"An account named {new_alias!r} already exists.")
            raw["Accounts"].append(
                {
                    "alias": new_alias,
                    "token": _validate_token(action.get("token")),
                    "proxy": None,
                    "streamers": [],
                    "max_concurrent": 2,
                }
            )
            _atomic_write(path, raw)
            return read_editable(path)

        if kind == "remove_account":
            if len(raw["Accounts"]) <= 1:
                raise ConfigEditError("Cannot remove the last account.")
            before = len(raw["Accounts"])
            raw["Accounts"] = [
                a for a in raw["Accounts"] if str(a.get("alias")) != alias
            ]
            if len(raw["Accounts"]) == before:
                raise ConfigEditError(f"Unknown account: {alias!r}")
            _atomic_write(path, raw)
            return read_editable(path)

        if kind == "set_cycle":
            cy = raw.setdefault("Cycle", {})
            cy["enabled"] = bool(action.get("enabled"))
            if "interval_minutes" in action:
                try:
                    m = int(action.get("interval_minutes"))
                except (TypeError, ValueError):
                    raise ConfigEditError("interval must be a number of minutes.") from None
                if not 5 <= m <= 120:
                    raise ConfigEditError("interval must be between 5 and 120 minutes.")
                cy["interval_minutes"] = m
            if "no_points_grace_minutes" in action:
                try:
                    g = int(action.get("no_points_grace_minutes"))
                except (TypeError, ValueError):
                    raise ConfigEditError(
                        "no-points grace must be a number of minutes."
                    ) from None
                if g != 0 and not 10 <= g <= 240:
                    raise ConfigEditError(
                        "no-points grace must be 0 (off) or between 10 and 240 minutes."
                    )
                raw["No_points_grace_minutes"] = g
            _atomic_write(path, raw)
            return read_editable(path)

        if kind in ("set_telegram", "set_discord"):
            key = "Telegram" if kind == "set_telegram" else "Discord"
            tgt = raw.setdefault(key, {})
            tgt["enabled"] = bool(action.get("enabled"))
            for flag in (
                "notify_points",
                "notify_status_change",
                "notify_errors",
                "notify_startup",
            ):
                if flag in action:
                    tgt[flag] = bool(action[flag])
            if "min_points_gain" in action:
                try:
                    tgt["min_points_gain"] = max(0, int(action.get("min_points_gain") or 0))
                except (TypeError, ValueError):
                    raise ConfigEditError("min_points_gain must be a number.") from None

            if kind == "set_telegram":
                tgt.pop("allowed_users", None)  # single-user only now
                if str(action.get("bot_token") or "").strip():
                    tok = str(action["bot_token"]).strip()
                    if not TELEGRAM_TOKEN_RE.match(tok):
                        raise ConfigEditError(
                            "That does not look like a Telegram bot token "
                            "(expected '123456789:AA...' from @BotFather)."
                        )
                    tgt["bot_token"] = tok
                if "chat_id" in action:
                    tgt["chat_id"] = str(action.get("chat_id") or "").strip()
                if tgt["enabled"] and not tgt.get("bot_token"):
                    raise ConfigEditError("Enter a bot token before enabling Telegram.")
            else:
                if str(action.get("webhook_url") or "").strip():
                    url = str(action["webhook_url"]).strip()
                    if not url.startswith(_DISCORD_HOSTS):
                        raise ConfigEditError(
                            "That is not a Discord webhook URL "
                            "(https://discord.com/api/webhooks/...)."
                        )
                    tgt["webhook_url"] = url
                if tgt["enabled"] and not tgt.get("webhook_url"):
                    raise ConfigEditError("Enter a webhook URL before enabling Discord.")

            _atomic_write(path, raw)
            return read_editable(path)

        # ---- streamer-level actions (operate on one account) ----
        acc = _find(raw, alias)
        streamers: list[str] = [
            str(s).strip().lower() for s in acc.get("streamers", []) if str(s).strip()
        ]

        if kind == "add":
            name = _clean_name(action.get("streamer"))
            if name in streamers:
                raise ConfigEditError(f"{name} is already in the list.")
            streamers.append(name)

        elif kind == "remove":
            name = _clean_name(action.get("streamer"))
            if name not in streamers:
                raise ConfigEditError(f"{name} is not in the list.")
            streamers = [s for s in streamers if s != name]

        elif kind == "reorder":
            new_order = [_clean_name(s) for s in action.get("streamers", [])]
            if sorted(new_order) != sorted(streamers):
                raise ConfigEditError("Reorder list does not match current streamers.")
            streamers = new_order

        elif kind == "set_limit":
            try:
                limit = int(action.get("max_concurrent"))
            except (TypeError, ValueError):
                raise ConfigEditError("max_concurrent must be a number.") from None
            if not 1 <= limit <= 50:
                raise ConfigEditError("max_concurrent must be between 1 and 50.")
            acc["max_concurrent"] = limit

        elif kind == "set_token":
            acc["token"] = _validate_token(action.get("token"))

        else:
            raise ConfigEditError(f"Unknown action: {kind!r}")

        acc["streamers"] = streamers
        _atomic_write(path, raw)

    return read_editable(path)


def _atomic_write(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".config-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
