"""
POST /api/control  {action: "on" | "off" | "logout"}

Remote control from the dashboard. It only changes the database; the ESP32 picks up
the new relay state on its next sync (within poll_ms).
"""
from flask import Blueprint, jsonify

import config
from core.db import commit, execute
from core.models import device_online, get_device, get_user, log_event, settings
from core.utils import ApiError, body

bp = Blueprint("control", __name__)


@bp.post("/api/control")
def control():
    action = body().get("action")
    s = settings()
    dev = get_device(lock=True)
    user = get_user(dev["active_user_id"])
    user_id = user["id"] if user else None

    if action == "on":
        if user is None:
            raise ApiError("No student is logged in. Scan a registered RFID card at the room first.", 409)
        if s["auto_cutoff"] and user["balance"] <= 0:
            raise ApiError("Balance is empty. Recharge before switching the supply on.", 409)
        if dev["fault"]:
            raise ApiError("Cannot switch on while a fault is active.", 409)
        execute("UPDATE device_state SET relay_on = 1 WHERE id = %s", (config.DEVICE_ID,))
        log_event("remote_on", "Supply switched ON from the dashboard", user_id=user_id)

    elif action == "off":
        execute("UPDATE device_state SET relay_on = 0 WHERE id = %s", (config.DEVICE_ID,))
        log_event("remote_off", "Supply switched OFF from the dashboard", user_id=user_id)

    elif action == "logout":
        execute("UPDATE device_state SET relay_on = 0, active_user_id = NULL WHERE id = %s", (config.DEVICE_ID,))
        log_event("remote_logout", (user["name"] if user else "Session") + " ended from the dashboard", user_id=user_id)

    else:
        raise ApiError("action must be on, off or logout")

    commit()
    return jsonify(ok=True, relay=action == "on", online=device_online(dev, s["poll_ms"]))
