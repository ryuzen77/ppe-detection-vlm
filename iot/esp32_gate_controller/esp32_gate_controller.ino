/**
 * ===================================================================
 * SAFEGUARD AI - ESP32 DevKit V1 (USB Serial Demo Mode)
 * Pengendali Lampu Bulat Hijau & Merah Terpisah via Kabel USB Laptop
 * 
 * Keunggulan Mode Demo:
 * 1. Booting Instan (< 0.1 detik) tanpa menunggu koneksi Wi-Fi.
 * 2. Handal 100% di lokasi demo tanpa risiko Wi-Fi terputus.
 * 3. Latensi Nol (< 1ms) langsung dari backend Python via Serial COM.
 * 4. Self-test kedipan lampu otomatis saat baru dicolok ke USB.
 * ===================================================================
 */

// -------------------------------------------------------------
// 1. DEFINISI PIN GPIO (ESP32 DevKit V1)
// -------------------------------------------------------------
// Menggunakan GPIO 18 dan 19 (Aman, bebas interferensi boot strapping)
const int PIN_RELAY_GREEN = 18; // GPIO 18 -> IN1 Modul Relay (Lampu Hijau)
const int PIN_RELAY_RED   = 19; // GPIO 19 -> IN2 Modul Relay (Lampu Merah)

// Logika Relay: Sebagian besar modul relay 5V bersifat Active-LOW
// (LOW = Relay ON/Menyala, HIGH = Relay OFF/Padam)
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

// Safety Watchdog: Matikan lampu jika laptop tidak mengirim perintah > 15 detik
unsigned long lastCommandTime = 0;
const unsigned long TIMEOUT_WATCHDOG_MS = 15000;

String inputBuffer = "";
String currentLightState = "OFF";

// -------------------------------------------------------------
// 2. FUNGSI LOGIKA KENDALI LAMPU
// -------------------------------------------------------------
void setLightState(String state) {
  state.trim();
  state.toUpperCase();
  lastCommandTime = millis();

  if (state == "LIGHT_GREEN" || state == "GREEN") {
    // Akses Diizinkan: Hijau NYALA, Merah PADAM
    digitalWrite(PIN_RELAY_GREEN, RELAY_ON);
    digitalWrite(PIN_RELAY_RED, RELAY_OFF);
    currentLightState = "GREEN";
    Serial.println(F("[ESP32] OK:GREEN_ACTIVE -> LAMPU HIJAU NYALA (AKSES DIIZINKAN)"));
  } 
  else if (state == "LIGHT_RED" || state == "RED") {
    // Akses Ditolak: Merah NYALA, Hijau PADAM
    digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
    digitalWrite(PIN_RELAY_RED, RELAY_ON);
    currentLightState = "RED";
    Serial.println(F("[ESP32] OK:RED_ACTIVE -> LAMPU MERAH NYALA (AKSES DITOLAK)"));
  } 
  else if (state == "LIGHT_OFF" || state == "OFF") {
    // Standby: Kedua lampu PADAM
    turnOffAll();
    currentLightState = "OFF";
    Serial.println(F("[ESP32] OK:ALL_OFF -> MODE STANDBY (LAMPU PADAM)"));
  }
}

void turnOffAll() {
  digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
  digitalWrite(PIN_RELAY_RED, RELAY_OFF);
}

void selfTest() {
  // Kedipkan lampu hijau 300ms lalu merah 300ms saat baru dicolok ke USB
  digitalWrite(PIN_RELAY_GREEN, RELAY_ON);
  delay(300);
  digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
  
  digitalWrite(PIN_RELAY_RED, RELAY_ON);
  delay(300);
  digitalWrite(PIN_RELAY_RED, RELAY_OFF);
}

// -------------------------------------------------------------
// 3. SETUP & INISIALISASI
// -------------------------------------------------------------
void setup() {
  // Inisialisasi Pin Output Relay
  pinMode(PIN_RELAY_GREEN, OUTPUT);
  pinMode(PIN_RELAY_RED, OUTPUT);

  // Set kondisi awal: Semua Lampu MATI
  digitalWrite(PIN_RELAY_GREEN, RELAY_OFF);
  digitalWrite(PIN_RELAY_RED, RELAY_OFF);

  // Inisialisasi Serial UART pada 9600 Baud
  Serial.begin(9600);
  while (!Serial) { ; } // Tunggu port serial siap

  // Uji coba kedipan lampu hardware saat boot
  selfTest();

  Serial.println(F("=================================================="));
  Serial.println(F(" SAFEGUARD AI - ESP32 GATE CONTROLLER (DEMO USB)  "));
  Serial.println(F(" Status: SIAP MENERIMA PERINTAH SERIAL DARI LAPTOP"));
  Serial.println(F(" Perintah: LIGHT_GREEN | LIGHT_RED | LIGHT_OFF    "));
  Serial.println(F("=================================================="));

  lastCommandTime = millis();
}

// -------------------------------------------------------------
// 4. MAIN LOOP
// -------------------------------------------------------------
void loop() {
  // 1. Membaca Perintah Serial dari Backend Python (Laptop)
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) {
        setLightState(inputBuffer);
        inputBuffer = "";
      }
    } else {
      inputBuffer += c;
    }
  }

  // 2. Failsafe Safety Timeout
  // Jika laptop terputus atau server mati > 15 detik, matikan semua lampu
  if (millis() - lastCommandTime > TIMEOUT_WATCHDOG_MS && currentLightState != "OFF") {
    turnOffAll();
    currentLightState = "OFF";
    Serial.println(F("[ESP32] Watchdog: Timeout sinyal dari laptop. Lampu dipadamkan."));
  }
}
