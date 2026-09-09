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


def read_editable(path: str | Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for acc in raw.get("Accounts", []) or []:
        streamers = [
            str(s).strip().lower()
            for s in acc.get("streamers", [])
            if str(s).strip()
        ]
        out.append(
            {
                "alias": acc.get("alias"),
                "streamers": streamers,
                "max_concurrent": int(acc.get("max_concurrent", 2) or 2),
                "proxy": bool(acc.get("proxy")),
            }
        )
    return {"accounts": out}


def apply_action(path: str | Path, action: dict) -> dict:
    path = Path(path)
    kind = action.get("action")
    alias = action.get("account")

    with _LOCK:
        raw = json.loads(path.read_text(encoding="utf-8"))
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
