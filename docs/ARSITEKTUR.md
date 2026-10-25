# Arsitektur DEPRO

Ringkasan singkatnya ada di [README](../README.md). Keputusan produk dan status
task ada di [RENCANA.md](RENCANA.md). Angka yang disebut di sini adalah nilai
bawaan; sumber kebenarannya `backend/config.py`.

## Alur keputusan

1. **Kamera dan pose.** YOLO26s-Pose (Ultralytics, CUDA) dengan pelacakan
   ByteTrack menilai apakah tubuh pekerja terlihat utuh dari kepala hingga kaki,
   memakai 17 titik pose. Selama belum utuh, pekerja diberi arahan posisi
   (kuning) dan VLM belum dipanggil.
2. **Zona titik berdiri** (opsional, diatur di Pengaturan). Posisi pergelangan
   kaki menentukan apakah pekerja sudah berdiri di titik periksa.
3. **Pemilihan frame.** Satu frame terbaik (ketajaman, diam, pose) dipotong lalu
   dikirim ke VLM.
4. **VLM.** Model mengembalikan JSON per item APD. Keputusan lolos atau ditolak
   dihitung di `backend/ppe_rules.py`, bukan oleh model.
   - **Utama:** VLM cloud (penyedia bebas, bawaan Gemini), batas 4 dtk.
   - **Cadangan:** VLM lokal (Ollama `qwen2.5vl:7b`), batas 12 dtk. Pekerja yang
     sama langsung diperiksa cadangan tanpa mengulang dari awal.
   - Setelah 2 kegagalan berturut-turut, utama dilewati sementara.
   - Keduanya gagal → tidak ada keputusan; pekerja diminta menunggu dan diperiksa
     ulang otomatis.
   - Penjaga model lokal memuat ulang Ollama bila model sebagian jatuh ke CPU.
5. **Hasil.** Hasil dikeluarkan lewat tiga jalur:
   - lampu (hijau lolos, merah **hanya** untuk APD kurang);
   - suara panduan (menyebut item yang kurang);
   - baris audit SQLite beserta foto bukti.
6. **Sesi.** Keputusan terkunci sampai jalur kosong. Keputusan lolos diingat
   sebentar per ID supaya pekerja yang sama tidak diperiksa ulang.

## Aturan APD bawaan

| Item | Lolos | Ditolak |
| :-- | :-- | :-- |
| Helm | Helm keselamatan, warna bebas | Tanpa helm, topi biasa, kupluk |
| Rompi | Rompi hi-vis (oranye, kuning, hijau stabilo/lime) atau reflektor | Tanpa rompi; kaos berwarna mencolok bukan rompi |
| Celana panjang | Menutupi seluruh kaki | Celana pendek, 3/4, rok |
| Sepatu tertutup | Safety boots, sepatu tertutup | Sandal, selop, telanjang kaki |

Item yang diwajibkan bisa diatur di dashboard. Katalognya
(`backend/ppe_rules.py`) adalah satu-satunya sumber definisi item, label, dan suara.
Prompt juga meminta VLM menolak foto di layar atau cetakan (`orang_nyata`).

## Teknologi

| Lapisan | Teknologi |
| :-- | :-- |
| Visi | YOLO26s-Pose + ByteTrack, OpenCV (headless) |
| VLM | Adaptor `backend/vlm_providers/`: Gemini (`google-genai`) dan API OpenAI-compatible (Ollama, OpenRouter, Qwen, DeepSeek, OpenAI, vLLM) |
| Backend | Python 3.12, FastAPI + Uvicorn, WebSocket telemetri 20 Hz, MJPEG |
| Data | SQLite (WAL, `synchronous=FULL`), foto JPEG ditulis atomik; retensi otomatis (foto 30 hari, audit 1 tahun, batas 2 GB) |
| Suara | pygame mixer (antrean non-blocking; hasil keputusan memotong suara lain), MP3 dari gTTS |
| UI | Svelte 5 + TypeScript + Vite (`web/`, hasil build di-commit); UI lama `frontend/` akan dihapus |
| IoT | ESP32 lewat USB serial (heartbeat 1 dtk, kuning berkedip bila server diam); lampu merah/kuning/hijau; simulasi Wokwi |

## Dashboard

- **Monitoring**:
  - video langsung dengan HUD;
  - tahap posisi → APD → hasil;
  - checklist APD;
  - riwayat terbaru;
  - status VLM (utama / cadangan / gangguan; nama model tidak ditampilkan ke operator).
- **Laporan**:
  - ringkasan kepatuhan;
  - filter status/tanggal;
  - tabel dengan foto bukti;
  - ekspor CSV.
- **Pengaturan**:
  - kamera & koridor;
  - zona titik berdiri;
  - item APD wajib;
  - uji lampu;
  - penyedia & model VLM (T28; API key hanya di `.env`) dan uji latensi;
  - akun pengguna (T51).

## Struktur folder

```
backend/              Paket Python (jalankan: python -m backend)
  config.py           Semua angka & pengaturan (dibaca dari .env)
  messages.py         Semua teks: UI server, suara, prompt, log
  ppe_rules.py        Katalog item APD & perhitungan keputusan
  detector.py         YOLO pose, pelacakan, cek tubuh utuh
  frame_quality.py    Pemilihan frame terbaik untuk VLM
  zone.py             Zona titik berdiri
  state_manager.py    Sesi gerbang, pemanggilan VLM, telemetri
  vlm/                Pemeriksaan VLM dan pemilihan penyedia
    analyzer.py       Fasad, rute utama/cadangan/darurat dan lock inspeksi
    engine.py         Mesin VLM, batas waktu, pemanasan dan gambar bersama
    breaker.py        State pemutus utama tanpa I/O
    prompt.py         Prompt dan metadata validasi
    result.py         Model hasil dan penguraian jawaban
    image.py          Crop serta panel perbesaran
    selection.py      Pilihan penyedia/model, key per peran dan validasi
  vlm_providers/      Adaptor penyedia VLM
  local_model_guard.py  Menjaga model lokal tetap di GPU
  audit/              Audit SQLite, foto bukti, retensi dan CSV
    report_manager.py Fasad pemegang koneksi, transaksi dan lock
    db.py             Pabrik koneksi dan migrasi skema
    snapshots.py      Berkas foto bukti
    queries.py        Kueri laporan dan identitas
    export.py         Ekspor CSV
    attendance.py     Informasi lintasan pekerja
    retention.py      Pemilihan audit/foto kedaluwarsa
    summary.py        Perhitungan ringkasan laporan
  audio_engine.py     Pemutar suara
  notifier.py         Lampu gerbang (IoT)
  camera_manager.py   Daftar & pengukuran kamera
  uptime.py           Catatan waktu hidup (deteksi mati listrik)
  logging_setup.py    Application log & security log: antrean, ringkas pesan berulang, rotasi (T53)
  security_log.py     Satu baris JSON per kejadian keamanan (login, akun, akses ditolak, ganti VLM)
  disk_guard.py       Sisa disk DATA_DIR: kurangi/hentikan log berkas sebelum audit gagal tersimpan
  video/              Pembacaan kamera & HUD
  api/                Endpoint REST & WebSocket
web/                  UI Svelte (src/, dist/ di-commit)
frontend/             UI lama (akan dihapus)
tests/                pytest (termasuk tests/test_code_hygiene.py)
tools/                eval_vlm.py, bench_vlm.py
iot/                  Firmware ESP32 & simulasi Wokwi
deploy/               Unit systemd
scripts/check.py      Pemeriksaan sebelum commit (sama dengan CI)
data/                 DATA_DIR bawaan: audit, foto, log (diabaikan git)
docs/                 RENCANA, INSTALASI, ARSITEKTUR
```

## Batasan yang diketahui

- **Cadangan lokal butuh GPU yang cukup.** Bersama YOLO, `qwen2.5vl:7b` memakai
  hampir seluruh 8 GB VRAM (RTX 4060 Laptop). Ollama sesekali crash pada gambar
  tertentu (ollama#14170). Inspeksi itu diulang, dan penjaga model memuat ulang
  model bila perlu.
- **Anti-spoofing bergantung pada VLM.** Ketangguhannya mengikuti model yang
  sedang memutuskan dan belum dievaluasi terpisah.
- **Semua data & perintah wajib login akun** (T30, T51): foto bukti, video, CSV,
  telemetri, dan pengaturan. Admin pertama hanya bisa dibuat dari mesin gerbang.
  Demo: semua akun berperan admin; peran operator & akun terpusat untuk banyak
  gerbang ada di rencana jangka panjang.
- **Foto bukti berisi wajah.** Perlakukan `DATA_DIR` sebagai data pribadi dan
  batasi aksesnya.
- **Satu orang per inspeksi.** Dua orang berdampingan di zona belum ditangani;
  saat ini dicegah dengan batas fisik di lokasi.
- **Nama kamera** hanya terbaca di Windows dan Linux; di macOS labelnya generik.
- **Pemindaian kamera** menghentikan video ~15–25 dtk per kamera. Lakukan
  sebelum demo.
- **Resolusi rendah** menurunkan ketelitian VLM. Mode kamera diutamakan lancar;
  setel `CAMERA_AUTO_MODE=false` dan `FRAME_WIDTH`/`FRAME_HEIGHT` untuk
  mengutamakan ketelitian.
