"""Web dashboard: live status, per-streamer point charts, streamer editor, log.

Served from a daemon thread. Read-only except ``POST /api/config``, which edits
``config.json`` (streamer add/remove/reorder, concurrency limit) and then asks
the supervisor to restart so the change takes effect.

    GET  /                       dashboard page
    GET  /api/data               live snapshot of every account / streamer
    GET  /api/history?streamer=  balance-over-time series
    GET  /api/config             editable view of config.json
    POST /api/config             apply one edit action, then restart
    GET  /api/log?bytes=N        tail of logs/kickminer.log
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from flask import Flask, jsonify, request
from loguru import logger

from ..config_editor import ConfigEditError, apply_action, read_editable

_TEMPLATE_PATH = Path(__file__).parent / "dashboard.html"
_LOG_PATH = Path("logs") / "kickminer.log"
_MAX_LOG_TAIL = 512 * 1024


def start_dashboard(
    get_manager,
    analytics,
    port: int = 5000,
    *,
    config_path: str = "config.json",
    on_config_change=None,
) -> None:
    """``get_manager`` is a callable returning the current AccountManager
    (it is replaced on every supervisor restart)."""

    app = Flask(__name__)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    @app.route("/")
    def index():
        return _TEMPLATE_PATH.read_text(encoding="utf-8")

    @app.route("/api/data")
    def api_data():
        manager = get_manager()
        try:
            accounts = manager.snapshot() if manager is not None else []
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"dashboard /api/data: {exc}")
            accounts = []
        now_watching = [
            {"account": a["alias"], "streamer": name, "points": s.get("points", 0)}
            for a in accounts
            for name, s in a.get("streamers", {}).items()
            if s.get("watching")
        ]
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
                "now_watching": now_watching,
                "grand_total": grand_total,
                "session_gain": session_gain,
                "history_streamers": analytics.streamers() if analytics else [],
            }
        )

    @app.route("/api/history")
    def api_history():
        streamer = (request.args.get("streamer") or "").lower().strip()
        if not streamer or analytics is None:
            return jsonify({"streamer": streamer, "points": [], "series": []})
        account = request.args.get("account") or None
        try:
            hours = max(1, min(720, int(request.args.get("hours", 24))))
        except ValueError:
            hours = 24
        rows = analytics.history(streamer, account=account, hours=hours)
        series = [[r["ts"] * 1000, r["balance"]] for r in rows]
        return jsonify(
            {"streamer": streamer, "hours": hours, "points": rows, "series": series}
        )

    @app.route("/api/config", methods=["GET", "POST"])
    def api_config():
        if request.method == "GET":
            try:
                return jsonify(read_editable(config_path))
            except Exception as exc:  # noqa: BLE001
                return jsonify({"error": str(exc)}), 500

        payload = request.get_json(silent=True) or {}
        try:
            updated = apply_action(config_path, payload)
        except ConfigEditError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            logger.exception("config edit failed")
            return jsonify({"error": f"Could not apply edit: {exc}"}), 500

        restarting = False
        if on_config_change is not None:
            on_config_change()
            restarting = True
        logger.info(f"dashboard applied config action: {payload.get('action')}")
        return jsonify({"ok": True, "config": updated, "restarting": restarting})

    @app.route("/api/log")
    def api_log():
        try:
            want = min(_MAX_LOG_TAIL, max(1024, int(request.args.get("bytes", 40000))))
        except ValueError:
            want = 40000
        try:
            size = _LOG_PATH.stat().st_size
            with _LOG_PATH.open("rb") as fh:
                fh.seek(max(0, size - want))
                data = fh.read()
            if size > want:
                data = data.split(b"\n", 1)[-1]
            return app.response_class(data, mimetype="text/plain")
        except OSError:
            return app.response_class(b"", mimetype="text/plain")

    def _serve():
        logger.info(f"Web dashboard: http://localhost:{port}")
        try:
            from waitress import serve

            serve(app, host="0.0.0.0", port=port, threads=8, ident=None)
        except ImportError:
            app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    threading.Thread(target=_serve, name="dashboard", daemon=True).start()
