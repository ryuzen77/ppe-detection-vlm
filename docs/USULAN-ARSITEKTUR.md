# Usulan arsitektur DEPRO v2 — bahan diskusi (Claude, 25-10-2026)

Status: **draf diskusi** antara pengguna, Claude, dan Codex. Belum ada yang disetujui; setelah sepakat, keputusan
dipindah ke `docs/RENCANA.md` sebagai task berisiko (AGENTS.md §2.2a) dan dokumen ini diarsipkan.

Cara menanggapi: tulis tanggapan di bagian **Tanggapan** paling bawah (nama + nomor bagian), jangan menyunting
usulan orang lain. Pertanyaan yang butuh keputusan pengguna diberi tanda **[Keputusan]**.

---

## Keputusan pengguna (25-10)

1. **Produksi: VLM utama & cadangan berbayar.** Free tier hanya untuk pengembangan & demo.
2. **Fokus sekarang: satu gerbang** — perapian struktur folder (backend & web) dengan best practice (clean code,
   system design, log) **dan MLOps**. Multi-gerbang, server pusat, dan PostgreSQL/pgvector **ditunda** (rancangannya
   tetap di bagian 6 & 8 sebagai arah, tidak dikerjakan sekarang).
3. **GPU vs edge computing di skala besar** didiskusikan nanti (bagian 8.4) — biaya GPU per gerbang dianggap mahal.

## 0. Prinsip yang tidak berubah

1. Keputusan produk AGENTS.md §5 tetap: semua keputusan APD oleh VLM, merah hanya APD kurang/larangan, gagal VLM →
   pekerja menunggu, nama penyedia tidak tampil di UI operator.
2. **Gerbang tetap berdiri sendiri** (offline-first): listrik/jaringan ke pusat putus → gerbang tetap memeriksa dan
   mencatat. Apa pun yang terpusat (PostgreSQL, log pusat) adalah *tambahan*, bukan syarat jalan.
3. Perapian dikerjakan seperti T99: **tahap kecil, pindah-saja, perilaku & kontrak API tetap**, bukti AST/tes, satu
   tahap satu tinjauan. Tidak ada "rewrite besar".
4. Tiap tahap dinilai risikonya; perapian = Rendah, tetapi yang menyentuh audit/keputusan gerbang dieksekusi
   hati-hati dan didahului tes karakterisasi.

## 1. Kondisi sekarang (angka 25-10)

| Bagian | Fakta | Masalah |
| :-- | :-- | :-- |
| Backend | 15.372 baris; **41 modul datar** di `backend/` + paket `api/`, `audit/`, `vlm/`, `vlm_providers/`, `video/` | Sulit melihat batas fitur; `state_manager` 894, `worker_store` 814, `vlm/analyzer` 813, `video/capture` 750 baris |
| Berkas bersama | `config.py` 652, `messages.py` 588 | Titik bentrok utama antaragen; semua fitur menulis di sini |
| Frontend | 41 Svelte, 36 TS, 23 tes; folder per halaman (`components/monitoring|reports|settings|workers`) | `messages.ts` 961, `api/types.ts` 815 baris — sama-sama satu berkas raksasa |
| Basis data | 3 SQLite terpisah: `audit.db`, `accounts.db`, `workers.db` (wajah terenkripsi AES-GCM) | Akses tersebar (`audit/`, `accounts.py`, `worker_store.py`); migrasi skema buatan sendiri per DB |
| Log | Application log (antrean, ringkas banjir, rotasi, umur), security log JSONL terpisah, penjaga disk | Tidak ada pengenal korelasi sesi/inspeksi; teks bebas (sulit dikueri); tidak ada metrik |
| ML | YOLO26s-pose (`backend/yolo26s-pose.pt`), VLM cloud + lokal (prompt `PROMPT_VERSION` di `messages.py`), FR YuNet + reid-0095; catatan validasi VLM = `VALIDATIONS` di kode (`profiles.py`); alat `tools/eval_vlm.py`, `bench_vlm.py`, `tools/fr_eval/` | Dataset uji (`picture_test/`) tanpa manifest/versi; hasil evaluasi tersebar di `data/eval/`; tidak ada registri model tunggal; tidak ada pemantauan kualitas model di produksi |

## 2. Struktur backend yang diusulkan — paket per fitur, lapisan di dalamnya

Satu aplikasi (bukan microservice). Tiap fitur satu paket; di dalam paket, logika murni dipisah dari I/O:

```
backend/
  core/          config, messages (dipecah per fitur, lihat 2.2), logging, security_log, storage, disk_guard,
                 runtime_settings, readiness, uptime, shutdown, supervisor, startup_checks, gpu_processes
  gate/          state_manager → session.py (mesin keadaan murni) + orchestrator.py (thread, executor),
                 zone, frame_quality, pose_keypoints, registration_policy
  vision/        detector, camera_manager, camera_health, video/ (capture, stream)
  vlm/           (sudah) analyzer, engine, breaker, prompt, result, image, selection
                 + providers/ (dari vlm_providers/), local_model_guard, api_monitor, internet_monitor
  identity/      face_engine, face_align, face_identity, face_crypto, worker_store, worker_voice
  audit/         (sudah) report_manager, db, queries, export, attendance, retention, snapshots, summary
  signals/       notifier, audio_engine, usb_relay, generate_audio   (lampu, suara, relay)
  accounts/      accounts, auth
  api/           routes_* tetap tipis: validasi → panggil layanan fitur → bentuk JSON
  app.py, runtime.py (satu "composition root": semua objek dirakit di sini), __main__.py
```

Aturan lapisan (dijaga tes, bukan hanya kesepakatan):
- Berkas logika murni (mis. `gate/session.py`, `vlm/result.py`, `audit/summary.py`) **tidak** mengimpor
  `sqlite3`, `cv2.VideoCapture`, `httpx`, `fastapi`, atau `threading`.
- `api/` hanya mengimpor layanan fitur; fitur **tidak** mengimpor `api/`.
- Fitur tidak saling meraih isi dalam: `gate` memakai `audit.report_manager.ReportManager`, bukan `audit.db`.
- Usul: tes `test_architecture.py` (AST impor, gaya import-linter tanpa dependensi baru) yang memeriksa aturan
  di atas — seperti `test_code_hygiene.py` menjaga hex & fungsi panjang.

### 2.1 Pecah dua berkas terbesar dulu (risiko keputusan gerbang)
- `state_manager.py` (894): pisahkan **mesin keadaan sesi** (murni: masukan frame/track → keadaan & aksi) dari
  **orkestrator** (thread, executor VLM/FR, audio, simpan audit). Ini yang paling berharga untuk diuji, karena
  keputusan "lolos/tolak/tunggu/tahan" ada di sini. Didahului tes karakterisasi seperti T99c.
- `worker_store.py` (814): repositori pekerja (SQL) vs galeri wajah di memori vs enkripsi — tiga tanggung jawab.

### 2.2 Berkas bersama
- `messages.py` → paket `core/messages/` per fitur (`gate.py`, `vlm.py`, `audit.py`, …) dengan `__init__` yang
  **tidak** mengekspor ulang (lihat pelajaran T99: shim = target patch palsu). Mengurangi bentrok antaragen.
- `config.py`: tetap satu sumber `.env`, tetapi kelompokkan per fitur (dataclass bersarang `cfg.vlm.*`,
  `cfg.audit.*`) **hanya bila** nama kunci `.env` tidak berubah. **[Keputusan]** layak tidak, karena menyentuh
  ratusan pemakai `cfg.X`?

## 3. Struktur frontend yang diusulkan — fitur, bukan jenis berkas

```
web/src/
  app/           App.svelte, router, layout (TopBar), main.ts
  features/
    monitoring/  components/, logic/ (murni + *.test.ts), messages.ts, api.ts (panggilan & tipe fitur ini)
    reports/     …   (Laporan, Kehadiran, grafik)
    workers/     …
    settings/    …   (VLM, zona, akun, diagnostik)
    auth/        …   (login, setup)
  shared/
    ui/          ModalDialog, ModalOverlay, PasswordInput, StatTile, Toasts, PpeIcon
    api/         client.ts (HTTP, galat, sesi) — tanpa tipe per fitur
    lib/         format, url, settings (angka UI bersama)
  styles/        tokens.css, fonts.css, app.css
```

- `messages.ts` (961) dan `api/types.ts` (815) dipecah per fitur; impor lintas fitur hanya lewat `shared/`.
- Aturan "logika murni di lib, komponen merakit" tetap, hanya pindah ke `features/<x>/logic/`.
- ESLint `no-restricted-imports` menjaga `features/a` tidak mengimpor isi `features/b`.

## 4. System design — alur & batas

```
Kamera → vision (frame, pose) → gate (sesi: posisi → pilih frame → minta keputusan)
                                   ├─► vlm (utama → cadangan → lokal darurat → "tunggu")
                                   ├─► identity (FR paralel, opsional)
                                   └─► keputusan terkunci → signals (lampu, suara) + audit (SQLite + foto)
api (REST/WS) ◄── membaca keadaan gate, audit, identity; mengubah setelan lewat layanan fitur
```

- **Satu composition root** (`runtime.py`): objek global modul (`report_mgr`, `vlm_analyzer`, …) dirakit di satu
  tempat dan dioper, bukan diimpor sebagai singleton dari mana-mana. Memudahkan tes & penggantian DB (bagian 6).
- **Antarmuka repositori** untuk data yang kelak bisa terpusat: `AuditRepository`, `WorkerRepository`,
  `AccountRepository` (Protocol Python). Implementasi SQLite sekarang; PostgreSQL nanti tanpa mengubah `gate`.
  (`WorkerStore` T34b sudah sebagian seperti ini.)
- **Peristiwa domain** sederhana (`InspectionDecided`, `SessionHeld`, …) di dalam proses: audit, lampu, notifikasi,
  dan kelak sinkron pusat berlangganan, bukan dipanggil berurutan di `state_manager`.

## 5. Log management

Yang sudah baik (T53): antrean asinkron, ringkas banjir, rotasi + umur, security log terpisah, penjaga disk.
Usulan tambahan:

1. **Pengenal korelasi**: `session_id` / `inspection_id` / `track_id` lewat `contextvars`, otomatis masuk tiap baris
   log & disimpan di baris audit → satu inspeksi bisa ditelusuri dari audit ke log (VLM mana, berapa lama, kenapa
   pindah ke cadangan).
2. **Format terstruktur opsional**: `LOG_FORMAT=text|json` (bawaan text untuk manusia; json untuk dikirim ke pusat).
3. **Kategori tetap tiga**: application, security, audit (keputusan 08-10) — ditambah **metrics** (bukan log):
   hitungan & latensi (inspeksi/jam, VLM p50/p95, rasio cadangan, FR dikenali, antrean log dibuang) di endpoint
   `/api/metrics` (format Prometheus teks, tanpa dependensi baru) untuk dashboard/pemantauan.
4. **Data pribadi**: nama pekerja & wajah **tidak** masuk application log (cukup `worker_id`); audit tetap sumber
   kebenaran dengan retensinya (T20).
5. **Multi-gerbang (nanti)**: pengirim log ringan (Vector/Fluent Bit) ke pusat (Loki/ELK); gerbang tidak menunggu.

## 6. Menuju PostgreSQL + pgvector (rencana panjang, sudah ada di RENCANA "Basis data terpusat")

Usul tahapan supaya pindahnya murah dan aman:

| Tahap | Isi | Kapan |
| :-- | :-- | :-- |
| 6a | Antarmuka repositori (bagian 4) untuk audit, pekerja, akun; SQL terkumpul di satu modul per DB | Bisa sekarang (perapian) |
| 6b | **Alat migrasi skema** seragam untuk 3 DB (ganti "versi skema" buatan sendiri). **[Keputusan]** Alembic + SQLAlchemy Core (dependensi baru, dua dialek) vs tetap SQL mentah + migrasi bernomor sendiri | Sebelum PG |
| 6c | **Outbox di gerbang**: tiap baris audit/pendaftaran dicatat juga di tabel `outbox`; pengirim mengunggah idempoten (UUID baris) saat jaringan ada | Saat ada server pusat |
| 6d | Server pusat: PostgreSQL + pgvector (skema di RENCANA: `workers`, `face_templates vector(256)`, HNSW cosine), API sinkron, galeri ditarik gerbang & disimpan terenkripsi lokal | Setelah jumlah gerbang & pengelola server jelas |

Catatan penting (dari RENCANA): pgvector **tidak bisa** mengindeks kolom terenkripsi per baris → di pusat
diganti enkripsi disk/KMS + TLS + RLS + `pgaudit`, masuk DPIA. Risiko tahap 6c–6d **Tinggi** (biometrik lintas
jaringan, UU PDP). **[Keputusan]** Target jumlah gerbang & siapa pengelola server menentukan apakah 6c–6d
dikerjakan tahun ini.

## 7. MLOps — inti produk

Model yang menentukan keputusan: **VLM (cloud + lokal) + prompt**, **YOLO pose** (siapa & posisi), **FR**
(identitas). Yang sudah ada: versi prompt, katalog validasi VLM, uji wajib sebelum model baru dipakai (T97),
alat eval/bench, eval FR. Kekurangannya ada di **ketertelusuran** dan **pemantauan produksi**.

### 7.1 Artefak & registri
- `models/registry.json` (satu sumber): tiap model/prompt → versi, sumber, lisensi, sha256 berkas, peran,
  status validasi, tanggal. `VALIDATIONS` di `profiles.py` & `tools/fr_eval/models.json` dipindah ke sini (dibaca
  kode, bukan ditulis tangan di Python).
- Bobot model tidak di git (24 MB `.pt` sekarang di `backend/`) → diunduh & diverifikasi sha256 saat instalasi
  (`tools/fr_eval/fetch_models.py` sudah polanya).

### 7.2 Dataset evaluasi
- `datasets/<nama>/manifest.json`: daftar foto (hash, bukan isi), label per item APD, kondisi (cahaya, jarak,
  pengecoh), sumber & **dasar persetujuan**. Foto asli tetap di luar git (`picture_test/` berisi orang sungguhan).
- Versi dataset = hash manifest. Setiap angka validasi menyebut versi dataset yang dipakai.

### 7.3 Evaluasi yang bisa diulang
- `tools/eval_vlm.py` menulis **catatan run** terstruktur: model, prompt, versi dataset, metrik (APD kurang lolos =
  **harus 0**, patuh salah ditolak, latensi p50/p95), biaya panggilan. Ringkasan run lolos = masuk registri.
- **Gerbang rilis**: model/prompt baru tidak boleh `validated` tanpa run penuh di dataset terkini; CI menjalankan
  evaluasi dengan VLM tiruan (logika parser/keputusan), evaluasi sungguhan manual karena kuota.

### 7.4 Pemantauan produksi (dari audit, tanpa data tambahan)
- Per hari/model: rasio ditolak per item, rasio "VLM ragu", rasio pindah ke cadangan/lokal, latensi p95, FR dikenali,
  konfirmasi larangan T58. Lonjakan = tanda drift (mis. kamera kotor, cahaya berubah, model penyedia diganti diam-diam).
- Ditampilkan di Pengaturan → Diagnostik (admin) dan `/api/metrics`.

### 7.5 Umpan balik manusia
- Admin menandai keputusan yang salah dari Laporan ("seharusnya lolos/ditolak") → kandidat dataset.
  **Konflik yang harus diputuskan [Keputusan]**: foto bukti dihapus 30 hari (T20, data pribadi). Memasukkan foto
  ke dataset = tujuan baru → perlu persetujuan pekerja & DPIA, atau hanya simpan label + hash tanpa foto.

## 8. Skalabilitas — batas sekarang, pemicu, dan langkahnya

Prinsip: **skala ke luar per gerbang** (tiap gerbang = satu unit mandiri: kamera, GPU, VLM, SQLite), lalu
**pusat** untuk data bersama. Tidak ada satu server yang memproses video semua gerbang — video tidak pernah
dikirim ke pusat (bandwidth & data pribadi).

### 8.1 Dimensi & angka terukur

| Dimensi | Sekarang (terukur) | Batas / risiko | Pemicu penskalaan | Langkah |
| :-- | :-- | :-- | :-- | :-- |
| **Throughput 1 gerbang** | 1 jalur, keputusan terkunci per sesi; VLM cloud ±2–5 dtk, lokal 3,5–7,9 dtk | Antrean di jam masuk shift (mis. 200 pekerja dalam 15 menit = 1 orang / 4,5 dtk) | Antrean > N orang terukur di gerbang | Tambah **jalur/gerbang** (scale-out), bukan mempercepat satu jalur; tahap 2 IoT (pekerja berikutnya diperiksa lebih awal) |
| **Kamera & deteksi** | YOLO26s-pose GPU ~88 FPS bench, server 15–17 FPS di CPU-only; 1 kamera per proses | 2+ kamera per PC → GPU/CPU berbagi | Satu PC melayani >1 jalur | 1 proses per kamera (port berbeda) atau proses vision terpisah + antrean frame; ukur dulu |
| **Kuota & biaya VLM cloud** | Produksi **berbayar** (utama & cadangan, keputusan 25-10); free tier ±15 RPM / ±500 per hari hanya dev & demo; key per peran (T98) | 1 inspeksi = 1–2 panggilan (+ konfirmasi larangan T58); biaya per pekerja per hari belum diukur | Tagihan/bulan atau batas RPM tier berbayar | **Penghitung panggilan & biaya** per peran (tahu biaya per inspeksi), pembatas laju; cadangan lokal tetap jalan |
| **GPU lokal** | VRAM puncak 7,6 / 8 GB (`qwen2.5vl:7b` + YOLO) | OOM bila ada beban GPU lain | Model lokal lebih besar / 2 kamera | GPU ≥ 12–16 GB per gerbang atau server inferensi lokal bersama di lokasi (vLLM, ditunda T40) |
| **Galeri wajah** | Teruji ±300 pekerja/gerbang; 10.000 pekerja < 0,1 ms/pencarian (numpy di memori) | Akurasi 1:N turun saat galeri besar (lebih banyak salah kenal) | > 300 pekerja aktif atau multi-gerbang | Ukur ulang ambang per ukuran galeri; galeri per lokasi; pusat pgvector (6d) untuk cek ganda & lintas lokasi |
| **Audit** | 100.000 baris: laporan ±32–63 ms, ringkasan ±300–600 ms (indeks `idx_date_str`); simpan ±12 ms (T100) | Ringkasan bulanan tumbuh linear; retensi 1 tahun | Ringkasan > 1 dtk atau > 1 juta baris | Tabel agregat harian (dihitung saat simpan/malam), bukan hitung ulang; di pusat: partisi per bulan di PG |
| **Foto bukti** | Lokal, 30 hari, maksimal 2 GB (T20) | Disk gerbang sempit | Multi-gerbang butuh foto di pusat | Object storage (S3/MinIO) di pusat via outbox; gerbang tetap simpan lokal dulu |
| **Jumlah gerbang** | 1 | Konfigurasi, akun, pembaruan per gerbang manual | ≥ 3 gerbang | Pusat: akun terpusat + akun darurat lokal, konfigurasi terpusat (gerbang menarik), **pembaruan armada** (image Docker berversi, rollout bertahap, rollback) |
| **Pusat** | Belum ada | — | Multi-gerbang | API tanpa state (bisa >1 instance di belakang load balancer), PG + replika baca, antrean sinkron idempoten (outbox) |

### 8.2 Prinsip desain supaya skala tidak perlu rewrite

1. **Tanpa state global tersembunyi** — objek dirakit di composition root (bagian 4) dan diberi `gate_id`; data yang
   dikirim ke pusat selalu membawa `gate_id` + UUID baris (bukan id autoincrement lokal).
2. **Idempoten** — unggahan ulang baris yang sama tidak menggandakan (UUID + upsert).
3. **Batas waktu & tekanan balik** di setiap I/O jaringan (sudah: VLM cloud 4 dtk, daftar model 5 dtk); antrean
   berbatas, bukan tak terbatas (sudah: antrean log).
4. **Ukur dulu** — tiap langkah di tabel 8.1 baru dikerjakan bila pemicunya terukur (metrics bagian 5.3), sesuai
   §4.1 "jalur panas diukur dulu".
5. **Gerbang tetap jalan saat pusat mati** — semua yang terpusat bersifat sinkron-tunda (outbox), tidak pernah
   memblokir keputusan.

### 8.3 Yang perlu diukur dulu (masuk uji nyata)
- Laju datang pekerja di jam masuk shift sungguhan (orang/menit) vs waktu per inspeksi end-to-end.
- Pemakaian kuota VLM per hari pada pemakaian nyata.
- Biaya simpan audit di perangkat gerbang (T100) dan ringkasan pada 1 tahun data sintetis.
- Biaya VLM berbayar per inspeksi (token gambar + jawaban) → biaya per gerbang per bulan.

### 8.4 GPU vs edge computing — **didiskusikan nanti** (keputusan pengguna 25-10)

Pertanyaan: di skala besar, apakah tiap gerbang harus ber-GPU? Apa yang sebenarnya butuh GPU:

| Beban | Butuh GPU? | Catatan terukur |
| :-- | :-- | :-- |
| YOLO26s-pose (deteksi & posisi) | **Tidak wajib** | CPU laptop 16 thread: server 15–17 FPS (uji 19-10). Perangkat 4–8 inti kemungkinan < 15 FPS → perlu NPU/iGPU |
| FR (YuNet + reid-0095, OpenVINO) | Tidak | Sudah CPU |
| VLM utama & cadangan | Tidak di gerbang | Cloud berbayar |
| **VLM lokal darurat** (`qwen2.5vl:7b`) | **Ya** (±6–7 GB VRAM) | Satu-satunya beban yang memaksa GPU besar; hanya dipakai saat internet putus / cloud gagal |

Pilihan yang dibandingkan nanti (biaya perangkat + listrik + perawatan vs risiko saat internet putus):
- **A. Gerbang tanpa GPU** (PC mini / edge CPU + NPU untuk YOLO), VLM cloud utama & cadangan berbayar, **tanpa VLM
  lokal** → saat internet putus pekerja *menunggu* (sesuai §5: tidak pernah lolos tanpa diperiksa) + SOP manual.
- **B. Edge dengan akselerator** (mis. NVIDIA Jetson Orin, Intel Core Ultra NPU/iGPU + OpenVINO, Hailo) untuk YOLO +
  **VLM lokal kecil** (2–4B, mis. `qwen2.5vl:3b`) — wajib lolos validasi yang sama (`apd_10` helm di rambut lebat,
  `apd_4` sepatu; "APD kurang lolos = 0") sebelum dipakai.
- **C. Satu server GPU per lokasi** dipakai bersama banyak gerbang sebagai VLM darurat (LAN lokal tetap jalan saat
  internet putus); gerbang sendiri tanpa GPU.
- **D. Seperti sekarang** (GPU per gerbang) untuk lokasi dengan internet tidak andal.

Yang perlu disiapkan dari sekarang **tanpa** memilih: struktur kode tidak mengunci ke GPU — `vision/` & `vlm/` memilih
perangkat lewat konfigurasi (sudah: `CUDA_VISIBLE_DEVICES`, VLM lokal opsional), dan MLOps (bagian 7) mencatat
metrik per **perangkat** juga, supaya perbandingan A–D nanti memakai angka, bukan perkiraan.

## 9. Urutan yang saya usulkan (dinilai ulang setelah diskusi)

| # | Tahap | Risiko | Siapa |
| :-- | :-- | :-- | :-- |
| 1 | Sepakati dokumen ini → keputusan di RENCANA | — | semua |
| 2 | `test_architecture.py` (aturan impor) + backend ke paket fitur, pindah-saja (seperti T99d) | Rendah | Codex |
| 3 | Pecah `state_manager` (mesin keadaan murni + orkestrator), didahului tes karakterisasi | Rendah, eksekusi hati-hati (keputusan gerbang) | Codex, tinjau Claude |
| 4 | Frontend ke `features/` + pecah `messages.ts` / `types.ts` | Rendah | Claude |
| 5 | Pengenal korelasi log + `/api/metrics` + pemantauan model di Diagnostik | Sedang (mempercepat diagnosis insiden) | Codex backend, Claude UI |
| 6 | Registri model + manifest dataset + catatan run evaluasi | Sedang (menjaga "APD kurang lolos = 0" tertelusur) | Codex |
| 7 | Antarmuka repositori + alat migrasi (6a–6b) | Rendah–Sedang | Codex |
| 8 | Pembatas laju + penghitung kuota VLM, agregat harian audit (8.1) — bila pemicu terukur | Sedang (kuota habis = pekerja menunggu) | Codex |
| 9 | Outbox + server pusat PG/pgvector (6c–6d), `gate_id` + UUID baris, pembaruan armada | **Tinggi** | setelah keputusan pengguna |

**Fokus sekarang (keputusan 25-10): tahap 1–7 untuk satu gerbang.** Tahap 8 (penghitung biaya/kuota) boleh
dikerjakan bila tagihan VLM berbayar perlu dipantau; tahap 9 (multi-gerbang/PG) ditunda. Uji nyata berisiko Tinggi
(antrean 3/4/4b) **tetap didahulukan** begitu perangkat demo tersedia; tahap di atas mengisi waktu sampai itu.

## 10. Pertanyaan terbuka

Untuk pengguna:
1. ~~Target jumlah gerbang & server pusat~~ → ditunda (fokus satu gerbang, keputusan 25-10).
   Berapa pekerja lewat satu gerbang di jam masuk shift (orang/menit)? (menentukan perlu jalur tambahan atau tidak)
2. Boleh menambah dependensi besar (SQLAlchemy/Alembic, Prometheus client) atau tetap minimal?
3. Foto untuk dataset evaluasi: siap mengurus persetujuan pekerja, atau cukup label + hash?
4. ~~Prioritas~~ → struktur folder + best practice **dan** MLOps (keputusan 25-10). Sisa: mana duluan di antara
   keduanya — usul Claude: tes arsitektur + struktur backend dulu (tahap 2–3), MLOps registri/dataset (tahap 6)
   bisa paralel karena area berkasnya berbeda (`tools/`, `models/`, `datasets/`).

Untuk Codex:
1. Pemetaan 41 modul ke paket di bagian 2 — ada yang salah tempat?
2. Cara memecah `state_manager` tanpa mengubah urutan keputusan & lock?
3. Alembic vs migrasi bernomor sendiri untuk 3 SQLite + PG kelak?
4. Biaya korelasi `contextvars` di thread kamera/VLM (jalur panas)?
5. Pembatas laju & penghitung kuota VLM: di `vlm/` per peran/key, atau lapisan bersama per penyedia?

---

## Tanggapan

<!-- Format: **Nama (tanggal), bagian N:** isi. Jangan menyunting usulan di atas. -->
