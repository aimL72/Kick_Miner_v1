"""In-memory state for the mining supervisor.

These objects are mutated by the account workers and read by the dashboard /
notifiers, so keep them plain and cheap to snapshot.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class StreamerState:
    name: str
    priority: int  # index in the account's list; 0 = highest

    channel_id: int | None = None
    user_id: int | None = None
    stream_id: int | None = None

    is_online: bool = False
    is_watching: bool = False

    points: int = 0
    points_start: int | None = None  # balance when this watch session began
    last_points_update: datetime | None = None

    error_count: int = 0
    last_error: str | None = None
    cooldown_until: float = 0.0  # time.monotonic() before which we won't reconnect

    ws_task: asyncio.Task | None = None
    points_task: asyncio.Task | None = None

    @property
    def points_gained(self) -> int:
        if self.points_start is None:
            return 0
        return max(0, self.points - self.points_start)

    def snapshot(self) -> dict:
        return {
            "name": self.name,
            "priority": self.priority,
            "channel_id": self.channel_id,
            "online": self.is_online,
            "watching": self.is_watching,
            "points": self.points,
            "points_gained": self.points_gained,
            "last_update": (
                self.last_points_update.isoformat()
                if self.last_points_update
                else None
            ),
            "stream_id": self.stream_id,
            "errors": self.error_count,
            "cooldown_seconds": max(0, int(self.cooldown_until - time.monotonic())),
        }


@dataclass(slots=True)
class AccountState:
    alias: str
    proxy: str | None
    max_concurrent: int
    streamers: dict[str, StreamerState] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=_now)

    token_valid: bool | None = None       # None = not checked yet
    token_username: str | None = None
    token_checked_at: datetime | None = None
    cycle: dict = field(default_factory=lambda: {"enabled": False})

    @property
    def watching(self) -> list[str]:
        return [s.name for s in self.streamers.values() if s.is_watching]

    @property
    def online(self) -> list[str]:
        return [s.name for s in self.streamers.values() if s.is_online]

    @property
    def total_points(self) -> int:
        return sum(s.points for s in self.streamers.values())

    def snapshot(self) -> dict:
        return {
            "alias": self.alias,
            "proxy": bool(self.proxy),
            "max_concurrent": self.max_concurrent,
            "active_count": len(self.watching),
            "active_streamers": self.watching,
            "streamer_order": self.order,
            "uptime_seconds": int((_now() - self.started_at).total_seconds()),
            "total_points": self.total_points,
            "token_valid": self.token_valid,
            "token_username": self.token_username,
            "token_checked_at": (
                self.token_checked_at.isoformat() if self.token_checked_at else None
            ),
            "cycle": self.cycle,
            "streamers": {
                name: st.snapshot() for name, st in self.streamers.items()
            },
        }
