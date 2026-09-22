# 🌐 Panduan Simulasi IoT Gerbang K3 di Wokwi

Simulator ini memvisualisasikan sirkuit rekomendasi:
- **Arduino Uno**
- **2 Unit Modul Relay SPDT** (Relay Hijau & Relay Merah)
- **2 Unit Lampu Bulat Terpisah** (Lampu Hijau & Lampu Merah)
- **Resistor Pull-Down 10k $\Omega$** pada Pin D2 & D3 (Anti-Glitch)
- **Resistor Pembatas Arus 220 $\Omega$** untuk lampu

---

## Cara Menjalankan Simulasi di Browser (Gratis, Tanpa Install)

1. Buka browser dan kunjungi: **[https://wokwi.com/projects/new/arduino-uno](https://wokwi.com/projects/new/arduino-uno)**
2. Pada tab **`sketch.ino`**:
   - Hapus semua isi kodenya, lalu salin dan tempel (*paste*) isi file [`sketch.ino`](sketch.ino) dari folder ini.
3. Pada tab **`diagram.json`**:
   - Klik tab `diagram.json` (di sebelah tab code).
   - Hapus semua isinya, lalu salin dan tempel (*paste*) isi file [`diagram.json`](diagram.json) dari folder ini.
4. Klik tombol **Play (▶️)** di pojok kanan atas untuk memulai simulasi.

---

## Cara Menguji Lampu Fisik Virtual

Setelah tombol Play ditekan:
1. Arduino akan melakukan **Self-Test** otomatis: Lampu Hijau berkedip 1x, lalu Lampu Merah berkedip 1x.
2. Di bagian bawah layar Wokwi terdapat jendela **Serial Monitor**.
3. Ketik perintah berikut lalu tekan **Enter**:
   - `LIGHT_GREEN` $\rightarrow$ Relay 1 berbunyi *klik*, **Lampu Bulat Hijau MENYALA**.
   - `LIGHT_RED` $\rightarrow$ Relay 2 berbunyi *klik*, **Lampu Bulat Merah MENYALA**.
   - `LIGHT_OFF` $\rightarrow$ Kedua lampu **PADAM** (Mode Standby).

---

## Menghubungkan Simulator Wokwi dengan Backend Python (`main.py`)

Jika Anda menginstall ekstensi **Wokwi for VS Code**:
1. Pasang ekstensi **Wokwi Simulator** di VS Code.
2. Jalankan simulasi di VS Code (`Ctrl+Shift+P` $\rightarrow$ `Wokwi: Start Simulator`). Wokwi akan membuka server serial virtual RFC2217 pada port `4000`.
3. Pada file `backend/.env`, ubah:
   ```ini
   IOT_ENABLED=true
   IOT_TYPE=serial
   IOT_SERIAL_PORT=rfc2217://localhost:4000
   IOT_SERIAL_BAUD=9600
   ```
4. Jalankan backend AI:
   ```bash
   python main.py
   ```
   Setiap kali AI mendeteksi pekerja di kamera:
   - APD Lengkap $\rightarrow$ Lampu Bulat Hijau di Wokwi otomatis menyala real-time!
   - APD Melanggar $\rightarrow$ Lampu Bulat Merah di Wokwi otomatis menyala real-time!
