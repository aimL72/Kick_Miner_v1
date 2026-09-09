"""Thin typed wrapper over the handful of Kick REST endpoints we need.

All calls go through a shared :class:`KickHttpClient`. Every method degrades to
``None`` / ``False`` instead of raising, so callers can treat Kick as flaky
(which it is, behind Cloudflare).

Known endpoints (v2, unofficial - Kick has no public points API):

* ``GET /api/v2/channels/{slug}``            -> channel id, user id, live state
* ``GET /api/v2/channels/{slug}/livestream`` -> current stream id (or null)
* ``GET /api/v2/channels/{slug}/points``     -> viewer's point balance
* ``GET wss host /viewer/v1/token``          -> short-lived viewer WS token
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from .http_client import KickHttpClient, safe_get
from .i18n import t

API_BASE = "https://kick.com/api/v2"
WS_TOKEN_URL = "https://websockets.kick.com/viewer/v1/token"


@dataclass(slots=True)
class ChannelInfo:
    slug: str
    channel_id: int
    user_id: int
    is_live: bool
    stream_id: int | None = None


class KickApi:
    def __init__(self, http: KickHttpClient) -> None:
        self.http = http

    # ------------------------------------------------------------------ #

    def get_channel(self, slug: str) -> ChannelInfo | None:
        """Full channel lookup. Also tells us whether the channel is live."""

        slug = slug.lower().strip()
        logger.debug(t("api_channel_fetch", streamer=slug))

        data = self.http.get_json(
            f"{API_BASE}/channels/{slug}",
            headers={"Referer": f"https://kick.com/{slug}"},
        )
        if data is None:
            logger.warning(t("api_channel_failed", streamer=slug, status="?"))
            return None

        root = data.get("data") if isinstance(data.get("data"), dict) else data

        channel_id = safe_get(root, "id")
        user_id = safe_get(root, "user_id") or safe_get(root, "user", "id")
        if not channel_id:
            logger.warning(t("api_channel_id_missing", streamer=slug))
            return None
        if not user_id:
            user_id = channel_id

        livestream = safe_get(root, "livestream")
        is_live = isinstance(livestream, dict) and bool(livestream.get("id"))
        stream_id = safe_get(livestream, "id") if is_live else None

        logger.debug(
            t("api_channel_ids", channel_id=channel_id, user_id=user_id, streamer=slug)
        )
        return ChannelInfo(
            slug=slug,
            channel_id=int(channel_id),
            user_id=int(user_id),
            is_live=is_live,
            stream_id=int(stream_id) if stream_id else None,
        )

    def get_stream_id(self, slug: str) -> int | None:
        """Lightweight online check via the dedicated livestream endpoint.

        Falls back to the channel endpoint when the livestream route 403s.
        """

        slug = slug.lower().strip()
        data = self.http.get_json(
            f"{API_BASE}/channels/{slug}/livestream",
            headers={"Referer": f"https://kick.com/{slug}"},
        )
        stream_id = safe_get(data, "data", "id") or safe_get(data, "id")
        if stream_id:
            logger.debug(t("api_livestream_online", streamer=slug, stream_id=stream_id))
            return int(stream_id)

        # fallback: the channel object embeds livestream too
        channel = self.get_channel(slug)
        if channel and channel.is_live and channel.stream_id:
            logger.debug(
                t("api_livestream_online", streamer=slug, stream_id=channel.stream_id)
            )
            return channel.stream_id

        logger.debug(t("api_livestream_offline", streamer=slug))
        return None

    def get_points(self, slug: str) -> int | None:
        """Viewer's channel-point balance for ``slug``. ``None`` = lookup failed."""

        slug = slug.lower().strip()
        resp = self.http.get(
            f"{API_BASE}/channels/{slug}/points",
            headers={"Referer": f"https://kick.com/{slug}"},
        )
        if resp is not None and resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                data = None
            points = safe_get(data, "data", "points")
            if points is None:
                points = safe_get(data, "points")
            if points is not None:
                logger.debug(t("api_points_balance", streamer=slug, amount=points))
                return int(points)

        # fallback: channel object sometimes carries user.points
        data = self.http.get_json(
            f"{API_BASE}/channels/{slug}",
            headers={"Referer": f"https://kick.com/{slug}"},
        )
        points = safe_get(data, "data", "user", "points") or safe_get(
            data, "user", "points"
        )
        if points is not None:
            logger.debug(t("api_points_balance", streamer=slug, amount=points))
            return int(points)

        status = resp.status_code if resp is not None else "?"
        logger.warning(t("api_points_failed", streamer=slug, status=status))
        return None

    def get_viewer_ws_token(
        self, slug: str, channel_id: int, user_id: int
    ) -> str | None:
        """Short-lived token required to open the viewer WebSocket."""

        slug = slug.lower().strip()
        resp = self.http.get(
            WS_TOKEN_URL,
            headers={
                "Referer": f"https://kick.com/{slug}",
                "X-Chatroom": str(channel_id),
                "X-User-Id": str(user_id),
            },
        )
        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp is not None else "?"
            logger.warning(t("api_ws_token_failed", streamer=slug, status=status))
            return None

        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return None

        token = (
            safe_get(data, "data", "token")
            or safe_get(data, "data", "websocket_token")
            or safe_get(data, "token")
            or safe_get(data, "websocket_token")
        )
        if token:
            logger.debug(t("api_ws_token_ok", streamer=slug))
            return str(token)

        logger.warning(t("api_ws_token_failed", streamer=slug, status="no-token"))
        return None
