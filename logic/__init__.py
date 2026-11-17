"""
The rules of the system, one file per job (no web / HTTP code in here):
    billing.py     prepaid billing and recharges
    rfid.py        RFID card login / logout and the room push-button
    protection.py  fault & theft detection, automatic cut-offs

Several functions take a `room` dict describing the room's live state:
    {"relay": bool, "user": student row or None, "message": str, "authorized": bool or None}
They change it in place; routes/device.py saves the final result.
"""
