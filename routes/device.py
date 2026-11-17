"""
POST /api/device/sync - the ONLY address the ESP32 talks to.

Called every poll_ms (2 s by default), and straight away when a card is tapped
or the room button is pressed.

Request  (JSON + header X-Device-Key):
    {voltage, current, power, energy_wh, frequency, pf, relay, uid?, button?, rssi?}
Response (JSON):
    {ok, relay, authorized, user, balance, tariff, fault, theft, low_balance, message, poll_ms}

The server decides the relay state; the ESP32 just applies "relay" from the response.
"""
import hmac
import random

from flask import Blueprint, jsonify, request

import config
from core.db import commit, execute
from core.models import get_device, get_user, settings
from core.utils import ApiError, body, minutes_ago, normalize_uid, now, num
from logic import billing, protection, rfid

bp = Blueprint("device", __name__)


@bp.post("/api/device/sync")
def sync():
    if not hmac.compare_digest(config.DEVICE_KEY, request.headers.get("X-Device-Key", "")):
        raise ApiError("Invalid device key", 401)

    data = body()
    s = settings()
    dev = get_device(lock=True)
    relay_was_on = bool(dev["relay_on"])        # relay state while this reading was measured

    reading = {key: num(data.get(key)) for key in ("voltage", "current", "power", "energy_wh", "frequency", "pf")}
    room = {
        "relay": relay_was_on,
        "user": get_user(dev["active_user_id"], lock=True),
        "message": "",
        "authorized": None,
    }

    # 1. Prepaid billing - charged to whoever was logged in while the energy was used,
    #    before a card tap below can switch students.
    billed_user = room["user"]
    new_wh, cost, baseline = billing.bill_energy(dev["last_energy_wh"], reading["energy_wh"], billed_user, s)

    # 2. Fault & theft detection
    fault, theft, voltage_fault = protection.check_fault_and_theft(reading, relay_was_on, dev, s)

    # 3. RFID card tapped?
    uid = normalize_uid(data.get("uid"))
    if uid:
        rfid.handle_card(room, uid, s)

    # 4. Room push-button pressed?
    if data.get("button"):
        rfid.handle_button(room, s)

    # 5. Safety cut-offs (voltage fault, no student, no balance)
    protection.apply_cutoffs(room, voltage_fault, reading["voltage"], s)

    # 6. Save the reading and the new room state
    save(reading, relay_was_on, billed_user, cost, fault, theft)
    user = room["user"]
    rssi = data.get("rssi")
    execute(
        """UPDATE device_state
              SET relay_on = %s, active_user_id = %s, last_energy_wh = %s,
                  total_energy_wh = total_energy_wh + %s, total_spent = total_spent + %s,
                  fault = %s, theft = %s, last_seen = %s, ip = %s, rssi = %s
            WHERE id = %s""",
        (int(room["relay"]), user["id"] if user else None, baseline, new_wh, cost, int(fault), int(theft),
         now(), request.remote_addr, int(rssi) if isinstance(rssi, (int, float)) else None, config.DEVICE_ID),
    )
    commit()

    return jsonify(
        ok=True,
        relay=room["relay"],
        authorized=room["authorized"],
        user={"name": user["name"], "room": user["room"]} if user else None,
        balance=round(user["balance"], 2) if user else None,
        tariff=s["tariff_per_kwh"],
        fault=fault,
        theft=theft,
        low_balance=user is not None and user["balance"] <= s["low_balance"],
        message=room["message"],
        poll_ms=s["poll_ms"],
        server_time=now(),
    )


def save(reading, relay_was_on, billed_user, cost, fault, theft):
    """Store one row for the Reports charts (and occasionally drop rows older than 7 days)."""
    execute(
        """INSERT INTO readings (device_id, created_at, voltage, current, power, energy_wh, frequency, pf,
                                 relay_on, user_id, balance, cost, fault, theft)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (config.DEVICE_ID, now(), reading["voltage"], reading["current"], reading["power"], reading["energy_wh"],
         reading["frequency"], reading["pf"], int(relay_was_on),
         billed_user["id"] if billed_user else None, billed_user["balance"] if billed_user else None,
         cost, int(fault), int(theft)),
    )
    if random.randint(1, 500) == 1:
        execute("DELETE FROM readings WHERE created_at < %s", (minutes_ago(7 * 24 * 60),))
