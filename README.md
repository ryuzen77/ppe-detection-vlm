# 🛡️ SAFEGUARD AI: Real-Time PPE Compliance Inspection System
> **Sistem Inspeksi Kepatuhan Alat Pelindung Diri (APD) Otomatis Berbasis YOLO26s-Pose, Google Gemini VLM, dan IoT Gerbang K3**

Sistem inspeksi kepatuhan K3 modern yang dirancang untuk memverifikasi kelengkapan APD pekerja secara *real-time* di gerbang masuk area industri/proyek. Menggabungkan kecepatan **Computer Vision Edge AI (RTX 4060)** untuk verifikasi postur tubuh utuh (*Full-Body Gatekeeper*) dan kecerdasan **Vision-Language Model (Gemini 2.5 Flash)** untuk audit visual mendalam.

---

## 💻 Teknologi yang Digunakan (*Tech Stack*)

### 1. Computer Vision & AI / ML (Edge Layer)
* **Model Pose Estimation:** `YOLO26s-Pose` (Ultralytics) terakselerasi **NVIDIA CUDA** pada **NVIDIA GeForce RTX 4060 Laptop GPU** (~4–7 ms per frame).
* **Multi-Object Tracking:** `ByteTrack` untuk pelacakan ID subjek pekerja secara konsisten tanpa tumpang tindih.
* **Keypoints Analysis:** Evaluasi 17 titik sendi tubuh (mata, bahu, pinggul, lutut, dan pergelangan kaki) untuk memastikan postur pekerja utuh dari kepala hingga kaki sebelum analisis APD dipicu.
* **Corridor & Fast-Pass Engine:** OpenCV (`cv2`) untuk Virtual Inspection Corridor, segmentasi warna HSV reflektif rompi (*Hi-Vis Orange/Yellow*), dan ekstraksi area kepala/kaki.

### 2. Vision-Language Model (VLM & Cloud Layer)
* **Model VLM:** `Google Gemini 2.5 Flash` via Google GenAI SDK.
* **Hybrid Auto / Local Fallback:** Jika jaringan internet terputus atau mode offline diaktifkan, sistem secara otomatis beralih ke analisis lokal GPU RTX 4060 (100% *air-gapped* tanpa dependensi cloud).
* **Prompt Engineering K3:** Inferensi terstruktur yang mengembalikan format JSON standar untuk helm, rompi hi-vis, celana panjang, dan sepatu tertutup.
* **API Anti-Spam Cache:** Membatasi inferensi tepat **1 frame per subjek unik** untuk mencegah pemborosan kuota API.

### 3. Backend & Layanan Komunikasi
* **Runtime:** Python 3.10 (Conda Environment).
* **Web Framework:** `FastAPI` (REST API asinkron) & `Uvicorn` (dengan integrasi *Graceful Server Shutdown*).
* **Real-time Telemetry:** `WebSocket` murni (frekuensi transmisi ~20 Hz) untuk streaming bounding box, status APD, FPS, dan status cloud ke antarmuka pengguna dengan latensi <10 ms.
* **Video Pipeline:** MJPEG Multi-part HTTP Video Streaming dengan *non-blocking threading* dan *frame lock*.
* **Database & Penyimpanan:** `SQLite3` (mode WAL - *Write-Ahead Logging*) untuk pencatatan riwayat audit pekerja, serta penyimpanan crop bukti foto snapshot JPEG otomatis.

### 4. Audio Engine & Panduan Suara
* **Playback Engine:** `pygame.mixer` (multi-threaded, non-blocking audio queue).
* **Voice Generation:** Microsoft Edge-TTS dengan profil suara Bahasa Indonesia alami (`id-ID-ArdiNeural`).
* **Smart Voice Limiter:** Pembatas otomatis maksimal 2 kali peringatan per orang untuk mencegah kebisingan berlebih (*anti-audio spam*), disertai sakelar *Mute* di web dashboard.

### 5. Frontend & UI/UX
* **Arsitektur:** Single Page Application (SPA) 3-Tab tanpa reload halaman.
* **Teknologi:** Vanilla HTML5, Vanilla Modern CSS3 (Dark Navy Slate Theme, CSS Custom Properties / Tokens, Glassmorphism, Micro-animations), dan Vanilla JavaScript (ES6+ Modules).
* **HUD Overlay:** HTML5 `<canvas>` rendering 60 FPS untuk rendering garis batas koridor neon, bounding box dinamis, dan zona jejak kaki (*footprint standoff guide*).
* **Desain Responsif:** Disesuaikan untuk monitor pos operator gerbang K3 maupun laptop pengawas.

### 6. IoT & Kontrol Gerbang Fisik
* **Mikrokontroler:** `ESP32 DevKit V1` (C++ / Arduino framework).
* **Protokol Komunikasi:** USB Serial Cable (Baud rate 115200) untuk demo langsung ke laptop, serta dukungan wireless HTTP REST client.
* **Perangkat Keras:** Modul Relay 5V / Optocoupler, Tower Light Indikator Industri (Merah / Hijau / Buzzer), atau Solenoid Door Lock.
* **Simulasi Virtual:** Integrasi siap pakai dengan simulator perangkat keras **Wokwi** (`diagram.json`).

---

## 🌟 Aturan Pemeriksaan APD Wajib

| Item APD | Kriteria Lolos (Hijau) | Kriteria Pelanggaran (Merah) |
| :--- | :--- | :--- |
| 🪖 **Helm Safety** | Terdeteksi helm keselamatan kerja proyek (**Warna bebas**: putih, kuning, biru, merah, oranye, dll). | Tidak memakai helm, atau memakai topi santai/kupluk. |
| 🦺 **Rompi Reflektif** | Memakai rompi dengan warna keselamatan **Orange**, **Kuning**, atau **Lime Green** reflektif. | Tidak memakai rompi, atau memakai rompi kain biasa tanpa warna keselamatan / reflektor. |
| 👖 **Celana Panjang** | Memakai celana panjang menutupi seluruh kaki. | Memakai celana pendek, celana 3/4, atau rok/gaun terbuka. |
| 👞 **Sepatu Tertutup** | Memakai sepatu tertutup (*safety boots*, sneakers, sepatu kerja tertutup). | Memakai sandal, selop, sandal jepit, atau telanjang kaki. |

---

## 🖥️ Fitur Dashboard UI/UX (3-Tab Architecture)

### 1. Menu Monitoring
* **Kamera Inspeksi Live:** Tampilan video resolusi penuh dengan overlay batas area inspeksi neon kuning.
* **Toolbar Kontrol:**
  * Sakelar **Panduan Posisi**: Sembunyikan atau tampilkan panduan batas lorong di layar.
  * Sakelar **Suara**: Membisukan (*Mute*) atau mengaktifkan suara panduan speaker secara instan.
  * **Detail Teknis**: Accordion informasi engine mode, latensi inferensi, dan active track ID.
  * **Mulai Ulang**: Tombol reset pelacakan subjek.
* **Kartu Panduan Interaktif & Stepper 3-Tahap:**
  1. *Tahap 1 (Posisi)*: Memandu subjek berdiri tepat di tengah lorong hingga kepala sampai kaki terlihat.
  2. *Tahap 2 (APD)*: Menganalisis kelengkapan 4 item APD menggunakan AI.
  3. *Tahap 3 (Hasil)*: Menampilkan keputusan final (*Akses Diizinkan / Akses Ditolak*).
* **Checklist APD 4-Item:** Lencana status interaktif untuk helm, rompi, celana, dan sepatu.
* **Riwayat Pemeriksaan Terbaru:** Log singkat subjek yang baru saja diperiksa.

### 2. Menu Laporan
* **Ringkasan KPI K3:** Kartu metrik Total Pemeriksaan, Lolos APD, Pelanggaran, dan Tingkat Kepatuhan (%).
* **Filter Interaktif:** Filter segmented (*Semua Data*, *✅ Lengkap*, *⚠️ Pelanggaran*) dan pemilih tanggal (*Date Picker*).
* **Tabel Riwayat & Bukti Snapshot:** Menampilkan foto snapshot pekerja saat diperiksa, waktu presisi, status kelulusan, dan catatan APD yang kurang. Foto dapat diklik untuk pratinjau resolusi penuh.
* **Ekspor CSV:** Unduh spreadsheet audit riwayat kepatuhan pekerja untuk arsip HSE K3.

### 3. Menu Pengaturan
* **Kamera & Koridor:** Pilihan indeks kamera fisik (Webcam/USB) dan sakelar batas koridor tengah.
* **Aturan APD Wajib:** Checklist konfigurasi item APD yang diwajibkan untuk membuka gerbang.
* **Pengujian Lampu Gerbang (IoT):** Tombol uji coba manual indikator fisik (**🟢 Tes Hijau**, **🔴 Tes Merah**, **⚪ Padam**).
* **Google Gemini API Key:** Input kunci API tersimpan aman di *server-side* dengan tombol uji latensi (*Ping*).

---

## 📁 Struktur Direktori Proyek

```
ppe_detection_vlm/
├── backend/
│   ├── config.py                 # Konfigurasi server, batas koridor, dan threshold
│   ├── detector.py               # YOLO26s-Pose inference, ByteTrack & Full-Body Gatekeeper
│   ├── vlm_analyzer.py           # Gemini 2.5 Flash VLM client & Hybrid Local GPU Engine
│   ├── state_manager.py          # State Machine, Smart Voice Limiter & Anti-Spam Queue
│   ├── audio_engine.py           # Non-blocking audio queue player & Mute controller
│   ├── notifier.py               # Pengendali sinyal lampu gerbang & IoT Hardware Bridge
│   ├── report_manager.py         # SQLite3 audit repository & Snapshot JPEG manager
│   ├── api_monitor.py            # Real-time latency monitor & engine mode switcher
│   ├── main.py                   # FastAPI REST backend, WebSocket /ws, & Static Server
│   ├── requirements.txt          # Dependensi Python library
│   ├── .env                      # File variabel lingkungan lokal
│   ├── audio/                    # File suara instruksi K3 (MP3)
│   └── reports/
│       ├── audit.db              # Database SQLite3 riwayat pemeriksaan
│       └── snapshots/            # Arsip bukti foto pekerja JPEG
│
├── frontend/
│   ├── index.html                # Tampilan utama Dashboard (Single Page App 3-Tab)
│   ├── css/
│   │   └── style.css             # Desain styling Dark Navy Slate Industrial K3
│   └── js/
│       ├── app.js                # Pengendali utama frontend, tab switcher, dan audio toggle
│       ├── apd_card.js           # Pengendali kartu panduan, stepper 3-tahap, dan checklist
│       ├── hud_overlay.js        # Canvas overlay 60 FPS untuk koridor dan jejak kaki
│       └── websocket.js          # Klien WebSocket telemetri real-time (<10 ms)
│
├── iot/
│   ├── esp32_gate_controller/
│   │   └── esp32_gate_controller.ino  # Firmware Arduino/C++ ESP32 USB & Wi-Fi
│   └── wokwi_simulation/
│       ├── diagram.json          # Rangkaian diagram sirkuit Wokwi
│       ├── sketch.ino            # Kode simulasi Wokwi
│       └── wokwi.toml            # Konfigurasi simulator Wokwi
│
├── IOT_HARDWARE_SPEC.md          # Spesifikasi teknis perangkat keras & wiring ESP32
├── start_system.bat              # Skrip 1-klik untuk menjalankan sistem di Windows
└── README.md                     # Dokumentasi komprehensif proyek
```

---

## 🚀 Panduan Menjalankan Sistem

### 1. Prasyarat Lingkungan
Pastikan Conda environment `apd_detection` telah aktif:
```powershell
conda activate apd_detection
```

### 2. Menjalankan Server Backend
Jalankan file server utama:
```powershell
python backend/main.py
```
*(Atau Anda cukup menjalankan berkas `start_system.bat`)*

Server akan otomatis memuat model YOLO26s-Pose di GPU CUDA dan melayani aplikasi di `http://0.0.0.0:8000`.

### 3. Membuka Dashboard Web
Buka browser (Google Chrome, Microsoft Edge, atau Brave) dan navigasikan ke:
```
http://localhost:8000
```

Untuk menghentikan server, tekan **`Ctrl + C`** di jendela terminal. Sistem akan melepaskan kamera dan menutup seluruh koneksi secara bersih.

---

## 🔌 Uji Coba Hardware ESP32 (Demo via Kabel USB)

1. Hubungkan board **ESP32 DevKit V1** ke laptop menggunakan kabel data USB.
2. Buka **Device Manager** di Windows, periksa nomor port COM yang terdeteksi (misal: `COM3`).
3. Flash firmware dari `iot/esp32_gate_controller/esp32_gate_controller.ino` melalui Arduino IDE.
4. Pada Dashboard Web di menu **Pengaturan**, periksa bagian **Lampu Indikator Fisik Gerbang (ESP32)** dan klik tombol **🟢 Tes Hijau** atau **🔴 Tes Merah** untuk menguji aktuasi relay/LED secara langsung.
