"""Small shared helpers."""

from __future__ import annotations

_UNITS = ["", "k", "M", "B", "T"]


def millify(value: float, precision: int = 2) -> str:
    """Compact number formatting, matching the Twitch miner's ``_millify``.

    1234 -> "1.23k", 1000000 -> "1M", 950 -> "950".
    """

    try:
        value = float(value)
    except (TypeError, ValueError):
        return "0"

    negative = value < 0
    value = abs(value)

    idx = 0
    while value >= 1000 and idx < len(_UNITS) - 1:
        value /= 1000.0
        idx += 1

    formatted = f"{value:.{precision}f}".rstrip("0").rstrip(".")
    return f"{'-' if negative else ''}{formatted}{_UNITS[idx]}"
