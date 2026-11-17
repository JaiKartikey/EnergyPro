/*
 * EnergyPro – Smart Hostel Electricity Control System : ESP32 room node
 *
 * Hardware: ESP32-WROOM-32 DevKit, MFRC522 RFID (SPI), PZEM-004T v3 + CT (UART2),
 *           SRD-05VDC-SL-C relay module, 1.8" ST7735 TFT 160x128 (SPI), push button.
 *
 * Every SYNC interval (2 s by default, set from the dashboard) the node POSTs its PZEM
 * readings to  http://<server>:5000/api/device/sync  and applies the relay state the
 * server returns. An RFID scan or a button press triggers an immediate sync.
 *
 * Arduino IDE libraries (Library Manager):
 *   - MFRC522            by GithubCommunity (miguelbalboa)
 *   - PZEM004Tv30        by Jakub Mandula
 *   - Adafruit ST7735 and ST7789 Library  (+ Adafruit GFX Library)
 *   - ArduinoJson        by Benoit Blanchon  (version 7.x)
 * Board: "ESP32 Dev Module" (esp32 core by Espressif).
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <MFRC522.h>
#include <PZEM004Tv30.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>

// ======================= CONFIGURE THESE =======================
const char* WIFI_SSID  = "YOUR_WIFI_NAME";
const char* WIFI_PASS  = "YOUR_WIFI_PASSWORD";
// Laptop running "python app.py": use its Wi-Fi IP (ipconfig), port 5000.
const char* SERVER_URL = "http://192.168.1.10:5000/api/device/sync";
// Deployed on Render instead (HTTPS, no port):
// const char* SERVER_URL = "https://your-app-name.onrender.com/api/device/sync";
const char* DEVICE_KEY = "change-me-device-key";   // must match DEVICE_KEY in config.py / Render
// ===============================================================

// ---- Pin map (matches README) ----
// SPI bus shared by RFID + TFT: SCK 18, MOSI 23, MISO 19
#define RFID_SS      5
#define RFID_RST     22
#define TFT_CS       15
#define TFT_DC       2
#define TFT_RST      4
#define PZEM_RX_PIN  16   // ESP32 RX2  <- PZEM TX
#define PZEM_TX_PIN  17   // ESP32 TX2  -> PZEM RX
#define RELAY_PIN    26
#define BUTTON_PIN   27   // push button to GND (internal pull-up)

#define RELAY_ACTIVE_LOW   true    // most blue relay modules switch ON when IN is LOW
#define RELAY_MIN_GAP_MS   1000    // never switch the relay faster than this (anti-chatter)
#define OFFLINE_AFTER_MS   15000   // show OFFLINE if no good sync for this long

MFRC522 rfid(RFID_SS, RFID_RST);
Adafruit_ST7735 tft(TFT_CS, TFT_DC, TFT_RST);
PZEM004Tv30 pzem(Serial2, PZEM_RX_PIN, PZEM_TX_PIN);
WiFiClient plainClient;          // http://  (laptop on the same Wi-Fi)
WiFiClientSecure secureClient;   // https:// (cloud server, e.g. Render)

// ---- live state ----
struct Reading { float v, i, p, e_wh, f, pf; } rd = {NAN, NAN, NAN, NAN, NAN, NAN};

bool     relayOn = false;          // what the relay is doing now
bool     relayWanted = false;      // what the server asked for
uint32_t lastRelaySwitch = 0;

uint32_t pollMs = 2000;
uint32_t lastSyncAttempt = 0;
uint32_t lastSyncOk = 0;
String   pendingUid = "";
bool     pendingButton = false;

String   userName = "";
float    balance = 0;
bool     hasUser = false, fault = false, theft = false, lowBalance = false;
String   message = "";
uint32_t messageUntil = 0;

String   lastUid = "";
uint32_t lastUidAt = 0;
bool     lastButtonLevel = HIGH;
uint32_t lastButtonChange = 0;

// ------------------------------------------------------------------
void applyRelay(bool on) {
  digitalWrite(RELAY_PIN, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
  relayOn = on;
  lastRelaySwitch = millis();
}

void showMessage(const String& m, uint32_t ms = 3000) {
  message = m;
  messageUntil = millis() + ms;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(300);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) Serial.println(" connected: " + WiFi.localIP().toString());
  else Serial.println(" failed (will keep retrying)");
}

// ---- PZEM-004T ----
void readPzem() {
  rd.v  = pzem.voltage();
  rd.i  = pzem.current();
  rd.p  = pzem.power();
  float kwh = pzem.energy();
  rd.e_wh = isnan(kwh) ? NAN : kwh * 1000.0f;
  rd.f  = pzem.frequency();
  rd.pf = pzem.pf();
}

void putNum(JsonDocument& doc, const char* key, float v) {
  if (isnan(v)) doc[key] = nullptr;   // server treats null as "sensor read failed"
  else doc[key] = v;
}

// ---- RFID ----
void checkRfid() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) return;
  String uid = "";
  for (byte k = 0; k < rfid.uid.size; k++) {
    if (rfid.uid.uidByte[k] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[k], HEX);
  }
  uid.toUpperCase();
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  if (uid == lastUid && millis() - lastUidAt < 2500) return;   // ignore the same card held on the reader
  lastUid = uid;
  lastUidAt = millis();
  pendingUid = uid;
  Serial.println("Card: " + uid);
  showMessage("Card " + uid);
}

// ---- push button (debounced, triggers on press) ----
void checkButton() {
  bool level = digitalRead(BUTTON_PIN);
  if (level != lastButtonLevel && millis() - lastButtonChange > 50) {
    lastButtonChange = millis();
    lastButtonLevel = level;
    if (level == LOW) pendingButton = true;
  }
}

// ---- server sync ----
void syncWithServer() {
  lastSyncAttempt = millis();
  readPzem();

  if (WiFi.status() != WL_CONNECTED) {
    if (pendingUid.length() || pendingButton) showMessage("No WiFi");
    pendingUid = "";
    pendingButton = false;
    return;
  }

  JsonDocument doc;
  putNum(doc, "voltage", rd.v);
  putNum(doc, "current", rd.i);
  putNum(doc, "power", rd.p);
  putNum(doc, "energy_wh", rd.e_wh);
  putNum(doc, "frequency", rd.f);
  putNum(doc, "pf", rd.pf);
  doc["relay"] = relayOn;
  doc["rssi"] = WiFi.RSSI();
  doc["uptime_s"] = millis() / 1000;
  if (pendingUid.length()) doc["uid"] = pendingUid;
  if (pendingButton) doc["button"] = true;

  String body;
  serializeJson(doc, body);

  HTTPClient http;
  if (strncmp(SERVER_URL, "https", 5) == 0) {
    // Encrypted connection to a cloud server (Render). setInsecure() skips checking the
    // server's certificate: fine for a student prototype; for production load the CA with setCACert().
    secureClient.setInsecure();
    http.begin(secureClient, SERVER_URL);
  } else {
    http.begin(plainClient, SERVER_URL);     // plain HTTP to the laptop on the same Wi-Fi
  }
  http.setTimeout(8000);                       // cloud servers can be slower to answer
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.POST(body);

  if (code == 200) {
    JsonDocument res;
    DeserializationError err = deserializeJson(res, http.getString());
    if (!err && res["ok"] == true) {
      lastSyncOk  = millis();
      relayWanted = res["relay"] | false;
      hasUser     = !res["user"].isNull();
      userName    = hasUser ? String((const char*)(res["user"]["name"] | "")) : String("");
      balance     = res["balance"] | 0.0f;
      fault       = res["fault"] | false;
      theft       = res["theft"] | false;
      lowBalance  = res["low_balance"] | false;
      uint32_t p  = res["poll_ms"] | 2000;
      pollMs      = p < 500 ? 500 : (p > 60000 ? 60000 : p);
      const char* m = res["message"] | "";
      if (strlen(m)) showMessage(m);
    } else {
      Serial.println("Bad JSON from server");
    }
  } else {
    Serial.printf("Sync failed: HTTP %d %s\n", code, http.errorToString(code).c_str());
    if (code == 401) showMessage("Bad device key", 5000);
    else if (pendingUid.length() || pendingButton) showMessage("Server offline");
  }
  http.end();

  pendingUid = "";        // a scan is sent once; tap again if the server was unreachable
  pendingButton = false;
}

// ---- TFT (160x128, landscape) ----
void line(int y, uint16_t color, const String& text, uint8_t size = 1) {
  tft.setTextSize(size);
  tft.setTextColor(color, ST77XX_BLACK);   // background colour overwrites old text, no flicker
  tft.setCursor(4, y);
  String t = text;
  int width = 26 / size;                   // characters per row at this text size
  while ((int)t.length() < width) t += ' ';
  tft.print(t.substring(0, width));
}

String fmtF(float v, int d) { return isnan(v) ? String("--") : String(v, d); }

void drawScreen() {
  bool online = lastSyncOk && millis() - lastSyncOk < OFFLINE_AFTER_MS;
  line(2,   ST77XX_YELLOW, String("EnergyPro  ") + (online ? "ONLINE" : "OFFLINE"));
  line(16,  ST77XX_WHITE,  hasUser ? userName : String("Tap RFID card"));
  line(28,  lowBalance ? ST77XX_RED : ST77XX_GREEN, hasUser ? "Bal: Rs " + String(balance, 2) : String(""));
  line(44,  ST77XX_CYAN,   "V " + fmtF(rd.v, 1) + "  I " + fmtF(rd.i, 3));
  line(56,  ST77XX_CYAN,   "P " + fmtF(rd.p, 1) + " W  PF " + fmtF(rd.pf, 2));
  line(68,  ST77XX_CYAN,   "E " + fmtF(rd.e_wh, 1) + " Wh");
  line(84,  relayOn ? ST77XX_GREEN : ST77XX_RED, relayOn ? "POWER ON" : "POWER OFF", 2);
  String alert = theft ? "THEFT ALERT" : fault ? "FAULT" : lowBalance ? "LOW BALANCE" : "";
  line(104, ST77XX_RED,    alert);
  line(116, ST77XX_WHITE,  millis() < messageUntil ? message : String(""));
}

// ------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  applyRelay(false);                      // always start with the supply OFF
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  SPI.begin();                            // SCK 18, MISO 19, MOSI 23
  rfid.PCD_Init();
  tft.initR(INITR_BLACKTAB);              // try INITR_GREENTAB if colours/edges look wrong
  tft.setRotation(1);
  tft.fillScreen(ST77XX_BLACK);
  line(2, ST77XX_YELLOW, "EnergyPro booting...");

  connectWiFi();
  syncWithServer();
}

void loop() {
  checkRfid();
  checkButton();

  if (pendingUid.length() || pendingButton || millis() - lastSyncAttempt >= pollMs) {
    syncWithServer();
  }

  // Apply the server's relay decision, but never switch faster than RELAY_MIN_GAP_MS.
  if (relayWanted != relayOn && millis() - lastRelaySwitch >= RELAY_MIN_GAP_MS) {
    applyRelay(relayWanted);
  }

  static uint32_t lastDraw = 0;
  if (millis() - lastDraw > 500) {
    lastDraw = millis();
    drawScreen();
  }
}
