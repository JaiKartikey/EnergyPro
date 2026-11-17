"""
EnergyPro settings.

Every value can be overridden by an environment variable of the same name. On your laptop
the defaults below are used (XAMPP MySQL). On Render you set the variables in the
dashboard (or render.yaml), so no passwords end up in the code.
"""
import os


def env(name, default):
    return os.environ.get(name, default)


# ---- MySQL ----
DB_HOST = env("DB_HOST", "127.0.0.1")
DB_PORT = int(env("DB_PORT", "3306"))
DB_NAME = env("DB_NAME", "smart_hostel_v2")
DB_USER = env("DB_USER", "root")
DB_PASS = env("DB_PASS", "")
# Cloud MySQL providers require an encrypted connection. Set this to the path of the
# provider's CA certificate file (e.g. ca.pem). Leave empty for local XAMPP.
DB_SSL_CA = env("DB_SSL_CA", "")

# ---- IoT node ----
# Shared secret the ESP32 sends in the X-Device-Key header (must match the firmware).
DEVICE_KEY = env("DEVICE_KEY", "change-me-device-key")
# Row in device_state this server controls (prototype = one room node).
DEVICE_ID = int(env("DEVICE_ID", "1"))

# ---- Dashboard login ----
# Empty = no login (fine on your own laptop). Set a password before putting the
# dashboard on the internet, otherwise anyone could switch the supply or add balance.
ADMIN_PASSWORD = env("ADMIN_PASSWORD", "")
# Signs the login cookie. Use a long random string in production.
SECRET_KEY = env("SECRET_KEY", "dev-only-change-me")

# ---- Web server ----
HOST = env("HOST", "0.0.0.0")       # 0.0.0.0 = reachable from the ESP32 on the same Wi-Fi
PORT = int(env("PORT", "5000"))     # Render sets PORT automatically
# "1" when running behind a hosting proxy (Render), so the real client IP is logged.
BEHIND_PROXY = env("BEHIND_PROXY", "0") == "1"
