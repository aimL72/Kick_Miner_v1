"""Formatting helpers shared by the notifiers."""

from __future__ import annotations


def format_uptime(seconds: int | float) -> str:
    seconds = int(seconds)
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def summarize_accounts(snapshot: list[dict]) -> str:
    """Plain-text overview of every account/streamer, for chat replies."""

    lines: list[str] = []
    grand = 0
    for acc in snapshot:
        streamers = acc.get("streamers", {})
        order = acc.get("streamer_order", list(streamers))
        sub = acc.get("total_points", 0)
        grand += sub
        lines.append(
            f"▸ {acc.get('alias')}  "
            f"[{acc.get('active_count')}/{acc.get('max_concurrent')}]  "
            f"up {format_uptime(acc.get('uptime_seconds', 0))}  ·  {sub:,} pts"
        )
        for name in order:
            s = streamers.get(name, {})
            icon = "👁" if s.get("watching") else ("🟢" if s.get("online") else "⚫")
            gained = s.get("points_gained", 0)
            extra = f" (+{gained})" if gained else ""
            lines.append(
                f"   {icon} #{s.get('priority', '?')} {name} — {s.get('points', 0):,}{extra}"
            )
    lines.append(f"\nΣ {grand:,} points")
    return "\n".join(lines)
