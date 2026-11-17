"""
Web addresses (Flask Blueprints), one file per group:
    auth.py       GET /api/me, POST /api/login, /api/logout <- optional dashboard password
    device.py    POST /api/device/sync                     <- the ESP32 room node
    dashboard.py  GET  /api/status, /api/history, /api/events, POST /api/clear
    control.py    POST /api/control                         <- Power ON / OFF / end session
    recharge.py   POST /api/recharge                        <- prepaid top-up
    users.py      GET/POST /api/users                       <- RFID cards
    settings.py   GET/POST /api/settings
Each file only reads the request, calls core/ and logic/, and returns JSON.
"""
