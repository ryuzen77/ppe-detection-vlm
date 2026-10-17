# DEPRO — Digital Safety Protection

Gerbang pemeriksaan **Alat Pelindung Diri (APD)** otomatis untuk area kerja
industri dan proyek. Kamera memastikan tubuh pekerja terlihat utuh, lalu
Vision-Language Model (VLM) menilai kelengkapan APD. Hasilnya berupa lampu,
suara panduan, dan catatan audit berfoto.

```text
Kamera → YOLO26 pose (tubuh utuh?) → VLM menilai APD → lampu · suara · audit
```

> **Status:** demo/prototipe, belum untuk produksi. Lihat [Status & lisensi](#status--lisensi).

## Fitur

- **Pemeriksaan konsisten tanpa petugas di setiap gerbang.** Pekerja yang APD-nya
  kurang ditolak (lampu merah), disertai suara yang menyebut item yang kurang.
- **Tetap berjalan saat internet putus.** VLM utama di cloud (bawaan Gemini),
  VLM cadangan di mesin sendiri (Ollama `qwen2.5vl:7b`), peralihan otomatis. Bila
  keduanya gagal, pekerja diminta menunggu, bukan ditolak.
- **Jejak audit K3.** Setiap keputusan tersimpan beserta foto bukti dan bisa
  diekspor ke CSV. Masa simpan diatur (bawaan: foto 30 hari, audit 1 tahun).
- **Dashboard web** dengan akun & login: Monitoring, Laporan, dan Pengaturan
  (APD wajib, kamera, zona berdiri, penyedia VLM, akun).
- **APD yang diperiksa** (bisa diatur): helm, rompi hi-vis, celana panjang, sepatu
  tertutup. **Larangan**: rokok/vape terlihat = ditolak.
- **Lampu gerbang fisik opsional** (relay USB atau ESP32). Tanpa perangkat itu,
  lampu hanya tampil di layar.

## Kebutuhan sistem

| Komponen | Kebutuhan |
| :-- | :-- |
| OS | Windows 10/11 (utama) atau Linux |
| GPU | NVIDIA, disarankan VRAM 8 GB (untuk VLM cadangan lokal). Tanpa GPU NVIDIA belum diuji |
| Driver NVIDIA | `nvidia-smi` menampilkan **CUDA Version 13.2 atau lebih baru**. CUDA Toolkit **tidak** perlu dipasang |
| Python | Lewat [Miniconda](https://www.anaconda.com/docs/getting-started/miniconda/main) (environment `ppe_detection`, Python 3.12) |
| Kamera | Webcam USB (diuji dengan Logitech C920) |
| Internet | Untuk VLM utama (cloud) dan unduhan pertama (paket Python ±4 GB, bobot YOLO 24 MB) |
| Opsional | [Ollama](https://ollama.com) untuk VLM cadangan lokal; relay USB/ESP32 untuk lampu fisik |

## Instalasi (Miniconda)

Jalankan dari **Anaconda Prompt** atau PowerShell yang sudah `conda init powershell`.

### 1. Ambil kode dan cek driver GPU

```powershell
git clone https://github.com/ryuzen77/ppe-detection-vlm.git
cd ppe-detection-vlm
nvidia-smi                      # baris "CUDA Version" harus 13.2 atau lebih baru
```

### 2. Buat environment conda (Python 3.12 + [uv](https://docs.astral.sh/uv/))

```powershell
conda env create -f environment.yml
conda activate ppe_detection
```

### 3. Pasang paket Python dari berkas terkunci

```powershell
uv pip sync --torch-backend cu132 backend/requirements.lock
```

Perintah ini memasang PyTorch versi CUDA beserta runtime CUDA-nya (tanpa CUDA
Toolkit) ke environment `ppe_detection` yang sedang aktif. Unduhan pertama ±4 GB dan bisa
makan 20–30 menit. Untuk pengembangan (pytest, ruff), ganti dengan
`backend/requirements-dev.lock`.

### 4. Pastikan GPU terbaca

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Harus mencetak `True` dan nama GPU-mu.

### 5. Konfigurasi

```powershell
copy backend\.env.example backend\.env      # Linux: cp backend/.env.example backend/.env
```

Isi minimal `GEMINI_API_KEY` (atau penyedia VLM lain) di `backend/.env`. Semua
variabel dijelaskan di berkas contoh itu. `backend/.env` tidak pernah ikut ke git.

### 6. (Opsional) VLM cadangan lokal

Pasang [Ollama](https://ollama.com), lalu `ollama pull qwen2.5vl:7b`. Tanpa API
key, gerbang langsung memakai VLM cadangan ini.

## Menjalankan

```powershell
conda activate ppe_detection
python -m backend               # atau .\start_system.bat (Linux: ./start_system.sh)
```

1. Buka <http://localhost:8000> **di komputer gerbang itu sendiri**. Saat pertama kali,
   dashboard meminta membuat akun admin (dari komputer lain ditolak).
2. Login, lalu pilih kamera di halaman Monitoring.
3. Hentikan server dengan `Ctrl+C`.

Saat pertama kali dijalankan, bobot YOLO (`yolo26s-pose.pt`) diunduh otomatis.
`start_system.bat` / `start_system.sh` menemukan environment `ppe_detection` sendiri dan
menyalakan ulang server bila crash; cocok untuk autostart (lihat
[docs/INSTALASI.md](docs/INSTALASI.md)).

## Pemecahan masalah

| Gejala | Penyebab & solusi |
| :-- | :-- |
| `torch.cuda.is_available()` = `False` | Driver NVIDIA terlalu lama atau tidak ada. Perbarui driver sampai `nvidia-smi` menampilkan CUDA 13.2+ |
| `torch==…+cu132` tidak ditemukan | Flag `--torch-backend cu132` terlupa (sengaja gagal supaya torch CPU tidak terpasang diam-diam) |
| `conda activate` tidak dikenal di PowerShell | Jalankan sekali `conda init powershell`, lalu buka ulang PowerShell |
| `uv pip sync` menolak memasang ke env `base` | Aktifkan dulu `conda activate ppe_detection` |
| `FileNotFoundError` di `ssl.py`, atau unduhan uv gagal TLS | Shell masih mewarisi `SSL_CERT_FILE` dari env conda yang sudah dihapus. Buka shell baru lalu `conda activate ppe_detection`, atau kosongkan `SSL_CERT_FILE` & `SSL_CERT_DIR` |
| VLM cadangan lambat (> 6 dtk per pekerja) | Laptop dengan GPU ganda: pakai mode dGPU dan tutup aplikasi lain. Rincian di [docs/INSTALASI.md](docs/INSTALASI.md) |

## Pengembangan

```powershell
uv pip sync --torch-backend cu132 backend/requirements-dev.lock
python scripts/check.py         # ruff + pytest + cek tipe, vitest, dan build UI
```

UI ada di `web/` (Svelte 5 + TypeScript) dan butuh Node.js hanya saat
mengembangkan. Hasil build (`web/dist/`) ikut di-commit, jadi komputer gerbang
tidak butuh Node.js. Aturan kode (tanpa hard code, tes wajib, daftar periksa) ada
di [AGENTS.md](AGENTS.md).

```text
backend/    server FastAPI: kamera, YOLO, VLM, keputusan, audit, API
web/        dashboard (Svelte); web/dist = hasil build yang dilayani server
tests/      pytest (termasuk tes karakterisasi)
tools/      evaluasi & benchmark VLM
deploy/     autostart Windows & layanan systemd Linux
iot/        firmware ESP32 untuk lampu gerbang
docs/       instalasi, arsitektur, rencana
```

## Dokumentasi

| Dokumen | Isi |
| :-- | :-- |
| [docs/INSTALASI.md](docs/INSTALASI.md) | Instalasi rinci, konfigurasi, mode GPU, autostart, ESP32 |
| [docs/ARSITEKTUR.md](docs/ARSITEKTUR.md) | Teknologi, alur keputusan, aturan APD, batasan |
| [docs/RENCANA.md](docs/RENCANA.md) | Status, antrean task, dan keputusan produk |
| [IOT_HARDWARE_SPEC.md](IOT_HARDWARE_SPEC.md) | Spesifikasi perangkat keras & wiring lampu gerbang |
| [AGENTS.md](AGENTS.md) | Aturan kerja & kontribusi (manusia dan agen AI) |

## Status & lisensi

Masih tahap **demo/prototipe**. Uji fisik di gerbang sungguhan belum selesai, dan
lisensi Ultralytics YOLO (AGPL-3.0) harus ditinjau sebelum dipakai komersial.
Dikelola oleh Muhamad Zen Fikri; pertanyaan dan laporan masalah lewat *Issues*.
