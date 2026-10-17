# Instalasi & menjalankan DEPRO

Ringkasan singkatnya ada di [README](../README.md). Dokumen ini berisi rinciannya.

## 1. Prasyarat lingkungan

Python **3.12** lewat **Miniconda**. Versi paket dikunci di `backend/requirements.lock`
(server) dan `backend/requirements-dev.lock` (server + pytest + ruff).

- **Conda hanya menyediakan Python 3.12 dan [uv](https://docs.astral.sh/uv/)**
  (`environment.yml`, channel conda-forge). Semua paket Python, termasuk PyTorch
  versi CUDA, dipasang uv dari berkas terkunci, jadi versinya sama persis dengan CI.
  PyTorch sudah berhenti menerbitkan paket di channel conda-nya sendiri dan
  menganjurkan wheel pip.
- **Tidak perlu CUDA Toolkit.** Wheel torch `+cu132` membawa runtime CUDA sendiri;
  yang dibutuhkan hanya driver NVIDIA yang cukup baru: `nvidia-smi` menampilkan
  **CUDA Version 13.2** atau lebih tinggi.

Sekali per mesin, dari akar repo (Anaconda Prompt, atau PowerShell setelah
`conda init powershell`):

```powershell
conda env create -f environment.yml
conda activate apd_detection
uv pip sync --torch-backend cu132 backend/requirements-dev.lock     # mesin gerbang cukup requirements.lock
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

- uv memasang ke environment conda yang **sedang aktif** (`CONDA_PREFIX`); env `base`
  ditolak, jadi aktifkan `apd_detection` dulu.
- Unduhan pertama ±4 GB (torch + pustaka CUDA); di koneksi biasa bisa 20–30 menit.
- `--torch-backend cu132` wajib. Torch versi CUDA hanya ada di index PyTorch,
  sedangkan paket lain tetap diambil dari PyPI. Tanpa flag ini instalasi
  **sengaja gagal** dengan pesan `torch==…+cu132` tidak ditemukan, supaya torch
  versi CPU tidak terpasang diam-diam.
- Memperbarui setelah `git pull` yang mengubah `.lock`: jalankan lagi `uv pip sync`
  yang sama di env `apd_detection`.

**Tanpa conda (venv biasa).** Masih didukung, misalnya untuk server Linux/Docker:
`uv venv --python 3.12 ~/.venvs/apd_py312`, lalu
`uv pip sync --python ~/.venvs/apd_py312/bin/python --torch-backend cu132 backend/requirements.lock`.

**Linux.** Perintah conda dan uv sama persis. Suara
butuh pustaka sistem, karena SDL di dalam pygame memuat driver audio dengan nama
standar dan tidak memakai salinan yang dibawa wheel-nya:

```bash
# Debian 13 / Ubuntu 24.04+ / Kali
sudo apt install libglib2.0-0t64 libpulse0 libasound2t64
# Ubuntu 22.04 dan yang lebih lama
sudo apt install libglib2.0-0 libpulse0 libasound2
```

- `libglib2.0` wajib untuk modul mixer.
- `libpulse0` dipakai bila ada server PulseAudio/PipeWire (desktop, WSLg).
- `libasound2` untuk ALSA langsung di mesin gerbang tanpa server suara.

Tanpa paket-paket ini sistem tetap berjalan, hanya tanpa suara (ada peringatan
di log). OpenCV memakai varian `opencv-python-headless`, jadi tidak butuh `libGL`.

`start_system.bat` dan `start_system.sh` mencari environment Python dengan urutan:

1. `SAFEGUARD_VENV` bila diisi (folder venv atau env conda);
2. env conda `apd_detection` yang sedang aktif;
3. env conda `apd_detection` di lokasi instal Miniconda/Anaconda yang umum
   (`~/miniconda3`, `~/anaconda3`, dan seterusnya). Nama env bisa diganti lewat `DEPRO_CONDA_ENV`;
4. venv lama `~/.venvs/apd_py312`.

Kandidat yang bukan Python 3.12 (misalnya env lama yang belum dibuat ulang) dilewati dengan
pesan `[INFO] Dilewati`, jadi env usang tidak pernah dipakai diam-diam.

Karena itu autostart Windows (`deploy/windows/install_autostart.ps1`) tidak perlu
`conda activate`. Bila Miniconda dipasang di tempat lain, isi `SAFEGUARD_VENV`
dengan jalur env-nya (lihat `conda env list`).

### Memperbarui versi yang dikunci

Ubah `requirements.txt` / `requirements-dev.txt`, hapus berkas `.lock` lama, lalu:

```powershell
cd backend
uv pip compile requirements.txt --universal --python-version 3.12 --torch-backend cu132 --emit-index-url --excludes lock-excludes.txt -o requirements.lock
uv pip compile requirements-dev.txt --universal --python-version 3.12 --torch-backend cu132 --emit-index-url --excludes lock-excludes.txt -o requirements-dev.lock
```

- `.lock` lama harus dihapus dulu, karena uv mempertahankan versi yang sudah
  tercatat di dalamnya.
- Jangan menaruh `--extra-index-url` PyTorch di `requirements.txt`. Index itu
  juga memuat salinan lama `urllib3`, `certifi`, `requests`, dan lain-lain, yang
  lalu ikut terpilih.
- `--excludes lock-excludes.txt` juga wajib. Ultralytics menuntut
  `opencv-python` (varian GUI), yang bila ikut terpasang menimpa folder `cv2`
  milik varian headless.

### Mesin gerbang: GPU & VLM lokal

VLM cadangan (Ollama) sangat peka terhadap **clock GPU** dan **VRAM**. Ini hanya berpengaruh saat
gerbang memakai cadangan (VLM utama cloud tidak bergantung pada GPU laptop). Terukur di laptop
RTX 4060 8 GB:

| Mode GPU (Legion) | Clock saat inferensi | Baca prompt | Per inspeksi | Terukur |
| :-- | :-- | --: | --: | :-- |
| dGPU + overclock | ±2.600 MHz | 1,4–1,5 dtk | ±3,5 dtk | 06-10 |
| **dGPU, overclock mati** (pilihan gerbang/demo) | ±2.565 MHz | 1,2–1,5 dtk | 3,4–3,9 dtk | 14-10 |
| Hybrid, overclock mati | — | 2,0–2,1 dtk | 4,0–4,5 dtk | 14-10 |
| Hybrid + "Prefer maximum performance" & GPU NVIDIA dipilih per aplikasi | sebagian besar 780–960 MHz | 3,1–3,2 dtk | 5,3–5,9 dtk | 14-10 |

Di mode Hybrid driver menahan clock GPU untuk program komputasi (CUDA) seperti Ollama;
pengaturan per aplikasi di NVIDIA Control Panel tidak mengangkatnya. **Mode GPU ditentukan oleh
peran laptop:**

- **Saat menjadi gerbang / demo: mode dGPU** (Lenovo Vantage / Legion Space → GPU working mode
  dGPU, berlaku setelah restart), rencana daya **Performance**, laptop dicolok. Overclock tidak
  perlu.
- **Saat kerja harian (IDE, browser, rapat): mode Hybrid**, overclock mati. Aplikasi biasa
  memakai GPU Intel sehingga VRAM NVIDIA tidak penuh.
- **Di mode dGPU semua aplikasi memakai GPU NVIDIA.** VRAM 8 GB hampir habis oleh
  `qwen2.5vl:7b` (±5,5 GB) + YOLO + Windows. Bila browser, Discord, IDE, dan sejenisnya ikut
  terbuka, Windows memindah sebagian memori ke RAM. Akibatnya VLM lokal macet diam-diam,
  padahal `ollama ps` tetap "100% GPU". Di laptop gerbang **jalankan gerbang saja**.
  Terukur 14-10 setelah restart: aplikasi latar (tray, Edge, overlay NVIDIA) ±0,8 GB +
  model ±6,6 GB + satu YOLO ≈ 7,7 dari 8,2 GB. Sisanya hanya ±0,5 GB, sehingga **satu YOLO
  tambahan sudah cukup membuat Ollama macet** (terjadi pada bench lama yang memuat dua YOLO).
  Penjaga T56 memantau gejala ini: dua panggilan lambat/habis waktu berturut-turut memicu
  peringatan di log dan di `GET /api/health` → `local_vlm` (beserta nama aplikasi lain di
  GPU yang perlu ditutup), lalu model dimuat ulang.
- Pengaturan NVIDIA Control Panel per aplikasi (`ollama.exe`, `llama-server.exe`, `python.exe`):
  Preferred graphics processor = **High-performance NVIDIA processor**, Power management mode =
  **Prefer maximum performance**, CUDA Sysmem Fallback = **Prefer No Sysmem Fallback**. Pengaturan ini
  tidak merugikan, tetapi tidak menggantikan mode dGPU.
- **Kunci versi Ollama** (validasi model dilakukan di 0.34.4) dan **matikan update otomatis**
  di aplikasi Ollama (Settings), supaya kecepatan & perilaku tidak berubah diam-diam.
- Cek cepat (setelah `nvidia-smi` menunjukkan tidak ada aplikasi lain di GPU):
  `python tools/bench_vlm.py picture_test --prompts P0 --limit 3`. Waktu baca masukan
  (`baca_input_median_ms`) harus ±1.500 ms. Bila ±2.000–3.000 ms, GPU sedang ditahan (masih
  Hybrid atau tidak dicolok).

## 2. Konfigurasi (`backend/.env`)

Salin `backend/.env.example` menjadi `backend/.env`. Setiap variabel dijelaskan di
berkas contoh itu. Yang wajib diperhatikan:

- **VLM utama**: `VLM_PROVIDER`, `VLM_MODEL`, dan API key penyedia.
- **VLM cadangan**: `VLM_BACKUP_*`. Contohnya Ollama lokal `qwen2.5vl:7b`, yang
  dipasang dengan `ollama pull qwen2.5vl:7b`.
- **API key per penyedia** (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`,
  `ANTHROPIC_API_KEY`, ...): penyedia yang key-nya terisi bisa dipilih admin di
  **Pengaturan → VLM** tanpa restart. Pilihan dashboard menang atas `.env` sampai
  ditekan "kembali ke .env". Penggantian hanya terjadi saat jalur inspeksi kosong;
  model yang pernah meloloskan APD kurang selalu ditolak, model yang belum
  tervalidasi perlu konfirmasi. Setiap pergantian tercatat di security log
  (`DATA_DIR/logs/security.jsonl`). Key tidak pernah diisi lewat dashboard.
- **Akun (T51)**: dashboard selalu meminta **login** dengan nama pengguna + kata sandi;
  foto bukti, video, CSV, telemetri, dan pengaturan tertutup tanpa login (sesi
  `SESSION_HOURS`). Saat belum ada akun, buka `http://localhost:8000` **di mesin
  gerbang** untuk membuat admin pertama (dari komputer lain ditolak). Akun lain
  ditambah di Pengaturan → Akun. Kata sandi minimal 12 karakter, disimpan ter-hash
  di `DATA_DIR/accounts.db`. Lupa kata sandi admin terakhir, dari akar repo di mesin gerbang:
  `python -m backend.accounts reset-password <nama>` (juga `list`, `create <nama>`).
  `ADMIN_TOKEN` & `ALLOW_INSECURE_DEMO` lama tidak dipakai lagi; hapus dari `.env`.
- **Data**: `DATA_DIR`. Bawaannya `data/` di akar repo. Untuk produksi, pakai
  jalur absolut di luar repo supaya deploy ulang tidak menyentuh data.
- **Log (T53)**, di `DATA_DIR/logs/`:
  - `safeguard.log` — **application log** (kamera, VLM, sesi, galat). Untuk tim teknis.
  - `security.jsonl` — **security log**, satu baris JSON per kejadian: login berhasil/gagal,
    penguncian karena salah sandi, setup/akses ditolak, akun dibuat/dihapus/reset/ganti sandi,
    ganti VLM (siapa, kapan, dari alamat mana). Tanpa kata sandi atau key.
  - `supervisor.log` — nyala/mati server oleh penjaga proses.
  - **Audit** keputusan per pekerja tetap di `reports/audit.db` + foto (retensi `RETENTION_*`).

  Semua berkas log dibatasi ukuran dan umur (`LOG_*` di `.env.example`), penulisan log tidak
  pernah menahan gerbang, dan saat sisa disk menipis log dikurangi lebih dulu supaya audit tetap
  tersimpan. Sisa disk terlihat di `GET /api/health` → `disk`.

## 3. Menjalankan server

Dari akar repositori:

```powershell
python -m backend
```

Cara lain: `.\start_system.bat` (Windows) atau `./start_system.sh` (Linux/macOS).
PowerShell tidak menjalankan skrip di folder aktif tanpa awalan `.\`.

- `backend/` adalah paket dengan impor relatif, jadi harus dijalankan sebagai
  modul dari akar repo. Menjalankan `python backend/app.py` tidak didukung.
- Hentikan server dengan `Ctrl+C` di terminalnya. Kamera, aliran video, dan
  WebSocket dilepas dalam ~1 detik. Bila server dijalankan dari panel
  **Output** VS Code, `Ctrl+C` tidak sampai ke program; pakai tab **Terminal**.
- Data lama yang masih ada di `backend/` dipindah otomatis ke `DATA_DIR` saat
  server pertama kali dijalankan. Berkas yang bentrok tidak ditimpa, melainkan
  dilaporkan di log.
- **Linux (menyala saat boot):** pasang `deploy/safeguard.service`; petunjuknya
  ada di dalam berkas itu. Server berhenti bersih saat menerima `SIGTERM`.

### Menyala sendiri (Windows, demo) — T29

1. Di `backend/.env`: `CAMERA_AUTOSTART=true` dan `CAMERA_NAME=<nama kamera eksternal>` (nama persis seperti di
   daftar kamera dashboard, mis. `HD Pro Webcam C920`). Kamera **hanya** dicari lewat nama: bila belum terlihat
   (Windows bisa butuh ±30 dtk setelah dicolok), gerbang menunggu dengan lampu kuning, tidak membuka kamera lain.
2. Pasang sekali: `powershell -ExecutionPolicy Bypass -File deploy\windows\install_autostart.ps1`
   (pintasan di folder Startup pengguna; lepas dengan `uninstall_autostart.ps1`). Ollama sudah menyala sendiri
   lewat pintasannya; matikan update otomatisnya.
3. `start_system.bat` menjalankan `python -m backend.supervisor`: server dinyalakan ulang bila crash
   (jeda 5 dtk, berlipat bila crash beruntun, maks. 60 dtk; catatan di `DATA_DIR/logs/supervisor.log`).
   Berhenti rapi dengan `Ctrl+C`.
4. Saat menyala, server memeriksa CUDA, versi Ollama (`OLLAMA_VALIDATED_VERSION`), dan kamera target;
   peringatannya di log dan `GET /api/health` → `startup_warnings`.

Buka <http://localhost:8000>. Saat pertama dibuka, dashboard meminta Anda memilih
kamera; video belum tersambung sebelum kamera dipilih. Tampilan lama masih ada

### Daftar persiapan demo

Kamera di lokasi demo belum tentu sama dengan kamera pengembangan, jadi **`CAMERA_NAME` dikosongkan**: gerbang
mengikuti kamera yang dipilih operator di lokasi (cukup sekali; sesudahnya dibuka otomatis lewat namanya).

1. `backend/.env`: `CAMERA_AUTOSTART=true`, `CAMERA_NAME=` (kosong), `IOT_*` sesuai perangkat. Akun admin sudah
   dibuat dari `http://localhost:8000` di mesin gerbang (sekali; tersimpan di `DATA_DIR/accounts.db`).
2. Mesin: mode GPU **dGPU** (pindah dari Hybrid, restart) + rencana daya Performance + dicolok, Ollama
   **0.34.4** dengan update otomatis mati (lihat "Mesin gerbang: GPU & VLM lokal"); pintasan Startup terpasang
   (`install_autostart.ps1`). Tutup aplikasi lain; `nvidia-smi` tidak menampilkan aplikasi selain Ollama/gerbang.
   Selesai demo, kembalikan ke Hybrid bila laptop dipakai kerja harian.
3. Di lokasi: colok kamera eksternal → buka dashboard → **Pilih Kamera** (Pengaturan) → pilih kamera eksternal.
   Bila laptop masih mengingat kamera lain, gerbang menunggu kamera itu dengan lampu kuning: cukup pilih ulang.
4. Uji cepat: tutup lensa (kuning + suara "terhalang"), satu giliran APD lengkap (hijau), satu giliran tanpa
   helm (merah), lalu cabut-colok kamera sekali (kuning + suara "terputus", tersambung lagi sendiri).
5. Restart PC sekali: server, Ollama, dan kamera harus menyala sendiri tanpa memilih ulang.
6. `GET /api/health` → `startup_warnings` kosong (atau baca log): bila ada peringatan CUDA/Ollama/kamera,
   bereskan sebelum demo dimulai.


## 4. Pengembangan

- `python scripts/check.py` wajib lolos sebelum commit. Isinya ruff dan pytest;
  bila Node.js terpasang, juga cek tipe, vitest, dan build UI.
- `python -m pytest`: tes memakai `DATA_DIR` sementara, tidak memanggil VLM
  cloud, dan tidak membuka port IoT.
- `python -m backend.generate_audio`: membangkitkan ulang MP3 panduan suara dari
  teks di `backend/messages.py`.
- `tools/eval_vlm.py` dan `tools/bench_vlm.py`: mengevaluasi akurasi dan latensi
  VLM pada foto berlabel.

**UI (`web/`)** butuh Node.js 24, hanya di mesin pengembang. Mesin gerbang tidak
butuh Node.js, karena hasil build `web/dist` ikut di-commit.

```bash
cd web && npm ci        # sekali
npm run dev             # Vite http://localhost:5173, API diteruskan ke :8000
npm run check           # svelte-check + tsc
npm test                # vitest
npm run build           # lalu commit web/dist (CI menolak dist yang tidak sesuai sumber)
```

## 5. Uji ESP32 (kabel USB)

1. Hubungkan **ESP32 DevKit V1** ke laptop dengan kabel data USB.
2. Cek nomor port di Device Manager (mis. `COM3`), lalu isi `IOT_SERIAL_PORT` di `.env`.
3. Flash `iot/esp32_gate_controller/esp32_gate_controller.ino` lewat Arduino IDE.
4. Di dashboard, buka **Pengaturan → Uji lampu** untuk menguji relay/LED.

Wiring dan spesifikasinya ada di [IOT_HARDWARE_SPEC.md](../IOT_HARDWARE_SPEC.md).

**Tanpa ESP32 — relay USB 2 kanal (T54):** colok relay USB "USBRelay2", lampu hijau di
relay 1 dan merah di relay 2 (kontak **NO**), lalu di `.env`: `IOT_ENABLED=true`,
`IOT_TYPE=usb_relay`. Tidak perlu driver atau nomor COM. Jalankan lewat
`start_system.bat` supaya lampu dimatikan otomatis bila server crash. Rincian di
IOT_HARDWARE_SPEC.md bagian 9.
