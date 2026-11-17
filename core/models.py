"""
Reading and writing the app's main data: settings, the room node (device_state),
students (users) and the activity log (events).
"""
from datetime import datetime

import config
from core.db import execute, query, query_one
from core.utils import ApiError, now

# ---------------- Settings ----------------
# name -> type
SETTING_TYPES = {
    "tariff_per_kwh": float, "auto_cutoff": bool, "low_balance": float,
    "volt_min": float, "volt_max": float, "theft_current": float, "poll_ms": int,
}
# used when a row is missing from the settings table
SETTING_DEFAULTS = {
    "tariff_per_kwh": "8", "auto_cutoff": "1", "low_balance": "20",
    "volt_min": "180", "volt_max": "260", "theft_current": "0.010", "poll_ms": "2000",
}
# allowed range for each number setting (checked when saving from the Settings page)
SETTING_LIMITS = {
    "tariff_per_kwh": (0, 10000), "low_balance": (0, 100000), "volt_min": (50, 300),
    "volt_max": (100, 400), "theft_current": (0, 10), "poll_ms": (500, 60000),
}


def to_setting(kind, raw):
    """Convert a stored text value to its real type."""
    if kind is bool:
        return str(raw).lower() in ("1", "true", "on", "yes")
    return kind(float(raw))


def settings():
    """All settings as a dict, e.g. {"tariff_per_kwh": 8.0, "auto_cutoff": True, ...}"""
    rows = {r["k"]: r["v"] for r in query("SELECT k, v FROM settings")}
    return {k: to_setting(kind, rows.get(k, SETTING_DEFAULTS[k])) for k, kind in SETTING_TYPES.items()}


# ---------------- Room node ----------------
def get_device(lock=False):
    """The device_state row. lock=True holds it until commit, so two syncs can't clash."""
    sql = "SELECT * FROM device_state WHERE id = %s" + (" FOR UPDATE" if lock else "")
    dev = query_one(sql, (config.DEVICE_ID,))
    if dev is None:
        raise ApiError("Device row missing - import schema.sql", 500)
    return dev


def device_online(dev, poll_ms):
    """Online = the ESP32 synced within the last 3 sync intervals (at least 10 s)."""
    if not dev["last_seen"]:
        return False
    age = datetime.now() - datetime.strptime(dev["last_seen"], "%Y-%m-%d %H:%M:%S")
    return age.total_seconds() <= max(10, poll_ms * 3 / 1000)


# ---------------- Students ----------------
def get_user(user_id, lock=False):
    if user_id is None:
        return None
    return query_one("SELECT * FROM users WHERE id = %s" + (" FOR UPDATE" if lock else ""), (user_id,))


def public_user(u):
    """The fields of a student the dashboard shows."""
    if not u:
        return None
    return {
        "id": u["id"], "name": u["name"], "roll_no": u["roll_no"], "room": u["room"],
        "rfid_uid": u["rfid_uid"], "balance": round(u["balance"], 4),
        "active": bool(u["active"]), "created_at": u.get("created_at"),
    }


# ---------------- Activity log ----------------
def log_event(kind, message, uid=None, user_id=None):
    """Add a line to the activity log shown on the Control page."""
    execute(
        "INSERT INTO events (device_id, type, message, rfid_uid, user_id, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
        (config.DEVICE_ID, kind, message[:255], uid, user_id, now()),
    )
