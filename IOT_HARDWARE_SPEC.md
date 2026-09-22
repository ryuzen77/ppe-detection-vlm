# 🛠️ Spesifikasi Kebutuhan & Panduan Implementasi Hardware IoT
## Sistem Indikator Fisik Gerbang K3 (Lampu Bulat Hijau & Merah Terpisah)

Dokumen ini berisi panduan lengkap kebutuhan perangkat keras (hardware), spesifikasi teknis, skema pengkabelan (*wiring*), estimasi biaya, kode firmware mikrokontroler, dan konfigurasi backend untuk menghubungkan **PPE Detection AI Backend** dengan lampu fisik di gerbang inspeksi pekerja.

---

## 📑 Daftar Isi
1. [Arsitektur & Alur Kerja Sistem](#1-arsitektur--alur-kerja-sistem)
2. [Pilihan Implementasi Hardware](#2-pilihan-implementasi-hardware)
   - [Opsi A: Standar Industri Lapangan (Pilot Lamp 22mm 12V/24V) - Rekomendasi Utama](#opsi-a-standar-industri-lapangan-pilot-lamp-22mm-12v24v---rekomendasi-lapangan)
   - [Opsi B: Prototipe Meja Lab (LED Bulat Jumbo 10mm 5V)](#opsi-b-prototipe-meja-lab-led-bulat-jumbo-10mm-5v)
3. [Daftar Kebutuhan Komponen (Bill of Materials & Biaya)](#3-daftar-kebutuhan-komponen-bill-of-materials--biaya)
4. [Skema Rangkaian & Diagram Pengkabelan (Wiring Diagram)](#4-skema-rangkaian--diagram-pengkabelan-wiring-diagram)
5. [Kode Firmware Mikrokontroler (Arduino / ESP32)](#5-kode-firmware-mikrokontroler-arduino--esp32)
6. [Konfigurasi pada Backend Python](#6-konfigurasi-pada-backend-python)
7. [Prosedur Pengujian & Troubleshooting](#7-prosedur-pengujian--troubleshooting)

---

## 1. Arsitektur & Alur Kerja Sistem

```
┌─────────────────────────────────┐
│     Kamera Gerbang K3 (USB)     │
└────────────────┬────────────────┘
                 │ Feed Video 30 FPS
                 ▼
┌────────────────────────────────────────────────────────┐
│     Komputer / Edge Server (RTX 4060)                  │
│  - backend/main.py & detector.py (YOLO-Pose)           │
│  - backend/vlm_analyzer.py (Gemini VLM / Local)        │
│  - backend/notifier.py (IoT Serial Controller)         │
└────────────────┬───────────────────────────────────────┘
                 │ Kabel USB Serial (Baud: 9600)
                 │ Sinyal: LIGHT_GREEN / LIGHT_RED / LIGHT_OFF
                 ▼
┌─────────────────────────────────┐
│   Mikrokontroler                │
│   (Arduino Nano / Uno / ESP32)  │
└───────┬─────────────────┬───────┘
        │ Pin D2          │ Pin D3
        ▼                 ▼
 ┌───────────────┐ ┌───────────────┐
 │ Driver Relay  │ │ Driver Relay  │
 └──────┬────────┘ └──────┬────────┘
        ▼                 ▼
 ┌───────────────┐ ┌───────────────┐
 │ 🟢 LAMPU      │ │ 🔴 LAMPU      │
 │    HIJAU      │ │    MERAH      │
 │    BULAT      │ │    BULAT      │
 └───────────────┘ └───────────────┘
  (AKSES DIIZINKAN) (AKSES DITOLAK)
```

### Protokol Serial Komunikasi:
Perintah dikirimkan dari modul `backend/notifier.py` melalui port USB Serial dengan kecepatan **9600 baud**:
- `LIGHT_GREEN\n` : Pekerja lulus APD lengkap $\rightarrow$ Nyalakan Lampu Hijau, Matikan Lampu Merah.
- `LIGHT_RED\n` : Terjadi pelanggaran APD $\rightarrow$ Nyalakan Lampu Merah, Matikan Lampu Hijau.
- `LIGHT_OFF\n` : Kondisi standby / gerbang kosong $\rightarrow$ Matikan kedua lampu.

---

## 2. Pilihan Implementasi Hardware

Sesuai kebutuhan lapangan di mana lampu indikator hijau dan merah menggunakan **lampu bulat terpisah**, terdapat 2 opsi yang dapat dipilih:

---

### OPSI A: Standar Industri Lapangan (Pilot Lamp 22mm 12V/24V) - Rekomendasi Lapangan
Sangat direkomendasikan untuk pemasangan permanen di gate proyek, pabrik, atau pos sekuriti outdoor.

#### Spesifikasi Teknis Komponen:
1. **Lampu Bulat Terpisah (Industrial LED Pilot Lamp Ø22mm)**
   - **Tipe**: AD16-22DS / XB2-BVB (Merk: Chint, Fort, Omron, atau Schneider).
   - **Diameter Lubang Pemasangan**: 22 mm standard industrial cut-out.
   - **Warna**: 
     - 1 unit Bulat Hijau (*Pure Green* 525nm, intensitas > 100 cd/m²).
     - 1 unit Bulat Merah (*Bright Red* 625nm, intensitas > 80 cd/m²).
   - **Tegangan Kerja**: **12V DC** (atau 24V DC). Sangat disarankan tegangan ekstra rendah (SELV) agar aman terhadap cipratan air dan bahaya sengatan listrik di lapangan.
   - **Ketahanan Cuaca**: IP65 (tahan debu industri & semprotan air saat dipasang di enclosure).
   - **Kelebihan**: Sangat terang dan terlihat jelas oleh pekerja dari jarak 5–10 meter bahkan di bawah terik sinar matahari siang.

2. **Modul Penggerak (2-Channel Relay Module 5V with Optocoupler)**
   - **Komponen Utama**: Relay Songle SRD-05VDC-SL-C dengan isolasi optocoupler PC817.
   - **Tegangan Koil**: 5V DC (ditenagai langsung dari pin 5V mikrokontroler).
   - **Kapasitas Kontak**: Hingga 10A 250VAC / 30VDC (jauh melampaui beban LED pilot yang hanya ~20-50mA).
   - **Trigger**: Active-LOW atau Active-HIGH (tergantung jumper modul).

3. **Mikrokontroler**
   - **Pilihan 1**: **Arduino Nano V3 (ATmega328P, CH340 USB chip)** — Sangat ringkas, murah, dan handal untuk serial UART.
   - **Pilihan 2**: **Arduino Uno R3** — Ukuran lebih besar, mudah dihubungkan dengan kabel jumper dupont.
   - **Pilihan 3**: **ESP32 DevKit V1 (30 pin)** — Jika di masa depan ingin dihubungkan via Wi-Fi/MQTT (tanpa kabel USB).

4. **Catu Daya (Power Supply Adaptor)**
   - Adaptor Switching **12V DC 2A** (stabil, regulated, jack DC 5.5x2.1mm) untuk menyalakan lampu pilot lamp.

---

### OPSI B: Prototipe Meja Lab (LED Bulat Jumbo 10mm 5V)
Cocok untuk pengujian di atas meja kerja, presentasi, atau simulasi sebelum pengadaan alat lapangan.

#### Spesifikasi Teknis Komponen:
1. **Lampu Bulat Terpisah (LED Bulat 10mm Jumbo / Diffused)**
   - **Ukuran**: Diameter kepala 10 mm (round top).
   - **Warna**: 1 unit Hijau (Green) + 1 unit Merah (Red).
   - **Tegangan Maju ($V_f$)**:
     - LED Merah: 1.8V – 2.2V DC (arus tipikal 20 mA).
     - LED Hijau: 3.0V – 3.2V DC (arus tipikal 20 mA).
2. **Resistor Pembatas Arus (Current Limiting Resistor)**
   - Resistor Metal Film 1/4 Watt:
     - Untuk LED Merah (5V): **220 $\Omega$** atau **330 $\Omega$**.
     - Untuk LED Hijau (5V): **150 $\Omega$** atau **220 $\Omega$**.
3. **Mikrokontroler**: Arduino Nano / Uno (langsung mengendalikan pin GPIO tanpa perlu modul relay tambahan).

---

## 3. Daftar Kebutuhan Komponen (Bill of Materials & Biaya)

Berikut rincian perkiraan biaya untuk **Opsi A (Standar Lapangan/Gerbang Industri)**:

| No | Komponen | Spesifikasi Teknis | Jumlah | Estimasi Harga Satuan | Total |
| :---: | :--- | :--- | :---: | :---: | :---: |
| 1 | **Mikrokontroler** | Arduino Nano V3 CH340 + Kabel Mini USB | 1 unit | Rp 42.000 | Rp 42.000 |
| 2 | **Lampu Bulat Hijau** | Industrial LED Pilot Lamp 22mm 12V DC (Green) | 1 unit | Rp 16.000 | Rp 16.000 |
| 3 | **Lampu Bulat Merah** | Industrial LED Pilot Lamp 22mm 12V DC (Red) | 1 unit | Rp 16.000 | Rp 16.000 |
| 4 | **Modul Driver** | 2-Channel Relay Module 5V Optocoupler | 1 unit | Rp 18.000 | Rp 18.000 |
| 5 | **Power Supply Adaptor** | Adaptor AC 220V ke DC 12V 2A | 1 unit | Rp 35.000 | Rp 35.000 |
| 6 | **Jack DC Female** | DC Power Female Jack Socket Screw Terminal 5.5x2.1mm | 1 pcs | Rp 3.500 | Rp 3.500 |
| 7 | **Box Enclosure** | Box Panel Outdoor Waterproof IP65 (misal uk. 150x100x70mm) | 1 unit | Rp 45.000 | Rp 45.000 |
| 8 | **Kabel & Aksesoris** | Kabel jumper dupont, kabel serabut 2x0.75mm, terminal strip | 1 set | Rp 25.000 | Rp 25.000 |
| **Total** | **Estimasi Biaya Keseluruhan** | | | | **± Rp 200.500** |

> [!TIP]
> Semua komponen di atas merupakan barang umum industri dan sangat mudah didapatkan di marketplace lokal (Tokopedia / Shopee / toko komponen elektronik).

---

## 4. Skema Rangkaian & Diagram Pengkabelan (Wiring Diagram)

### Pengkabelan Arduino ke Modul Relay 5V:
- **Arduino 5V** $\rightarrow$ **VCC** Modul Relay
- **Arduino GND** $\rightarrow$ **GND** Modul Relay
- **Arduino Pin D2** $\rightarrow$ **IN1** Modul Relay (Kontrol Lampu Hijau)
- **Arduino Pin D3** $\rightarrow$ **IN2** Modul Relay (Kontrol Lampu Merah)

### Pengkabelan Relay ke Lampu Pilot 12V & Adaptor:
- **Adaptor (+) 12V** $\rightarrow$ Sambungkan ke Terminal **COM (Common)** pada Relay 1 dan Relay 2.
- **Relay 1 Terminal NO (Normally Open)** $\rightarrow$ Terminal (+) Lampu Hijau.
- **Relay 2 Terminal NO (Normally Open)** $\rightarrow$ Terminal (+) Lampu Merah.
- **Adaptor (-) GND 12V** $\rightarrow$ Sambungkan langsung ke Terminal (-) Lampu Hijau dan Terminal (-) Lampu Merah.

```
       ADAPTOR 12V DC
      ┌───────────────┐
      │  (+) 12V DC   │─────────┬────────────────────────┐
      │  (-) GND      │───┐     │                        │
      └───────────────┘   │     │                        │
                          │     ▼                        ▼
                          │  [RELAY 1 (COM)]          [RELAY 2 (COM)]
                          │  [RELAY 1 (NO) ]          [RELAY 2 (NO) ]
                          │         │                        │
                          │         ▼ (+)                    ▼ (+)
                          │   ┌───────────────┐        ┌───────────────┐
                          │   │  LAMPU BULAT  │        │  LAMPU BULAT  │
                          │   │  HIJAU (12V)  │        │  MERAH (12V)  │
                          │   └───────┬───────┘        └───────┬───────┘
                          │           │ (-)                    │ (-)
                          └───────────┴────────────────────────┘
```

> [!NOTE]
> Kontak **NO (Normally Open)** memastikan bahwa saat PC mati atau kabel terputus, kedua lampu dalam kondisi padam (hemat daya dan aman).

---

## 5. Kode Firmware Mikrokontroler (Arduino / ESP32)

Salin kode C++ berikut ke dalam **Arduino IDE**, pilih board **Arduino Nano** (atau Uno), lalu unggah (*Upload*):

```cpp
/**
 * ===================================================================
 * SAFEGUARD AI - IoT Industrial Gate Controller
 * Pengendali Lampu Bulat Hijau & Merah Terpisah
 * Komunikasi: Serial UART (9600 Baud)
 * ===================================================================
 */

// Definisi Pin Output
const int PIN_LAMP_GREEN = 2; // Pin D2 -> Relay 1 (Lampu Hijau)
const int PIN_LAMP_RED   = 3; // Pin D3 -> Relay 2 (Lampu Merah)

// Logika Relay (Sebagian besar modul relay 5V bersifat Active-LOW)
// Jika relay Anda Active-HIGH, ubah RELAY_ON menjadi HIGH dan RELAY_OFF menjadi LOW
const int RELAY_ON  = LOW;  
const int RELAY_OFF = HIGH;

// Safety Watchdog: Matikan lampu jika PC tidak mengirim kabar > 10 detik
unsigned long lastCommandTime = 0;
const unsigned long TIMEOUT_WATCHDOG_MS = 10000;

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
  lastCommandTime = millis();
}

void loop() {
  // 1. Membaca Serial Command dari Python Backend
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
  // Jika server backend tertutup / crash > 10 detik, matikan lampu demi keselamatan
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
    Serial.println(F("OK:GREEN_ACTIVE"));
  } 
  else if (cmd == "LIGHT_RED") {
    // Akses Ditolak: Merah NYALA, Hijau PADAM
    digitalWrite(PIN_LAMP_GREEN, RELAY_OFF);
    digitalWrite(PIN_LAMP_RED, RELAY_ON);
    Serial.println(F("OK:RED_ACTIVE"));
  } 
  else if (cmd == "LIGHT_OFF") {
    // Standby: Kedua lampu PADAM
    turnOffAll();
    Serial.println(F("OK:ALL_OFF"));
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
```

---

## 6. Konfigurasi pada Backend Python

Modul kontroler serial sudah tertanam di [`backend/notifier.py`](file:///c:/Users/zenin/Desktop/PROJECTS/ppe_detection_vlm/backend/notifier.py). Anda hanya perlu mengaktifkannya di file `.env`.

### Langkah 1: Install Paket `pyserial`
Jalankan di terminal Anaconda:
```bash
pip install pyserial
```

### Langkah 2: Cek Nomor COM Port di Windows
1. Buka **Device Manager** di Windows (`Win + X` $\rightarrow$ `Device Manager`).
2. Periksa bagian **Ports (COM & LPT)**.
3. Catat port mikrokontroler yang terdeteksi, misalnya: `USB-SERIAL CH340 (COM3)` atau `Arduino Nano (COM4)`.

### Langkah 3: Update `backend/.env`
Buka file `backend/.env` dan ubah variabel IoT:
```ini
# IoT Hardware Stage 2
IOT_ENABLED=true
IOT_TYPE=serial
IOT_SERIAL_PORT=COM3     # Ganti sesuai COM port yang terdeteksi di Device Manager
IOT_SERIAL_BAUD=9600
```

---

## 7. Prosedur Pengujian & Troubleshooting

### Pengujian Mandiri Serial (Tanpa Kamera):
Anda dapat menguji apakah relay dan lampu merespon dengan menjalankan script Python singkat di bawah ini:

```python
import serial
import time

ser = serial.Serial("COM3", 9600, timeout=1) # Sesuaikan port COM
time.sleep(2) # Tunggu Arduino reset

print("Menguji Lampu Hijau...")
ser.write(b"LIGHT_GREEN\n")
time.sleep(3)

print("Menguji Lampu Merah...")
ser.write(b"LIGHT_RED\n")
time.sleep(3)

print("Menguji Lampu Mati (Standby)...")
ser.write(b"LIGHT_OFF\n")
time.sleep(1)

ser.close()
print("Pengujian Selesai!")
```

### Panduan Troubleshooting:
1. **Error: `PermissionError: [Errno 13] could not open port 'COM3'`**
   - **Penyebab**: Port COM sedang dibuka oleh program lain (misalnya Serial Monitor di Arduino IDE masih terbuka).
   - **Solusi**: Tutup jendela Serial Monitor pada Arduino IDE sebelum menjalankan backend AI.
2. **Lampu Terbalik (Perintah `LIGHT_GREEN` malah menyalakan lampu merah)**
   - **Solusi**: Tukar colokan kabel jumper pin D2 dan D3 pada Arduino, atau ubah nomor pin di firmware Arduino.
3. **Lampu Menyala Terus Saat Standby, dan Mati Saat Aktif (Inverted Logic)**
   - **Penyebab**: Modul relay bertipe Active-HIGH sedangkan kode diset Active-LOW.
   - **Solusi**: Pada kode Arduino, ubah:
     ```cpp
     const int RELAY_ON  = HIGH;
     const int RELAY_OFF = LOW;
     ```
4. **Jarak Kabel Panjang (> 5 meter)**
   - Jangan menggunakan kabel USB yang terlalu panjang (> 3 meter) karena rentan drop tegangan data.
   - **Rekomendasi**: Letakkan Arduino di dekat PC, lalu tarik kabel 2-kawat tegangan 12V dari relay ke lampu gerbang (kabel 12V DC kuat ditarik hingga 20 meter tanpa gangguan sinyal).
