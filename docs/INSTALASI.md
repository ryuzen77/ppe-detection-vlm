# Instalasi & menjalankan DEPRO

Ringkasan singkatnya ada di [README](../README.md). Dokumen ini berisi rinciannya.

## 1. Prasyarat lingkungan

Python **3.12**. Versi dependensi dikunci di `backend/requirements.lock` (server)
dan `backend/requirements-dev.lock` (server + pytest). Environment dibuat sekali
dengan [uv](https://docs.astral.sh/uv/) dari akar repo:

```powershell
uv venv --python 3.12 "$env:USERPROFILE\.venvs\apd_py312"
uv pip sync --python "$env:USERPROFILE\.venvs\apd_py312\Scripts\python.exe" --torch-backend cu132 backend\requirements-dev.lock
```

`--torch-backend cu132` wajib. Torch versi CUDA hanya ada di index PyTorch,
sedangkan paket lain tetap diambil dari PyPI. Tanpa flag ini instalasi
**sengaja gagal** dengan pesan `torch==…+cu132` tidak ditemukan, supaya torch
versi CPU tidak terpasang diam-diam.

**Linux.** Perintahnya sama, dengan jalur `~/.venvs/apd_py312/bin/python`. Suara
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

`start_system.bat` dan `start_system.sh` memakai environment ini secara otomatis.
Lokasinya bisa diganti lewat variabel `SAFEGUARD_VENV`.

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

VLM cadangan (Ollama) sangat peka terhadap clock GPU. Terukur 06-10 di laptop RTX 4060:
dengan GPU ditahan manajemen daya (900–1.400 MHz) waktu baca prompt 3,1 dtk; setelah mode
dGPU + overclock aktif (±2.600 MHz) 1,4 dtk — latensi VLM lokal 5,3 → 3,5 dtk.

- **Mode GPU dGPU** (Legion: Lenovo Vantage / Legion Space → GPU mode dGPU, aktif setelah restart)
  dan **GPU Overclock / Dynamic Boost** menyala; rencana daya **Performance**.
- NVIDIA Control Panel → Manage 3D settings → Preferred graphics processor →
  **High-performance NVIDIA processor**.
- **Kunci versi Ollama** (validasi model dilakukan di 0.34.4) dan **matikan update otomatis**
  di aplikasi Ollama (Settings), supaya kecepatan & perilaku tidak berubah diam-diam.
- Cek cepat: `python tools/bench_vlm.py picture_test --prompts P0 --limit 3` — waktu baca
  masukan (`baca_input_median_ms`) harus ±1.500 ms; bila ±3.000 ms, GPU sedang ditahan.

## 2. Konfigurasi (`backend/.env`)

Salin `backend/.env.example` menjadi `backend/.env`. Setiap variabel dijelaskan di
berkas contoh itu. Yang wajib diperhatikan:

- **VLM utama**: `VLM_PROVIDER`, `VLM_MODEL`, dan API key penyedia.
- **VLM cadangan**: `VLM_BACKUP_*`. Contohnya Ollama lokal `qwen2.5vl:7b`, yang
  dipasang dengan `ollama pull qwen2.5vl:7b`.
- **Keamanan**: `ADMIN_TOKEN` wajib bila `HOST` bukan localhost. Tanpa token,
  server menolak menyala, kecuali `ALLOW_INSECURE_DEMO=true`.
- **Data**: `DATA_DIR`. Bawaannya `data/` di akar repo. Untuk produksi, pakai
  jalur absolut di luar repo supaya deploy ulang tidak menyentuh data.

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

1. `backend/.env`: `CAMERA_AUTOSTART=true`, `CAMERA_NAME=` (kosong), `ADMIN_TOKEN` terisi, `IOT_*` sesuai perangkat.
2. Mesin: mode GPU dGPU + rencana daya Performance, Ollama **0.34.4** dengan update otomatis mati
   (lihat "Mesin gerbang: GPU & VLM lokal"); pintasan Startup terpasang (`install_autostart.ps1`).
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
