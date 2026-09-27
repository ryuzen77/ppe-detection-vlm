# DEPRO — Digital Safety Protection

Gerbang pemeriksaan **Alat Pelindung Diri (APD)** otomatis untuk area kerja
industri/proyek. Kamera memastikan tubuh pekerja terlihat utuh, lalu
Vision-Language Model (VLM) menilai kelengkapan APD. Hasilnya berupa lampu,
suara panduan, dan catatan audit berfoto.

```
Kamera → YOLO26 pose (tubuh utuh?) → VLM menilai APD → lampu · suara · audit
```

## Mengapa

- **Pemeriksaan konsisten tanpa petugas di setiap gerbang.** Pekerja yang APD-nya
  kurang ditolak (lampu merah) disertai suara yang menyebut item yang kurang.
- **Tetap berjalan saat internet putus.** VLM utama di cloud (bawaan Gemini),
  cadangan VLM lokal (Ollama `qwen2.5vl:7b`), dan peralihannya otomatis. Bila
  keduanya gagal, pekerja diminta menunggu, bukan ditolak.
- **Jejak audit K3.** Setiap keputusan tersimpan beserta foto bukti dan bisa
  diekspor ke CSV. Masa simpan diatur (foto 30 hari, audit 1 tahun).

APD yang diperiksa (bisa diatur di dashboard): helm, rompi hi-vis, celana
panjang, sepatu tertutup.

## Mulai cepat

Butuh Python 3.12, [uv](https://docs.astral.sh/uv/), dan GPU NVIDIA (CUDA).
Jalankan dari akar repo (Windows):

```powershell
uv venv --python 3.12 "$env:USERPROFILE\.venvs\apd_py312"
uv pip sync --python "$env:USERPROFILE\.venvs\apd_py312\Scripts\python.exe" --torch-backend cu132 backend\requirements.lock
copy backend\.env.example backend\.env
python -m backend                         # atau .\start_system.bat
```

Sebelum menjalankan, isi di `backend/.env`:

- **API key VLM utama**, dan bila perlu VLM cadangan (`VLM_BACKUP_*`, mis. Ollama lokal).
- **`ADMIN_TOKEN`**, atau `HOST=127.0.0.1` untuk uji di satu komputer. Dengan
  `HOST=0.0.0.0` tanpa token, server sengaja menolak menyala.

Buka <http://localhost:8000>, lalu pilih kamera. Hentikan server dengan `Ctrl+C`.

Panduan lengkap untuk Linux, VLM lokal, audio, ESP32, dan pembaruan dependensi
ada di **[docs/INSTALASI.md](docs/INSTALASI.md)**.

## Dokumentasi

| Dokumen | Isi |
| :-- | :-- |
| [docs/INSTALASI.md](docs/INSTALASI.md) | Prasyarat, menjalankan server, UI `web/`, ESP32 |
| [docs/ARSITEKTUR.md](docs/ARSITEKTUR.md) | Teknologi, alur keputusan, aturan APD, struktur folder, batasan |
| [docs/RENCANA.md](docs/RENCANA.md) | Status, antrean task, dan keputusan produk |
| [IOT_HARDWARE_SPEC.md](IOT_HARDWARE_SPEC.md) | Spesifikasi perangkat keras & wiring ESP32 |
| [AGENTS.md](AGENTS.md) | Aturan kerja & kontribusi (manusia dan agen AI) |

## Kontribusi

Sebelum commit, jalankan `python scripts/check.py` (ruff, pytest, serta cek tipe,
vitest, dan build UI). Pemeriksaan yang sama dijalankan CI di Linux dan Windows.
Aturan kode (tanpa hard code, tes wajib, daftar periksa) ada di
[AGENTS.md §4](AGENTS.md).

## Status & pengelola

Masih tahap **demo/prototipe**, belum untuk produksi. Contohnya, lisensi
Ultralytics YOLO (AGPL) masih harus ditinjau sebelum dipakai komersial.
Dikelola oleh Muhamad Zen Fikri. Pertanyaan dan laporan masalah bisa diajukan
lewat *Issues* repositori ini.
