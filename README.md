# EnergyPro – Smart Hostel Electricity Control System

An ESP32 room node (RFID, PZEM-004T energy meter, relay, TFT, push button) talks over Wi-Fi to a **Python (Flask)** server with a **MySQL** database. The server handles RFID login, prepaid billing, fault and theft detection and automatic cut-offs, and serves the web dashboard. The code is split into small files, and each file does one job.

## Files – what each one does

```
EnergyPro/
├─ app.py                 START HERE – builds the Flask app and plugs all the pieces together
├─ config.py              settings (DB login, device key, password, port) – read from env vars on Render
│
├─ core/                  shared building blocks
│  ├─ db.py               MySQL connection + query() / execute() / insert() / commit()
│  ├─ utils.py            small helpers: ApiError, num(), normalize_uid(), now()
│  └─ models.py           settings, room node (device_state), students, activity log
│
├─ logic/                 the RULES of the system (no web code here)
│  ├─ billing.py          prepaid billing: new Wh × tariff → deduct from balance; recharges
│  ├─ rfid.py             card login / logout, unknown & blocked cards, room push-button
│  └─ protection.py       voltage/sensor fault, theft detection, automatic cut-offs
│
├─ routes/                the WEB ADDRESSES – one file per group
│  ├─ device.py           POST /api/device/sync          ← the ESP32 (steps 1–6 call logic/)
│  ├─ dashboard.py        /api/status · /api/history · /api/events · /api/clear
│  ├─ control.py          /api/control                    Power ON / OFF / end session
│  ├─ recharge.py         /api/recharge                   prepaid top-up
│  ├─ users.py            /api/users                      register / block / delete cards
│  ├─ settings.py         /api/settings                   tariff and limits
│  └─ auth.py             /api/login · /api/logout        optional dashboard password
│
├─ static/                the dashboard page (HTML / CSS / JavaScript)
├─ firmware/SmartHostelNode/SmartHostelNode.ino   ESP32 code
├─ simulate.py            fake ESP32 for testing without hardware
├─ schema.sql             MySQL tables + default settings + demo card DEADBEEF (local XAMPP MySQL)
├─ schema_tidb.sql        the same tables for the TiDB Cloud SQL Editor (no USE statement)
├─ requirements.txt       flask, pymysql, gunicorn
└─ render.yaml            one-click deployment settings for Render
```

### What happens when the ESP32 syncs (every 2 s)

`routes/device.py` receives the reading and runs these steps in order:

| Step | File | What happens |
|---|---|---|
| 1 | `logic/billing.py` → `bill_energy()` | New Wh since the last sync × tariff is deducted from the logged-in student |
| 2 | `logic/protection.py` → `check_fault_and_theft()` | Voltage out of range or missing sensor data → FAULT. Current flowing while the relay is OFF → THEFT |
| 3 | `logic/rfid.py` → `handle_card()` | If a card was tapped: login, logout, or refuse |
| 4 | `logic/rfid.py` → `handle_button()` | If the room button was pressed: toggle the supply |
| 5 | `logic/protection.py` → `apply_cutoffs()` | Cut the supply on a voltage fault, when no student is logged in, or at ₹0 |
| 6 | `routes/device.py` → `save()` | Save the reading and the new relay state, then reply to the ESP32 |

## Run on your laptop

You need XAMPP (only its **MySQL** part) and Python 3.10 or newer.

1. Start **MySQL** in the XAMPP Control Panel.
2. Create the database:
   ```bash
   C:\xampp\mysql\bin\mysql.exe -u root < schema.sql
   ```
3. One-time Python setup, from this folder:
   ```bash
   python -m venv .venv
   ```
   ```bash
   .venv\Scripts\pip install -r requirements.txt
   ```
4. Start the server:
   ```bash
   .venv\Scripts\python app.py
   ```
   Then open http://localhost:5000.
5. Test without hardware, in a second terminal:
   ```bash
   .venv\Scripts\python simulate.py --scan DEADBEEF
   ```
   While the simulator runs you can type: another UID (an unknown card), `b` (button), `t` (theft), `v 270` (fault), `x` (sensor failure), `q` (quit).
6. **Real ESP32 on the same Wi-Fi:** set `SERVER_URL` to `http://<laptop IP>:5000/api/device/sync` in the firmware. Then allow the port through the firewall from an **Administrator** PowerShell:
   ```bash
   netsh advfirewall firewall add rule name="EnergyPro 5000" dir=in action=allow protocol=TCP localport=5000
   ```

## Deploy on Render (online)

Render runs the Python app, but **it has no MySQL**, so the database has to live with a cloud MySQL provider. The app connects to it using environment variables, and the code itself doesn't change.

```
ESP32 ──HTTPS──▶ Render (Flask app, Singapore) ──TLS──▶ TiDB Cloud Starter (MySQL-compatible, Singapore)
Browser ─HTTPS──▶       ▲
```

1. **Create the database** on **TiDB Cloud Starter** (free; keep the monthly spending limit at $0). Choose the **Singapore** region. Under **Connect**, generate a password and note the host, port (`4000`) and user (`xxxx.root`).
2. **Load the tables.** Open the instance's **SQL Editor**, paste all of `schema_tidb.sql`, click inside the editor and press **Ctrl + Shift + Enter** to run every statement. The last statement lists the 6 tables. (Plain **Run** only runs the statement under the cursor.)
3. **Encryption certificate.** Nothing to download: set `DB_SSL_CA=/etc/ssl/certs/ca-certificates.crt` (Render's built-in certificates). `DB_NAME` is `smart_hostel_v2`.
4. **Put the code on GitHub.** Push the `EnergyPro` folder to a GitHub repository. `.gitignore` already leaves out `.venv`.
5. **Create the service on Render.** Choose **New → Blueprint** and pick the repo; Render reads `render.yaml`. Fill in the values it asks for: `DEVICE_KEY`, `ADMIN_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_SSL_CA`.
6. **Point the ESP32 at Render.** Set `SERVER_URL = "https://<your-app>.onrender.com/api/device/sync"` and the same `DEVICE_KEY`, then upload. The firmware switches to HTTPS automatically when the URL starts with `https`.

**Things to know about hosting:**
* **Login:** once `ADMIN_PASSWORD` is set, the dashboard asks for it. The ESP32 doesn't need it, because it uses `DEVICE_KEY`.
* **Free Render services sleep after ~15 minutes without traffic**, and take up to about a minute to wake up. While the ESP32 syncs every 2 s the service stays awake. After a long power cut, the first syncs fail until it wakes up.
* **SQLite is not an option on Render's free plan**, because files are wiped on every restart or deploy, and all balances would be lost. Use a cloud MySQL.
* **Time zone:** `render.yaml` sets `TZ=Asia/Kolkata` so the timestamps match Indian time.
* **Security:** the firmware uses `setInsecure()`, which keeps the data encrypted but doesn't verify the server's certificate. That's acceptable for a prototype. For a real deployment, load the CA certificate with `setCACert()`.

## Firmware

1. In the Arduino IDE, install the **esp32** board package (Espressif) and select **ESP32 Dev Module**.
2. Install these libraries from Library Manager: **MFRC522**, **PZEM004Tv30** (Jakub Mandula), **Adafruit ST7735 and ST7789** (+ **Adafruit GFX**), **ArduinoJson 7.x**.
3. At the top of `SmartHostelNode.ino`, set `WIFI_SSID`, `WIFI_PASS`, `SERVER_URL` and `DEVICE_KEY`, then upload.

### Pin map

| Module | Module pin | ESP32 |
|---|---|---|
| MFRC522 | SDA/SS · SCK · MOSI · MISO · RST · 3.3V · GND | GPIO5 · 18 · 23 · 19 · 22 · 3V3 · GND |
| ST7735 TFT | CS · SCL/SCK · SDA/MOSI · A0/DC · RESET · VCC · LED | GPIO15 · 18 · 23 · 2 · 4 · 3V3 · 3V3 |
| PZEM-004T v3 | TX · RX · 5V · GND | GPIO16 (RX2) · GPIO17 (TX2) · VIN 5V · GND |
| Relay module | IN · VCC · GND | GPIO26 · VIN 5V · GND |
| Push button | one leg · other leg | GPIO27 · GND |

The RFID reader and the TFT share the SPI bus and use separate CS pins. The PZEM-004T only answers when 230 V AC is connected to its input terminals. Its TX line is 5 V logic, so a 1 kΩ series resistor on GPIO16 is a sensible precaution. Most blue relay modules are active-LOW; if yours isn't, set `RELAY_ACTIVE_LOW false`. **Mains wiring (relay contacts, PZEM input, CT, bulb) must be insulated and checked by your lab instructor before you power it.**

## Notes

* **Tariff:** the default is ₹8/kWh. For a fast demo with a small bulb, set about ₹950/kWh on the Settings page, and say so in the report.
* **Limitations:** there's one room node (`DEVICE_ID`), and the ESP32 polls every 2 s rather than using MQTT.
