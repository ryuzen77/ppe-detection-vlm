# Rencana DEPRO — status, antrean, dan keputusan

Rencana bersama untuk semua agen (lihat [`AGENTS.md`](../AGENTS.md)). Perbarui
berkas ini setiap kali status task atau keputusan berubah. Riwayat rinci ada di
pesan commit (`git log`).

Terakhir diperbarui: 25-09-2026.

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
| T33 langkah 3 — tab Pengaturan + Diagnostik | Gemini (keputusan pengguna 27-09) | `gemini/t33-pengaturan` | antre | `web/src/pages/`, `web/src/components/settings/` (baru), `web/src/lib/` (tambah), `web/src/lib/messages.ts` (tambah) | Kamera, APD wajib (checkbox), lampu (tes), VLM (penyedia & model — area admin), Diagnostik (uji latensi VLM, tes lampu); dialog token pindah ke sini; tampilkan **sejak kapan server terputus**; rapikan tombol Monitoring yang terpotong di ~360 px. Memakai endpoint yang **sudah ada**. Setelah selesai & digabung: hapus UI lama (`frontend/`, `/legacy/`) sebagai langkah terpisah. **Revisi wajib (tinjauan Claude 27-09):** tipe `VlmInfo` (bukan `vlmInfo.main`, tanpa `any`); tombol Monitoring 360 px (`VideoPanel.svelte`) belum ada di commit; semua teks ke `messages.ts`; hasil Uji Latensi/Tes Lampu/galat checkbox APD ditampilkan; isi token jadi satu komponen (tanpa salinan dialog); `formatLostSince` pakai `LOCALE`. **Ditambah (keputusan pengguna 27-09): UI zona titik berdiri** sesuai "Kontrak API T36d" — kartu Titik berdiri di Pengaturan + pita zona di video Monitoring; tipe di `types.ts`. Setelah itu uji nyata gabungan |
| T37 — ketahanan sistem utama | Claude | `claude/t37-ketahanan` | tinjau | `backend/report_manager.py`, `backend/uptime.py` (baru), `backend/runtime.py`, `backend/config.py`, `backend/messages.py`, `tests/test_durability.py` (baru) | (1) `synchronous=FULL` kini disetel di tiap koneksi. Temuan: pragma ini per koneksi; baris lama `NORMAL` hanya berlaku di koneksi inisialisasi yang langsung ditutup, sehingga penulisan audit memang sudah FULL (bawaan SQLite) — kini eksplisit + tes penjaga. (2) Foto bukti ditulis atomik (encode → berkas `.tmp` → fsync → ganti nama); sisa `.tmp` dibuang saat start. Temuan: dulu hasil `cv2.imwrite` tidak diperiksa, jadi foto gagal tulis (mis. disk penuh) tetap tercatat di audit. (3) `data/uptime.json` + log saat start: berhenti rapi (INFO) atau MENDADAK (WARNING) dan lama gerbang tidak aktif; diperbarui tiap 30 dtk. 9 tes baru; 2 gagal pada kode lama. **Tinjauan Gemini (27-09):** balapan di `uptime.py` — detak `clean=False` yang sedang menulis bisa selesai setelah `stop()` menulis `clean=True`, sehingga henti rapi tercatat mendadak. Diperbaiki: gembok penulisan + `stop()` menunggu thread detak. Tes deterministik (detak ditahan di tengah penulisan) gagal 3/3 tanpa perbaikan, lolos 3/3 dengan perbaikan |
| T28 — penyedia VLM dari dashboard (bagian backend) | — | — | antre | `backend/vlm_analyzer.py`, `backend/api/routes_vlm.py`, `backend/runtime_settings.py`, `tests/` | Setelah T36 (sama-sama menyentuh `vlm_analyzer.py`). Kontrak API ditulis di sini dulu |

### Kontrak API T36d — zona titik berdiri (disetujui 27-09)

Angka `y` = posisi kaki relatif tinggi gambar (0 = atas, 1 = bawah); kamera di atas gerbang menghadap pekerja, makin dekat ke gerbang makin besar `y`.

- `GET /api/config/zone` → `{"enabled": bool, "y_min": number, "y_max": number, "source": "bawaan" | "kalibrasi" | "manual"}`
- `POST /api/config/zone` (token admin), body `{"enabled"?: bool, "y_min"?: number, "y_max"?: number}` → bentuk sama; 400 `{"detail"}` bila `0 ≤ y_min < y_max ≤ 1` tidak terpenuhi atau pita terlalu sempit
- `POST /api/config/zone/calibrate` (token admin) → bentuk sama (`enabled: true`, `source: "kalibrasi"`, pita = posisi kaki subjek ± toleransi di `config.py`); 409 `{"detail"}` bila tidak ada orang atau kaki tidak terlihat
- Telemetri WebSocket: `"zone": {"enabled", "y_min", "y_max"}`; tiap `detections[i]` + `"foot_y": number | null`, `"in_zone": bool`
- Orang di belakang zona (antrean) diabaikan; subjek yang keluar zona mengakhiri sesi setelah jeda jalur kosong. Pengaturan persisten di `data/runtime_settings.json`

## Antrean berikutnya (urut)

| # | Task | Isi |
| :-- | :-- | :-- |
| 1 | **T36 a→d — perbaikan antrean** (Claude) | Lihat papan tugas; satu sub-langkah per giliran, masing-masing dites & ditinjau |
| 2 | **T35 Uji 2 & 3** | Uji 2: beban GPU saat gerbang + kamera berjalan (`ollama ps`, `nvidia-smi`). Uji 3: 20 lintasan/mode dengan protokol "langsung jalan", diukur dari log; hitung ulang skenario 100 orang |
| 2b | **T39 — profil penyedia VLM + validasi model** (Claude, setelah uji nyata) | Katalog profil per penyedia di kode (`backend/vlm_providers/profiles.py`): cara panggil, cara memaksa JSON/skema, mode berpikir (parameter & nilai "mati" per penyedia; ganti `GEMINI_THINKING_LEVEL` dengan `VLM_THINKING` umum), jeda minimal, batas waktu, pemanasan, lokasi data. `.env` hanya memilih penyedia + model + key; nilai profil bisa ditimpa per engine. `.env.example` netral (bagian umum + contoh per penyedia). Daftar model tervalidasi dari `tools/bench_vlm.py` (syarat 0 APD kurang lolos + latensi < batas waktu); model belum tervalidasi = **peringatan** (log, nanti Pengaturan), tidak memblokir. Resmi untuk demo: gemini & ollama; lainnya eksperimental. Uji ulang Gemini dengan prompt T36a (belum). Fondasi T28 |
| 3 | **T37 — ketahanan sistem utama** (Claude) | SQLite `synchronous=FULL` (keputusan pengguna 27-09); foto bukti ditulis atomik (berkas sementara → ganti nama); log lama server terputus. Server menyala ulang otomatis ikut T29 |
| 4 | T38 — crash Ollama pada gambar tertentu | `apd_19`, `no_23` selalu 500; kadang runner dimuat ulang sebagian ke CPU (`GPU discovery watchdog timed out`) → tiap inspeksi ~31 dtk sampai Ollama dimuat ulang. Selidiki versi Ollama & pemulihan otomatis (cek porsi GPU setelah galat) |
| 5 | T30 — autentikasi Pengaturan | Login untuk Pengaturan & semua endpoint yang mengubah state; wajib di produksi |
| 6 | T28 — penyedia VLM dipilih dari dashboard | Utama & cadangan dari Pengaturan, persisten, tanpa restart, uji koneksi per penyedia. Menyerap T17 |
| 7 | T29 — operasi otomatis + Docker | Produksi Linux lewat Docker Compose; `restart: unless-stopped` |
| 8 | T26 sisa — evaluasi Gemini; T25 sisa latensi | |
| — | **Ditunda** | Aturan helm untuk rambut lebat (`apd_10`); akurasi sepatu tertutup (`apd_4`) |

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
