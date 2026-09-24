# 🛡️ SAFEGUARD AI: Real-Time PPE Compliance Inspection System
> **Sistem Inspeksi Kepatuhan Alat Pelindung Diri (APD) Otomatis Berbasis YOLO26s-Pose, Google Gemini VLM, dan IoT Gerbang K3**

Sistem inspeksi kepatuhan K3 modern yang dirancang untuk memverifikasi kelengkapan APD pekerja secara *real-time* di gerbang masuk area industri/proyek. Menggabungkan kecepatan **Computer Vision Edge AI (RTX 4060)** untuk verifikasi postur tubuh utuh (*Full-Body Gatekeeper*) dan kecerdasan **Vision-Language Model (Gemini 3.5 Flash-Lite)** untuk audit visual mendalam.

---

## 💻 Teknologi yang Digunakan (*Tech Stack*)

### 1. Computer Vision & AI / ML (Edge Layer)
* **Model Pose Estimation:** `YOLO26s-Pose` (Ultralytics) terakselerasi **NVIDIA CUDA** pada **NVIDIA GeForce RTX 4060 Laptop GPU** (~4–7 ms per frame).
* **Multi-Object Tracking:** `ByteTrack` untuk pelacakan ID subjek pekerja secara konsisten tanpa tumpang tindih.
* **Keypoints Analysis:** Evaluasi 17 titik sendi tubuh (mata, bahu, pinggul, lutut, dan pergelangan kaki) untuk memastikan postur pekerja utuh dari kepala hingga kaki sebelum analisis APD dipicu.
* **Pemilihan Sumber di Awal:** Saat server menyala, tidak ada kamera yang dibuka sama sekali. Dashboard menampilkan dialog pemilihan berisi nama asli tiap perangkat, dan video baru tersambung setelah operator memilih — tidak ada kamera yang terlanjur dipakai lalu diganti. Kamera yang terakhir dipakai hanya disorot sebagai bawaan, bukan disambung otomatis.
* **Pemilihan Mode Kamera:** Kamera dibuka seketika dengan permintaan bawaan yang terbukti lancar di berbagai perangkat, lalu tombol **Pindai kamera** mengukur seluruh mode dan memilih yang terbaik. Dua temuan pengukuran mendasari rancangan ini: (1) laju frame bergantung pada angka yang **diminta**, bukan hasilnya — meminta 848×480 menghasilkan 19,9 FPS sedangkan meminta 854×480 menghasilkan 29,7 FPS walau frame-nya sama-sama 848×480; (2) sebagian kamera USB baru mencapai laju stabilnya ~3,5 detik setelah dibuka (1 FPS di detik pertama, 26 FPS di detik keempat), sehingga pengukuran yang akurat tidak mungkin dilakukan secara instan.
* **Kelancaran di Atas Rasio:** Mode dipilih dengan mengutamakan laju frame. Kamera USB penguji hanya mampu 7 FPS pada 16:9 tetapi 25 FPS pada 4:3, dan sistem memilih yang 4:3 — frame 4:3 aman karena overlay canvas menyesuaikan diri terhadap letterbox.
* **Pemulihan Kamera:** Kamera yang tercabut terdeteksi dalam ~1 detik, dilaporkan di ribbon dashboard, dan disambung ulang otomatis tanpa membekukan aliran video.
* **Corridor & Fast-Pass Engine:** OpenCV (`cv2`) untuk Virtual Inspection Corridor, segmentasi warna HSV reflektif rompi (*Hi-Vis Orange/Yellow*), dan ekstraksi area kepala/kaki.

### 2. Vision-Language Model (VLM & Cloud Layer)
* **Model VLM (bebas penyedia):** dipilih lewat `VLM_PROVIDER` / `VLM_MODEL` di `backend/.env`, tanpa mengubah kode. Bawaan `Google Gemini 3.5 Flash-Lite` (SDK `google-genai`, ~1,5 dtk per inspeksi). Alternatif offline: model lokal lewat Ollama, mis. `qwen2.5vl:3b` (~3 dtk, tanpa API key). Juga didukung OpenRouter, Qwen (DashScope), DeepSeek (`deepseek-flash`), OpenAI, dan server vLLM. Semua penyedia memakai adaptor di `backend/vlm_providers/`; timeout, percobaan ulang, dan penilaian kelengkapan sama untuk semuanya. Model dipanaskan saat server menyala sehingga pekerja pertama tidak menunggu model dimuat.
* **Hybrid Auto / Local Fallback:** Jika jaringan terputus, API lambat, atau mode offline diaktifkan, sistem beralih otomatis ke *engine* lokal berbasis heuristik warna OpenCV (HSV) yang berjalan di CPU — tanpa dependensi cloud, tetapi dengan akurasi yang jauh lebih rendah daripada VLM. Keputusan yang berasal dari jalur ini ditandai eksplisit di dashboard dan di kolom CSV audit.
* **Prompt Engineering K3:** Inferensi terstruktur yang mengembalikan format JSON standar untuk helm, rompi hi-vis, celana panjang, dan sepatu tertutup.
* **API Anti-Spam Cache:** Membatasi inferensi tepat **1 frame per subjek unik**, dengan jeda minimum 4 detik antar panggilan dan kunci konkurensi, untuk mencegah pemborosan kuota API dan galat 429.

### 3. Backend & Layanan Komunikasi
* **Runtime:** Python 3.10 (Conda Environment).
* **Web Framework:** `FastAPI` (REST API asinkron) & `Uvicorn` (dengan integrasi *Graceful Server Shutdown*).
* **Real-time Telemetry:** `WebSocket` murni (interval 50 ms, ~20 Hz) untuk streaming bounding box, status APD, FPS, dan status cloud ke antarmuka pengguna.
* **Video Pipeline:** MJPEG Multi-part HTTP Video Streaming. Pembacaan kamera dan inferensi YOLO berjalan di dua thread terpisah sehingga frame yang tertahan di buffer driver dibuang, bukan menumpuk jadi latensi.
* **Database & Penyimpanan:** `SQLite3` (mode WAL - *Write-Ahead Logging*) untuk pencatatan riwayat audit pekerja, serta penyimpanan crop bukti foto snapshot JPEG otomatis.

### 4. Audio Engine & Panduan Suara
* **Playback Engine:** `pygame.mixer` (multi-threaded, non-blocking audio queue).
* **Voice Generation:** gTTS (Google Text-to-Speech) berbahasa Indonesia, dibangkitkan sekali lewat `python -m backend.generate_audio` menjadi berkas MP3 statis.
* **Smart Voice Limiter:** Pembatas otomatis maksimal 2 kali peringatan per orang untuk mencegah kebisingan berlebih (*anti-audio spam*), disertai sakelar *Mute* di web dashboard.

### 5. Frontend & UI/UX
* **Arsitektur:** Single Page Application (SPA) 3-Tab tanpa reload halaman.
* **Teknologi:** Vanilla HTML5, Vanilla Modern CSS3 (Dark Navy Slate Theme, CSS Custom Properties / Tokens, Glassmorphism, Micro-animations), dan Vanilla JavaScript (ES6+ Modules).
* **HUD Overlay:** HTML5 `<canvas>` yang digambar ulang setiap paket telemetri (~20 Hz) untuk garis batas koridor neon, bounding box dinamis, dan zona jejak kaki (*footprint standoff guide*). Overlay disejajarkan dengan kotak video hasil `object-fit: contain`, sehingga tetap presisi walau kamera mengirim rasio selain 16:9.
* **Desain Responsif:** Disesuaikan untuk monitor pos operator gerbang K3 maupun laptop pengawas.

### 6. IoT & Kontrol Gerbang Fisik
* **Mikrokontroler:** `ESP32 DevKit V1` (C++ / Arduino framework).
* **Protokol Komunikasi:** USB Serial Cable (baud rate **9600**) untuk demo langsung ke laptop, serta dukungan wireless HTTP REST client.
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
* **Kamera & Koridor:** Daftar kamera dengan **nama perangkat asli** (webcam bawaan maupun USB), tombol **Pindai kamera** untuk mengukur resolusi dan laju frame nyata tiap perangkat, serta sakelar batas koridor tengah. Pergantian kamera berlaku langsung tanpa menjalankan ulang server. Pilihan disimpan berdasarkan **nama**, bukan indeks, karena mencolokkan kamera USB menggeser nomor perangkat lain.
* **Aturan APD Wajib:** Checklist konfigurasi item APD yang diwajibkan untuk membuka gerbang.
* **Lepas & Pilih Ulang:** Tombol untuk melepas kamera yang sedang dipakai dan kembali ke dialog pemilihan tanpa menjalankan ulang server.
* **Pengujian Lampu Gerbang (IoT):** Tombol uji coba manual indikator fisik (**🟢 Tes Hijau**, **🔴 Tes Merah**, **⚪ Padam**).
* **Google Gemini API Key:** Input kunci API tersimpan aman di *server-side* dengan tombol uji latensi (*Ping*).
* **Token Admin (opsional):** Diisi hanya jika server dijalankan dengan `ADMIN_TOKEN`. Tersimpan di browser operator dan dilampirkan sebagai header pada setiap perintah yang mengubah state server.

---

## 📁 Struktur Direktori Proyek

```
ppe_detection_vlm/
├── backend/                      # Paket Python; jalankan dengan `python -m backend`
│   ├── __main__.py               # Titik masuk tunggal (memanggil `app.run()`)
│   ├── config.py                 # Konfigurasi server, batas koridor, dan threshold
│   ├── detector.py               # YOLO26s-Pose inference, ByteTrack & Full-Body Gatekeeper
│   ├── vlm_analyzer.py           # Klien VLM (timeout, rate-guard, fallback) & engine lokal
│   ├── vlm_providers/            # Adaptor penyedia VLM (kontrak di base.py; gemini.py)
│   ├── state_manager.py          # State Machine, Smart Voice Limiter & Anti-Spam Queue
│   ├── audio_engine.py           # Non-blocking audio queue player & Mute controller
│   ├── notifier.py               # Pengendali sinyal lampu gerbang & IoT Hardware Bridge
│   ├── report_manager.py         # SQLite3 audit repository & Snapshot JPEG manager
│   ├── camera_manager.py         # Enumerasi perangkat, probing mode, & pemilihan resolusi
│   ├── api_monitor.py            # Real-time latency monitor & engine mode switcher
│   ├── app.py                    # Bootstrap FastAPI: middleware, router, frontend statis, server
│   ├── shutdown.py               # Penanda berhenti bersama untuk stream & WebSocket
│   ├── messages.py               # Seluruh teks operasional (lampu, HUD, API, CSV)
│   ├── ppe_rules.py              # Katalog item APD — satu-satunya sumber definisi
│   ├── runtime_settings.py       # Pengaturan yang diubah operator (item APD aktif)
│   ├── video/
│   │   ├── capture.py            # Pembacaan kamera, inferensi per frame, JPEG untuk stream
│   │   └── hud.py                # HUD server-side & layar tunggu
│   ├── api/
│   │   ├── deps.py               # Guard ADMIN_TOKEN
│   │   ├── routes_system.py      # Health, reset, koridor, audio, uji lampu IoT
│   │   ├── routes_cameras.py     # Katalog, pemindaian, & pergantian kamera
│   │   ├── routes_ppe.py         # Katalog & item APD aktif
│   │   ├── routes_reports.py     # Riwayat inspeksi, snapshot, ekspor CSV
│   │   ├── routes_vlm.py         # API key, pemantauan latensi, mode engine
│   │   ├── routes_stream.py      # Aliran video MJPEG
│   │   └── websocket.py          # Telemetri real-time /ws
│   ├── generate_audio.py         # Pembangkit berkas MP3 panduan suara (gTTS)
│   ├── requirements.txt          # Dependensi Python library
│   ├── requirements-dev.txt      # + pytest, untuk pengembangan
│   ├── .env                      # File variabel lingkungan lokal
│   ├── .env.example              # Contoh variabel lingkungan
│   ├── storage.py                # Menyiapkan DATA_DIR & memindahkan data dari tata letak lama
│   ├── logging_setup.py          # Log konsol + berkas berotasi di DATA_DIR/logs
│   ├── yolo26s-pose.pt           # Satu-satunya bobot model (diabaikan git; diunduh otomatis bila hilang)
│   └── audio/                    # File suara instruksi K3 (MP3, aset rilis)
│
├── data/                         # DATA_DIR bawaan (diabaikan git; bisa dipindah lewat .env)
│   ├── camera_state.json         # Kamera & mode terakhir yang dipilih operator
│   ├── runtime_settings.json     # Item APD yang diwajibkan
│   ├── logs/safeguard.log        # Log aplikasi & uvicorn (berotasi 5 MB x 5)
│   └── reports/
│       ├── audit.db              # Database SQLite3 riwayat pemeriksaan
│       └── snapshots/            # Arsip bukti foto pekerja JPEG
│
├── tests/                        # pytest: gerbang, engine lokal, kamera, migrasi DB & data
│   └── conftest.py               # Isolasi: DATA_DIR sementara, tanpa Gemini, tanpa IoT
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
│   ├── arduino_gate_controller/
│   │   └── arduino_gate_controller.ino # Firmware alternatif Arduino Uno/Nano
│   ├── test_serial_lights.py     # Uji manual perintah lampu lewat serial
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

## ⚠️ Batasan yang Diketahui

Bagian ini sengaja dicantumkan agar klaim sistem dapat dipertanggungjawabkan.

* **Engine lokal bukan model AI.** `LocalVisionAnalyzer` adalah heuristik warna OpenCV (segmentasi HSV, rasio piksel) yang berjalan di CPU — bukan model *deep learning* dan bukan inferensi GPU. Hanya deteksi pose YOLO26s yang berjalan di CUDA. Akurasinya jauh di bawah Gemini VLM, terutama untuk helm dan alas kaki. Keputusan dari jalur ini selalu ditandai "Engine lokal — akurasi terbatas" di dashboard.
* **Anti-spoofing hanya pada jalur Gemini.** Penolakan foto di layar ponsel atau cetakan kertas ditegakkan lewat instruksi prompt VLM. Jalur lokal tidak memilikinya, sehingga dalam mode offline sistem dapat tertipu oleh foto.
* **Tanpa autentikasi secara bawaan.** Endpoint yang mengubah state dilindungi hanya jika `ADMIN_TOKEN` diisi pada `.env`. Tanpa itu, siapa pun yang dapat menjangkau host ini di jaringan bisa mengganti API key atau menyalakan lampu gerbang.
* **Data pribadi pada snapshot.** `DATA_DIR/reports/snapshots/` menyimpan potongan foto wajah pekerja tanpa batas waktu, dan `audit.db` menyimpan riwayat inspeksinya. Perlakukan sebagai data pribadi: batasi akses direktori tersebut dan tetapkan kebijakan retensi sebelum dipakai di lapangan.
* **Penamaan kamera khusus Windows.** Nama perangkat diambil lewat DirectShow (`pygrabber`). Di platform lain daftar tetap berfungsi, tetapi hanya menampilkan label generik `Kamera 0`, `Kamera 1`, dan seterusnya.
* **Resolusi rendah menurunkan ketelitian VLM.** Mode dipilih dengan prioritas kelancaran, sehingga potongan gambar yang dikirim ke Gemini bisa lebih kecil dari batas 640 px. Dashboard menampilkan peringatan saat ini terjadi. Untuk mengutamakan ketelitian, set `CAMERA_AUTO_MODE=false` lalu tentukan `FRAME_WIDTH`/`FRAME_HEIGHT` sendiri di `.env`.
* **Pemindaian kamera menghentikan video sementara.** Kamera yang sedang aktif terkunci oleh aliran video, jadi untuk mengukurnya sistem melepas perangkat itu lebih dulu. Selama proses (~15–25 detik per kamera) dashboard menampilkan layar tunggu. Lakukan pemindaian sebelum demo dimulai, bukan di tengahnya.
* **Satu subjek per inspeksi.** Koridor virtual dirancang untuk satu orang di tengah frame; beberapa orang sekaligus dalam koridor tidak ditangani secara eksplisit.

---

## 🚀 Panduan Menjalankan Sistem

### 1. Prasyarat Lingkungan
Pastikan Conda environment `apd_detection` telah aktif:
```powershell
conda activate apd_detection
```

### 2. Menjalankan Server Backend
Dari akar repositori, jalankan paket `backend`:
```powershell
python -m backend
```
*(Atau Anda cukup menjalankan berkas `start_system.bat`)*

Dari PowerShell (termasuk terminal bawaan VS Code), tulis `.\start_system.bat`. PowerShell tidak menjalankan skrip di folder aktif tanpa awalan `.\`. Hentikan server dengan `Ctrl+C` di jendela terminal tempat server berjalan; cmd lalu bertanya *Terminate batch job (Y/N)?*, jawab `Y`. `Ctrl+C` tidak sampai ke program bila server dijalankan dari panel **Output** VS Code; karena itu proyek ini menyetel `code-runner.runInTerminal` agar tombol Run Code memakai tab **Terminal**.

`backend/` adalah paket Python dengan impor relatif, sehingga harus dijalankan sebagai modul dari akar repo. Menjalankan berkas di dalam `backend/` secara langsung (misalnya `python backend/app.py`) tidak didukung. Jalur `.env`, bobot model, dan audio diselesaikan relatif terhadap direktori `backend/`, bukan direktori kerja terminal.

**Data runtime terpisah dari kode.** Audit, foto bukti, pilihan kamera, dan item APD aktif disimpan di `DATA_DIR`. Bawaannya folder `data/` di akar repo. Untuk produksi, isi `DATA_DIR` di `.env` dengan jalur absolut di luar repo, misalnya `C:\ProgramData\SafeguardAI`, supaya deploy ulang tidak menyentuh data. Data lama yang masih berada di `backend/` dipindah otomatis saat server pertama kali dijalankan; berkas yang bentrok dengan isi tujuan tidak ditimpa, melainkan dilaporkan di log.

Perintah bantu lain juga dijalankan dari akar repo: `python -m backend.generate_audio` untuk membangkitkan MP3, dan `python -m pytest` untuk menjalankan seluruh tes di `tests/` (pasang dulu `pip install -r backend/requirements-dev.txt`). Tes memakai `DATA_DIR` sementara, tidak memanggil Gemini, dan tidak membuka port IoT, jadi aman dijalankan di mesin produksi.

Server akan otomatis memuat model YOLO26s-Pose di GPU CUDA dan melayani aplikasi di `http://0.0.0.0:8000`.

### 3. Membuka Dashboard Web
Buka browser (Google Chrome, Microsoft Edge, atau Brave) dan navigasikan ke:
```
http://localhost:8000
```

Saat pertama dibuka, dashboard menampilkan dialog **Pilih Sumber Kamera**. Video belum tersambung sampai Anda memilih salah satu perangkat.

Untuk menghentikan server, tekan **`Ctrl + C`** sekali di jendela terminal. Sistem melepaskan kamera dan menutup seluruh koneksi dalam ~1 detik, termasuk aliran video dan WebSocket yang masih terbuka di browser.

---

## 🔌 Uji Coba Hardware ESP32 (Demo via Kabel USB)

1. Hubungkan board **ESP32 DevKit V1** ke laptop menggunakan kabel data USB.
2. Buka **Device Manager** di Windows, periksa nomor port COM yang terdeteksi (misal: `COM3`).
3. Flash firmware dari `iot/esp32_gate_controller/esp32_gate_controller.ino` melalui Arduino IDE.
4. Pada Dashboard Web di menu **Pengaturan**, periksa bagian **Lampu Indikator Fisik Gerbang (ESP32)** dan klik tombol **🟢 Tes Hijau** atau **🔴 Tes Merah** untuk menguji aktuasi relay/LED secara langsung.
