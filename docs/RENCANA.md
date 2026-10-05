# Rencana DEPRO — status, antrean, dan keputusan

Rencana bersama untuk semua agen (lihat [`AGENTS.md`](../AGENTS.md)). Perbarui
berkas ini setiap kali status task atau keputusan berubah. Riwayat rinci ada di
pesan commit (`git log`).

Terakhir diperbarui: 25-09-2026.

## Lanjut dari sini (28-09-2026, jeda karena limit harian)

- **Pengguna menjalankan uji nyata hari ini** (satu penguji; UI/UX + kamera). **Besok Claude:** minta jam
  mulai tiap mode dari pengguna → analisis log (`data/logs/`) & audit: rata-rata waktu per pekerja
  (internet normal vs putus), keputusan salah, suara, sesi, zona, pemulihan GPU (T38), catatan UI/UX.
- Skenario kamera yang diminta ikut diuji (data untuk T45): tutup lensa ~10 dtk, cabut kamera saat lampu
  hijau, penutup privasi/kamera mati — cocokkan dengan jam yang dicatat pengguna.
- **Terbuka (T45):** pengguna menjawab "lampu menyala merah dan ada suara" saat kamera bermasalah — ini
  bertentangan dengan AGENTS.md §5 (merah hanya APD kurang). Pilihan yang ditawarkan: (1) kuning + suara
  "gerbang gangguan" (saran Claude), (2) merah + suara gangguan, revisi §5, tidak dicatat pelanggaran,
  (3) merah berkedip + suara, revisi §5. Juga: suara diputar sekali atau diulang ~10 dtk. **Belum dijawab**
  — pastikan dulu apakah itu jawaban atau hasil uji.
- Selesai 28-09: audit kode + AGENTS.md §4.1 + `tests/test_code_hygiene.py`; aturan nama kode berbahasa
  Inggris; README ringkas + `docs/INSTALASI.md` & `docs/ARSITEKTUR.md`; antrean T41–T45.
- Gemini perlu `git rebase master` sebelum lanjut (master berubah 28-09).

## Lanjut dari sini (27-09-2026)

- **Pembagian putaran ini (keputusan pengguna):** Claude → **backend** (perbaikan antrean T36, lalu ketahanan T37).
  Gemini → **frontend** (T33 langkah 3). Ini kebalikan pembagian bawaan §2.2, khusus putaran ini.
- **Hasil T35 Uji 1 (84 foto, Ollama `qwen2.5vl:7b`, 100% GPU):** prompt produksi (P0) 7,8 dtk; jawaban
  ringkas (P1) **3,6 dtk**. Kesalahan utama = **baju kuning dikira rompi** → aturan rompi ketat (rompi = tanpa
  lengan, di atas baju, pita reflektif; baju kuning ≠ rompi). **P1 + rompi ketat: 0/58 APD kurang lolos**,
  2/26 APD lengkap ditolak (`apd_10` helm di atas rambut lebat — ditunda; `apd_4` sepatu). Ukuran gambar dari
  sisi kita tidak memengaruhi kecepatan (Ollama mengubah ukuran sendiri; 448 px merusak akurasi) → tetap
  640 px (896 px aman untuk kamera 4 MP). Hasil di `data/eval/`, alat `tools/bench_vlm.py`.
- **Analisa antrean (100 orang, satu jalur):** penentu terbesar kini **waktu keluar** (suara hasil menunggu
  "sedang menganalisa" 4,9 dtk; jeda jalur kosong 3 dtk) dan **posisi**, bukan VLM. Perkiraan: prompt baru
  ~46 mnt → + suara/jeda ~30 mnt → + zona titik berdiri ~17 mnt (lokal). Dibuktikan lewat Uji 3.
- Praktik tinjauan: laporan agen selalu dicocokkan ke isi commit (`git log`/diff) dan diuji nyata sebelum
  digabung.

## Papan tugas

Aturan klaim & penggabungan: [`AGENTS.md` §2](../AGENTS.md). Klaim dulu (isi
Pemilik, Branch, Status `dikerjakan`, Area berkas), commit papan ini sendirian,
baru mulai. Status: `antre` → `dikerjakan` → `tinjau` → `selesai`.

| Task | Pemilik | Branch | Status | Area berkas | Catatan |
| :-- | :-- | :-- | :-- | :-- | :-- |
| T46 — potret setelah pekerja siap | Claude | `claude/t46-ready-capture` | dikerjakan | `backend/state_manager.py`, `backend/frame_quality.py`, `backend/config.py` (tambah), `backend/messages.py` (tambah), `backend/.env.example` (tambah), `tests/test_frame_quality.py`, `tests/test_lifecycle.py`, tests baru | Disetujui 05-10, sebelum T45. Tanpa perubahan API; bila UI perlu status "tahan posisi", kontrak ditulis di sini dulu |
| T28 — penyedia VLM dari dashboard (bagian backend) | — | — | antre | `backend/vlm_analyzer.py`, `backend/api/routes_vlm.py`, `backend/runtime_settings.py`, `tests/` | Setelah T36 (sama-sama menyentuh `vlm_analyzer.py`). Kontrak API ditulis di sini dulu |

### Kontrak API T36d — zona titik berdiri (disetujui 27-09)

Angka `y` = posisi kaki relatif tinggi gambar (0 = atas, 1 = bawah); kamera di atas gerbang menghadap pekerja, makin dekat ke gerbang makin besar `y`.

- `GET /api/config/zone` → `{"enabled": bool, "y_min": number, "y_max": number, "source": "bawaan" | "kalibrasi" | "manual"}`
- `POST /api/config/zone` (token admin), body `{"enabled"?: bool, "y_min"?: number, "y_max"?: number}` → bentuk sama; 400 `{"detail"}` bila `0 ≤ y_min < y_max ≤ 1` tidak terpenuhi atau pita terlalu sempit
- `POST /api/config/zone/calibrate` (token admin) → bentuk sama (`enabled: true`, `source: "kalibrasi"`, pita = posisi kaki subjek ± toleransi di `config.py`); 409 `{"detail"}` bila tidak ada orang atau kaki tidak terlihat
- Telemetri WebSocket: `"zone": {"enabled", "y_min", "y_max"}`; tiap `detections[i]` + `"foot_y": number | null`, `"in_zone": bool`
- Orang di belakang zona (antrean) diabaikan; subjek yang keluar zona mengakhiri sesi setelah jeda jalur kosong. Pengaturan persisten di `data/runtime_settings.json`

## Antrean berikutnya (urut menurut risiko — AGENTS.md §2.2a, disusun 27-09, diperbarui 28-09)

| # | Risiko | Task | Alasan risiko / isi |
| :-- | :-- | :-- | :-- |
| 1 | **Tinggi** | **Uji nyata gabungan (T35 Uji 2 & 3)** | Perubahan besar T36a–d, T37, T38, T39a + UI T33 belum diuji di gerbang nyata (keputusan, suara, sesi, zona, pemulihan GPU). **Siap dijalankan** |
| 2 | **Tinggi** | **T46 — potret setelah pekerja siap** (temuan uji nyata 28-09) | 12 dari 20 sesi dipotret **0,08 dtk** setelah sesi dimulai: syarat `STABLE_FRAMES_REQUIRED=3` dihitung dalam frame (≈0,1 dtk di 30 FPS), jadi foto diambil saat pekerja masih melangkah → keputusan dari foto belum layak, foto bukti audit tidak valid, pekerja patuh bisa salah ditolak. Skor gerak antar-frame 30 ms tampak 0 walau orang berjalan. Isi: syarat **waktu** — utuh + diam (kaki & kotak badan nyaris tak bergeser) ~1 dtk; frame terbaik dari seluruh jendela; cek menghadap kamera (kedua bahu terlihat); ambang di `config.py`; tes orang berjalan tidak dipotret |
| 3 | **Tinggi** | **T45 — ketangguhan kamera** (usulan 28-09) | Kamera **terhalang** (lensa tertutup/gelap/seragam) tetap berstatus OK → gerbang mati diam-diam; gambar **membeku** (frame identik, laju tampak normal) → dugaan dari kode: sesi tak pernah kosong sehingga lampu hijau bisa tetap menyala untuk pekerja berikutnya (dibuktikan dulu dengan tes). Isi: deteksi terhalang (kecerahan/keseragaman/tepi, bertahan > N dtk) & beku (selisih antar-frame nol > N dtk → sambung ulang); saat kamera bermasalah sesi & keputusan dibatalkan, lampu kuning + suara tunggu (bukan merah); status `BLOCKED`/`FROZEN` di telemetri (kontrak API ditulis dulu, UI oleh Gemini) & log. Ambang dari data uji nyata (tutup lensa ~10 dtk, cabut saat hijau, penutup privasi). **Belum diputuskan:** kuning berkedip/tetap; suara tunggu sekali/berulang |
| 4 | **Tinggi** | **T30 — login + lindungi data baca** | Foto bukti (wajah), video langsung, dan CSV terbuka tanpa token di jaringan → kebocoran data pribadi |
| 5 | **Tinggi** | **Hapus UI lama (`frontend/`, `/legacy/`) + T18** | UI lama masih disajikan dan punya jalur XSS; dihapus setelah T33 digabung |
| 6 | Sedang | T29 — operasi otomatis + Docker | Gerbang belum menyala sendiri setelah listrik padam (risiko naik jadi Tinggi saat produksi) |
| 7 | Sedang | T39b — profil penyedia VLM (sisa T39) | Salah konfigurasi penyedia/mode berpikir; `.env.example` netral |
| 8 | Sedang | **T40 — alternatif mesin VLM lokal** (keputusan setelah uji nyata) | Crash `encoding image` berasal dari llama.cpp (llama.cpp#17422, #17881; ollama#14170), jadi mengganti Ollama dengan llama.cpp langsung kemungkinan tidak menghilangkannya. Bila uji nyata menunjukkan cadangan masih sering bermasalah walau ada penjaga T38: uji coba Qwen2.5-VL 4-bit lewat Transformers (PyTorch) di **proses terpisah** berantarmuka OpenAI-compatible (adaptor sudah mendukung, cukup ganti `.env`), diukur dengan `tools/bench_vlm.py` (akurasi, 0 APD kurang lolos, waktu, VRAM bersama YOLO). vLLM ditinjau untuk produksi Linux/GPU besar (T29). Data sejauh ini: ~2–4 crash per 84 foto |
| 9 | Sedang | Helm di atas rambut lebat (`apd_10`), sepatu tertutup (`apd_4`) | Pekerja patuh salah ditolak (2/26 foto) |
| 10 | Sedang | **T41 — satu sumber indeks pose COCO + rasio `detector` ke config** (audit 28-09) | Indeks 5/6/13–16 ditulis ulang di `detector.py`, `frame_quality.py`, `zone.py`; bila satu berubah yang lain tertinggal → salah menilai tubuh utuh/titik berdiri. Rasio 0.20/0.12/0.15/0.65/0.05/0.08 di `detector.py` ke `config.py` |
| 11 | Rendah | T28 — penyedia VLM dari dashboard | Kenyamanan admin; bisa lewat `.env` |
| 12 | Rendah | Dua orang berdampingan di zona (T36d); T25 sisa latensi | Dicegah batas fisik di lokasi; latensi sudah jauh turun |
| 13 | Rendah | T42 — cicil utang kode (audit 28-09) | 24 fungsi > 30 baris (terpanjang `capture._reader_loop` 199, `detector.detect_and_track` 164, `state_manager.update_frame_detections` 101) — daftar di `tests/test_code_hygiene.py`; 8 blok kembar (web: dialog CameraPicker/SnapshotDialog/AdminToken, ZoneSettings/Pengaturan); pesan log di luar `messages.py` (`camera_manager`, `detector`, `audio_engine`, `capture`); angka HUD/resolusi ke config; warna `#000` VideoPanel ke token; nama Indonesia → Inggris saat disentuh |
| 14 | Rendah | T43 — laporan skala besar (audit 28-09) | 100 rb baris: halaman 17 ms, filter tanggal 20 ms (belum ada indeks `date_str`), ekspor CSV 700 ms / 16,8 MB di RAM → indeks `date_str` + ekspor bertahap (streaming) |
| 15 | Rendah | T44 — formatter & linter web (audit 28-09) | `ruff format` massal (62 berkas) sebagai commit sendiri; eslint + prettier untuk `web/` (mengubah `web/package*.json`, perlu giliran dependensi) |

### Rencana (belum dikerjakan) — setelah sistem utama lolos semua tes

- **Fitur larangan rokok:** item jenis *larangan* (terdeteksi = melanggar) di katalog; hanya yang terlihat
  kamera. Detail (akibat di gerbang, sikap saat VLM ragu, crop detail mulut/tangan dalam satu panggilan
  lewat mosaik) diputuskan sebelum dikerjakan. Butuh foto uji baru (rokok, pengecoh pulpen/sedotan).
- **Set uji tambahan:** baju kuning/oranye tanpa rompi, rompi asli di atas baju kuning, rompi tanpa pita
  reflektif, kaos bertulisan (termasuk "APD LENGKAP" — uji prompt injection lewat tulisan), foto kamera 4 MP;
  label per item.
- **IoT & palang boom** (tahap setelah fitur utama berjalan): ESP, relay, LED merah/hijau/kuning, sirine bila
  perlu; sensor setelah palang memastikan pekerja lewat sebelum palang menutup. Tahap 1: **berurutan penuh**
  (periksa → lampu + suara + palang buka → sensor lewat → palang tutup → pekerja berikutnya). Tahap 2:
  pekerja berikutnya diperiksa lebih awal, pengumuman ditahan sampai palang SIAP. Heartbeat server → ESP,
  tanda "sistem tidak aktif" (kuning berkedip), batas waktu bila lolos tapi tidak lewat, catat tailgating.
  **Belum diputuskan:** palang saat listrik padam terbuka atau tertutup.
- **Listrik padam:** UPS untuk PC, kamera, jaringan + shutdown rapi otomatis; BIOS "power on after AC loss";
  SOP pemeriksaan manual oleh petugas.

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
| T35 Uji 1 | Alat uji kecepatan VLM lokal `tools/bench_vlm.py` (varian prompt/gambar, token & waktu baca vs tulis, porsi GPU, galat server dipisah). Temuan utama: jawaban ringkas 2× lebih cepat; baju kuning dikira rompi; ukuran gambar dari sisi kita tidak memengaruhi kecepatan |
| T36a | Prompt ringkas + aturan rompi ketat di gerbang: VLM lokal 7,8 → 3,45 dtk, 0/57 APD kurang lolos pada 82 foto; anti-spoof lewat `orang_nyata` |
| T36b | Suara hasil & gangguan memotong suara lain; pesan dipersingkat (mohon tunggu 4,9→1,3 dtk, lengkap 4,8→3,1); pembangkit MP3 peka perubahan teks. Bug tanda suara penting ditemukan saat tinjau ulang & diperbaiki |
| T36c | Jeda jalur kosong 3→1,5 dtk; keputusan LOLOS per ID diingat 10 dtk (ditolak selalu diperiksa ulang — temuan Gemini) |
| T36d | Zona titik berdiri dari posisi kaki (pergelangan paling bawah + ingatan per ID saat tertutup — temuan Gemini); API & telemetri sesuai kontrak; bawaan nonaktif |
| T37 | Ketahanan: audit `synchronous=FULL` per koneksi (eksplisit), foto bukti atomik (+ bug `imwrite` tak diperiksa), catatan hidup server `uptime.json` (+ balapan detak/stop dari tinjauan Gemini) |
| T39a | Validasi Gemini (VLM utama) dengan prompt T36a pada 10 foto tersulit: **10/10 benar setelah perbaikan**, 0 APD kurang lolos, 0 lengkap ditolak, median ~2,5 dtk. Menemukan & memperbaiki bug `"color": null` yang menggagalkan jawaban Gemini untuk orang tanpa rompi (digabung segera karena Tinggi; tinjauan Gemini menyusul). Uji penuh 84 foto Gemini tetap di T39b bila kuota diizinkan |
| T33 langkah 3 | Tab Pengaturan (Gemini): token admin, titik berdiri (sakelar, slider, kalibrasi), kamera, APD wajib, VLM, tes lampu, diagnostik (terputus sejak, uji latensi); pita zona di video; Monitoring 360 px. Empat putaran tinjauan Claude |
| T38 | Penjaga model lokal: porsi GPU Ollama diperiksa setelah gagal & tiap 60 dtk, dimuat ulang bila < 99% (crash hulu ollama#14170). Digabung sebelum tinjauan (izin pengguna); **tinjauan Gemini 27-09: tidak ada temuan** (tanpa reload di tengah inspeksi, tanpa deadlock, beban cek berkala ringan) |
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

**Kecepatan & antrean (27-09-2026)**
- VLM menjawab ringkas (nilai per item) — deskripsi bebas tidak dipakai keputusan dan memperlambat ~2×.
- Aturan rompi: bentuk (tanpa lengan, di atas baju, pita reflektif) dinilai terpisah dari warna; baju
  kuning bukan rompi.
- Kamera dipasang di atas gerbang/palang, menghadap pekerja yang datang; titik berdiri 2–3 m sebelum palang.
- Audit SQLite `synchronous=FULL`: baris audit tidak boleh hilang walau listrik padam mendadak.
- IoT/palang baru dikerjakan setelah sistem utama lolos semua tes.
- **Format jawaban VLM tetap JSON bernama (T36a)** — eksperimen 0/1 (27-09, `tools/bench_vlm.py` varian PA/PB/PC): deret bit tanpa nama (PB) 3,45→2,06 dtk tetapi APD lengkap ditolak 7/26 (celana & sepatu jadi 0; model kehilangan pegangan posisi) — netto antrean lebih lambat; kunci bernama 0/1 (PA/PC) ~59–60 token, hanya hemat ~0,4 dtk. Sisa ~1,45 dtk adalah biaya tetap membaca gambar.

**Pengaman akses jaringan (T20b, 25-09-2026)**
- `HOST` bukan localhost (`127.0.0.1`, `::1`, `localhost`) + `ADMIN_TOKEN` kosong → server **menolak menyala** dengan pesan jelas di log. Pengecualian demo hanya bila diizinkan eksplisit lewat `.env` (mis. `ALLOW_INSECURE_LAN=true`), disertai peringatan setiap start.
- Yang dikunci token hanya perintah yang mengubah state (POST, sudah memakai `require_admin`). Perlindungan data baca (foto bukti, CSV, riwayat, video langsung) menunggu login sesungguhnya di T30.
- Isi permintaan `POST` maksimal **1 MB** (angka di `config.py`); lebih besar → 413 dengan pesan dari `messages.py`.
- Urutan: kolom token di UI baru (T20b-UI, Claude) digabung dulu, baru T20b.
- Akibat bagi pengembangan: `backend/.env` di folder utama perlu `ADMIN_TOKEN` (diisi pengguna sendiri) atau `HOST=127.0.0.1`; worktree Gemini tanpa `.env` menjalankan server dengan `HOST=127.0.0.1`.

**Kode (28-09)**
- Daftar periksa kode (efisiensi, clean code, hardcode & rahasia) = AGENTS.md §4.1, dijaga `tests/test_code_hygiene.py`.
- Nama di kode berbahasa Inggris; komentar & docstring boleh Bahasa Indonesia; teks pengguna tetap Indonesia di `messages.*`.

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
