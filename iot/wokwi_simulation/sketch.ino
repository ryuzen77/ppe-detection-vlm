/**
 * ===================================================================
 * SAFEGUARD AI - IoT Industrial Gate Controller (Wokwi Simulation)
 * Pengendali Lampu Bulat Hijau & Merah Terpisah
 * Komunikasi: Serial UART (9600 Baud)
 * ===================================================================
 */

// Definisi Pin Output
const int PIN_LAMP_GREEN = 2; // Pin D2 -> Relay 1 (Lampu Hijau)
const int PIN_LAMP_RED   = 3; // Pin D3 -> Relay 2 (Lampu Merah)

// Logika Relay (Modul relay Wokwi di-set PNP active-low)
const int RELAY_ON  = LOW;  
const int RELAY_OFF = HIGH;

// Safety Watchdog: Matikan lampu jika PC tidak mengirim kabar > 15 detik
unsigned long lastCommandTime = 0;
const unsigned long TIMEOUT_WATCHDOG_MS = 15000;

String inputBuffer = "";

void setup() {
  // Inisialisasi Pin Output
  pinMode(PIN_LAMP_GREEN, OUTPUT);
  pinMode(PIN_LAMP_RED, OUTPUT);

  // Set kondisi awal: Semua Lampu MATI
  digitalWrite(PIN_LAMP_GREEN, RELAY_OFF);
  digitalWrite(PIN_LAMP_RED, RELAY_OFF);

  // Inisialisasi Serial Port pada 9600 Baud
  Serial.begin(9600);
  while (!Serial) { ; } // Tunggu port siap

  // Tes kedipan sambutan saat boot (Self-test hardware)
  selfTest();
  
  Serial.println(F("[GATE_CONTROLLER_READY]"));
  Serial.println(F("Ketik perintah: LIGHT_GREEN, LIGHT_RED, atau LIGHT_OFF"));
  lastCommandTime = millis();
}

void loop() {
  // 1. Membaca Serial Command dari Python Backend / Serial Monitor
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) {
        processCommand(inputBuffer);
        inputBuffer = "";
      }
    } else {
      inputBuffer += c;
    }
  }

  // 2. Failsafe Safety Timeout
  if (millis() - lastCommandTime > TIMEOUT_WATCHDOG_MS) {
    turnOffAll();
  }
}

void processCommand(String cmd) {
  cmd.trim();
  lastCommandTime = millis();

  if (cmd == "LIGHT_GREEN") {
    // Akses Diizinkan: Hijau NYALA, Merah PADAM
    digitalWrite(PIN_LAMP_GREEN, RELAY_ON);
    digitalWrite(PIN_LAMP_RED, RELAY_OFF);
    Serial.println(F(">>> OK: LAMPU HIJAU NYALA (AKSES DIIZINKAN)"));
  } 
  else if (cmd == "LIGHT_RED") {
    // Akses Ditolak: Merah NYALA, Hijau PADAM
    digitalWrite(PIN_LAMP_GREEN, RELAY_OFF);
    digitalWrite(PIN_LAMP_RED, RELAY_ON);
    Serial.println(F(">>> OK: LAMPU MERAH NYALA (AKSES DITOLAK)"));
  } 
  else if (cmd == "LIGHT_OFF") {
    // Standby: Kedua lampu PADAM
    turnOffAll();
    Serial.println(F(">>> OK: STANDBY (SEMUA LAMPU PADAM)"));
  }
}

void turnOffAll() {
  digitalWrite(PIN_LAMP_GREEN, RELAY_OFF);
  digitalWrite(PIN_LAMP_RED, RELAY_OFF);
}

void selfTest() {
  // Kedipkan lampu hijau lalu merah selama 300ms untuk memastikan kabel terpasang baik
  digitalWrite(PIN_LAMP_GREEN, RELAY_ON);
  delay(300);
  digitalWrite(PIN_LAMP_GREEN, RELAY_OFF);
  
  digitalWrite(PIN_LAMP_RED, RELAY_ON);
  delay(300);
  digitalWrite(PIN_LAMP_RED, RELAY_OFF);
}
