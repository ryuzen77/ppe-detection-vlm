# Rencana DEPRO — status, antrean, dan keputusan

Rencana bersama untuk semua agen (lihat [`AGENTS.md`](../AGENTS.md)). Perbarui
berkas ini setiap kali status task atau keputusan berubah. Riwayat rinci ada di
pesan commit (`git log`).

Terakhir diperbarui: 25-09-2026.

## Lanjut dari sini (jeda 25-09-2026)

- **Menunggu pengguna:** uji nyata T20b + T20b-UI (restart server, tombol kunci di bilah atas, perintah tanpa token → dialog, isi token → berhasil; opsional akses dari perangkat lain & uji tolak menyala).
- **Menunggu Gemini:** `git checkout --detach master` di worktree-nya agar branch `gemini/t20b-akses` bisa dihapus. Belum ada task baru untuk Gemini.
- **Usulan putaran berikutnya (paralel, area tidak beririsan):** Claude → T33 langkah 3 (tab Pengaturan + Diagnostik, lalu hapus UI lama; kolom token pindah ke sana). Gemini → bagian backend T28 (penyedia VLM dari dashboard), **kontrak API ditulis & disetujui dulu** di berkas ini sebelum kode.
- Praktik tinjauan: laporan agen selalu dicocokkan ke isi commit (`git log`/diff) dan diuji nyata sebelum digabung; beberapa laporan sebelumnya tidak sesuai isi branch.

## Papan tugas

Aturan klaim & penggabungan: [`AGENTS.md` §2](../AGENTS.md). Klaim dulu (isi
Pemilik, Branch, Status `dikerjakan`, Area berkas), commit papan ini sendirian,
baru mulai. Status: `antre` → `dikerjakan` → `tinjau` → `selesai`.

| Task | Pemilik | Branch | Status | Area berkas | Catatan |
| :-- | :-- | :-- | :-- | :-- | :-- |
| T28 — penyedia VLM dari dashboard (bagian backend) | — | — | antre | `backend/vlm_analyzer.py`, `backend/api/routes_vlm.py`, `backend/runtime_settings.py`, `tests/` | Kontrak API ditulis di sini dulu sebelum kode; UI-nya ikut T33 langkah 3 |

## Antrean berikutnya (urut)

| # | Task | Isi |
| :-- | :-- | :-- |
| 1 | **T33 langkah 3 — tab Pengaturan** | Kamera, aturan APD wajib (checkbox), lampu gerbang (IoT), VLM (penyedia & model tampil di sini — area admin), bagian **Diagnostik** (uji latensi VLM, tes lampu). Setelahnya **UI lama (`frontend/`) dihapus** beserta `/legacy/`. |
| 2 | T28 — penyedia VLM dipilih dari dashboard | Utama & cadangan (penyedia, model, base URL, API key) dari Pengaturan, tersimpan persisten (key di penyimpanan rahasia), tanpa restart, uji koneksi per penyedia. Menyerap T17. |
| 3 | T30 — autentikasi Pengaturan | Login untuk Pengaturan & semua endpoint yang mengubah state; wajib di produksi. Rincian didiskusikan saat mulai. |
| 4 | T26 sisa — evaluasi Gemini | 84 foto berlabel lewat `tools/eval_vlm.py` saat layanan Google normal (24-09 sedang 503/lambat). |
| 5 | T29 — operasi otomatis + Docker | Produksi Linux lewat Docker Compose (kamera, GPU, suara, serial diteruskan; `restart: unless-stopped`). |
| 6 | T18 XSS (UI lama; gugur bila UI lama sudah dihapus), T25 sisa latensi | T20 kini hanya retensi; pengerasan keamanan jadi T20b (sebelum T30) |

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
| T20 | Retensi data (Gemini): foto 30 hari, audit 1 tahun, foto maks. 2 GB, pembersihan otomatis saat start + tiap `RETENTION_INTERVAL_HOURS`; nilai ≤ 0 = nonaktif. Pengerasan keamanan dipecah ke T20b |
| T33 langkah 1 | UI baru Svelte 5 + TS di `/`, sistem desain, tab Monitoring, nama DEPRO, hard code dibereskan (`messages.ts`, `settings.ts`, token CSS, `icon_name` di katalog) |
| T20b | Pengaman akses jaringan (Gemini): server menolak menyala (kode keluar 1) bila `HOST` bukan localhost tanpa `ADMIN_TOKEN`, kecuali `ALLOW_INSECURE_DEMO=true`; isi `POST` maks. 1 MB → 413 (termasuk *chunked*). Ditinjau Claude |
| T20b-UI | Tombol kunci + dialog token admin di UI baru; 401 membuka dialog; cadangan memori bila penyimpanan browser diblokir. Ditinjau Gemini |
| T33 langkah 2 | Tab Laporan di UI baru: 6 statistik (kepatuhan dengan meter), saring status & tanggal, halaman, foto bukti, APD per item, "Dinilai oleh" tanpa nama penyedia, ekspor CSV, muat ulang otomatis. Ditinjau Gemini |
| T33 perbaikan bilah atas | Bilah atas responsif 360–1440 px tanpa scroll horizontal (chip menyempit → ikon → baris kedua). Ditinjau Gemini |

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

**Retensi data (T20, 25-09-2026)**
- Foto bukti disimpan **30 hari** (berisi wajah pekerja = data pribadi); baris audit disimpan **1 tahun** (setelah fotonya terhapus, baris tampil "Tanpa foto").
- Pengaman ukuran: total foto maksimal **2 GB**; bila terlewati, foto tertua dihapus lebih dulu.
- Semua angka di `config.py`, bisa diubah lewat `.env`.
- Pembersihan **otomatis** saat server menyala dan sekali sehari di latar (tanpa cron OS), hasilnya dicatat di log. Tombol manual "Hapus data tua" menyusul di Pengaturan setelah login admin (T30).
- Log sistem tidak ikut; cukup rotasi bawaan (`LOG_MAX_BYTES` 5 MB × `LOG_BACKUP_COUNT` 5).
- Larangan "jangan hapus `data/`" di AGENTS.md berlaku untuk agen, bukan untuk fitur retensi.

**Pengaman akses jaringan (T20b, 25-09-2026)**
- `HOST` bukan localhost (`127.0.0.1`, `::1`, `localhost`) + `ADMIN_TOKEN` kosong → server **menolak menyala** dengan pesan jelas di log. Pengecualian demo hanya bila diizinkan eksplisit lewat `.env` (mis. `ALLOW_INSECURE_LAN=true`), disertai peringatan setiap start.
- Yang dikunci token hanya perintah yang mengubah state (POST, sudah memakai `require_admin`). Perlindungan data baca (foto bukti, CSV, riwayat, video langsung) menunggu login sesungguhnya di T30.
- Isi permintaan `POST` maksimal **1 MB** (angka di `config.py`); lebih besar → 413 dengan pesan dari `messages.py`.
- Urutan: kolom token di UI baru (T20b-UI, Claude) digabung dulu, baru T20b.
- Akibat bagi pengembangan: `backend/.env` di folder utama perlu `ADMIN_TOKEN` (diisi pengguna sendiri) atau `HOST=127.0.0.1`; worktree Gemini tanpa `.env` menjalankan server dengan `HOST=127.0.0.1`.

**Operasi**
- OS produksi belum tentu Windows; produksi lewat Docker di Linux, pengembangan di Windows dengan venv.
- Belum ada layar untuk pekerja di gerbang (suara & lampu saja); mode kios = rencana ke depan.

## Catatan terbuka

- VRAM puncak 7,6 / 8 GB dengan `qwen2.5vl:7b` + YOLO — risiko OOM bila ada beban GPU lain.
- Ollama kadang crash pada gambar tertentu (ollama/ollama#14170); inspeksi itu jatuh ke jalur gangguan dan diulang.
- Build `web/dist` kini identik antar folder/worktree (akhir baris `web/` dikunci LF lewat `.gitattributes`); kesamaan di Linux CI belum dibuktikan langsung (repo belum punya remote).
- Repo belum punya remote git, jadi CI belum pernah berjalan.
- Monitoring di lebar ~360 px: satu tombol panel video melewati tepi kanan (terpotong, tanpa scroll horizontal) — rapikan di T33 langkah 3.
- Data baca (foto bukti, CSV, riwayat, video langsung) masih terbuka tanpa token di jaringan — ditutup oleh login T30.
