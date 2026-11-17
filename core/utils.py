"""Small helpers with no database access."""
import math
import re
from datetime import datetime, timedelta

from flask import request


class ApiError(Exception):
    """Raise this anywhere to send {"ok": false, "error": message} back with an HTTP status code."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def body():
    """The JSON sent with the request, or {} if there was none."""
    return request.get_json(silent=True) or {}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def minutes_ago(minutes):
    return (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def num(value):
    """A number, or None. The ESP32 sends null when a PZEM-004T read fails."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def normalize_uid(uid):
    """'de:ad:be:ef' / 'DE AD BE EF' -> 'DEADBEEF'"""
    return re.sub(r"[^0-9A-Fa-f]", "", str(uid or "")).upper()
