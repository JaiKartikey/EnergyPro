"""
GET  /api/settings   current settings + room/node name
POST /api/settings   update any of: tariff_per_kwh, auto_cutoff, low_balance, volt_min,
                     volt_max, theft_current, poll_ms, device_name
"""
from flask import Blueprint, jsonify, request

import config
from core.db import commit, execute
from core.models import SETTING_LIMITS, SETTING_TYPES, get_device, log_event, settings, to_setting
from core.utils import ApiError, body, num

bp = Blueprint("settings", __name__)


@bp.route("/api/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        save_settings(body())
    return jsonify(ok=True, settings=settings(), device_name=get_device()["name"])


def save_settings(data):
    new = settings()
    for key, kind in SETTING_TYPES.items():
        if key not in data:
            continue
        if kind is bool:
            new[key] = to_setting(bool, data[key])
            continue
        value = num(data[key])
        low, high = SETTING_LIMITS[key]
        if value is None or not low <= value <= high:
            raise ApiError(f"{key} must be between {low} and {high}")
        new[key] = kind(value)

    if new["volt_min"] >= new["volt_max"]:
        raise ApiError("volt_min must be lower than volt_max")

    for key, value in new.items():
        stored = ("1" if value else "0") if isinstance(value, bool) else str(value)
        execute("INSERT INTO settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", (key, stored))

    if "device_name" in data:
        name = str(data["device_name"]).strip()
        if not 1 <= len(name) <= 40:
            raise ApiError("Room / node name must be 1-40 characters")
        execute("UPDATE device_state SET name = %s WHERE id = %s", (name, config.DEVICE_ID))

    log_event("settings", "Settings updated from the dashboard")
    commit()
