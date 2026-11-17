"""
Fake ESP32 node for testing without hardware. Sends exactly what the firmware sends
to POST /api/device/sync and applies the relay state the server returns.

    python simulate.py                     (server at http://127.0.0.1:5000)
    python simulate.py --scan DEADBEEF     (tap the demo card straight away)
    python simulate.py --watts 60          (bigger load = balance falls faster)

While it runs, type a command and press Enter:
    <card UID>   tap a card, e.g. DEADBEEF     b          press the room button
    t            toggle theft (load draws current even with relay OFF)
    v <volts>    force line voltage, e.g. "v 270" (fault); "v" alone = normal
    x            toggle PZEM sensor failure (sends nulls)
    q            quit
"""
import argparse
import json
import random
import re
import threading
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser(description="Fake ESP32 room node")
# 127.0.0.1 rather than "localhost": on Windows "localhost" tries IPv6 first and adds ~2 s per request.
parser.add_argument("--url", default="http://127.0.0.1:5000")
parser.add_argument("--key", default="change-me-device-key")
parser.add_argument("--watts", type=float, default=7.3)
parser.add_argument("--scan", default="", help="card UID to tap on start")
args = parser.parse_args()

SYNC_URL = args.url.rstrip("/") + "/api/device/sync"

# Simulated node state
state = {
    "relay": False, "poll_ms": 2000, "uid": "", "button": False,
    "theft": False, "sensor_dead": False, "forced_volts": None,
    "volts": 231.0, "energy_wh": 1234.5, "last_t": time.time(),
}
wake = threading.Event()         # set() = sync now instead of waiting for the next interval


def make_reading():
    now = time.time()
    hours = (now - state["last_t"]) / 3600
    state["last_t"] = now
    state["volts"] = min(236, max(228, state["volts"] + random.uniform(-0.4, 0.4)))
    v = state["forced_volts"] or state["volts"]
    load_on = state["relay"] or state["theft"]
    p = args.watts * random.uniform(0.97, 1.03) if load_on else 0.0
    pf = 0.99 if load_on else 0.0
    i = p / (v * pf) if load_on else 0.0
    state["energy_wh"] += p * hours
    if state["sensor_dead"]:
        return dict.fromkeys(["voltage", "current", "power", "energy_wh", "frequency", "pf"])
    return {"voltage": round(v, 1), "current": round(i, 3), "power": round(p, 1),
            "energy_wh": round(state["energy_wh"], 3), "frequency": 50.0, "pf": pf}


def sync():
    payload = make_reading()
    payload.update(relay=state["relay"], rssi=random.randint(-62, -52))
    if state["uid"]:
        payload["uid"] = state["uid"]
    if state["button"]:
        payload["button"] = True
    state["uid"], state["button"] = "", False

    req = urllib.request.Request(
        SYNC_URL, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Device-Key": args.key},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as e:
        print("sync failed:", e.code, e.read().decode()[:120])
        return
    except (urllib.error.URLError, OSError) as e:
        print("sync failed:", e)
        return

    state["relay"] = data["relay"]
    state["poll_ms"] = data.get("poll_ms") or 2000
    who = f"{data['user']['name']} Rs {data['balance']:.2f}" if data["user"] else "no user"
    flags = " ".join(name for name, on in (("FAULT", data["fault"]), ("THEFT", data["theft"]), ("LOW", data["low_balance"])) if on)
    print(f"{time.strftime('%H:%M:%S')}  {payload['voltage'] or '--':>5} V  {payload['power'] if payload['power'] is not None else '--':>5} W"
          f"  relay {'ON ' if state['relay'] else 'OFF'}  {who}"
          + (f"  [{flags}]" if flags else "") + (f"  > {data['message']}" if data["message"] else ""))


def read_commands():
    while True:
        try:
            cmd = input().strip()
        except EOFError:                 # no keyboard (e.g. run in the background) - just keep syncing
            return
        if cmd == "q":
            os_exit()
        elif cmd == "b":
            state["button"] = True
        elif cmd == "t":
            state["theft"] = not state["theft"]
            print("theft simulation", "ON" if state["theft"] else "OFF")
        elif cmd == "x":
            state["sensor_dead"] = not state["sensor_dead"]
            print("sensor failure", "ON" if state["sensor_dead"] else "OFF")
        elif cmd.startswith("v"):
            try:
                state["forced_volts"] = float(cmd[1:]) or None
            except ValueError:
                state["forced_volts"] = None
            print("voltage", state["forced_volts"] or "normal")
        elif re.fullmatch(r"[0-9a-fA-F: ]{4,}", cmd):
            state["uid"] = re.sub(r"[^0-9a-fA-F]", "", cmd).upper()
        elif cmd:
            print("commands: <UID> | b | t | v <volts> | x | q")
        wake.set()


def os_exit():
    import os
    os._exit(0)


if __name__ == "__main__":
    if args.scan:
        state["uid"] = re.sub(r"[^0-9a-fA-F]", "", args.scan).upper()
    print(f"Simulated node -> {SYNC_URL}  (load {args.watts} W)")
    print("Type a card UID (demo card: DEADBEEF) and press Enter. b = button, t = theft, v 270 = fault, x = sensor fail, q = quit")
    threading.Thread(target=read_commands, daemon=True).start()
    try:
        while True:
            sync()
            wake.wait(state["poll_ms"] / 1000)
            wake.clear()
    except KeyboardInterrupt:
        pass
