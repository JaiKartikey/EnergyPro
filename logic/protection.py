"""
Fault detection, theft detection and automatic cut-offs.

    Voltage outside volt_min..volt_max      -> FAULT, supply cut
    PZEM-004T sends no data                 -> FAULT (sensor)
    Current flowing while the relay is OFF  -> THEFT alert (load is bypassing the relay)
    Balance reaches Rs 0                    -> supply cut (if auto_cutoff is on)
"""
from core.models import log_event


def check_fault_and_theft(reading, relay_was_on, dev, s):
    """
    reading       {"voltage", "current", ...} from the ESP32 (None where the sensor failed)
    relay_was_on  relay state while the reading was measured
    dev           device_state row (holds the previous fault / theft flags)

    Returns (fault, theft, voltage_fault). Logs an event only when a flag changes.
    """
    v, i = reading["voltage"], reading["current"]
    sensor_ok = None not in (v, i, reading["power"], reading["energy_wh"])

    voltage_fault = v is not None and not (s["volt_min"] <= v <= s["volt_max"])
    fault = not sensor_ok or voltage_fault
    theft = sensor_ok and not relay_was_on and i > s["theft_current"]

    if fault and not dev["fault"]:
        log_event("fault", f"Voltage out of range: {v:.1f} V" if sensor_ok else "Energy sensor (PZEM-004T) not responding")
    elif not fault and dev["fault"]:
        log_event("fault_cleared", "Readings back to normal")

    if theft and not dev["theft"]:
        log_event("theft", f"{i:.3f} A drawn while supply is OFF - possible bypass")
    elif not theft and dev["theft"]:
        log_event("theft_cleared", "No current while supply is OFF")

    return fault, theft, voltage_fault


def apply_cutoffs(room, voltage_fault, voltage, s):
    """Last safety pass before the relay state is sent to the ESP32."""
    user = room["user"]

    if room["relay"] and voltage_fault:
        room["relay"] = False
        room["message"] = "Voltage fault - OFF"
        log_event("fault_cutoff", f"Supply cut: voltage {voltage:.1f} V outside {s['volt_min']:g}-{s['volt_max']:g} V")

    if room["relay"] and user is None:
        room["relay"] = False                  # never supply power without a logged-in student

    if room["relay"] and s["auto_cutoff"] and user["balance"] <= 0:
        room["relay"] = False
        room["message"] = "Balance exhausted"
        log_event("cutoff", f"{user['name']}'s balance ran out - supply cut", user_id=user["id"])
