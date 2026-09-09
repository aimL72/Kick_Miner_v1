"""Formatting helpers shared by the notifiers (Discord + Telegram use the same)."""

from __future__ import annotations

from ..utils import millify

# One emoji vocabulary for every outbound channel.
EMOJI = {
    "online": "🥳",
    "offline": "😴",
    "gain": "🚀",
    "claim": "🎁",
    "start": "🟢",
    "stop": "🔴",
    "error": "⚠️",
}


def streamer_repr(name: str, channel_id, points) -> str:
    """The Twitch miner's ``Streamer.__repr__`` form."""

    cid = channel_id if channel_id is not None else "?"
    return (
        f"Streamer(username={name}, channel_id={cid}, "
        f"channel_points={millify(points)})"
    )


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
        label = acc.get("token_username") or acc.get("alias")
        token_flag = "" if acc.get("token_valid") is not False else "  ⚠ token expired"
        lines.append(
            f"▸ Account ({label})  "
            f"[{acc.get('active_count')}/{acc.get('max_concurrent')}]  "
            f"up {format_uptime(acc.get('uptime_seconds', 0))}  ·  {sub:,} pts"
            f"{token_flag}"
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
