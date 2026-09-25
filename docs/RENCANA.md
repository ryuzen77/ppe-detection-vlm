# Rencana DEPRO — status, antrean, dan keputusan

Rencana bersama untuk semua agen (lihat [`AGENTS.md`](../AGENTS.md)). Perbarui
berkas ini setiap kali status task atau keputusan berubah. Riwayat rinci ada di
pesan commit (`git log`).

Terakhir diperbarui: 25-09-2026.

## Papan tugas

Aturan klaim & penggabungan: [`AGENTS.md` §2](../AGENTS.md). Klaim dulu (isi
Pemilik, Branch, Status `dikerjakan`, Area berkas), commit papan ini sendirian,
baru mulai. Status: `antre` → `dikerjakan` → `tinjau` → `selesai`.

| Task | Pemilik | Branch | Status | Area berkas | Catatan |
| :-- | :-- | :-- | :-- | :-- | :-- |
| T33 langkah 2 — tab Laporan | Claude (usulan) | `claude/t33-laporan` | antre | `web/src/pages/`, `web/src/components/reports/`, `web/src/lib/` (tambah) | Memakai `GET /api/reports` yang sudah ada; tanpa perubahan backend |
| T20 — retensi data & pengerasan keamanan | Gemini (usulan) | `gemini/t20-retensi` | antre | `backend/report_manager.py`, `backend/storage.py`, `backend/config.py` (tambah), `tests/` | Butuh keputusan pengguna: lama simpan foto/audit, cara hapus. Diskusikan dulu sebelum kode |
| T28 — penyedia VLM dari dashboard (bagian backend) | — | — | antre | `backend/vlm_analyzer.py`, `backend/api/routes_vlm.py`, `backend/runtime_settings.py`, `tests/` | Kontrak API ditulis di sini dulu sebelum kode; UI-nya ikut T33 langkah 3 |

## Antrean berikutnya (urut)

| # | Task | Isi |
| :-- | :-- | :-- |
| 1 | **T33 langkah 2 — tab Laporan di UI baru** | Riwayat pemeriksaan (tabel, filter status & tanggal, halaman), foto bukti (kecil, bisa diperbesar), statistik (total, lolos, pelanggaran, kepatuhan, diputuskan cadangan, gangguan), ekspor CSV. Mengikuti sistem desain langkah 1; semua teks di `messages.ts`. |
| 2 | **T33 langkah 3 — tab Pengaturan** | Kamera, aturan APD wajib (checkbox), lampu gerbang (IoT), VLM (penyedia & model tampil di sini — area admin), bagian **Diagnostik** (uji latensi VLM, tes lampu). Setelahnya **UI lama (`frontend/`) dihapus** beserta `/legacy/`. |
| 3 | T28 — penyedia VLM dipilih dari dashboard | Utama & cadangan (penyedia, model, base URL, API key) dari Pengaturan, tersimpan persisten (key di penyimpanan rahasia), tanpa restart, uji koneksi per penyedia. Menyerap T17. |
| 4 | T30 — autentikasi Pengaturan | Login untuk Pengaturan & semua endpoint yang mengubah state; wajib di produksi. Rincian didiskusikan saat mulai. |
| 5 | T26 sisa — evaluasi Gemini | 84 foto berlabel lewat `tools/eval_vlm.py` saat layanan Google normal (24-09 sedang 503/lambat). |
| 6 | T29 — operasi otomatis + Docker | Produksi Linux lewat Docker Compose (kamera, GPU, suara, serial diteruskan; `restart: unless-stopped`). |
| 7 | T18 XSS (UI lama; gugur bila UI lama sudah dihapus), T20 retensi & pengerasan, T25 sisa latensi | |

## Selesai (ringkas)

| Task | Hasil |
| :-- | :-- |
| T1–T9 | Katalog APD terpusat (`ppe_rules.py`), prompt dirakit dari katalog, migrasi DB v1, audio per item, checkbox APD wajib berfungsi, konstanta ke `config.py`, teks ke `messages.py` |
| T10–T16 | Paket Python `backend`, `main.py` dipecah, `DATA_DIR` terpisah dari kode, bobot model dirapikan, pytest, `logging`, tanpa efek samping saat impor |
| T19/T31 | Python 3.12, dependensi terkunci (`uv`, `requirements*.lock`), ruff + CI, kamera netral OS, `start_system.sh` + systemd, OpenCV headless |
| T21–T23 | VLM bebas penyedia: adaptor Gemini (`google-genai`) & OpenAI-compatible (OpenRouter, Qwen, DeepSeek, Ollama, vLLM), konfigurasi lewat `.env` |
| T24–T25a | Keputusan terkunci per sesi gerbang, merah hanya APD kurang, pilih frame terbaik dari 3 |
| T26 | Evaluasi 84 foto: cadangan lokal = `qwen2.5vl:7b` (akurasi 94%, 0/58 APD kurang lolos, median 7,9 dtk) |
| T27 | Failover otomatis utama → cadangan, pemutus sirkuit, heuristik OpenCV dibuang, "mohon tunggu" bila keduanya gagal |
| T32 | Ditutup: "kaki terpotong" pada foto uji karena foto dibingkai terlalu rapat (bukan bug); dipantau ulang dengan kamera nyata |
| T33 langkah 1 | UI baru Svelte 5 + TS di `/`, sistem desain, tab Monitoring, nama DEPRO, hard code dibereskan (`messages.ts`, `settings.ts`, token CSS, `icon_name` di katalog) |

## Keputusan pengguna (acuan)

**Gerbang & VLM**
- Alur: pekerja datang → selama tubuh belum utuh API terkunci (arahan posisi) → satu gambar ke VLM → keputusan terkunci sampai orang keluar dari jalur.
- Utama = VLM cloud (penyedia bebas, bawaan Gemini 3.5 Flash-Lite); cadangan = VLM lokal (`qwen2.5vl:7b` via Ollama). Batas waktu cloud 4 dtk, lokal 12 dtk; setelah 2 kegagalan utama berturut-turut, utama dilewati dan dicoba lagi pada pekerja nyata setelah 60 dtk (tanpa probe yang memakan kuota).
- Keduanya gagal → tidak ada keputusan: suara "mohon tunggu", lampu padam, diperiksa ulang otomatis, gangguan cukup dicatat di log.
- Heuristik OpenCV dibuang. vLLM ditunda (tidak cocok GPU 8 GB bersama YOLO; ditinjau ulang di GPU lebih besar).
- Proyek untuk demo: lisensi Ultralytics AGPL belum jadi masalah.

**UI (T33)**
- Stack: Svelte 5 + TypeScript + Vite, scoped CSS + token (tanpa Tailwind), ikon Lucide, font lokal. `web/dist` dicommit.
- Tema gelap tenang; warna hanya untuk status (hijau lengkap, merah APD kurang, kuning peringatan/belum dinilai/cadangan).
- Monitoring: video kiri setinggi layar; kanan keputusan besar, checklist APD, riwayat. Video diputus saat meninggalkan Monitoring; status gerbang selalu tampil di bilah atas; notifikasi DITOLAK/gangguan saat di halaman lain.
- Tiap bagian ber-URL (`#/monitoring`, `#/laporan`, `#/pengaturan`). Pengaturan = area admin.
- Nama penyedia VLM tidak tampil di UI operator (hanya log & Pengaturan admin).
- Uji latensi & tes lampu dipindah ke bagian Diagnostik di Pengaturan.
- Nama produk: **DEPRO — Digital Safety Protection**. Pengenal teknis lama (`SAFEGUARD_VENV`, `safeguard.service`, `safeguard.log`, kunci browser `safeguard_*`) sengaja tetap.
- UI lama dihapus setelah Laporan & Pengaturan selesai dipindah.

**Operasi**
- OS produksi belum tentu Windows; produksi lewat Docker di Linux, pengembangan di Windows dengan venv.
- Belum ada layar untuk pekerja di gerbang (suara & lampu saja); mode kios = rencana ke depan.

## Catatan terbuka

- VRAM puncak 7,6 / 8 GB dengan `qwen2.5vl:7b` + YOLO — risiko OOM bila ada beban GPU lain.
- Ollama kadang crash pada gambar tertentu (ollama/ollama#14170); inspeksi itu jatuh ke jalur gangguan dan diulang.
- Kesamaan build `web/dist` Linux (CI) vs Windows belum dibuktikan — CI akan menunjukkannya.
- Repo belum punya remote git, jadi CI belum pernah berjalan.
