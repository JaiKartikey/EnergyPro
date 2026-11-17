"""
Dashboard login - only switched on when ADMIN_PASSWORD is set (config.py / environment).
    GET  /api/me       is a login needed, and are we logged in?
    POST /api/login    {password}
    POST /api/logout

The ESP32 never logs in: it proves who it is with the X-Device-Key header instead.
"""
import hmac

from flask import Blueprint, jsonify, request, session

import config
from core.utils import ApiError, body

bp = Blueprint("auth", __name__)

# Addresses that work without logging in.
OPEN_PATHS = {"/api/me", "/api/login", "/api/device/sync"}


def login_required():
    """Runs before every request (registered in app.py)."""
    if not config.ADMIN_PASSWORD:
        return                                   # no password set -> dashboard is open
    if request.path.startswith("/api/") and request.path not in OPEN_PATHS and not session.get("admin"):
        raise ApiError("Please log in", 401)


@bp.get("/api/me")
def me():
    needed = bool(config.ADMIN_PASSWORD)
    return jsonify(ok=True, login_required=needed, logged_in=not needed or bool(session.get("admin")))


@bp.post("/api/login")
def login():
    if config.ADMIN_PASSWORD:
        typed = str(body().get("password", "")).encode()
        if not hmac.compare_digest(typed, config.ADMIN_PASSWORD.encode()):
            raise ApiError("Wrong password", 401)
        session.permanent = True
        session["admin"] = True
    return jsonify(ok=True)


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)
