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
| T46 — potret setelah pekerja siap | Claude | `claude/t46-ready-capture` | selesai | `backend/readiness.py` (baru), `backend/pose_keypoints.py` (baru), `backend/state_manager.py`, `backend/frame_quality.py`, `backend/config.py`/`messages.py`/`.env.example` (tambah), `tests/test_readiness.py` (baru), `tests/test_lifecycle.py`, `tests/test_frame_quality.py` | Pekerja dipotret hanya setelah utuh + kedua bahu terlihat + diam `READY_HOLD_SECONDS`=1,0 dtk (pergeseran titik tengah/tinggi < `READY_MAX_DRIFT`=5% terhadap awal jendela, bukan antar-frame); frame terbaik dari ≤10 kandidat terakhir jendela. Log baru: "pekerja siap setelah diam X dtk (jendela diulang Nx)". Tanpa perubahan API. Tes: 10 baru (4 gagal pada kode lama). Biaya: 0,015 ms/frame (20 orang), choose_best 3,2 ms sekali per pekerja. **Cara uji nyata:** berjalan masuk tanpa berhenti → tidak dipotret; berdiri diam → dipotret ~1 dtk kemudian; menyamping → menunggu. Terbuka: belum ada suara "hadap kamera" Ditinjau Gemini tanpa temuan; **uji nyata 06-10 lolos** (jalan lewat tidak dipotret; dipotret 1,0–1,1 dtk setelah diam; jendela diulang 2–9x saat melangkah, tidak macet; kamera C920). Digabung 06-10 |
| Hapus UI lama (`frontend/`, `/legacy/`) + T18 (XSS) | Gemini | `gemini/remove-legacy-ui` | selesai | `frontend/` (hapus), `backend/app.py` (bagian `/legacy` saja), `web/src/pages/NotYetMigrated.svelte`, `web/src/lib/settings.ts` & `format.ts` (hanya rujukan legacy), `tests/test_frontend_serving.py`, `tests/conftest.py`, `tests/test_storage.py` (hanya rujukan legacy), `README.md` & `docs/*.md` (hanya rujukan legacy) | Diklaim 05-10. Tidak beririsan dengan T46. `docs/RENCANA.md` (papan) tetap ditulis integrator; Gemini cukup menulis catatan di laporan. Tes wajib: `GET /legacy/` & `/legacy/index.html` → 404 Commit `39f5c1e` diverifikasi Claude 05-10 (pytest 259 & ruff di salinan terpisah). **Temuan:** pemetaan `legacyGemini` di `web/src/lib/format.ts` + tesnya ikut dihapus padahal untuk DATA audit lama (10 baris `GEMINI_LIVE`, 23–24 Sep) → wajib dikembalikan. Penghapusan pengalihan `/app` di luar lingkup tetapi tidak dirujuk lagi (diterima) Perbaikan `legacyGemini` (`701d096`) terverifikasi (vitest 75); digabung 06-10 (`e7c7d89`), T18 tertutup. |
| T47 — IoT lampu demo (ESP32, merah/kuning/hijau) | Claude | `claude/t47-iot-lights` | selesai | `iot/esp32_gate_controller/`, `iot/wokwi_simulation/` (diagram, toml; `sketch.ino` dihapus), `iot/arduino_gate_controller/` (dihapus), `iot/test_serial_lights.py`, `IOT_HARDWARE_SPEC.md`, `backend/notifier.py`, `backend/api/routes_system.py`, `backend/api/websocket.py`, `backend/config.py`/`messages.py`/`.env.example`, `tests/test_notifier.py` (baru), `tests/test_lifecycle.py`, `tests/test_import_side_effects.py`, `docs/ARSITEKTUR.md`, `.gitignore` | Firmware: heartbeat 3 dtk → kuning berkedip, mulai dari kuning berkedip (tanpa self-test hijau), buffer 32 karakter, balasan OK/ERR; lolos kompilasi toolchain ESP8266 terpasang (ESP32 belum terpasang di mesin ini). Backend: port dibuka tanpa reset (DTR/RTS), heartbeat 1 dtk, sambung ulang 2 dtk, status `iot` di telemetri, gangguan sistem = `YELLOW`, uji lampu 400/409; HTTP dibuang. Tes 16 baru (mutasi DTR & heartbeat tertangkap). **Belum:** uji papan nyata (barang belum datang); UI (Gemini) menunggu persetujuan kontrak; `iot/wokwi_simulation/README.md` (dilarang disunting) masih menyebut Uno & sketch lama Ditinjau Gemini tanpa temuan; backend digabung 06-10 (IoT bawaan mati) untuk membuka T45. **Uji fisik ESP32 menunggu perangkat** |
| T47-UI — lampu kuning & status lampu gerbang di UI | Gemini | `gemini/t47-iot-ui` | tinjau | `web/src/lib/api/types.ts`, `web/src/lib/api/client.ts`, `web/src/lib/messages.ts`, `web/src/lib/settings.ts` (tambah), `web/src/lib/status.ts` + tesnya (chip lampu, di samping `cameraChip`), `web/src/components/TopBar.svelte`, `web/src/pages/Pengaturan.svelte` | Mulai setelah tugas Gemini "Hapus UI lama" selesai (satu agen satu task). Ikuti kontrak T47 di atas. Uji langsung setelah `claude/t47-iot-lights` digabung; sebelum itu cukup vitest dengan telemetri tiruan — `0fa9b0a` (dari claude/t47-iot-lights): check.py lolos (vitest 75). **Temuan:** (1) chip lampu terputus bernada `danger` (MERAH) — kontrak & §5: kuning/warn; (2) tanpa vitest `iotChip` (4 keadaan); (3) status lampu gerbang belum tampil di Pengaturan (kontrak). Rebase ke master sebelum digabung. |
| T30 — login + lindungi data baca (backend) | Claude | `claude/t30-login` | dikerjakan | `backend/auth.py` (baru), `backend/api/routes_auth.py` (baru), `backend/api/deps.py`, `backend/api/websocket.py` (cek sesi), `backend/app.py` (**hanya** tupel pendaftaran router, baris ~130; Gemini menyunting bagian `/legacy` di bawahnya — hunk berbeda), `backend/config.py`/`messages.py`/`.env.example` (tambah), `tests/test_auth.py` (baru) | Diklaim 05-10. Demo: admin saja, kata sandi = `ADMIN_TOKEN`. UI login (Gemini) setelah T47-UI, ikut kontrak di bawah |
| T39b — profil penyedia VLM + daftar model tervalidasi | Claude | `claude/t39b-provider-profiles` | selesai | `backend/vlm_providers/profiles.py` (baru), `vlm_providers/__init__.py`, `openai_compatible.py`, `backend/vlm_analyzer.py`, `backend/config.py` (bagian VLM), `backend/messages.py` (tambah), `backend/.env.example` (bagian VLM), `tests/test_vlm_profiles.py` (baru) | Katalog profil = satu sumber (alamat/model bawaan, lokal, mode berpikir, lokasi data); `VLM_THINKING` umum (off=Gemini minimal, nama lama dibaca); daftar validasi: ollama qwen2.5vl:7b tervalidasi, gemini parsial (10 foto), qwen2.5vl:3b TIDAK AMAN; peringatan log untuk eksperimental/belum tervalidasi/kedaluwarsa/tidak aman; `PROMPT_VERSION` + tes sidik jari prompt (prompt berubah tanpa naik versi = gagal). Konfigurasi sekarang tidak berubah perilaku (Gemini tetap MINIMAL). Tes 14 baru. **Terbuka:** uji 84 foto Gemini (perlu izin kuota ~84 panggilan) |
| T48 — longgarkan aturan helm & sepatu (yang penting APD dipakai) | Claude | `claude/t48-relax-helmet-shoes` | tinjau | `backend/ppe_rules.py` (teks helm & sepatu), `backend/messages.py` (`PROMPT_VERSION`=T48), `backend/vlm_providers/profiles.py`, `backend/vlm_analyzer.py` (find_validation), `tests/test_vlm_profiles.py` | Ditumpuk di atas T39b (gabung T39b dulu). Hasil: Gemini T48 12/12 benar, 0 lolos (10 foto kurang helm/sepatu); Ollama sepatu apd_4 0/3 → 2/4 benar, helm apd_10 tetap salah (→ T40); Ollama 10 foto 0 lolos. Usulan diterima pengguna: gabung |
| T49 — ringkasan laporan harian/mingguan/bulanan (backend) | Claude | `claude/t49-report-summary` | selesai | `backend/report_summary.py` (baru, logika murni), `backend/report_manager.py` (indeks `date_str`, `_range_clause`, `get_summary`), `backend/api/routes_reports.py`, `backend/messages.py` (tambah), `tests/test_report_summary.py` (baru) | Sesuai kontrak T49. Tes 12 baru (termasuk EXPLAIN QUERY PLAN memakai `idx_date_str`). 100 rb baris: ringkasan harian 12 ms, mingguan 9 ms, bulanan 31 ms; tabel 1 bulan 12 ms; CSV 1 bulan 72 ms. Indeks dibuat otomatis saat server membuka DB. Ditinjau Gemini 05-10 tanpa temuan; digabung 05-10. Menunggu T49-UI (Gemini) |
| T49-UI — pemilih periode & grafik laporan | Gemini | `gemini/t49-report-ui` | selesai | `web/src/pages/Laporan.svelte`, `web/src/lib/api/types.ts` & `client.ts`, `web/src/lib/reports.ts` (+ tes), `web/src/components/reports/` (komponen baru), `web/src/lib/messages.ts` & `settings.ts` (tambah) | Diklaim 05-10 lewat pengguna. Mulai setelah perbaikan `legacyGemini` di branch hapus UI lama. Ikut kontrak T49; tanpa pustaka grafik baru Commit `f8a8027`: check.py lolos (diverifikasi Claude 06-10). **Temuan:** (1) periode tanpa data → nada meter MERAH (complianceTone(null ?? 0)) — melanggar §5; (2) pesan kosong tak pernah tampil (buckets selalu berisi 24/7/31 bucket nol) — pakai totals.total === 0; (3) logika (geser tanggal, skala) di komponen tanpa vitest & angka 16/24/40/150/600 tertulis langsung — pindah ke lib/reports.ts + settings.ts (§4); (4) pemilih tanggal dihapus — tambah input tanggal di PeriodSelector agar bisa lompat ke tanggal tertentu. — **06-10** perbaikan `d5e2047` diverifikasi (pytest 271, vitest 78, svelte-check 0): temuan 1, 3, 4 beres; sisa: grafik batang masih `buckets.length === 0` (harus `totals.total === 0`), teks `title` & `padding` px tertulis langsung, `calculateYAxis` belum dites — Sisa temuan beres (`86650c9`, vitest 79); digabung 06-10 (`a2574db`) + web/dist. |
| T45 — ketangguhan kamera (terputus, tertutup, membeku) | Claude | `claude/t45-camera-health` | dikerjakan | `backend/camera_health.py` (baru, murni), `backend/video/capture.py` (`_capture_loop` + `get_camera_status` saja), `backend/state_manager.py` (`set_camera_fault`, telemetri), `backend/config.py`/`messages.py`/`.env.example` (tambah), `backend/audio/gangguan_kamera.mp3` (baru), `tests/test_camera_health.py` (baru) | Diklaim 06-10. Keputusan pengguna: gangguan kamera = **kuning menyala tetap**, suara **sekali** saat gangguan mulai. UI (Gemini) ikut kontrak di bawah setelah T47-UI |
| T28 — penyedia VLM dari dashboard (bagian backend) | — | — | antre | `backend/vlm_analyzer.py`, `backend/api/routes_vlm.py`, `backend/runtime_settings.py`, `tests/` | Setelah T36 (sama-sama menyentuh `vlm_analyzer.py`). Kontrak API ditulis di sini dulu |

### Kontrak API T45 — gangguan kamera (06-10)

- Telemetri `camera.status` bertambah nilai **`"BLOCKED"`**: kamera tersambung tetapi gambar terlalu gelap, terlalu terang, atau
  seragam (lensa tertutup/kotor) selama ≥ `CAMERA_BLOCKED_SECONDS`. Gambar **membeku** (frame identik ≥ `CAMERA_FROZEN_SECONDS`)
  ditangani seperti terputus: `status` `"LOST"`, `error` berisi pesan "gambar membeku", kamera disambung ulang otomatis.
- Telemetri baru **`camera_fault`** (tingkat atas): `null` | `"lost"` | `"blocked"` | `"frozen"` — selama tidak null, gerbang
  tidak memeriksa siapa pun: sesi & keputusan dibatalkan, `light.light_state` = `"YELLOW"` (menyala tetap) dengan pesan gangguan
  kamera, suara gangguan diputar **sekali** saat mulai. Pulih → `null`, lampu padam (siaga).
- UI (Gemini, setelah T47-UI): chip & layar video untuk `BLOCKED` ("Kamera tertutup / terlalu gelap"), panel keputusan
  menampilkan gangguan kamera (kuning, bukan merah), tanpa nama perangkat baru di tampilan operator.

### Kontrak API T49 — ringkasan laporan (disetujui 05-10)

Tanggal = waktu lokal server (`YYYY-MM-DD`). Minggu = Senin–Minggu.

- `GET /api/reports/summary?period=day|week|month&date=YYYY-MM-DD` (`date` kosong = hari ini) →
  `{"period": str, "range": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
    "totals": {"total": int, "passed": int, "rejected": int, "compliance_rate": number | null},
    "buckets": [{"start": str, "label": str, "passed": int, "rejected": int}],
    "missing_items": [{"key": str | null, "label": str, "count": int}]}`
  — `buckets` lengkap termasuk yang nol: harian 24 jam (`start` "HH:00", `label` "07"), mingguan 7 hari dan bulanan
  semua tanggal (`start` "YYYY-MM-DD", `label` "Sen"/"1"); `missing_items` urut terbanyak; `compliance_rate` null bila total 0.
  400 `{"detail"}` untuk `period`/`date` tidak sah.
- `GET /api/reports` dan `GET /api/reports/export` menerima `from` & `to` (`YYYY-MM-DD`, inklusif); `date` lama tetap jalan.
  Ekspor CSV hanya berisi rentang itu; nama berkas memuat rentangnya.
- Grafik UI: batang bertumpuk lolos (hijau) / APD kurang (merah) per bucket + batang mendatar `missing_items` dengan angka
  di ujung batang. Kartu, grafik, tabel, dan CSV memakai rentang yang sama; ◀ ▶ pindah periode.

### Kontrak API T30 — login admin (disetujui 05-10)

Berlaku bila `ADMIN_TOKEN` terisi. Tanpa `ADMIN_TOKEN` (hanya `HOST=127.0.0.1` / `ALLOW_INSECURE_DEMO`) semua terbuka seperti sebelumnya.

- `POST /api/login` `{"password": string}` → 200 `{"expires_in_s": number}` + cookie sesi `HttpOnly; SameSite=Strict; Path=/`;
  401 `{"detail"}` salah; 429 `{"detail", "retry_after_s"}` setelah 5 gagal (jeda 60 dtk, per alamat klien).
- `POST /api/logout` → 204, cookie dihapus.
- `GET /api/session` (bebas login) → 200 `{"authenticated": bool, "auth_required": bool, "expires_in_s": number | null}`.
- Semua `/api/*` lain (termasuk `/api/stream`, foto bukti, CSV, `/api/health`) → **401** tanpa sesi sah; `/ws` diterima lalu
  ditutup dengan kode **4401**. Header `X-Admin-Token` lama tetap diterima (alat/skrip).
- Sesi 8 jam (`SESSION_HOURS`), disimpan di memori server: server dinyalakan ulang = login ulang.
- UI (Gemini): halaman login (menggantikan dialog token admin), tombol keluar, 401/4401 → halaman login, 429 → tampilkan sisa detik.

### Kontrak API T47 — lampu kuning & status IoT (disetujui 05-10)

- Telemetri `light.light_state`: `"OFF" | "GREEN" | "RED" | "YELLOW"`. `YELLOW` = sistem gangguan / pekerja diminta menunggu
  (sebelumnya `OFF`). Merah tetap khusus APD kurang. Gangguan kamera (T45) dan arahan posisi memakai `YELLOW` setelah T46 digabung.
- Telemetri baru `iot` (selalu ada):
  `{"enabled": bool, "connected": bool, "last_ack_age_s": number | null, "error": string | null}`
  — `connected` = balasan `OK` dari papan diterima dalam `IOT_ACK_TIMEOUT_SECONDS`; `error` = teks Indonesia dari `messages.py`.
- `POST /api/iot/test` (token admin), body `{"action": "green" | "red" | "yellow" | "off"}`
  → 200 `{"status": "success", "action": string, "light_state": LightState}`;
  **409** `{"detail"}` bila ada pekerja di jalur (sesi berjalan) supaya lampu uji tidak terlihat pekerja sungguhan;
  400 `{"detail"}` untuk `action` lain (sebelumnya diam-diam dianggap `off`).
- UI (Gemini): chip/baris status "Lampu gerbang: tersambung / terputus / nonaktif" di Pengaturan & TopBar, tombol uji
  **Kuning**, tampilkan pesan 409. Nama port tidak ditampilkan ke operator.

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
| 3 | **Tinggi** | **T47 — IoT lampu demo (ESP32, merah/kuning/hijau)** (analisa 05-10) | Spesifikasi lama salah & berbahaya: server crash saat hijau → hijau bertahan ≤15 dtk (tanpa heartbeat); self-test menyalakan HIJAU tiap boot, dan membuka port serial me-reset ESP32 (DTR/RTS) → hijau berkedip tiap server start; pull-down 10k pada relay Active-LOW menyalakan relay saat boot; relay 5V dari GPIO 3,3V bisa tak padam; tanpa sambung ulang & tanpa status IoT di UI; belum ada kuning; mode HTTP tanpa autentikasi (GET, CSRF, mDNS palsu) dan firmware-nya tidak ada. Isi: ESP32 **USB serial saja**, heartbeat ~1 dtk + balasan `OK`, firmware kuning berkedip bila heartbeat hilang ~3 dtk, self-test kuning, buka port tanpa reset, sambung ulang otomatis, status IoT di telemetri (kontrak dulu), uji lampu ditolak saat sesi berjalan, buffer perintah dibatasi, spesifikasi ditulis ulang. **Memblokir T45** (gangguan kamera = kuning) |
| 4 | **Tinggi** | **T45 — ketangguhan kamera** (usulan 28-09) | Kamera **terhalang** (lensa tertutup/gelap/seragam) tetap berstatus OK → gerbang mati diam-diam; gambar **membeku** (frame identik, laju tampak normal) → dugaan dari kode: sesi tak pernah kosong sehingga lampu hijau bisa tetap menyala untuk pekerja berikutnya (dibuktikan dulu dengan tes). Isi: deteksi terhalang (kecerahan/keseragaman/tepi, bertahan > N dtk) & beku (selisih antar-frame nol > N dtk → sambung ulang); saat kamera bermasalah sesi & keputusan dibatalkan, lampu kuning + suara tunggu (bukan merah); status `BLOCKED`/`FROZEN` di telemetri (kontrak API ditulis dulu, UI oleh Gemini) & log. Ambang dari data uji nyata (tutup lensa ~10 dtk, cabut saat hijau, penutup privasi). Gangguan kamera = **kuning** (keputusan 05-10, lewat lampu T47); belum diputuskan: kuning berkedip/tetap, suara sekali/berulang |
| 5 | **Tinggi** | **T30 — login + lindungi data baca** | Foto bukti (wajah), video langsung, dan CSV terbuka tanpa token di jaringan → kebocoran data pribadi |
| 6 | **Tinggi** | **Hapus UI lama (`frontend/`, `/legacy/`) + T18** | UI lama masih disajikan dan punya jalur XSS; dihapus setelah T33 digabung |
| 7 | Sedang | T29 — operasi otomatis + Docker | Gerbang belum menyala sendiri setelah listrik padam (risiko naik jadi Tinggi saat produksi) |
| 8 | Sedang | T39b — profil penyedia VLM (sisa T39) | Salah konfigurasi penyedia/mode berpikir; `.env.example` netral |
| 9 | Sedang | **T40 — alternatif mesin VLM lokal** (keputusan setelah uji nyata) | Crash `encoding image` berasal dari llama.cpp (llama.cpp#17422, #17881; ollama#14170), jadi mengganti Ollama dengan llama.cpp langsung kemungkinan tidak menghilangkannya. Bila uji nyata menunjukkan cadangan masih sering bermasalah walau ada penjaga T38: uji coba Qwen2.5-VL 4-bit lewat Transformers (PyTorch) di **proses terpisah** berantarmuka OpenAI-compatible (adaptor sudah mendukung, cukup ganti `.env`), diukur dengan `tools/bench_vlm.py` (akurasi, 0 APD kurang lolos, waktu, VRAM bersama YOLO). vLLM ditinjau untuk produksi Linux/GPU besar (T29). Data sejauh ini: ~2–4 crash per 84 foto. Kriteria tambahan (T48, 05-10): `qwen2.5vl:7b` tidak melihat helm di atas rambut lebat (`apd_10`, salah 4/4; Gemini benar) dan sepatu `apd_4` hanya benar 2/4 — model pengganti harus lolos keduanya |
| 10 | Sedang | Helm di atas rambut lebat (`apd_10`), sepatu tertutup (`apd_4`) | Pekerja patuh salah ditolak (2/26 foto) |
| 11 | Sedang | **T41 — satu sumber indeks pose COCO + rasio `detector` ke config** (audit 28-09) | Indeks 5/6/13–16 ditulis ulang di `detector.py`, `frame_quality.py`, `zone.py`; bila satu berubah yang lain tertinggal → salah menilai tubuh utuh/titik berdiri. Rasio 0.20/0.12/0.15/0.65/0.05/0.08 di `detector.py` ke `config.py` |
| 12 | Rendah | T28 — penyedia VLM dari dashboard | Kenyamanan admin; bisa lewat `.env` |
| 13 | Rendah | Dua orang berdampingan di zona (T36d); T25 sisa latensi | Dicegah batas fisik di lokasi; latensi sudah jauh turun |
| 14 | Rendah | T42 — cicil utang kode (audit 28-09) | 24 fungsi > 30 baris (terpanjang `capture._reader_loop` 199, `detector.detect_and_track` 164, `state_manager.update_frame_detections` 101) — daftar di `tests/test_code_hygiene.py`; 8 blok kembar (web: dialog CameraPicker/SnapshotDialog/AdminToken, ZoneSettings/Pengaturan); pesan log di luar `messages.py` (`camera_manager`, `detector`, `audio_engine`, `capture`); angka HUD/resolusi ke config; warna `#000` VideoPanel ke token; nama Indonesia → Inggris saat disentuh |
| 15 | Rendah | T43 — laporan skala besar (audit 28-09) | 100 rb baris: halaman 17 ms, filter tanggal 20 ms (belum ada indeks `date_str`), ekspor CSV 700 ms / 16,8 MB di RAM → indeks `date_str` + ekspor bertahap (streaming) |
| 16 | Rendah | T44 — formatter & linter web (audit 28-09) | `ruff format` massal (62 berkas) sebagai commit sendiri; eslint + prettier untuk `web/` (mengubah `web/package*.json`, perlu giliran dependensi) |

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

- VRAM puncak 7,6 / 8 GB dengan `qwen2.5vl:7b` + YOLO — risiko OOM bila ada beban GPU lain.
- Ollama kadang crash pada gambar tertentu (ollama/ollama#14170); inspeksi itu jatuh ke jalur gangguan dan diulang.
- Build `web/dist` kini identik antar folder/worktree (akhir baris `web/` dikunci LF lewat `.gitattributes`); kesamaan di Linux CI belum dibuktikan langsung (repo belum punya remote).
- Repo belum punya remote git, jadi CI belum pernah berjalan.
- Monitoring di lebar ~360 px: satu tombol panel video melewati tepi kanan (terpotong, tanpa scroll horizontal) — rapikan di T33 langkah 3.
- Data baca (foto bukti, CSV, riwayat, video langsung) masih terbuka tanpa token di jaringan — ditutup oleh login T30.
