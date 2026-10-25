# Rencana DEPRO — status, antrean, dan keputusan

Rencana bersama untuk semua agen (lihat [`AGENTS.md`](../AGENTS.md)). Perbarui
berkas ini setiap kali status task atau keputusan berubah. Riwayat rinci ada di
pesan commit (`git log`).

Terakhir diperbarui: 24-10-2026. Task `selesai`, kontrak/rancangan task selesai, dan catatan lama dipindah ke [`arsip/RENCANA-selesai.md`](arsip/RENCANA-selesai.md) (tidak perlu dibaca rutin; cari di sana bila butuh angka uji atau alasan keputusan lama).

## Lanjut dari sini (24-10-2026, akhir sesi panjang)

- **`master` di-push 24-10** setelah T97a (T95, T96, T98, T97a, lanjutan Kehadiran, papan) — lolos `check.py` (pytest 1.132, vitest 252).
- **25-10:** T97 tuntas (T97a/b/c), T99a–c selesai — digabung; push terakhir `ef544fe` (T99c belum di-push). Berikutnya: T99d (opsional), T100 (koneksi SQLite), antrean 9c
  (grafik Ditahan), T99c–d, uji nyata (antrean 3/4/4b, diblokir perangkat demo).
- **Server gerbang asli** perlu dinyalakan ulang dengan `master` terbaru agar T98 (cadangan memakai key cadangan) berlaku.
- Keputusan sesi 24-10: "Lolos" = lolos gerbang (ditahan bukan lolos, tetap patuh APD); cadangan Gemini dengan akun/key
  berbeda = disengaja; kolom Model VLM kini dropdown dari penyedia (T97, selesai 24-10).
- Kebiasaan hemat token: sesi baru per task, laporan Codex cukup commit + status + angka `check.py`.

## Papan tugas

Aturan klaim & penggabungan: [`AGENTS.md` §2](../AGENTS.md). Klaim dulu (isi
Pemilik, Branch, Status `dikerjakan`, Area berkas), commit papan ini sendirian,
baru mulai. Status: `antre` → `dikerjakan` → `tinjau` → `selesai`.

| Task | Pemilik | Branch | Status | Area berkas | Catatan |
| :-- | :-- | :-- | :-- | :-- | :-- |

### Rancangan T99 — perapian backend per fitur (usul Codex 24-10, ditinjau Claude, **disetujui pengguna 24-10**)

**Tujuan:** memecah `vlm_analyzer.py` (1.222 baris) & `report_manager.py` (1.079) per tanggung jawab, tetap satu
aplikasi; **perilaku, kontrak API, skema DB, dan nama publik tetap**. **Risiko: Rendah** (perapian), dikerjakan
hati-hati karena menyentuh audit (salah pindah = baris/foto audit hilang). Lanjutan T42; berhenti bila uji nyata
(antrean 3/4/4b) bisa jalan.

**Urutan tahap** (satu tahap = commit pindah-saja + `check.py` lolos + ditinjau Claude):
- **T99a** — `vlm_analyzer` bagian murni saja: `vlm_result.py` (ItemResult, InspectionResult, `_parse_vlm_payload`,
  `_is_spoof_rejection`), `vlm_prompt.py` (prompt, konfirmasi, `thinking_option`, `profile_warnings`).
- **T99b** — `report_manager`: `audit_db.py` (koneksi, indeks, migrasi + cadangan sebelum migrasi, SQL apa adanya),
  `snapshot_store.py`, `audit_queries.py`, `audit_export.py` (CSV), `attendance.py`, `retention.py`.
  `ReportManager` tetap fasad dengan metode publik sama.
- **T99c** — `vlm_analyzer` mesin & rute/peralihan: `vlm_engine.py` (VLMEngine, LaneBusy, EngineFailed); pemutus utama
  jadi kelas murni `PrimaryBreaker` (+tes); `VLMAnalyzer` tetap fasad pemegang lock & rute `_inspect_route`/`_attempt_*`;
  siklus mesin (apply/test) boleh dipisah.
- **T99d** — pengelompokan folder setelah batas modul stabil; commit terpisah yang hanya mengubah path impor.

**Aturan:**
- Hanya fasad yang memegang koneksi SQLite & lock; modul lain = fungsi atas `conn`/mesin, tanpa koneksi/lock sendiri
  (`synchronous=FULL` & urutan tulis terjaga). Diperjelas 24-10 (Codex): `audit_db.py` boleh berisi fungsi pembuat
  koneksi & migrasi, tetapi **`ReportManager` tetap mengendalikan buka/tutup koneksi, transaksi, dan lock**; modul
  kueri, CSV, dan retensi menerima koneksi dari fasad.
- Target monkeypatch tes (`backend.vlm_analyzer.create_provider`, `rm.time`, `rm_module.cv2.*`, `rm.os.replace`,
  `rm_mod.sqlite3.connect`, `vlm_analyzer.primary_*`) dipindah di commit yang sama; **jangan ekspor ulang nama yang
  di-patch** (patch "berhasil" di namespace lama = tes lolos palsu).
- Modul murni baru hanya mengimpor `config`/`messages`/`ppe_rules`; `test_import_side_effects` tetap lolos.
  `tools/bench_vlm.py`, `tools/eval_vlm.py` tetap jalan. Berkas bersama (`config.py`, `messages.py`) tidak disentuh.
- Sebelum memindah: tes karakterisasi (`test_save_inspection_characterization`, `test_retention_characterization`,
  `test_state_characterization`, `test_durability`) lolos & jumlahnya dicatat; jalur tanpa tes (mis. migrasi v0→v3)
  diberi fixture skema lama di tmp pytest — **tidak pernah `data/`**.
- Jalur panas (§4.1): ukur `analyze_person` & `save_inspection` sebelum/sesudah (1 vs 20 orang; `get_reports`/
  `get_summary` 100 vs 100.000 baris) — fasad tidak menambah latensi terukur.
- Perbaikan logika yang ditemukan di jalan → dicatat di papan, dikerjakan terpisah.

**Pembagian:** Codex (backend/, tests/); Claude peninjau tiap tahap. Selama T99 diklaim, task backend lain yang
menyentuh `report_manager`, `vlm_analyzer`, `state_manager`, `routes_vlm`/`routes_reports` tidak diklaim bersamaan.

**Catatan T99a (25-10):** pengecualian impor disetujui pengguna: `vlm_prompt` mempertahankan dependensi metadata
`vlm_providers.profiles` dan `vlm_selection.prompt_version_for`, supaya tidak menduplikasi logika atau mengubah
perilaku. Sepuluh definisi cocok secara AST sebelum/sesudah (indentasi docstring dinormalkan; dekorator static
parser dipertahankan lewat binding fasad, diuji identitas objeknya). Tes acuan 68 lolos; setelah pemindahan
73 lolos termasuk lima tes baru untuk kompatibilitas fasad, logger, dan impor tanpa engine/thread/storage.

Pengukuran `perf_counter`, median sebelum → sesudah, VLM tiruan tanpa jaringan, crop sintetis 640×320;
31 pengulangan inspeksi, 9 pengulangan simpan tanpa foto, 7 pengulangan kueri. Semua DB di folder sementara:

| Jalur | Beban | Sebelum (ms) | Sesudah (ms) |
| :-- | :-- | --: | --: |
| `analyze_person` | 1 / 20 orang berurutan | 2,511 / 49,388 | 2,471 / 49,082 |
| `save_inspection` | 1 / 20 orang berurutan | 6,880 / 134,189 | 8,181 / 138,432 |
| `get_reports` | 100 / 100.000 baris | 0,964 / 32,048 | 0,991 / 31,737 |
| `get_summary` | 100 / 100.000 baris | 0,747 / 298,563 | 0,730 / 297,564 |

Inspeksi tidak menunjukkan tambahan latensi pada pengukuran ini; simpan audit berfluktuasi pada I/O disk
(kode audit tidak disentuh pada T99a). Angka tiruan ini tidak mengukur latensi penyedia VLM/perangkat nyata.

**Catatan T99b (25-10):** pemisahan ke `audit_db`, `snapshot_store`, `audit_queries`, `audit_export`, `attendance`,
dan `retention`. Pabrik koneksi SQLite ada di `audit_db`; hanya fasad yang memanggilnya serta memegang umur
koneksi, lock, BEGIN/COMMIT/ROLLBACK, commit sebelum penghapusan foto, dan penutupan koneksi ekspor dibatalkan.
Metode publik dan konstanta publik lama tetap; delegasi privat yang tidak dipakai tidak dipertahankan.
Target patch dipindahkan: jam simpan → `audit_db.time`; jam retensi → `retention.time`; OpenCV/replace/logger
foto → `snapshot_store`; pabrik SQLite → `audit_db.sqlite3`; SQL kehadiran → `attendance`.

Acuan sebelum pemindahan: 135 tes audit/karakterisasi lolos, ditambah 6 tes fixture v1/v2/v3 dan rollback yang
juga lolos pada kode lama (fixture v0 sudah tersedia). Sesudah pemindahan: 141 tes acuan lolos; 78 tes batas,
identitas, migrasi, impor, dan code hygiene lolos. Sepuluh kasus baru lain menjaga koneksi pinjaman, commit
sebelum menghapus foto (audit/foto/kuota), dan absennya namespace patch lama dari fasad. Nilai 43 literal SQL
identik; 27 badan fungsi cocok secara AST setelah normalisasi mekanis `self`/koneksi pinjaman. Uji diferensial
kode `c5b52e8` versus hasil pemindahan: 73 perintah SQLite aktual dan 13 hasil publik identik, termasuk CSV
dan retensi. Tidak ada perubahan skema, pragma synchronous=FULL, SQL, konfigurasi bersama, atau data produksi.

Pengukuran `perf_counter` di DB sementara tanpa foto: tiga putaran, pemanasan 10 simpan, median 15 sampel
untuk simpan (1/20 orang berurutan) dan 9 sampel untuk kueri (seluruh baris pada satu hari). Angka berikut
adalah median dari tiga putaran, sebelum → sesudah:

| Jalur | Beban | Sebelum (ms) | Sesudah (ms) |
| :-- | :-- | --: | --: |
| `save_inspection` | 1 / 20 orang | 7,427 / 165,796 | 8,478 / 167,348 |
| `get_reports` | 100 / 100.000 baris | 1,132 / 63,455 | 1,109 / 61,141 |
| `get_summary` | 100 / 100.000 baris | 0,841 / 602,986 | 0,837 / 593,052 |

Simpan satu orang masih berfluktuasi: sebelum 6,803/7,427/8,182 ms, sesudah 9,811/8,478/7,747 ms. Karena itu
ditambah pengukuran lama/baru berselang-seling di proses yang sama (3 putaran × 15 sampel, 15 simpan pemanasan).
Median pasangan sebelum → sesudah: 1 orang 7,293 → 7,249 ms; 20 orang 149,591 → 148,952 ms. Tidak terlihat
perlambatan konsisten akibat fasad pada uji ini; angka disk sesaat bukan batas latensi produksi.

Catatan untuk task terpisah: pola lama `with self._get_connection() as conn` pada beberapa metode hanya
mengakhiri transaksi, bukan menutup koneksi secara eksplisit; pola tersebut dipertahankan pada T99b agar
pemindahan tidak merangkap perubahan siklus koneksi. Ekspor dan kehadiran tetap memiliki penutupan eksplisit
seperti sebelumnya. Penyeragaman penutupan koneksi perlu dinilai dan diuji tersendiri.

**Catatan T99c (25-10):** `VLMEngine`, `LaneBusy`, dan `EngineFailed` pindah ke `vlm_engine`; pembantu
`image_for_vlm`/`warmup_image_jpeg` ikut dipindah agar pemanasan mesin tidak mengimpor balik fasad. Lima
definisi tersebut identik secara AST. Nama publik lama tetap merujuk objek yang sama; `create_provider`
tidak diekspor ulang. Target patch factory kini `backend.vlm_engine.create_provider`.

State pemutus kini `analyzer.breaker` (`PrimaryBreaker.failures`, `down_since`, `last_attempt`), tanpa alias
atribut lama. Pemutus menerima waktu eksplisit, membaca ambang dari config saat dipakai, dan tidak memiliki
lock, mesin, probe, log, atau I/O. Log dan pemberitahuan standby tetap di fasad dalam urutan semula.
`primary`/`backup` tetap atribut fasad (pemilik rute dan lock); patch engine di tes tetap mengenai objek yang
dipakai, bukan ekspor ulang modul. `api_lock`/`apply_lock` dan semua metode rute tetap di `VLMAnalyzer`.

Sebelum pemindahan, 227 tes terarah lolos termasuk 15 kasus karakterisasi baru: tepat dua gagal, lewatkan
utama hingga batas 60 detik dari percobaan terakhir, coba lagi hanya saat pekerja diperiksa (tanpa probe),
semua mesin gagal → menunggu, lokal darurat saat lambat/putus/loading, konfirmasi larangan/ragu/timeout,
serta `LaneBusy` tanpa menukar engine dan dengan pelepasan lock. Sesudah pemindahan 298 tes terarah lolos,
termasuk 17 kasus unit/penjaga kepemilikan baru untuk pemutus. Lima definisi mesin/gambar/exception identik
secara AST; 57 metode fasad identik setelah normalisasi lokasi state. Perbandingan kode `ef544fe` versus
kode baru pada 10.000 kejadian berbenih menghasilkan izin mencoba dan state pemutus yang identik.

Pengukuran `perf_counter` memakai crop sintetis 640×320 dan panggilan VLM tiruan (JPEG/prompt/parser/rute/lock
tetap berjalan), tanpa jaringan atau perangkat. Acuan awal 3 putaran × 21 sampel, pemanasan 20 inspeksi:
1 orang 2,534/2,567/2,587 ms; 20 orang 53,191/53,019/97,480 ms. Karena variasi beban, pengukuran utama memakai
kode lama/baru berselang-seling di proses sama, 3 putaran × 21 sampel dan pemanasan 20 inspeksi per versi:

| Beban `analyze_person` | Median sebelum (ms) | Median sesudah (ms) | Rentang median putaran sebelum / sesudah (ms) |
| :-- | --: | --: | :-- |
| 1 orang | 2,486 | 2,469 | 2,461–2,498 / 2,468–2,485 |
| 20 orang berurutan | 49,426 | 49,969 | 49,220–50,511 / 49,900–50,359 |

Selisih median batch 20 orang +0,542 ms (1,1%), dengan rentang sampel yang bertumpang tindih; angka ini tidak
menunjukkan perlambatan konsisten pada ketiga putaran dan bukan batas latensi VLM produksi. Batas waktu,
urutan peralihan, jumlah panggilan VLM, dan bentuk telemetri tidak diubah. Berkas bersama tidak disentuh.

## Antrean berikutnya (urut menurut risiko — AGENTS.md §2.2a, disusun 27-09, dirapikan 14-10)

| # | Risiko | Task | Alasan risiko / isi |
| :-- | :-- | :-- | :-- |
| 3 | **Tinggi** | **Uji nyata gabungan (T35 Uji 2 & 3)** | Belum diuji di gerbang: T72 jaringan (cabut LAN/Wi-Fi → lokal, hotspot lemah → lambat, colok lagi → utama, bongkar 10 menit), T88 lampu relay, VLM lokal darurat, T83 (panel ditahan + suara, ulang FR, FR mati), T98 (cadangan memakai akun kedua saat kuota utama habis), sisa lama (cabut kamera, setengah badan, berjalan lewat). Uji 2 sebagian 20-10 & penyebab gagalnya (T86, T87) sudah ditutup. **Diblokir:** perangkat dipakai demo. Riwayat rinci: arsip "Riwayat antrean (dipindah 24-10)" |
| 4 | **Tinggi** | **Uji fisik T57 & T58** (kamera terhalang; rokok/vape + pengecoh) | Sisa: pengecoh (pulpen, sedotan, ponsel, tangan kotor), vape, bungkus di saku, jalur cadangan lokal, kamera tertutup tangan/kain/plastik sistematis. Uji luring 22-10: 13/14 benar (0 merah palsu; terlewat foto 480p rokok ±4–5 px) — kebijakan "ragu = tidak ada" tetap. Riwayat: arsip "Riwayat antrean (dipindah 24-10)" |
| 4b | **Tinggi** | **T74 — rokok/benda kecil terlihat VLM** | Akar masalah 19-10: area tangan buram (bukan ukuran gambar/`media_resolution`). 1080p: luring 7/7, kamera langsung 4/5. Lanjutan (diblokir uji fisik): (a) cahaya tambahan → syarat pemasangan; (b) pemilih frame peka tangan; (c) 2–3 frame terbaik per panggilan; (d) eksposur dikunci. Uji ulang: rokok di tangan setinggi pinggang berlatar putih, 1080p. Riwayat: arsip "Riwayat antrean (dipindah 24-10)" |
| 5 | Sedang | **Validasi Gemini untuk prompt T58** — 10 foto 10/10 benar (pagi + sore 14-10, `data/eval/20261014-070915`, `-171309`); sore Gemini lambat (median 5,5 dtk, 4/5 > batas 4 dtk). Sisa: 84 foto penuh bila kuota mengizinkan | Status Gemini kini `outdated` (terakhir diuji T48) → peringatan di log & Pengaturan; uji 10–20 foto dengan jeda RPM |
| 6 | Sedang | **T40 — alternatif mesin VLM lokal** (keputusan setelah uji nyata) | Bila cadangan lokal masih sering crash (`encoding image` llama.cpp, ~2–4 per 84 foto) walau penjaga T38: uji Qwen2.5-VL 4-bit via Transformers di proses terpisah (OpenAI-compatible) dengan `tools/bench_vlm.py`; pengganti wajib lolos `apd_10` (helm di rambut lebat) & `apd_4` (sepatu). Riwayat: arsip "Riwayat antrean (dipindah 24-10)" |
| 7f | **Tinggi** (rencana) | **T81 — absensi resmi** (arah produk pengguna 19-10: "absensi + pemeriksaan APD") | Hanya bila tingkat pengenalan FR di gerbang terbukti tinggi & HR/Legal setuju (tujuan baru data wajah → persetujuan pekerja & DPIA diperbarui). Butuh jam masuk/pulang, shift, koreksi manual HR; kesalahan berdampak ke gaji/disiplin. Rancangan dimatangkan & risiko dinilai ulang sebelum dikerjakan |
| 7g | **Tinggi** (setelan sudah dibangun 24-10 — T83a/b, bawaan MATI; rancangan di arsip "Rancangan T83") | **T83 — syarat sebelum "Wajib terdaftar" dipakai sungguhan** | (1) ukur tingkat pengenalan pekerja terdaftar: tiap pekerja ±10× lewat memakai helm, target ≥ 95% (laporan kehadiran); (2) persetujuan HR/Legal & DPIA diperbarui (FR jadi penentu akses, bersama T81); (3) uji gerbang: panel kuning ditahan + suara, ulang FR "Mohon tatap kamera", FR mati → semua ditahan + chip, amati kedipan track (VLM ulang/audit ganda saat setelan aktif) |
| 8 | Sedang | Uji fisik tertunda: lampu ESP32 (T47), restart PC sungguhan (T29) | Rancangan diuji tanpa perangkat/simulasi saja |
| 9 | Rendah | Dua orang berdampingan di zona (T36d); T25 sisa latensi | Dicegah batas fisik di lokasi; latensi sudah jauh turun |
| 9c | Rendah | Grafik volume Laporan tanpa seri "Ditahan" (lanjutan T96, 24-10) | Bucket ringkasan hanya `passed`/`rejected` → batang < total bila ada yang ditahan. Usul: kontrak bucket + `held`, grafik seri ketiga kuning (Codex backend + Claude UI) |
| 10a | Rendah (eksekusi hati-hati: audit) | **T99 — perapian backend per fitur** (lihat "Rancangan T99"; tahap a→d, Codex) | Usul Codex 24-10: `vlm_analyzer` 1.222 & `report_manager` 1.079 baris; perilaku & kontrak tetap, tiap tahap tes regresi. **T99a selesai 25-10**; **T99a & T99b selesai 25-10**; **T99a–c selesai 25-10**; sisa **T99d** (pengelompokan folder, hanya path impor — boleh ditunda) |
| 10b | Rendah | **T100 — penutupan koneksi SQLite audit diseragamkan** (temuan Codex di T99b) | Pola `with self._get_connection() as conn` hanya mengakhiri transaksi, tidak menutup koneksi (di CPython tertutup saat objek dibuang, jadi kecil risikonya). Seragamkan ke penutupan eksplisit (`closing`) tanpa mengubah transaksi/urutan tulis; tes: jumlah koneksi terbuka tidak bertambah setelah N panggilan |
| 10 | Rendah | T42 — cicil utang kode (sisa setelah T42a–i) | 6 fungsi > 30 baris logis (23-10): `tools/bench_vlm.py::main` 97, `tools/eval_vlm.py::main` 88, `capture.__init__` 43, `app.run` 38, `report_manager._migrate` 34, `routes_cameras.list_cameras` 32 — daftar di `tests/test_code_hygiene.py`; 8 blok kembar (web: dialog CameraPicker/SnapshotDialog/AdminToken, ZoneSettings/Pengaturan); pesan log di luar `messages.py` (`camera_manager`, `detector`, `audio_engine`, `capture`); angka HUD/resolusi ke config; warna `#000` VideoPanel ke token; nama Indonesia → Inggris saat disentuh |
| 12 | **Tinggi** (syarat pemakaian) | **T34 — identitas wajah (FR)**: dibangun lengkap (T34m–e, T75/T76 selesai; rancangan di arsip "Rancangan T34") | Sisa sebelum dipakai sungguhan: persetujuan pekerja & DPIA HR/Legal (bersama T81/T83), tingkat pengenalan pekerja terdaftar terukur di gerbang (antrean 7g) |


### Rencana (belum dikerjakan) — setelah sistem utama lolos semua tes

- **Perapian UI/UX (calon T50) — DITUNDA sampai semua alur logika berjalan (keputusan pengguna 06-10).** Bahan dari kritik
  06-10 (dinilai dari screenshot versi lama): (1) status zona langsung di kanvas video; (2) "Belum dinilai" dibedakan
  siaga / sedang menilai / hasil; (3) slider zona + kotak angka; (4) Pengaturan dua kolom di layar lebar; (5) ikon APD tabel
  lebih besar + label; (6) panel kanan & bilah kontrol Monitoring (perlu contoh visual); (7) filter per jenis APD kurang
  (+ parameter backend). Tidak disarankan: search ID pekerja (belum ada identitas, tunggu T34), sparkline (sudah ada grafik
  T49). Sudah tertangani: grafik laporan (T49-UI), kartu token admin diganti login (T30-UI). Ambil screenshot baru sebelum disusun. Tambahan (06-10): saat
  menunggu kamera tersimpan yang tidak ada, dashboard menawarkan langsung "Kamera '<nama>' tidak ditemukan. Pilih kamera lain?".

- **Fitur larangan rokok:** dikerjakan sebagai **T58** (keputusan pengguna 13-10, lihat papan tugas).
- **Set uji tambahan:** baju kuning/oranye tanpa rompi, rompi asli di atas baju kuning, rompi tanpa pita
  reflektif, kaos bertulisan (termasuk "APD LENGKAP" — uji prompt injection lewat tulisan), foto kamera 4 MP;
  label per item.
- **Basis data terpusat (rencana panjang, keputusan pengguna 06-10):** gerbang **tetap SQLite** (tahan listrik padam
  & jaringan putus, tanpa layanan tambahan). Bila kelak ada **banyak gerbang / laporan HSE terpusat**: PostgreSQL di
  server pusat + **kirim-dan-simpan** dari tiap gerbang (catat lokal dulu, sinkron saat tersambung; gerbang tidak pernah
  berhenti karena jaringan ke pusat). Persiapan murah: akses DB tetap terpusat di satu modul repository
  (`report_manager.py`). Risiko dinilai saat rencananya matang (§2.2a). Pertanyaan terbuka: jumlah gerbang target,
  laporan jarak jauh, pengelola server di lokasi.
- **PostgreSQL + pgvector untuk data wajah terpusat (rencana panjang, permintaan pengguna 18-10; melanjutkan
  "basis data terpusat").** Belum dikerjakan; T34b menyiapkan antarmuka `WorkerStore` supaya pindahnya hanya menambah
  implementasi, bukan mengubah gerbang.
  - **Kapan dipakai:** banyak gerbang berbagi satu daftar pekerja (daftar sekali, dikenali di semua gerbang), atau
    jumlah pekerja jauh melewati batas galeri yang teruji (±300 per gerbang, T34m2). Untuk satu gerbang, SQLite +
    numpy di memori sudah cukup (10.000 pekerja < 0,1 ms per pencarian).
  - **Pembagian peran:** server pusat = sumber kebenaran pendaftaran (PostgreSQL + pgvector); **gerbang tetap mencari
    di memori lokal** dari salinan galeri yang ditarik dari pusat dan disimpan terenkripsi di SQLite gerbang, jadi FR
    tetap jalan saat jaringan putus (sejalan dengan "kirim-dan-simpan" audit). pgvector dipakai di pusat untuk:
    cek pendaftaran ganda (orang sama didaftarkan dua kali, 1:N ke seluruh pekerja), pencarian lintas lokasi oleh
    admin, dan kalibrasi ambang dari data nyata.
  - **Skema pusat (usulan):** `workers` (id, nomor pegawai unik, nama, lokasi, aktif, persetujuan: waktu/admin/versi,
    `deactivated_at`) dan `face_templates` (id, worker_id, `embedding vector(256)` untuk Intel 0095, `model_version`,
    kondisi foto mis. kacamata/helm, dibuat oleh/kapan). Indeks HNSW `vector_cosine_ops`; pencarian
    `ORDER BY embedding <=> $1 LIMIT k` lalu ambang. Ganti model = kolom/indeks baru per `model_version` + daftar ulang.
  - **Catatan keamanan penting:** pgvector hanya bisa mengindeks vektor **tanpa enkripsi kolom** (AES-GCM per baris
    seperti di SQLite gerbang membuat indeks tidak bisa dipakai). Pengganti di pusat: enkripsi disk/volume (LUKS / KMS
    penyedia), TLS wajib gerbang↔pusat, peran DB terpisah (gerbang hanya baca galerinya; tulis hanya layanan admin),
    row-level security per lokasi, log akses (`pgaudit`) → masuk DPIA sebagai perbedaan perlakuan dengan gerbang.
  - **Retensi sama dengan gerbang:** hapus templat 30 hari setelah nonaktif dijalankan di pusat; gerbang ikut
    menghapus salinannya pada sinkron berikutnya (penghapusan juga dikirim, bukan hanya penambahan).
  - **Tahapan kasar:** (1) server pusat + skema + migrasi dari ekspor SQLite gerbang; (2) layanan pendaftaran pusat +
    sinkron galeri ke gerbang; (3) kirim-dan-simpan audit; (4) akun terpusat. Risiko dinilai saat rencana matang
    (kemungkinan **Tinggi**: data biometrik lintas jaringan). Pertanyaan terbuka: siapa mengelola server, lokasi
    server (on-premise / cloud — berpengaruh ke transfer data pribadi UU PDP), jumlah gerbang & pekerja target.
- **Akun terpusat & peran operator (rencana panjang, keputusan pengguna 07-10):** saat dipasang di banyak gerbang, akun per gerbang merepotkan (karyawan keluar = hapus di setiap gerbang). Arah: akun di server pusat (sejalan dengan basis data terpusat) atau login kantor (SSO/LDAP) bila perusahaan punya; gerbang memeriksa ke pusat dan tetap punya **akun lokal darurat** saat jaringan putus. Peran operator vs admin diaktifkan saat itu (T51 sudah menyiapkan kolom `role` & `require_role`). Risiko dinilai saat rencananya matang.
- **IoT & palang boom** (tahap setelah fitur utama berjalan): ESP, relay, LED merah/hijau/kuning, sirine bila
  perlu; sensor setelah palang memastikan pekerja lewat sebelum palang menutup. Tahap 1: **berurutan penuh**
  (periksa → lampu + suara + palang buka → sensor lewat → palang tutup → pekerja berikutnya). Tahap 2:
  pekerja berikutnya diperiksa lebih awal, pengumuman ditahan sampai palang SIAP. Heartbeat server → ESP,
  tanda "sistem tidak aktif" (kuning berkedip), batas waktu bila lolos tapi tidak lewat, catat tailgating.
  **Belum diputuskan:** palang saat listrik padam terbuka atau tertutup.
- **Listrik padam:** UPS untuk PC, kamera, jaringan + shutdown rapi otomatis; BIOS "power on after AC loss";
  SOP pemeriksaan manual oleh petugas.


## Keputusan pengguna (acuan)

**Gerbang & VLM**
- Alur: pekerja datang → selama tubuh belum utuh API terkunci (arahan posisi) → satu gambar ke VLM → keputusan terkunci sampai orang keluar dari jalur.
- Utama = VLM cloud (penyedia bebas, bawaan Gemini 3.5 Flash-Lite); cadangan = VLM lokal (`qwen2.5vl:7b` via Ollama). Batas waktu cloud 4 dtk, lokal 12 dtk; setelah 2 kegagalan utama berturut-turut, utama dilewati dan dicoba lagi pada pekerja nyata setelah 60 dtk (tanpa probe yang memakan kuota).
- Keduanya gagal → tidak ada keputusan: suara "mohon tunggu", lampu padam, diperiksa ulang otomatis, gangguan cukup dicatat di log.
- Heuristik OpenCV dibuang. vLLM ditunda (tidak cocok GPU 8 GB bersama YOLO; ditinjau ulang di GPU lebih besar).
- Proyek untuk demo: lisensi Ultralytics AGPL belum jadi masalah.

**Operasi (08-10)**
- Notifikasi insiden lewat WhatsApp (Fonnte, calon T52) **dibatalkan**; rancangannya dihapus dari rencana.
- Log dikelola per jenis — application, security, audit — dan tidak boleh membuat server hang (T53).

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

**IoT demo (05-10)**
- Demo tanpa palang: fokus lampu. Papan **ESP32 DevKit V1 lewat USB serial**; Wi-Fi/HTTP tidak dipakai sampai ada perintah bertanda tangan (HMAC + penghitung).
- Lampu **merah / kuning / hijau**; dibeli dua varian: pilot lamp industri 12V Ø22 mm dan LED 10 mm untuk meja, keduanya lewat relay yang sama.
- **Buzzer = cadangan** (kanal relay ke-4 disiapkan, mati bawaan) supaya tidak tumpang tindih dengan suara speaker.
- **Gangguan (kamera, VLM, sistem mati) = kuning**, bukan merah; merah tetap khusus APD kurang (§5).

**Mesin gerbang (06-10)**
- VLM lokal lambat di uji nyata 06-10 (7,5 dtk) karena GPU laptop ditahan manajemen daya, BUKAN versi Ollama (diuji: 0.34.4 = 0.35.1).
  Setelah mode dGPU + overclock (restart): baca prompt 3,1 → 1,4 dtk, latensi bench 5,3 → 3,5 dtk. Pengaturan di docs/INSTALASI.md.
- Ollama dikunci di **0.34.4** (versi validasi), update otomatis dimatikan. Produksi (T29/Docker): versi image dikunci.

**Operasi**
- OS produksi belum tentu Windows; produksi lewat Docker di Linux, pengembangan di Windows dengan venv.
- Belum ada layar untuk pekerja di gerbang (suara & lampu saja); mode kios = rencana ke depan.

## Catatan terbuka

- **Uji CPU only 19-10** (`CUDA_VISIBLE_DEVICES=-1`, tanpa cadangan, kamera 864×480, Gemini free tier): bench YOLO26s-pose frame 1080p — GPU RTX 4060 median 11,3 ms (~88 FPS), CPU laptop 16 thread 51,6 ms (~19 FPS); server nyata **15–17 FPS** (kosong maupun ada orang), CPU ~8 dari 16 inti logis, RAM ~958 MB. 13 sesi, 6 inspeksi: keputusan sesuai jawaban VLM, VLM 1,8–2,9 dtk setelah siap, tanpa galat; jalur lolos (hijau) 3×, merah 3×. Batas: perangkat edge 4–8 inti kemungkinan di bawah 15 FPS; 1080p belum diukur di CPU (ikut T74). Catatan Windows: `CUDA_VISIBLE_DEVICES=` (kosong) tidak berefek, pakai `-1`.
- VRAM puncak 7,6 / 8 GB dengan `qwen2.5vl:7b` + YOLO — risiko OOM bila ada beban GPU lain.
- Ollama kadang crash pada gambar tertentu (ollama/ollama#14170); inspeksi itu jatuh ke jalur gangguan dan diulang.
- Monitoring di lebar ~360 px: satu tombol panel video melewati tepi kanan (terpotong, tanpa scroll horizontal) — rapikan di T33 langkah 3.
