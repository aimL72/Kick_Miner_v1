"""Points history in a small SQLite file (``data/analytics.sqlite3``).

One row per successful points poll. The dashboard reads this to draw a
balance-over-time line per streamer. Safe to delete – the miner recreates it.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from loguru import logger

from .paths import ANALYTICS_DB


class Analytics:
    def __init__(self, path: str | Path | None = None, *, retention_days: int = 30):
        self.path = Path(path) if path else ANALYTICS_DB
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._db = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None
        )
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS points_history (
                ts       INTEGER NOT NULL,
                account  TEXT    NOT NULL,
                streamer TEXT    NOT NULL,
                balance  INTEGER NOT NULL
            )
            """
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ph_lookup "
            "ON points_history (streamer, account, ts)"
        )
        self._prune()

    # ------------------------------------------------------------------ #

    def record(self, account: str, streamer: str, balance: int) -> None:
        try:
            with self._lock:
                self._db.execute(
                    "INSERT INTO points_history (ts, account, streamer, balance) "
                    "VALUES (?, ?, ?, ?)",
                    (int(time.time()), account, streamer.lower(), int(balance)),
                )
        except sqlite3.Error as exc:
            logger.debug(f"analytics.record failed: {exc}")

    def history(
        self, streamer: str, *, account: str | None = None, hours: int = 24
    ) -> list[dict]:
        since = int(time.time()) - hours * 3600
        sql = (
            "SELECT ts, account, balance FROM points_history "
            "WHERE streamer = ? AND ts >= ?"
        )
        params: list[object] = [streamer.lower(), since]
        if account:
            sql += " AND account = ?"
            params.append(account)
        sql += " ORDER BY ts ASC"
        try:
            with self._lock:
                rows = self._db.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            logger.debug(f"analytics.history failed: {exc}")
            return []
        return [{"ts": ts, "account": acc, "balance": bal} for ts, acc, bal in rows]

    def streamers(self) -> list[str]:
        try:
            with self._lock:
                rows = self._db.execute(
                    "SELECT DISTINCT streamer FROM points_history ORDER BY streamer"
                ).fetchall()
        except sqlite3.Error:
            return []
        return [r[0] for r in rows]

    def _prune(self) -> None:
        cutoff = int(time.time()) - self.retention_days * 86400
        try:
            with self._lock:
                self._db.execute(
                    "DELETE FROM points_history WHERE ts < ?", (cutoff,)
                )
        except sqlite3.Error:
            pass

    def close(self) -> None:
        try:
            self._db.close()
        except sqlite3.Error:
            pass
