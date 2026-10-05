/**
 * DEPRO - ESP32 DevKit V1 gate light controller (USB serial), T47.
 *
 * Lampu: merah (APD kurang), kuning (gangguan / menunggu), hijau (lolos),
 * buzzer cadangan (mati bawaan; suara utama dari speaker server).
 *
 * Protokol (9600 baud, satu perintah per baris, maks. 31 karakter):
 *   LIGHT_GREEN | LIGHT_RED | LIGHT_YELLOW | LIGHT_OFF  -> balas "OK:<STATE>"
 *   PING                                              -> balas "OK:<STATE>"
 *   lainnya -> "ERR:UNKNOWN", baris terlalu panjang -> "ERR:TOO_LONG"
 *
 * Server mengirim ulang keadaan lampu tiap ~1 dtk sebagai heartbeat. Bila
 * tidak ada perintah sah selama HEARTBEAT_TIMEOUT_MS, papan sendiri memadamkan
 * hijau/merah dan menyalakan KUNING BERKEDIP ("sistem tidak aktif"), supaya
 * hijau tidak pernah tertinggal menyala saat server crash atau kabel lepas.
 * Saat baru menyala papan juga mulai dari kuning berkedip (bukan self-test
 * hijau), sampai server mengirim perintah pertama.
 */

// --- Pin (GPIO bebas strapping boot ESP32) ---
const int PIN_GREEN  = 18;
const int PIN_RED    = 19;
const int PIN_YELLOW = 21;
const int PIN_BUZZER = 22;
const bool BUZZER_ENABLED = false;   // cadangan: hidupkan hanya bila diputuskan

// Modul relay optocoupler umumnya Active-LOW. Untuk modul Active-HIGH tukar keduanya.
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

const unsigned long SERIAL_BAUD          = 9600;
const unsigned long HEARTBEAT_TIMEOUT_MS = 3000;
const unsigned long BLINK_INTERVAL_MS    = 500;
const size_t MAX_LINE = 32;           // termasuk terminator

enum LightState { STATE_OFF, STATE_GREEN, STATE_RED, STATE_YELLOW, STATE_LOST };

LightState state = STATE_LOST;
unsigned long lastCommandMs = 0;
unsigned long lastBlinkMs = 0;
bool blinkOn = false;
char line[MAX_LINE];
size_t lineLen = 0;
bool lineOverflow = false;

// Nilai keluaran ditulis sebelum pin dijadikan OUTPUT supaya relay tidak
// sempat menyala sesaat saat boot.
void initRelayPin(int pin) {
  digitalWrite(pin, RELAY_OFF);
  pinMode(pin, OUTPUT);
  digitalWrite(pin, RELAY_OFF);
}

void writeLamps(bool green, bool red, bool yellow) {
  digitalWrite(PIN_GREEN,  green  ? RELAY_ON : RELAY_OFF);
  digitalWrite(PIN_RED,    red    ? RELAY_ON : RELAY_OFF);
  digitalWrite(PIN_YELLOW, yellow ? RELAY_ON : RELAY_OFF);
}

void applyState(LightState next) {
  state = next;
  writeLamps(next == STATE_GREEN, next == STATE_RED, next == STATE_YELLOW);
}

const char* stateName(LightState s) {
  switch (s) {
    case STATE_GREEN:  return "GREEN";
    case STATE_RED:    return "RED";
    case STATE_YELLOW: return "YELLOW";
    case STATE_OFF:    return "OFF";
    default:           return "LOST";
  }
}

void reply(const char* prefix, const char* detail) {
  Serial.print(prefix);
  Serial.println(detail);
}

void handleCommand(const char* cmd) {
  LightState next;
  if (strcmp(cmd, "LIGHT_GREEN") == 0)       next = STATE_GREEN;
  else if (strcmp(cmd, "LIGHT_RED") == 0)    next = STATE_RED;
  else if (strcmp(cmd, "LIGHT_YELLOW") == 0) next = STATE_YELLOW;
  else if (strcmp(cmd, "LIGHT_OFF") == 0)    next = STATE_OFF;
  else if (strcmp(cmd, "PING") == 0)         next = state;
  else {
    reply("ERR:", "UNKNOWN");
    return;
  }
  lastCommandMs = millis();
  if (next != STATE_LOST && next != state) applyState(next);
  reply("OK:", stateName(state));
}

void readSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineOverflow) reply("ERR:", "TOO_LONG");
      else if (lineLen > 0) {
        line[lineLen] = '\0';
        handleCommand(line);
      }
      lineLen = 0;
      lineOverflow = false;
    } else if (lineLen < MAX_LINE - 1) {
      line[lineLen++] = c;
    } else {
      lineOverflow = true;   // buang sisa baris; RAM tidak bertambah
    }
  }
}

// Server diam terlalu lama: padamkan keputusan lama, kuning berkedip.
void checkHeartbeat(unsigned long now) {
  if (state != STATE_LOST && now - lastCommandMs > HEARTBEAT_TIMEOUT_MS) {
    applyState(STATE_LOST);
    reply("WARN:", "HEARTBEAT_LOST");
  }
  if (state == STATE_LOST && now - lastBlinkMs >= BLINK_INTERVAL_MS) {
    lastBlinkMs = now;
    blinkOn = !blinkOn;
    writeLamps(false, false, blinkOn);
  }
}

void setup() {
  initRelayPin(PIN_GREEN);
  initRelayPin(PIN_RED);
  initRelayPin(PIN_YELLOW);
  initRelayPin(PIN_BUZZER);
  (void)BUZZER_ENABLED;
  Serial.begin(SERIAL_BAUD);
  applyState(STATE_LOST);
  reply("READY:", "DEPRO_GATE_LIGHTS");
}

void loop() {
  readSerial();
  checkHeartbeat(millis());
}
