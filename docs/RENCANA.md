# Rencana DEPRO — status, antrean, dan keputusan

Rencana bersama untuk semua agen (lihat [`AGENTS.md`](../AGENTS.md)). Perbarui
berkas ini setiap kali status task atau keputusan berubah. Riwayat rinci ada di
pesan commit (`git log`).

Terakhir diperbarui: 24-10-2026. Task `selesai`, kontrak/rancangan task selesai, dan catatan lama dipindah ke [`arsip/RENCANA-selesai.md`](arsip/RENCANA-selesai.md) (tidak perlu dibaca rutin; cari di sana bila butuh angka uji atau alasan keputusan lama).

## Lanjut dari sini (24-10-2026, akhir sesi panjang)

- **`master` di-push 24-10** setelah T97a (T95, T96, T98, T97a, lanjutan Kehadiran, papan) — lolos `check.py` (pytest 1.132, vitest 252).
- **25-10:** T97 (a/b/c), T99 (a–d), T100, T101 (grafik Ditahan), T42j/k selesai — digabung & di-push. Berikutnya:
  T42 sisa (5 fungsi panjang), uji nyata (antrean 3/4/4b, diblokir perangkat demo).
- **Diskusi arsitektur v2 (25-10):** [`docs/USULAN-ARSITEKTUR.md`](USULAN-ARSITEKTUR.md) — usulan Claude + tanggapan Codex +
  topik baru pengguna (dua kamera masuk/keluar, admin vs operator, Monitoring tetap terlihat; bagian 11). **Diparkir**: pengguna
  memutuskan bereskan dulu pekerjaan sekarang; dibahas lagi sesudahnya.
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

## Antrean berikutnya (urut menurut risiko — AGENTS.md §2.2a, disusun 27-09, dirapikan 14-10)

| # | Risiko | Task | Alasan risiko / isi |
| :-- | :-- | :-- | :-- |
| 3 | **Tinggi** | **Uji nyata gabungan (T35 Uji 2 & 3)** | Belum diuji di gerbang: T72 jaringan (cabut LAN/Wi-Fi → lokal, hotspot lemah → lambat, colok lagi → utama, bongkar 10 menit), T88 lampu relay, VLM lokal darurat, T83 (panel ditahan + suara, ulang FR, FR mati), T98 (cadangan memakai akun kedua saat kuota utama habis), sisa lama (cabut kamera, setengah badan, berjalan lewat). Uji 2 sebagian 20-10 & penyebab gagalnya (T86, T87) sudah ditutup. **Diblokir:** perangkat dipakai demo. Riwayat rinci: arsip "Riwayat antrean (dipindah 24-10)" Tambahan 25-10: ukur biaya `save_inspection` di perangkat gerbang (T100: checkpoint WAL per simpan, 7,5 → 11,9 ms di laptop); bila berarti → satu koneksi penjaga terbuka sepanjang server hidup |
| 4 | **Tinggi** | **Uji fisik T57 & T58** (kamera terhalang; rokok/vape + pengecoh) | Sisa: pengecoh (pulpen, sedotan, ponsel, tangan kotor), vape, bungkus di saku, jalur cadangan lokal, kamera tertutup tangan/kain/plastik sistematis. Uji luring 22-10: 13/14 benar (0 merah palsu; terlewat foto 480p rokok ±4–5 px) — kebijakan "ragu = tidak ada" tetap. Riwayat: arsip "Riwayat antrean (dipindah 24-10)" |
| 4b | **Tinggi** | **T74 — rokok/benda kecil terlihat VLM** | Akar masalah 19-10: area tangan buram (bukan ukuran gambar/`media_resolution`). 1080p: luring 7/7, kamera langsung 4/5. Lanjutan (diblokir uji fisik): (a) cahaya tambahan → syarat pemasangan; (b) pemilih frame peka tangan; (c) 2–3 frame terbaik per panggilan; (d) eksposur dikunci. Uji ulang: rokok di tangan setinggi pinggang berlatar putih, 1080p. Riwayat: arsip "Riwayat antrean (dipindah 24-10)" |
| 5 | Sedang | **Validasi Gemini untuk prompt T58** — 10 foto 10/10 benar (pagi + sore 14-10, `data/eval/20261014-070915`, `-171309`); sore Gemini lambat (median 5,5 dtk, 4/5 > batas 4 dtk). Sisa: 84 foto penuh bila kuota mengizinkan | Status Gemini kini `outdated` (terakhir diuji T48) → peringatan di log & Pengaturan; uji 10–20 foto dengan jeda RPM |
| 6 | Sedang | **T40 — alternatif mesin VLM lokal** (keputusan setelah uji nyata) | Bila cadangan lokal masih sering crash (`encoding image` llama.cpp, ~2–4 per 84 foto) walau penjaga T38: uji Qwen2.5-VL 4-bit via Transformers di proses terpisah (OpenAI-compatible) dengan `tools/bench_vlm.py`; pengganti wajib lolos `apd_10` (helm di rambut lebat) & `apd_4` (sepatu). Riwayat: arsip "Riwayat antrean (dipindah 24-10)" |
| 7f | **Tinggi** (rencana) | **T81 — absensi resmi** (arah produk pengguna 19-10: "absensi + pemeriksaan APD") | Hanya bila tingkat pengenalan FR di gerbang terbukti tinggi & HR/Legal setuju (tujuan baru data wajah → persetujuan pekerja & DPIA diperbarui). Butuh jam masuk/pulang, shift, koreksi manual HR; kesalahan berdampak ke gaji/disiplin. Rancangan dimatangkan & risiko dinilai ulang sebelum dikerjakan |
| 7g | **Tinggi** (setelan sudah dibangun 24-10 — T83a/b, bawaan MATI; rancangan di arsip "Rancangan T83") | **T83 — syarat sebelum "Wajib terdaftar" dipakai sungguhan** | (1) ukur tingkat pengenalan pekerja terdaftar: tiap pekerja ±10× lewat memakai helm, target ≥ 95% (laporan kehadiran); (2) persetujuan HR/Legal & DPIA diperbarui (FR jadi penentu akses, bersama T81); (3) uji gerbang: panel kuning ditahan + suara, ulang FR "Mohon tatap kamera", FR mati → semua ditahan + chip, amati kedipan track (VLM ulang/audit ganda saat setelan aktif) |
| 8 | Sedang | Uji fisik tertunda: lampu ESP32 (T47), restart PC sungguhan (T29) | Rancangan diuji tanpa perangkat/simulasi saja |
| 9 | Rendah | Dua orang berdampingan di zona (T36d); T25 sisa latensi | Dicegah batas fisik di lokasi; latensi sudah jauh turun |
| 10 | Rendah | T42 — cicil utang kode (sisa setelah T42a–i) | 6 fungsi > 30 baris logis (23-10): `tools/bench_vlm.py::main` 97, `tools/eval_vlm.py::main` 88, `capture.__init__` 43, `app.run` 38, `report_manager._migrate` 34, `routes_cameras.list_cameras` 32 — daftar di `tests/test_code_hygiene.py`; 8 blok kembar (web: dialog CameraPicker/SnapshotDialog/AdminToken, ZoneSettings/Pengaturan); pesan log di luar `messages.py` (`camera_manager`, `detector`, `audio_engine`, `capture`); angka HUD/resolusi ke config; warna `#000` VideoPanel ke token; nama Indonesia → Inggris saat disentuh — **25-10 T42j selesai** (dialog `CameraPicker`/`SnapshotDialog` → `ModalDialog`, `#000` VideoPanel → token; Zona/Pengaturan sudah tanpa blok kembar). **T42k selesai** (9 modal → `ModalOverlay`). Sisa: 5 fungsi panjang |
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
- **Produksi: VLM utama & cadangan berbayar**; free tier hanya untuk pengembangan & demo (keputusan pengguna 25-10).
- **Fokus 25-10: satu gerbang** — perapian struktur folder + best practice + MLOps (lihat `docs/USULAN-ARSITEKTUR.md`); multi-gerbang/PostgreSQL ditunda; GPU vs edge computing didiskusikan nanti.
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
