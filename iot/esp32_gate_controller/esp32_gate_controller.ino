/**
 * ===================================================================
 * SAFEGUARD AI - ESP32 DevKit V1 Wireless Gate Controller
 * Pengendali Lampu Bulat Hijau & Merah Terpisah via Wi-Fi (HTTP & Serial)
 * 
 * Fitur:
 * 1. Wireless Wi-Fi: Tidak perlu terhubung kabel ke laptop!
 * 2. REST API Endpoint: /api/light?state=green | red | off
 * 3. Web Dashboard Bawaan: Buka http://gate-k3.local di HP/Laptop
 * 4. Dual Control: Tetap bisa menerima Serial via USB (9600 Baud)
 * 5. Auto Reconnect Wi-Fi & Safety Watchdog Failsafe
 * ===================================================================
 */

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>

// -------------------------------------------------------------
// 1. PENGATURAN WI-FI (Sesuaikan dengan Hotspot/Router Anda)
// -------------------------------------------------------------
const char* WIFI_SSID     = "NAMA_WIFI_PROYEK";
const char* WIFI_PASSWORD = "PASSWORD_WIFI";

// Nama Host mDNS: Anda bisa mengakses via http://gate-k3.local
const char* MDNS_HOST     = "gate-k3";

// -------------------------------------------------------------
// 2. DEFINISI PIN GPIO (ESP32 DevKit V1)
// -------------------------------------------------------------
// Gunakan GPIO 18 dan 19 (Aman, bebas konflik boot strapping)
const int PIN_RELAY_GREEN = 18; // GPIO 18 -> IN1 Modul Relay (Lampu Hijau)
const int PIN_RELAY_RED   = 19; // GPIO 19 -> IN2 Modul Relay (Lampu Merah)

// Logika Relay: Sebagian besar modul relay adalah Active-LOW
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

// Safety Watchdog: Matikan lampu jika server tidak mengirim kabar > 30 detik
unsigned long lastCommandTime = 0;
const unsigned long TIMEOUT_WATCHDOG_MS = 30000;

// Web Server pada port 80
WebServer server(80);

String currentLightState = "OFF";
String serialInputBuffer = "";

// -------------------------------------------------------------
// 3. FUNGSI LOGIKA KENDALI LAMPU
// -------------------------------------------------------------
void setLightState(String state) {
  state.toUpperCase();
  lastCommandTime = millis();

  if (state == "GREEN" || state == "LIGHT_GREEN") {
    digitalWrite(PIN_RELAY_GREEN, RELAY_ON);
    digitalWrite(PIN_RELAY_RED, RELAY_OFF);
    currentLightState = "GREEN";
    Serial.println(F("[ESP32] >>> LAMPU HIJAU AKTIF (AKSES DIIZINKAN)"));
  } 
  else if (state == "RED" || state == "LIGHT_RED") {
    digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
    digitalWrite(PIN_RELAY_RED, RELAY_ON);
    currentLightState = "RED";
    Serial.println(F("[ESP32] >>> LAMPU MERAH AKTIF (AKSES DITOLAK)"));
  } 
  else {
    digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
    digitalWrite(PIN_RELAY_RED, RELAY_OFF);
    currentLightState = "OFF";
    Serial.println(F("[ESP32] >>> STANDBY (SEMUA LAMPU PADAM)"));
  }
}

// -------------------------------------------------------------
// 4. HTTP HANDLERS (REST API & WEB DASHBOARD)
// -------------------------------------------------------------

// REST API: GET /api/light?state=green | red | off
void handleApiLight() {
  if (server.hasArg("state")) {
    String stateArg = server.arg("state");
    setLightState(stateArg);
    server.send(200, "application/json", "{\"status\":\"ok\",\"state\":\"" + currentLightState + "\"}");
  } else {
    server.send(400, "application/json", "{\"error\":\"Parameter 'state' is required (green, red, or off)\"}");
  }
}

// REST API Status: GET /api/status
void handleApiStatus() {
  String json = "{\"device\":\"ESP32 Gate Controller\",\"state\":\"" + currentLightState + 
                "\",\"ip\":\"" + WiFi.localIP().toString() + "\",\"rssi\":" + String(WiFi.RSSI()) + "}";
  server.send(200, "application/json", json);
}

// Web UI Dashboard: GET /
void handleRoot() {
  String html = "<!DOCTYPE html><html lang='id'><head><meta charset='UTF-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
                "<title>ESP32 Gate Controller</title>"
                "<style>"
                "body { font-family: sans-serif; background: #0d1117; color: #fff; text-align: center; padding: 20px; }"
                ".card { background: #161b22; border-radius: 12px; padding: 25px; max-width: 400px; margin: auto; border: 1px solid #30363d; }"
                "h1 { font-size: 20px; color: #58a6ff; margin-bottom: 5px; }"
                ".status { font-size: 28px; font-weight: bold; margin: 20px 0; padding: 12px; border-radius: 8px; }"
                ".status.GREEN { background: #00e69922; color: #00e699; border: 1px solid #00e699; }"
                ".status.RED { background: #ff336622; color: #ff3366; border: 1px solid #ff3366; }"
                ".status.OFF { background: #8b949e22; color: #8b949e; border: 1px solid #8b949e; }"
                ".btn { display: block; width: 100%; padding: 14px; margin: 10px 0; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; }"
                ".btn-green { background: #00e699; color: #000; }"
                ".btn-red { background: #ff3366; color: #fff; }"
                ".btn-off { background: #30363d; color: #c9d1d9; }"
                ".footer { font-size: 12px; color: #8b949e; margin-top: 15px; }"
                "</style></head><body>"
                "<div class='card'>"
                "<h1>👷 SAFEGUARD AI</h1>"
                "<p style='color:#8b949e;font-size:13px;'>Kontrol Fisik Gerbang K3 (ESP32)</p>"
                "<div class='status " + currentLightState + "'>STATUS: " + currentLightState + "</div>"
                "<a href='/api/light?state=green'><button class='btn btn-green'>🟢 NYALAKAN LAMPU HIJAU</button></a>"
                "<a href='/api/light?state=red'><button class='btn btn-red'>🔴 NYALAKAN LAMPU MERAH</button></a>"
                "<a href='/api/light?state=off'><button class='btn btn-off'>⚪ MATIKAN LAMPU (STANDBY)</button></a>"
                "<div class='footer'>IP: " + WiFi.localIP().toString() + " | mDNS: http://" + String(MDNS_HOST) + ".local</div>"
                "</div></body></html>";
  server.send(200, "text/html", html);
}

// -------------------------------------------------------------
// 5. SETUP & INISIALISASI
// -------------------------------------------------------------
void setup() {
  Serial.begin(9600);

  pinMode(PIN_RELAY_GREEN, OUTPUT);
  pinMode(PIN_RELAY_RED, OUTPUT);

  // Default: Matikan semua lampu
  digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
  digitalWrite(PIN_RELAY_RED, RELAY_OFF);

  // Self-test kedipan hardware 300ms
  digitalWrite(PIN_RELAY_GREEN, RELAY_ON);
  delay(300);
  digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
  digitalWrite(PIN_RELAY_RED, RELAY_ON);
  delay(300);
  digitalWrite(PIN_RELAY_RED, RELAY_OFF);

  // Inisialisasi Koneksi Wi-Fi
  Serial.println();
  Serial.print(F("[ESP32] Menghubungkan ke Wi-Fi: "));
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  // Tunggu koneksi Wi-Fi (maksimal 20 detik, lalu tetap jalan untuk Serial)
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(F("."));
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println(F("[ESP32] Wi-Fi Terhubung Sukses!"));
    Serial.print(F("[ESP32] Alamat IP ESP32: http://"));
    Serial.println(WiFi.localIP());

    // Inisialisasi mDNS responder
    if (MDNS.begin(MDNS_HOST)) {
      Serial.print(F("[ESP32] Akses via mDNS: http://"));
      Serial.print(MDNS_HOST);
      Serial.println(F(".local"));
    }
  } else {
    Serial.println();
    Serial.println(F("[ESP32] Peringatan: Wi-Fi belum tersambung. Mode USB Serial tetap aktif!"));
  }

  // Daftarkan route HTTP WebServer
  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/light", HTTP_GET, handleApiLight);
  server.on("/api/status", HTTP_GET, handleApiStatus);
  server.begin();
  Serial.println(F("[ESP32] HTTP REST Server Siap pada port 80."));

  lastCommandTime = millis();
}

// -------------------------------------------------------------
// 6. MAIN LOOP
// -------------------------------------------------------------
void loop() {
  // 1. Tangani Web Request HTTP
  server.handleClient();

  // 2. Tangani Perintah Serial UART jika ada yang colok kabel USB
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialInputBuffer.length() > 0) {
        setLightState(serialInputBuffer);
        serialInputBuffer = "";
      }
    } else {
      serialInputBuffer += c;
    }
  }

  // 3. Failsafe Safety Watchdog
  if (millis() - lastCommandTime > TIMEOUT_WATCHDOG_MS && currentLightState != "OFF") {
    setLightState("OFF");
    Serial.println(F("[ESP32] Watchdog Failsafe: Tidak ada sinyal dari server > 30s. Lampu dimatikan."));
  }

  // 4. Auto-reconnect Wi-Fi jika terputus di lapangan
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastReconnectAttempt = 0;
    if (millis() - lastReconnectAttempt > 10000) {
      Serial.println(F("[ESP32] Mencoba menghubungkan kembali ke Wi-Fi..."));
      WiFi.reconnect();
      lastReconnectAttempt = millis();
    }
  }
}
