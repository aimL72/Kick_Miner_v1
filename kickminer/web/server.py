"""Read-only Flask dashboard, served from a daemon thread.

Endpoints:
    GET /                      the dashboard page
    GET /api/data              live snapshot of every account / streamer
    GET /api/history?streamer= balance-over-time series (optional &account=, &hours=)
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from flask import Flask, jsonify, request
from loguru import logger

_TEMPLATE = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


def start_dashboard(manager, analytics, port: int = 5000) -> None:
    app = Flask(__name__)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.route("/")
    def index():
        return _TEMPLATE

    @app.route("/api/data")
    def api_data():
        try:
            accounts = manager.snapshot()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"dashboard /api/data: {exc}")
            accounts = []
        grand_total = sum(a.get("total_points", 0) for a in accounts)
        session_gain = sum(
            s.get("points_gained", 0)
            for a in accounts
            for s in a.get("streamers", {}).values()
        )
        return jsonify(
            {
                "status": "active",
                "accounts": accounts,
                "grand_total": grand_total,
                "session_gain": session_gain,
                "history_streamers": analytics.streamers() if analytics else [],
            }
        )

    @app.route("/api/history")
    def api_history():
        streamer = (request.args.get("streamer") or "").lower().strip()
        if not streamer or analytics is None:
            return jsonify({"streamer": streamer, "points": []})
        account = request.args.get("account") or None
        try:
            hours = max(1, min(720, int(request.args.get("hours", 24))))
        except ValueError:
            hours = 24
        rows = analytics.history(streamer, account=account, hours=hours)
        return jsonify({"streamer": streamer, "hours": hours, "points": rows})

    def _serve():
        logger.info(f"Web dashboard: http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    threading.Thread(target=_serve, name="dashboard", daemon=True).start()
