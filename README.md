# 🛡️ SAFEGUARD AI: Real-Time PPE Compliance Inspection System

Sistem inspeksi kepatuhan Alat Pelindung Diri (APD) otomatis dan *real-time* berbasis **Computer Vision (YOLOv8s-Pose)** dan **Vision-Language Model (Gemini VLM API)** yang dipisahkan secara tegas antara **Backend** dan **Frontend** (*Decoupled Architecture*).

---

## 🌟 Fitur Utama & Kepatuhan APD

1. **Aturan Kelengkapan APD**:
   - 🪖 **Helm Keselamatan (Hard Hat)**: Terdeteksi helm keselamatan kerja. **Warna bebas** (putih, kuning, biru, merah, dll diizinkan).
   - 🦺 **Rompi Keselamatan (Hi-Vis Vest)**: Wajib berwarna **orange** atau **kuning / lime green** reflektif.
   - 👖 **Celana Panjang**: Wajib celana panjang (bukan celana pendek).
   - 👟 **Sepatu Tertutup**: Wajib memakai sepatu tertutup jenis apa pun (safety boots, sneaker, dsb. Bukan sandal/telanjang kaki).

2. **Deteksi Cepat & Efisien (YOLO Small)**:
   - Menggunakan model `yolov8s-pose.pt` terakselerasi GPU NVIDIA RTX 4060 dengan latensi inferensi ultra-rendah (~4-7 ms).
   - Melacak pergerakan subjek dengan ID unik (`track_id`) menggunakan algoritma **ByteTrack**.

3. **Filter Full-Body & Audio "Silakan Mundur"**:
   - Jika seseorang mendekat ke kamera dan tubuhnya terpotong (misal: kepala atau kaki tidak terlihat di dalam batas frame kamera), sistem secara otomatis memicu suara speaker:
     > *"Silakan mundur sampai seluruh tubuh terlihat."*
   - Analisa Gemini VLM **hanya dipicu jika tubuh pekerja sudah tertangkap penuh dan stabil**.

4. **Anti-Spam Pengiriman API**:
   - **Tepat 1 frame per orang**: Setelah seseorang berhasil dianalisa, hasil JSON dan status kelulusan di-cache untuk `track_id` tersebut.
   - Tidak ada panggilan API berulang (*no spam*) selama orang tersebut masih berada di area inspeksi.

5. **Indikator Lampu & Audio Speaker**:
   - 🟢 **APD Lengkap**: Lampu hijau menyala + suara *"APD lengkap. Akses diizinkan. Silakan masuk."*
   - 🔴 **APD Tidak Lengkap**: Lampu merah menyala + suara peringatan menyebutkan item yang kurang.
   - 🟡 **Peringatan Mundur**: Lampu kuning menyala saat subjek terlalu dekat.
   - Dilengkapi modul **IoT Notifier** modular (Serial/Arduino/Relay) yang siap dihubungkan ke lampu tower fisik di tahap berikutnya.

6. **Keamanan API Key Server-Side**:
   - `GEMINI_API_KEY` disimpan secara aman di sisi server (`backend/.env`). Frontend tidak pernah menerima atau mengekspos API key.
   - Dilengkapi **Smart Mock Mode**: jika API key belum diisi, sistem tetap dapat diuji coba secara interaktif dan lancar tanpa error.

---

## 🏗️ Struktur Arsitektur

```
ppe_detection_vlm/
├── backend/
│   ├── config.py             # Konfigurasi server & model
│   ├── detector.py           # YOLOv8s-Pose, Tracking & Filter Full-Body
│   ├── vlm_analyzer.py       # Gemini VLM (Server-Side) & Smart Mock
│   ├── state_manager.py      # State tracking & Anti-Spam debouncer
│   ├── audio_engine.py       # Audio speaker non-blocking (pygame)
│   ├── notifier.py           # Virtual Tower Light & Modular IoT Interface
│   ├── generate_audio.py     # Generator klip suara Bahasa Indonesia
│   ├── main.py               # FastAPI server (MJPEG Stream & WebSocket /ws)
│   ├── requirements.txt      # Dependensi backend
│   ├── .env                  # Konfigurasi aktif (GEMINI_API_KEY, dsb)
│   └── audio/                # File MP3 suara instruksi K3
│
├── frontend/
│   ├── index.html            # Dashboard visualisasi real-time
│   ├── css/style.css         # Styling dark modern industrial K3
│   └── js/
│       ├── app.js            # Main controller
│       ├── websocket.js      # Real-time WebSocket client (<10ms)
│       ├── hud_overlay.js    # Canvas HUD renderer 60 FPS
│       └── apd_card.js       # Komponen kartu APD & Tower Light
│
├── start_system.bat          # Script 1-klik untuk menjalankan sistem
└── README.md
```

---

## 🚀 Cara Menjalankan Sistem

### 1. Prasyarat Lingkungan
Pastikan Anda berada di lingkungan Conda `apd_detection`:
```bash
conda activate apd_detection
```

### 2. Menjalankan Server Backend
Jalankan perintah berikut:
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Atau cukup klik dua kali pada file `start_system.bat`.

### 3. Membuka Dashboard Frontend
Buka browser favorit Anda dan akses:
```
http://localhost:8000
```

---

## ⚙️ Pengaturan & Kunci Gemini API

1. **Menggunakan Mode Simulasi (Tanpa API Key)**:
   - Secara *default*, sistem langsung aktif dalam **Smart Mock Mode** sehingga Anda dapat menguji pelacakan webcam, filter posisi, dan suara tanpa harus menunggu API key.
2. **Memasukkan Gemini API Key**:
   - Buka dashboard di browser $\rightarrow$ Klik tombol **⚙️ Pengaturan Server**.
   - Masukkan `GEMINI_API_KEY` Anda lalu klik **Simpan ke Server**.
   - Sistem akan langsung beralih ke model live **Gemini 2.5 Flash**.

---

## 🔌 Kesiapan IoT Hardware (Tahap 2)

Class `IoTNotifier` di `backend/notifier.py` telah disiapkan:
- Jika ingin menyambungkan ke lampu tower fisik via Arduino / ESP32:
  1. Ubah di `backend/.env`:
     ```env
     IOT_ENABLED=true
     IOT_TYPE=serial
     IOT_SERIAL_PORT=COM3
     IOT_SERIAL_BAUD=9600
     ```
  2. Perangkat akan menerima sinyal `LIGHT_GREEN`, `LIGHT_RED`, atau `LIGHT_OFF` secara otomatis.
