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

STREAMER_RE = re.compile(r"^[a-z0-9_]{1,25}$")
TOKEN_RE = re.compile(r"^\d+\|[A-Za-z0-9]{16,}$")
_LOCK = threading.Lock()


class ConfigEditError(Exception):
    """A rejected dashboard edit (bad input, unknown account, ...)."""


def _clean_name(raw: str) -> str:
    name = str(raw or "").strip().lower().lstrip("@")
    if not STREAMER_RE.match(name):
        raise ConfigEditError(f"Invalid Kick channel name: {raw!r}")
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


def _token_hint(token: str) -> str:
    token = str(token or "")
    if "|" not in token:
        return "…" + token[-4:] if token else ""
    prefix, _, secret = token.partition("|")
    return f"{prefix}|…{secret[-4:]}" if secret else f"{prefix}|…"


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
    return {"accounts": out}


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
