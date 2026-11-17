"""
RFID authentication and the room push-button.

    Registered card, balance > 0     -> supply ON, student logged in
    Same card tapped again while ON  -> supply OFF, student logged out
    Different card                   -> previous student logged out, new one logged in
    Unknown or blocked card          -> refused
    Push-button                      -> toggles the supply for the logged-in student
"""
from core.db import query_one
from core.models import log_event


def handle_card(room, uid, s):
    """A card with this UID was just tapped on the MFRC522 reader."""
    card = query_one("SELECT * FROM users WHERE rfid_uid = %s FOR UPDATE", (uid,))

    if card is None or not card["active"]:
        room["authorized"] = False
        room["message"] = "Card blocked" if card else "Unknown card"
        log_event("rfid_denied", f"{room['message']}: {uid}", uid, card["id"] if card else None)
        return

    room["authorized"] = True
    current = room["user"]
    same_student = current is not None and current["id"] == card["id"]

    if same_student and room["relay"]:
        room["relay"], room["user"] = False, None
        room["message"] = "Goodbye " + card["name"]
        log_event("rfid_logout", card["name"] + " ended the session", uid, card["id"])
        return

    if current is not None and not same_student:
        log_event("rfid_logout", current["name"] + " was logged out by another card", user_id=current["id"])

    room["user"] = card
    if s["auto_cutoff"] and card["balance"] <= 0:
        room["relay"] = False
        room["message"] = "No balance - recharge"
        log_event("rfid_no_balance", card["name"] + " has no balance", uid, card["id"])
    else:
        room["relay"] = True
        room["message"] = "Welcome " + card["name"]
        log_event("rfid_login", card["name"] + " started a session", uid, card["id"])


def handle_button(room, s):
    """The push-button in the room was pressed."""
    user = room["user"]
    if room["relay"]:
        room["relay"] = False
        room["message"] = "Supply OFF"
        log_event("button_off", "Supply switched OFF at the room button", user_id=user["id"] if user else None)
    elif user is None:
        room["message"] = "Scan card first"
    elif s["auto_cutoff"] and user["balance"] <= 0:
        room["message"] = "No balance - recharge"
    else:
        room["relay"] = True
        room["message"] = "Supply ON"
        log_event("button_on", "Supply switched ON at the room button", user_id=user["id"])
