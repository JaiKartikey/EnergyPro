"""
Read-only data for the dashboard pages, plus clearing the chart history.
    GET  /api/status    live tiles + system status (browser polls every 2 s)
    GET  /api/history   last N readings for the Reports charts
    GET  /api/events    activity log for the Control page
    POST /api/clear     delete chart history (balances and totals are kept)
"""
from flask import Blueprint, jsonify, request

import config
from core.db import commit, execute, query, query_one
from core.models import device_online, get_device, get_user, log_event, public_user, settings
from core.utils import minutes_ago, now

bp = Blueprint("dashboard", __name__)


@bp.get("/api/status")
def status():
    dev = get_device()
    s = settings()
    user = get_user(dev["active_user_id"])
    r = query_one("SELECT * FROM readings WHERE device_id = %s ORDER BY id DESC LIMIT 1", (config.DEVICE_ID,))

    # Most recent unregistered card (last 10 min), so the Account page can offer to register it.
    unknown = query_one(
        """SELECT e.rfid_uid, e.created_at FROM events e
             LEFT JOIN users u ON u.rfid_uid = e.rfid_uid
            WHERE e.device_id = %s AND e.type = 'rfid_denied' AND u.id IS NULL AND e.created_at >= %s
            ORDER BY e.id DESC LIMIT 1""",
        (config.DEVICE_ID, minutes_ago(10)),
    )

    return jsonify(
        ok=True,
        device={
            "name": dev["name"],
            "relay": bool(dev["relay_on"]),
            "online": device_online(dev, s["poll_ms"]),
            "last_seen": dev["last_seen"],
            "ip": dev["ip"],
            "rssi": dev["rssi"],
            "fault": bool(dev["fault"]),
            "theft": bool(dev["theft"]),
            "total_energy_wh": round(dev["total_energy_wh"], 4),
            "total_spent": round(dev["total_spent"], 4),
        },
        user=public_user(user),
        reading={
            "time": r["created_at"], "voltage": r["voltage"], "current": r["current"], "power": r["power"],
            "energy_wh": r["energy_wh"], "frequency": r["frequency"], "pf": r["pf"],
        } if r else None,
        settings=s,
        low_balance=user is not None and user["balance"] <= s["low_balance"],
        unknown_card=unknown,
        server_time=now(),
    )


@bp.get("/api/history")
def history():
    limit = max(10, min(500, request.args.get("limit", 50, type=int)))
    rows = query(
        """SELECT * FROM (SELECT id, created_at, voltage, current, power, balance, relay_on
                            FROM readings WHERE device_id = %s ORDER BY id DESC LIMIT %s) t
           ORDER BY id ASC""",
        (config.DEVICE_ID, limit),
    )

    def r4(x):
        return None if x is None else round(x, 4)

    readings = [{
        "t": r["created_at"][11:19],          # HH:MM:SS for the chart labels
        "voltage": r4(r["voltage"]), "current": r4(r["current"]), "power": r4(r["power"]),
        "balance": r4(r["balance"]), "relay": bool(r["relay_on"]),
    } for r in rows]

    powers = [r["power"] for r in rows if r["power"] is not None]
    dev = get_device()
    stats = {
        "peak_power": round(max(powers), 2) if powers else 0,
        "avg_power": round(sum(powers) / len(powers), 2) if powers else 0,
        "total_energy_wh": round(dev["total_energy_wh"], 4),
        "total_spent": round(dev["total_spent"], 4),
    }
    return jsonify(ok=True, readings=readings, stats=stats)


@bp.get("/api/events")
def events():
    limit = max(1, min(200, request.args.get("limit", 30, type=int)))
    rows = query(
        "SELECT id, type, message, rfid_uid, created_at FROM events WHERE device_id = %s ORDER BY id DESC LIMIT %s",
        (config.DEVICE_ID, limit),
    )
    return jsonify(ok=True, events=rows)


@bp.post("/api/clear")
def clear_history():
    deleted = execute("DELETE FROM readings WHERE device_id = %s", (config.DEVICE_ID,))
    log_event("history_cleared", "Report chart history cleared")
    commit()
    return jsonify(ok=True, deleted=deleted)
