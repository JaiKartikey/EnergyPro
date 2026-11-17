"""
RFID cards / students (Account page).
    GET  /api/users                                         list all cards
    POST /api/users {action: "add", name, roll_no, room, rfid_uid, balance}
    POST /api/users {action: "toggle", id}                  block / unblock
    POST /api/users {action: "delete", id}
"""
from flask import Blueprint, jsonify

import config
from core.db import commit, execute, insert, query, query_one
from core.models import get_device, get_user, log_event, public_user
from core.utils import ApiError, body, normalize_uid, num
from logic.billing import add_money

bp = Blueprint("users", __name__)


@bp.get("/api/users")
def list_users():
    users = query("SELECT * FROM users ORDER BY name")
    return jsonify(ok=True, users=[public_user(u) for u in users], active_user_id=get_device()["active_user_id"])


@bp.post("/api/users")
def change_user():
    data = body()
    action = data.get("action")
    if action == "add":
        return add_user(data)
    if action in ("toggle", "delete"):
        return block_or_delete(action, int(data.get("id") or 0))
    raise ApiError("action must be add, toggle or delete")


def add_user(data):
    name = str(data.get("name") or "").strip()
    uid = normalize_uid(data.get("rfid_uid"))
    room = str(data.get("room") or "").strip()[:20] or None
    roll = str(data.get("roll_no") or "").strip()[:20] or None
    opening = num(data.get("balance")) or 0.0

    if not name or len(name) > 80:
        raise ApiError("Name is required (max 80 characters)")
    if not 4 <= len(uid) <= 20:
        raise ApiError("RFID UID must be 4-20 hex characters, e.g. DEADBEEF")
    if not 0 <= opening <= 100000:
        raise ApiError("Opening balance must be between 0 and 100000")
    if query_one("SELECT id FROM users WHERE rfid_uid = %s", (uid,)):
        raise ApiError(f"Card {uid} is already registered")

    new_id = insert("INSERT INTO users (name, roll_no, room, rfid_uid, balance) VALUES (%s, %s, %s, %s, 0)",
                    (name, roll, room, uid))
    if opening > 0:
        add_money({"id": new_id, "name": name, "balance": 0.0}, opening, kind="opening")
    log_event("user_added", f"Registered {name} (card {uid})", uid, new_id)
    commit()
    return jsonify(ok=True, id=new_id)


def block_or_delete(action, user_id):
    user = get_user(user_id, lock=True)
    if user is None:
        raise ApiError("User not found", 404)
    dev = get_device(lock=True)
    blocking = action == "delete" or user["active"] == 1

    # Blocking or deleting the logged-in student ends their session and cuts the supply.
    if dev["active_user_id"] == user["id"] and blocking:
        execute("UPDATE device_state SET relay_on = 0, active_user_id = NULL WHERE id = %s", (config.DEVICE_ID,))

    if action == "delete":
        execute("DELETE FROM users WHERE id = %s", (user["id"],))
        log_event("user_deleted", f"Deleted {user['name']} (card {user['rfid_uid']})", user["rfid_uid"])
    else:
        execute("UPDATE users SET active = 1 - active WHERE id = %s", (user["id"],))
        log_event("user_blocked" if blocking else "user_unblocked",
                  ("Blocked " if blocking else "Unblocked ") + user["name"], user["rfid_uid"], user["id"])
    commit()
    return jsonify(ok=True)
