"""
EnergyPro - Smart Hostel Electricity Control System (Python backend).

START HERE. This file only builds the web app and plugs the pieces together:

    config.py            settings you edit (database login, device key, port)
    core/                shared building blocks
        db.py            MySQL connection + query helpers
        utils.py         small helpers (ApiError, num, normalize_uid, now)
        models.py        settings, room node, students, activity log
    logic/               the rules of the system
        billing.py       prepaid billing and recharges
        rfid.py          card login / logout and the room push-button
        protection.py    fault & theft detection, automatic cut-offs
    routes/              the web addresses (one file per group)
        auth.py          /api/login, /api/logout     <- optional dashboard password
        device.py        POST /api/device/sync       <- ESP32
        dashboard.py     /api/status, /api/history, /api/events, /api/clear
        control.py       /api/control
        recharge.py      /api/recharge
        users.py         /api/users
        settings.py      /api/settings
    static/              the dashboard web page (HTML / CSS / JS)

Run locally:   python app.py        then open http://localhost:5000
On Render:     gunicorn app:app     (see render.yaml and README.md)
"""
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from core.db import close_db
from core.utils import ApiError
from routes import auth, control, dashboard, device, recharge, settings, users

STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=None)
app.secret_key = config.SECRET_KEY               # signs the dashboard login cookie
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.BEHIND_PROXY,   # cookie only over HTTPS when hosted
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
if config.BEHIND_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)   # trust Render's proxy headers

# Plug in every group of web addresses.
for module in (auth, device, dashboard, control, recharge, users, settings):
    app.register_blueprint(module.bp)

# Check the dashboard login before every request (does nothing if ADMIN_PASSWORD is empty).
app.before_request(auth.login_required)

# Close the MySQL connection after every request.
app.teardown_appcontext(close_db)


@app.errorhandler(Exception)
def handle_error(e):
    """Every error goes back to the browser / ESP32 as JSON: {"ok": false, "error": "..."}"""
    if isinstance(e, ApiError):
        return jsonify(ok=False, error=e.message), e.status
    if isinstance(e, HTTPException):          # 404 not found, 405 wrong method, ...
        return jsonify(ok=False, error=e.description), e.code
    app.logger.exception(e)
    return jsonify(ok=False, error=str(e)), 500


# ---- The dashboard page itself ----
@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(STATIC_DIR / "assets", filename)


if __name__ == "__main__":
    print(f"EnergyPro running on http://localhost:{config.PORT}")
    # threaded=True lets the ESP32 and several browsers be served at the same time
    app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False)
