"""
Prepaid billing.

The PZEM-004T keeps a running energy total in Wh (like a house meter). On every sync we
bill only the increase since the previous sync:

    cost (Rs) = new Wh / 1000 * tariff (Rs per kWh)

and take it off the logged-in student's balance.
"""
from core.db import execute
from core.models import log_event
from core.utils import now


def bill_energy(last_energy_wh, energy_wh, user, s):
    """
    last_energy_wh  meter reading saved at the previous sync (None the first time)
    energy_wh       meter reading just received (None if the sensor failed)
    user            the student logged in while it was measured (None = nobody to bill)
    s               settings

    Returns (new_wh, cost, baseline) where baseline is the reading to remember for next time.
    Also lowers user["balance"] so the caller sees the new balance.
    """
    new_wh = 0.0
    baseline = last_energy_wh
    if energy_wh is not None:
        if last_energy_wh is not None and energy_wh >= last_energy_wh:
            new_wh = energy_wh - last_energy_wh
        baseline = energy_wh          # first reading, or the meter was reset: start counting from here

    cost = 0.0
    if new_wh > 0 and user is not None:
        cost = round(new_wh / 1000 * s["tariff_per_kwh"], 6)
        if cost > 0:
            before = user["balance"]
            execute("UPDATE users SET balance = balance - %s WHERE id = %s", (cost, user["id"]))
            user["balance"] = before - cost
            if before > s["low_balance"] >= user["balance"]:      # just crossed the warning level
                log_event("low_balance", f"{user['name']}: balance low (Rs {user['balance']:.2f})", user_id=user["id"])

    return new_wh, cost, baseline


def add_money(user, amount, kind="recharge"):
    """Add `amount` rupees to a student's balance and record it. Returns the new balance."""
    new_balance = user["balance"] + amount
    execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, user["id"]))
    execute(
        "INSERT INTO transactions (user_id, type, amount, balance_after, created_at) VALUES (%s, %s, %s, %s, %s)",
        (user["id"], kind, amount, new_balance, now()),
    )
    if kind == "recharge":
        log_event("recharge", f"{user['name']} recharged Rs {amount:.2f} (balance Rs {new_balance:.2f})", user_id=user["id"])
    return new_balance
