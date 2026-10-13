# Lampu gerbang DEPRO — spesifikasi perangkat keras (T47)

Lampu fisik gerbang untuk **demo tanpa palang**: **ESP32 DevKit V1** lewat **kabel
USB serial**, tiga lampu, dan buzzer sebagai cadangan. Firmware ada di
`iot/esp32_gate_controller/`, dan pengendalinya di `backend/notifier.py`.

| Lampu | Arti | Dipicu oleh |
| :-- | :-- | :-- |
| Hijau | APD lengkap, boleh lewat | Keputusan VLM |
| Merah | **Hanya** APD kurang | Keputusan VLM |
| Kuning menyala | Gangguan: VLM utama & cadangan gagal, kamera bermasalah (T45); pekerja diminta menunggu | Server |
| Kuning berkedip | **Sistem tidak aktif**: server mati/crash, kabel USB lepas, atau papan baru menyala | Papan sendiri (tanpa server) |
| Padam | Siaga, belum ada pekerja | Server |

Buzzer disiapkan di kanal relay ke-4, tetapi **mati bawaan**
(`BUZZER_ENABLED = false`) supaya tidak tumpang tindih dengan suara speaker.

## 1. Mengapa USB serial, bukan Wi-Fi

Perintah lampu lewat HTTP/Wi-Fi tanpa tanda tangan bisa dipalsukan oleh siapa
pun di jaringan yang sama. Halaman web pun bisa memicunya lewat `<img src=…>`
(CSRF), dan nama `*.local` (mDNS) bisa dibajak. Mode itu dibuang. Wi-Fi baru
dipertimbangkan lagi bila perintahnya ditandatangani (HMAC + penghitung) dan
jaringannya terpisah.

USB serial hanya bisa dikendalikan oleh orang yang memegang kabel. Simpan papan
di dalam box tertutup.

## 2. Daftar komponen

**Dipakai kedua varian lampu**

| Komponen | Jml | Catatan |
| :-- | :-: | :-- |
| ESP32 DevKit V1 (30 pin, CP2102/CH340) + kabel USB **data** | 1 | Kabel yang hanya untuk mengisi daya tidak bisa dipakai |
| Modul relay **4 kanal 5V**, optocoupler, **dengan jumper JD-VCC** | 1 | Kanal: hijau, merah, kuning, buzzer |
| Adaptor 12V DC 2A (jack 5,5×2,1) | 1 | Daya lampu 12V |
| Modul step-down 12V→5V (LM2596 / mini-360) | 1 | Daya koil relay (JD-VCC) dan LED meja |
| Fuse 1A + holder, terminal blok, kabel 2×0,75 mm, kabel dupont | 1 set | |
| Box panel | 1 | |

**Varian lapangan**: pilot lamp **AD16-22DS 12V DC** Ø22 mm, satu merah, satu
kuning, dan satu hijau. Resistornya sudah ada di dalam lampu.

**Varian meja**: LED 10 mm *diffused*, satu merah, satu kuning, dan satu hijau.
Masing-masing dinyalakan dari jalur **5V** lewat kontak relay dengan resistor
seri: **220 Ω** untuk merah dan kuning, **150 Ω** untuk hijau (±13 mA). Firmware
kedua varian sama, hanya lampunya yang ditukar.

**Cadangan**: buzzer aktif 5V/12V di kanal ke-4.

**Jangan dipakai**:
- Resistor pull-down 10k di pin relay. Pada modul Active-LOW resistor ini justru
  **menyalakan** relay saat boot.
- Menyambung VCC modul relay ke 5V bila sinyalnya dari ESP32 (lihat §3).

## 3. Pengkabelan

**Sisi kendali (ESP32 → modul relay)**

- **Cabut jumper JD-VCC.**
- `VCC` modul (sisi optocoupler) ke **3V3** ESP32, `GND` ke `GND` ESP32.
  Optocoupler dinyalakan 3,3V. Bila VCC 5V sedangkan sinyal 3,3V, LED opto
  masih mendapat ±1,7V saat pin HIGH dan relay bisa **tidak mau padam**.
- `IN1` ← GPIO 18 (hijau), `IN2` ← GPIO 19 (merah), `IN3` ← GPIO 21 (kuning),
  `IN4` ← GPIO 22 (buzzer). Keempat GPIO ini bukan pin strapping boot ESP32.
- `JD-VCC` dan `GND` di header JD ke keluaran **step-down 5V**. GND step-down
  **tidak** disambung ke GND ESP32, supaya sisi relay terisolasi optik dari laptop.

**Sisi beban**

```text
Adaptor 12V (+) ─[FUSE 1A]─┬─ COM relay hijau ─ NO ─ (+) lampu hijau ─┐
                           ├─ COM relay merah ─ NO ─ (+) lampu merah ─┤
                           └─ COM relay kuning ─ NO ─ (+) lampu kuning┤
Adaptor 12V (−) ──────────────────────────────────────── (−) semua lampu
Adaptor 12V ─ step-down ─ 5V ─ JD-VCC modul relay
```
Varian meja: jalur 12V diganti 5V dari step-down, dan resistor dipasang seri di
tiap LED. Kontak **NO** dipakai supaya lampu padam bila relay tidak diberi daya.

## 4. Protokol serial

9600 baud, satu perintah per baris (maks. 31 karakter):

| Server → papan | Balasan |
| :-- | :-- |
| `LIGHT_GREEN` / `LIGHT_RED` / `LIGHT_YELLOW` / `LIGHT_OFF` | `OK:GREEN` / `OK:RED` / `OK:YELLOW` / `OK:OFF` |
| `PING` | `OK:<keadaan>` |
| perintah lain / baris terlalu panjang | `ERR:UNKNOWN` / `ERR:TOO_LONG` |

- **Heartbeat.** Server mengirim ulang keadaan lampu tiap
  `IOT_HEARTBEAT_SECONDS` (1 dtk). Bila 3 dtk tanpa perintah sah, papan
  memadamkan hijau/merah lalu **kuning berkedip** dan mengirim
  `WARN:HEARTBEAT_LOST`. Hijau tidak bisa tertinggal menyala saat server crash.
- **Tanpa reset saat port dibuka.** Membuka port dengan DTR/RTS aktif me-reset
  ESP32. `open_serial` menyetel keduanya `False` sebelum `open()`.
- **Status.** Balasan `OK:` menandai sambungan sehat. Telemetri `iot.connected`
  menjadi `false` bila tidak ada balasan selama `IOT_ACK_TIMEOUT_SECONDS`, dan
  port yang galat dibuka ulang otomatis tiap `IOT_RECONNECT_SECONDS`.
- **Uji lampu** dari Pengaturan ditolak (409) selama ada pekerja di jalur.

## 5. Memasang firmware

1. Arduino IDE → Boards Manager → **esp32 by Espressif** → board **ESP32 Dev Module**.
2. Buka `iot/esp32_gate_controller/esp32_gate_controller.ino`, lalu Upload.
3. Untuk modul relay Active-HIGH, tukar nilai `RELAY_ON` dan `RELAY_OFF`.
4. Setelah papan menyala, lampu kuning berkedip. Ini benar: belum ada server.

## 6. Konfigurasi backend (`backend/.env`)

```ini
IOT_ENABLED=true
IOT_TYPE=serial
IOT_SERIAL_PORT=COM3        # Linux: /dev/ttyUSB0
```
Tutup Serial Monitor Arduino IDE sebelum server dijalankan, karena satu port
hanya bisa dibuka satu program.

## 7. Pengujian

1. **Tanpa server:** `python iot/test_serial_lights.py COM3`. Urutannya hijau,
   kuning, merah, padam (masing-masing 3 dtk), lalu heartbeat dihentikan dan
   papan harus kuning berkedip.
2. **Dengan server:** jalankan `python -m backend`, lalu buka Pengaturan → uji lampu.
   Saat ada orang di jalur, uji lampu harus ditolak.
3. **Server mati mendadak:** tutup server saat lampu hijau. Dalam ≤3 dtk lampu
   harus beralih ke kuning berkedip.
4. **Kabel dicabut lalu dicolok lagi:** lampu kuning berkedip, lalu kembali
   mengikuti server dalam ~2 dtk tanpa restart server.

**Simulator Wokwi (VS Code).** Kompilasi firmware dengan Arduino IDE
(*Sketch → Export Compiled Binary*) atau
`arduino-cli compile -b esp32:esp32:esp32 --export-binaries`. Hasilnya dipakai
oleh `iot/wokwi_simulation/wokwi.toml`. Jalankan simulator, lalu isi
`IOT_SERIAL_PORT=rfc2217://localhost:4000`.

## 8. Pemasangan lapangan (setelah demo)

- Untuk kabel USB panjang atau tiang besi, pasang isolator USB (ADuM3160).
- Kabel 12V ke lampu boleh panjang (≤20 m). Taruh ESP32 dekat PC.
- Palang/boom, sensor lewat, dan perilaku saat listrik padam ada di
  `docs/RENCANA.md`, bagian rencana IoT tahap 2.

## 9. Alternatif uji coba: relay USB HID 2 kanal (T54)

Tanpa ESP32: **relay USB dcttech "USBRelay2"** (VID `16C0`, PID `05DF`, tanpa
driver, tidak muncul sebagai port COM) + **adaptor 12V 1A** + **dua lampu LED 12V**.
Pengendalinya `backend/usb_relay.py`, lewat pustaka `hidapi`.

| Lampu | Kanal | Menyala saat |
| :-- | :-- | :-- |
| Hijau | relay 1 (`IOT_RELAY_GREEN_CHANNEL`) | **Hanya** APD lengkap |
| Merah | relay 2 (`IOT_RELAY_RED_CHANNEL`) | **Hanya** APD kurang |
| — | — | Selain itu (siaga, arahan posisi, menunggu VLM, gangguan kamera/sistem) **keduanya mati** — tidak ada kuning |

**Pengkabelan:** `+12V` adaptor → **COM** relay; **NO** relay → `+` lampu; `−` lampu →
`−12V` adaptor. Wajib **NO (Normally Open)**: lampu mati saat relay tidak aktif atau
papan tanpa daya. Kabel ke NC membuat lampu menyala justru saat sistem mati.

**`backend/.env`:** `IOT_ENABLED=true`, `IOT_TYPE=usb_relay` (kanal & serial: lihat `.env.example`).

**Protokol** (dari `usb_relay_lib.c` vendor & `usbrelay`): perintah = HID *feature report*
9 byte `[0x00, 0xFF nyala / 0xFD mati, nomor relay, 0…]`; status = feature report ID 0,
9 byte: byte 1–5 serial, byte 8 bitmask relay menyala (bit 0 = relay 1). `write()` biasa
diterima Windows tetapi **diabaikan papan** (uji 13-10).

**Relay mengunci keadaannya** (tanpa heartbeat seperti firmware ESP32). Pengaman:
- status dibaca balik tiap `IOT_HEARTBEAT_SECONDS` dan dikoreksi; tidak cocok / dicabut →
  status lampu "terputus" di dashboard, sambung ulang otomatis;
- server berhenti rapi → semua relay mati;
- server crash → penjaga proses (`python -m backend.supervisor`, dipakai `start_system.bat`)
  mematikan semua relay sebelum menyalakan ulang server;
- kabel USB dicabut / laptop mati → papan tanpa daya → relay lepas.

**Sisa risiko:** server **macet tanpa crash** (proses hidup, tidak menjawab) membuat
lampu tertahan pada keadaan terakhir, termasuk hijau. Untuk itu dibutuhkan papan
dengan heartbeat (ESP32, bagian 1–7). Diterima untuk uji coba demo (keputusan 13-10).
