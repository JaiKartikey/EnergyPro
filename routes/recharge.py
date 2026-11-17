"""
POST /api/recharge  {amount, user_id?}

Prepaid top-up. Without user_id it recharges the student currently logged in at the room.
"""
from flask import Blueprint, jsonify

from core.db import commit
from core.models import get_device, get_user
from core.utils import ApiError, body, num
from logic.billing import add_money

bp = Blueprint("recharge", __name__)


@bp.post("/api/recharge")
def recharge():
    data = body()
    amount = num(data.get("amount"))
    if amount is None or not 1 <= amount <= 100000:
        raise ApiError("Enter an amount between Rs 1 and Rs 100000")
    amount = round(amount, 2)

    user_id = data.get("user_id") or get_device()["active_user_id"]
    if user_id is None:
        raise ApiError("No student is logged in - pick a user on the Account page.", 409)
    user = get_user(int(user_id), lock=True)
    if user is None:
        raise ApiError("User not found", 404)

    new_balance = add_money(user, amount)
    commit()
    return jsonify(ok=True, user_id=user["id"], name=user["name"], balance=round(new_balance, 4))
