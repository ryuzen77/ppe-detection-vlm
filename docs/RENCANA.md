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
| T47-UI — lampu kuning & status lampu gerbang di UI | Gemini | `gemini/t47-iot-ui` | selesai | `web/src/lib/api/types.ts`, `web/src/lib/api/client.ts`, `web/src/lib/messages.ts`, `web/src/lib/settings.ts` (tambah), `web/src/lib/status.ts` + tesnya (chip lampu, di samping `cameraChip`), `web/src/components/TopBar.svelte`, `web/src/pages/Pengaturan.svelte` | Mulai setelah tugas Gemini "Hapus UI lama" selesai (satu agen satu task). Ikuti kontrak T47 di atas. Uji langsung setelah `claude/t47-iot-lights` digabung; sebelum itu cukup vitest dengan telemetri tiruan — `0fa9b0a` (dari claude/t47-iot-lights): check.py lolos (vitest 75). **Temuan:** (1) chip lampu terputus bernada `danger` (MERAH) — kontrak & §5: kuning/warn; (2) tanpa vitest `iotChip` (4 keadaan); (3) status lampu gerbang belum tampil di Pengaturan (kontrak). Rebase ke master sebelum digabung. — **06-10 lanjutan:** T45-UI ikut di branch ini (`4bb01a3`: tipe BLOCKED/camera_fault + teks; panel keputusan kuning lewat logika gate.ts yang ada — benar). Temuan T47-UI 1–3 BELUM diperbaiki; tambahan: chip kamera `LOST` merah (sisa lama) → warn; `camera_fault` diketik `string` → union `'lost'|'blocked'|'frozen'|null` — **Digabung 06-10** (`017c403`, vitest 80): chip lampu terputus kuning, tes iotChip, status di Pengaturan, T45-UI ikut. Tindak lanjut kecil (chip kamera `LOST` kuning, `camera_fault` union) **selesai** (`cacad01`, digabung 06-10) |
| T30 — login + lindungi data baca (backend) | Claude | `claude/t30-login` | selesai | `backend/auth.py` (baru), `backend/api/routes_auth.py` (baru), `backend/api/deps.py`, `backend/api/websocket.py`, `backend/app.py` (impor + tupel router saja), `backend/config.py`/`messages.py`/`.env.example` (tambah), `docs/INSTALASI.md`, `tests/test_auth.py` (baru) | Sesi cookie HttpOnly/SameSite=Strict di memori, 8 jam; batas 5 gagal → 60 dtk per alamat; `require_admin` = `require_session` (satu peran); perlindungan dipasang di tingkat router sehingga endpoint baru otomatis terkunci; `/ws` ditutup 4401. Tes 35 (penjaga semua 23 rute `/api` dari OpenAPI; mutasi tanpa perlindungan → 17 gagal). **JANGAN digabung sebelum UI login (Gemini) siap**: dengan `ADMIN_TOKEN` terisi, UI sekarang tidak bisa memuat video/foto/telemetri tanpa login — gabung bersamaan dengan UI login — UI login Gemini (`gemini/t30-login-ui`): temuan 06-10 (4401 tak tersambung, stop tak mengosongkan data, telemetri tak menyala saat muat ulang) beres di `98374e8` & `87d89f0`; check.py lolos; uji nyata port 8002: tanpa login, login + muat ulang, sesi hilang → login (1x sambung), WS tanpa cookie → 4401. Digabung 06-10 (backend + UI bersamaan) |
| T39b — profil penyedia VLM + daftar model tervalidasi | Claude | `claude/t39b-provider-profiles` | selesai | `backend/vlm_providers/profiles.py` (baru), `vlm_providers/__init__.py`, `openai_compatible.py`, `backend/vlm_analyzer.py`, `backend/config.py` (bagian VLM), `backend/messages.py` (tambah), `backend/.env.example` (bagian VLM), `tests/test_vlm_profiles.py` (baru) | Katalog profil = satu sumber (alamat/model bawaan, lokal, mode berpikir, lokasi data); `VLM_THINKING` umum (off=Gemini minimal, nama lama dibaca); daftar validasi: ollama qwen2.5vl:7b tervalidasi, gemini parsial (10 foto), qwen2.5vl:3b TIDAK AMAN; peringatan log untuk eksperimental/belum tervalidasi/kedaluwarsa/tidak aman; `PROMPT_VERSION` + tes sidik jari prompt (prompt berubah tanpa naik versi = gagal). Konfigurasi sekarang tidak berubah perilaku (Gemini tetap MINIMAL). Tes 14 baru. **Terbuka:** uji 84 foto Gemini (perlu izin kuota ~84 panggilan) |
| T48 — longgarkan aturan helm & sepatu (yang penting APD dipakai) | Claude | `claude/t48-relax-helmet-shoes` | selesai | `backend/ppe_rules.py` (teks helm & sepatu), `backend/messages.py` (`PROMPT_VERSION`=T48), `backend/vlm_providers/profiles.py`, `backend/vlm_analyzer.py` (find_validation), `tests/test_vlm_profiles.py` | Ditumpuk di atas T39b (gabung T39b dulu). Hasil: Gemini T48 12/12 benar, 0 lolos (10 foto kurang helm/sepatu); Ollama sepatu apd_4 0/3 → 2/4 benar, helm apd_10 tetap salah (→ T40); Ollama 10 foto 0 lolos. Usulan diterima pengguna: gabung Digabung 14-10 (`bb0ad12`). |
| T49 — ringkasan laporan harian/mingguan/bulanan (backend) | Claude | `claude/t49-report-summary` | selesai | `backend/report_summary.py` (baru, logika murni), `backend/report_manager.py` (indeks `date_str`, `_range_clause`, `get_summary`), `backend/api/routes_reports.py`, `backend/messages.py` (tambah), `tests/test_report_summary.py` (baru) | Sesuai kontrak T49. Tes 12 baru (termasuk EXPLAIN QUERY PLAN memakai `idx_date_str`). 100 rb baris: ringkasan harian 12 ms, mingguan 9 ms, bulanan 31 ms; tabel 1 bulan 12 ms; CSV 1 bulan 72 ms. Indeks dibuat otomatis saat server membuka DB. Ditinjau Gemini 05-10 tanpa temuan; digabung 05-10. Menunggu T49-UI (Gemini) |
| T49-UI — pemilih periode & grafik laporan | Gemini | `gemini/t49-report-ui` | selesai | `web/src/pages/Laporan.svelte`, `web/src/lib/api/types.ts` & `client.ts`, `web/src/lib/reports.ts` (+ tes), `web/src/components/reports/` (komponen baru), `web/src/lib/messages.ts` & `settings.ts` (tambah) | Diklaim 05-10 lewat pengguna. Mulai setelah perbaikan `legacyGemini` di branch hapus UI lama. Ikut kontrak T49; tanpa pustaka grafik baru Commit `f8a8027`: check.py lolos (diverifikasi Claude 06-10). **Temuan:** (1) periode tanpa data → nada meter MERAH (complianceTone(null ?? 0)) — melanggar §5; (2) pesan kosong tak pernah tampil (buckets selalu berisi 24/7/31 bucket nol) — pakai totals.total === 0; (3) logika (geser tanggal, skala) di komponen tanpa vitest & angka 16/24/40/150/600 tertulis langsung — pindah ke lib/reports.ts + settings.ts (§4); (4) pemilih tanggal dihapus — tambah input tanggal di PeriodSelector agar bisa lompat ke tanggal tertentu. — **06-10** perbaikan `d5e2047` diverifikasi (pytest 271, vitest 78, svelte-check 0): temuan 1, 3, 4 beres; sisa: grafik batang masih `buckets.length === 0` (harus `totals.total === 0`), teks `title` & `padding` px tertulis langsung, `calculateYAxis` belum dites — Sisa temuan beres (`86650c9`, vitest 79); digabung 06-10 (`a2574db`) + web/dist. |
| T45 — ketangguhan kamera (terputus, tertutup, membeku) | Claude | `claude/t45-camera-health` | selesai | `backend/camera_health.py` (baru, murni), `backend/video/capture.py` (`_capture_loop` + `get_camera_status` saja), `backend/state_manager.py` (`set_camera_fault`, telemetri), `backend/config.py`/`messages.py`/`.env.example` (tambah), `backend/audio/gangguan_kamera.mp3` (baru), `tests/test_camera_health.py` (baru) | Diklaim 06-10. Keputusan pengguna: gangguan kamera = **kuning menyala tetap**, suara **sekali** saat gangguan mulai. UI (Gemini) ikut kontrak di bawah setelah T47-UI — Selesai di branch: `camera_health.py` (tertutup = gelap/terang/seragam ≥3 dtk; membeku = cuplikan tanpa rata-rata identik ≥3 dtk → sambung ulang lewat jalur perangkat hilang dengan alasan "membeku"); `state_mgr.set_camera_fault` batalkan sesi (termasuk hijau), kuning tetap, suara `gangguan_kamera` sekali; telemetri `camera.status` BLOCKED & `camera_fault`. Tes 17 (mutasi batal sesi & kuning tertangkap); biaya 0,33 ms/frame. **Belum:** uji fisik (tutup lensa, cabut saat hijau) & UI (Gemini) Ditinjau Gemini 06-10 tanpa temuan; digabung 06-10. **Uji fisik menunggu** |
| T45b — perbaikan T45 dari uji fisik 06-10 | Claude | `claude/t45b-camera-fix` | selesai | `backend/camera_health.py`, `backend/state_manager.py` (`set_camera_fault`, `reset_all`), `backend/video/capture.py` (`_camera_fault`, log sambung ulang), `backend/config.py`/`.env.example`, `tests/test_camera_health.py` | Uji fisik 06-10 (kamera laptop): lensa tertutup = hitam pekat tanpa derau → dianggap MEMBEKU → buka ulang kamera → reset gerbang → gangguan 'selesai' & suara diulang tiap ±7 dtk (8x dalam 1 menit). Isi: membeku hanya bila gambar berdetail; sambung ulang tidak menghapus gangguan; suara tidak diulang <30 dtk; reaksi tertutup 3 → 1,5 dtk (keluhan pengguna: terlalu lama) — Selesai di branch. Tes 22 (5 regresi baru; pada kode lama gagal/error). **Uji fisik ulang** diperlukan: tutup lensa 10 dtk (kuning ±1,5 dtk, suara sekali, tanpa buka-ulang kamera), cabut saat hijau — **Uji fisik ke-2 (15:12–15:16):** tertutup benar (tanpa putaran membeku); cabut tanpa suara karena penahan 30 dtk global → kini suara **terputus** & **terhalang** dibedakan, penahan per jenis; colok ulang ke-2 tak muncul ±1 menit = Windows belum memunculkan C920 (uji pembeda: daftar thread sama = thread baru) → log "masih menunggu" tiap 10 dtk + petunjuk port USB di layar. Tes 25 — **Uji fisik ke-3 15:28–15:30 lolos** (tertutup, cabut setelah tertutup → suara terputus, colok ulang 3x: 11/32/11 dtk dengan log menunggu). Digabung 06-10 atas keputusan pengguna sebelum tinjauan Gemini (tinjauan menyusul). Belum teruji fisik: cabut saat lampu hijau (dijaga tes otomatis) |
| T41 — satu sumber indeks pose COCO + rasio detector ke config | Claude | `claude/t41-pose-single-source` | selesai | `backend/detector.py`, `backend/zone.py`, `backend/pose_keypoints.py`, `backend/config.py` (tambah), `tests/` (penjaga baru) | Diklaim 06-10. Refaktor tanpa mengubah perilaku: indeks titik pose hanya di `pose_keypoints.py`, rasio geometri kepala/crop ke config — Selesai: indeks hanya di `pose_keypoints.py` (+ `X, Y`), `zone.LEFT/RIGHT_ANKLE` dihapus, 6 rasio ke config. Tes karakterisasi baru `test_detector_fullbody.py` (400 kasus, acuan dibangkitkan dari kode `master` sebelum refaktor → identik; mutasi rasio helm & margin crop tertangkap) + penjaga indeks di `test_code_hygiene.py` Digabung 06-10 atas keputusan pengguna (perilaku terbukti identik); tinjauan Gemini menyusul |
| T29 — gerbang berjalan sendiri (demo Windows) | Claude | `claude/t29-autostart` | selesai | `backend/supervisor.py` (baru), `backend/startup_checks.py` (baru), `backend/video/capture.py` (autostart kamera), `backend/runtime.py`, `backend/api/routes_system.py` (health), `backend/config.py`/`messages.py`/`.env.example` (tambah), `deploy/windows/` (baru), `docs/INSTALASI.md`, `tests/` | Diklaim 06-10. Keputusan pengguna: menyala saat login + bangkit ulang bila crash; kamera otomatis HANYA lewat nama (`CAMERA_NAME`/pilihan terakhir), bila belum ada → menunggu (kuning), tanpa cadangan indeks 0; pemeriksaan kesehatan saat menyala; tanpa kios; Docker ditunda. T40 ditunda (keputusan 06-10) — Selesai di branch: penjaga proses `backend.supervisor` (dipakai start_system.bat), kamera otomatis lewat nama tanpa cadangan indeks 0, pemeriksaan start (CUDA, versi Ollama, kamera) di log & /api/health, skrip pintasan Startup Windows. Tes 11 (mutasi cadangan indeks 0 tertangkap). Smoke test nyata: server dibunuh paksa → hidup lagi; kamera tak ada → menunggu kuning. **Belum:** uji restart PC sungguhan oleh pengguna Digabung 06-10 (tinjauan Gemini menyusul). Demo: `CAMERA_NAME` dikosongkan — kamera dipilih operator di lokasi sekali (daftar persiapan demo di docs/INSTALASI.md) |
| T43 — ekspor CSV bertahap | Claude | `claude/t43-csv-stream` | selesai | `backend/report_manager.py` (ekspor), `backend/api/routes_reports.py` (ekspor), `tests/test_report_summary.py` | Diklaim 06-10. Indeks tanggal sudah beres (T49/T49b); sisa: CSV dikirim per potongan, tidak dibangun utuh di RAM — Selesai di branch: `iter_csv_chunks` (500 baris/potongan) + StreamingResponse. Isi CSV identik byte-per-byte dengan kode lama (1.203 baris dengan koma/kutip/baris baru). 100 rb baris: puncak memori 30,9 → 0,6 MB, waktu sama (±1,9 dtk). Tes 2 baru Digabung 06-10 (tinjauan Gemini menyusul) |
| T42a — pecah `detector.detect_and_track` (cicilan utang kode) | Claude | `claude/t42a-detector-split` | selesai | `backend/detector.py`, `tests/test_code_hygiene.py` (daftar utang) | Diklaim 06-10. Perilaku dijaga tes karakterisasi T41 (400 kasus) — wajib identik — Selesai: 164 baris → `detect_and_track` + `_track` + 9 fungsi murni ≤30 baris (`FrameMargins`, `_head_clipped`, `_feet_status`, `_full_body_status`, `_crop_for_vlm`, …); keluar dari daftar utang. Tes karakterisasi 400 kasus identik; mutasi urutan kepala/kaki tertangkap. Biaya logika 20 orang 0,24 → 0,27 ms/frame (YOLO ±5–7 ms) Digabung 06-10 (tinjauan Gemini menyusul) |
| T42b — pecah `state_manager.update_frame_detections` (cicilan utang kode) | Claude | `claude/t42b-state-split` | selesai | `backend/state_manager.py`, `tests/test_state_characterization.py` (baru) + acuan, `tests/test_code_hygiene.py` (daftar utang) | Diklaim 06-10. Tes karakterisasi dibuat & acuannya direkam dari kode sekarang SEBELUM refaktor — Selesai: ±100 baris → 9 langkah bernama ≤30 baris (`_people_in_lane`, `_close_session_if_lane_empty`, `_session_for`, `_follow_subject`, `_may_inspect`, `_guide_position`, `_collect_candidate`, `_start_analysis`). Tes karakterisasi baru 18 skenario × 1200 frame (acuan di-commit `cd2e47e` sebelum refaktor) identik; 3 mutasi tertangkap; keluar dari daftar utang Digabung 06-10 (tinjauan Gemini menyusul) |
| T28 — penyedia VLM dari dashboard (bagian backend) | Claude | `claude/t28-vlm-switch` | selesai | `backend/vlm_analyzer.py`, `backend/vlm_selection.py` (baru), `backend/vlm_providers/` (`profiles.py`: `key_env` + profil `anthropic`/`kimi`; `anthropic.py` baru; `__init__.py`), `backend/api/routes_vlm.py`, `backend/config.py`/`messages.py`/`.env.example` (tambah: key per penyedia), `docs/INSTALASI.md` (bagian VLM), `tests/` (baru) | Diklaim 07-10. Ikut rancangan & kontrak di bawah (disetujui 06-10). Risiko **Sedang**. Bercabang dari `master`; T48 (juga `profiles.py`) digabung lebih dulu, T28 di-rebase. UI (T28-UI, Gemini) setelah tinjauan T48, ikut kontrak — **07-10 selesai di branch:** `vlm_selection.py` (key/alamat per penyedia hanya dari `.env`, aturan tolak/konfirmasi, pilihan tersimpan diperiksa ulang saat start, jejak `vlm_changes.jsonl` fsync, katalog), `VLMAnalyzer.apply_selection` (rakit+panaskan di luar gembok, tukar di bawah gembok inspeksi saat jalur kosong, engine sama dipakai ulang), adaptor Claude httpx, profil Kimi; endpoint key lama dihapus; pesan galat penyedia dibersihkan dari potongan key. Tes 30 + 9 (adaptor Claude, server tiruan) + 3; 7 mutasi (unsafe, konfirmasi, key bocor, cek jalur, gembok, pemanasan, jejak) tertangkap. Smoke port 8002 tanpa key asli: 400 unsafe/needs_confirmation/missing_key, 502 engine_failed (key palsu, engine lama tetap), 405 key lama. Rincian kontrak (kode galat) ditambahkan di bawah. **Belum:** uji penyedia sungguhan (Claude/Kimi) — perlu key & kuota, izin pengguna; rebase setelah T48 (`find_validation` versi prompt) Digabung 14-10 bersama T28-UI, T51, T51-UI (`01fb24e`). |
| T28-UI — kartu VLM di Pengaturan admin | Gemini | `gemini/t28-vlm-ui` (bercabang dari `claude/t28-vlm-switch`) | selesai | `web/src/components/settings/VlmProviders.svelte` (baru), `web/src/lib/vlmSelection.ts` (+ tes, baru), `web/src/pages/Pengaturan.svelte` (sisipkan kartu saja), `web/src/lib/api/client.ts` (tambah metode T28, hapus `setVlmKey`), `web/src/lib/api/types.ts` / `messages.ts` / `settings.ts` (tambah) | Ikut kontrak T28 + rincian 07-10. Mulai setelah tinjauan T48 & T28 dilaporkan. Klaim dicatat integrator 07-10 Digabung 14-10 lewat rantai `gemini/t51-accounts-ui` (`01fb24e`); warna hex di VlmProviders sudah dibereskan T51-UI. |
| T51 — akun pengguna & halaman setup (backend) | Claude | `claude/t51-accounts` (bercabang dari `claude/t28-vlm-switch`) | selesai | `backend/accounts.py` (baru), `backend/auth.py`, `backend/api/deps.py`, `backend/api/routes_auth.py`, `backend/api/routes_accounts.py` (baru), `backend/app.py` (hapus cek T20b), `backend/config.py`/`messages.py`/`.env.example`, `docs/INSTALASI.md`, `tests/` | Disetujui 07-10. UI (T51-UI, Gemini) menyusul setelah backend — **07-10 selesai di branch:** `accounts.py` (SQLite `accounts.db`, scrypt N=2^14 ±136 ms/login, hash tiruan untuk nama tak terdaftar, BEGIN IMMEDIATE untuk setup sekali & akun terakhir, jejak `account_events.jsonl` fsync, perintah `list/create/reset-password`), sesi per akun + cabut per akun, limiter per alamat & per nama, `require_role` (403 untuk peran lain), rute setup/login/akun sesuai kontrak; `ADMIN_TOKEN`/`ALLOW_INSECURE_DEMO`/cek T20b dihapus, peringatan start bila `ADMIN_TOKEN` masih di `.env` / belum ada akun; jejak T28 mencatat nama pengguna. Tes: 54 login + 11 akun; 9 mutasi tertangkap. Smoke port 8002 (data sementara): setup 201 → health 200, setup ulang 409, login salah 401, tambah akun, CLI list; kata sandi tidak ada di log/jejak. Temuan smoke (peringatan 'belum ada akun' tetap setelah setup) diperbaiki. **JANGAN digabung sebelum T51-UI**: UI lama tidak mengenal `setup_required`/nama pengguna → dashboard tidak bisa login. Urutan gabung: T28 (+T28-UI) → T51 + T51-UI bersamaan Digabung 14-10 bersama T51-UI (`01fb24e`). Diuji browser nyata (DATA_DIR sementara): setup, salah ulang sandi, login salah/benar, kartu VLM `missing`, jam akun lokal, konsol bersih. Tinjauan T51-UI putaran 4 (207b4be): 2 temuan kecil (port hardcode di url.ts/Setup, tes formatServerDate tautologis) → ikut T57/T58-UI. |
| T57 — kamera terhalang benda apa pun & buram | Claude | `claude/t57-camera-obstruction` (dari `master`) | selesai | `tools/camera_probe.py` (baru), `backend/camera_health.py`, `backend/config.py`/`messages.py`/`.env.example` (tambah + ubah teks gangguan `blocked`), `backend/audio/kamera_terhalang.mp3` + `_texts.json`, `tests/test_camera_health.py` | **Ukur 13-10 (C920, `data/eval/20261013-215413` & `-215624`)**: jelas (jalur kosong/orang/orang 0,5 m) ketajaman Laplacian 368–610 & tepi Canny ≥ 0,08; tertutup tangan/kardus/kain & lensa diplastik ketajaman 3–17 & tepi ~0; setengah tertutup ~224/0,033 (sengaja **tidak** alarm, orang masih terlihat). Tangan menutup rapat sudah tertangkap T45 (gelap); yang lolos = **buram terang** (plastik: rata-rata 129, std 24). **Isi**: `is_blocked` = gelap/terang/seragam (T45) **atau** `is_blurred` (ketajaman < `CAMERA_MIN_SHARPNESS` 80 **dan** tepi < `CAMERA_MIN_EDGE_RATIO` 0,01, gambar abu 320x180), tetap lewat syarat bertahan `CAMERA_BLOCKED_SECONDS` → status `blocked` yang sudah ada (kuning, **kontrak API tidak berubah**). Biaya per frame 0,53 → 0,87 ms (854x480), 1,05 → 1,28 ms (1080p). Teks lampu & suara `blocked` jadi "terhalang / buram". Tes: 5 tes baru + `scene()` uji diganti bertekstur (bidang rata tidak mirip pemandangan nyata); mutasi "matikan buram" → 2 tes gagal. **UI (Gemini, setelah T51-UI)**: label `BLOCKED` di `web/src/lib/messages.ts` masih "Kamera tertutup / terlalu gelap" → ubah ke "terhalang / buram". Batas: ambang dari satu ruangan; di lokasi gerbang ukur ulang `python tools/camera_probe.py --find` lalu `--index <n>`. Temuan sampingan: jalur kosong YOLO tetap mendeteksi 2 orang (37/37 cuplikan) — perlu dicek Digabung 14-10 (`84e5ae8`) + `camera_probe.main` dipecah (aturan <= 30 baris kini mencakup tools/). **Belum: uji fisik di gerbang.** |
| T58 — larangan rokok (item larangan di katalog) | Claude | `claude/t58-smoking-rule` (dari `master`) | selesai | `backend/ppe_rules.py` (field `prohibited` + item `rokok`), `backend/messages.py` (tambah), `backend/audio/` (MP3 baru), `tools/bench_vlm.py` (metrik rokok dari prompt produksi), `tests/`, `AGENTS.md` §5 & `docs/RENCANA.md` (aturan merah) | Diklaim 13-10. **Keputusan pengguna 13-10**: rokok terlihat → **merah, ditolak** (aturan "merah hanya APD kurang" diperluas jadi "merah hanya APD kurang / larangan dilanggar"); yang dihitung: sedang merokok, memegang rokok batangan, bungkus rokok terlihat, rokok elektrik/vape; **VLM ragu = dianggap tidak ada**; bisa dinyalakan/dimatikan operator di Pengaturan, **bawaan menyala**. Kontrak UI: `GET /api/ppe-rules` item mendapat `"prohibited": bool` (true = `detected` berarti melanggar) → T58-UI (Gemini) membalik penilaian badge di `web/src/lib/ppe.ts`. Uji: tes + bench lokal `picture_test` (salah tolak karena rokok & akurasi APD tidak turun); foto/uji fisik rokok asli & pengecoh (pulpen, sedotan) oleh pengguna. **Selesai di branch 13-10**: `PPEItem.prohibited` (lulus bila tidak terdeteksi; jawaban hilang/null = tidak ada), item `rokok` (bawaan aktif), penjaga "minimal satu APD aktif" tidak menghitung larangan, `to_public_dict` + `prohibited`, suara `dilarang_rokok.mp3`, `PROMPT_VERSION` T36a→**T58**. Tes 8 baru (mutasi: larangan diperlakukan seperti APD → 15 gagal; penjaga menghitung larangan → 2 gagal). **Bench lokal qwen2.5vl:7b 84 foto (`data/eval/20261013-230959`)**: identik dengan T36a — akurasi 0,952, lolos padahal kurang **0**, salah tolak 2 (apd_10, apd_4, sama), galat server 2 (apd_19, no_23, sama), latensi median 3,39→3,63 dtk (+0,24, token input +196); rokok terlihat 1x di `no_34` (foto APD kurang, keputusan tidak berubah — perlu dicek pengguna apakah benar ada rokok). Bench pertama gagal (semua panggilan habis waktu 90 dtk) karena VRAM penuh oleh aplikasi lain saat beban YOLO = T56, bukan prompt (uji langsung 1,4 dtk). **Belum**: validasi Gemini untuk T58 (kuota cloud, butuh izin; status kini `outdated`), uji fisik rokok/vape asli + pengecoh (pulpen, sedotan), T58-UI (Gemini). **Konfirmasi kedua (disetujui pengguna 13-10)**: pengguna memastikan `no_34` tanpa rokok (tangan kosong bernoda semen) → deteksi palsu, konsisten diulang; pengetatan kalimat prompt tidak menolong (dikembalikan). Kini bila jawaban pertama menyatakan larangan terlihat, VLM yang sama ditanya ulang (`PPEItem.confirm_prompt`, `messages.VLM_CONFIRM_*`); ditolak hanya bila keduanya sepakat; konfirmasi gagal/habis waktu/ragu = tidak terlihat; dicatat di log. Tanpa larangan terlihat tidak ada panggilan tambahan. Sidik jari prompt mencakup pertanyaan konfirmasi. Tes 8 baru (mutasi "hasil konfirmasi diabaikan" → 6 gagal). **Bench ulang (`data/eval/20261013-233226`)**: lolos padahal kurang **0**, salah tolak 1 (apd_10), rokok awal 1 (no_34) → dibatalkan konfirmasi → rokok akhir **0**, akurasi 0,964, median 3,69 dtk (no_34 5,2 dtk) Digabung 14-10 (`bcd5812`). Rebase ke atas T48 → prompt gabungan dibench ulang 84 foto: 0 lolos, salah tolak 1, rokok palsu no_34 dibatalkan konfirmasi (galat no_23 memicu Ollama memuat model 26% di CPU = T38; sisa 36 foto diulang). **Belum: validasi Gemini T58 (kuota, izin), uji fisik rokok/vape asli + pengecoh, T58-UI.** |
| T57/T58-UI — badge larangan rokok, label kamera terhalang/buram, temuan T51-UI | Gemini | `gemini/t58-ui` (dari `master`) | selesai | `web/src/lib/api/types.ts` (`prohibited`), `web/src/lib/ppe.ts` (+ tes), registri ikon (`cigarette`), `web/src/pages/Pengaturan.svelte` (daftar larangan), `web/src/lib/messages.ts` (label BLOCKED), `web/src/lib/url.ts`/`settings.ts`/`Setup.svelte` (port), `web/src/lib/formatters.test.ts` | Dicatat integrator 14-10. Gemini belum mulai (menunggu T58 digabung; kini sudah di `master`); bercabang langsung dari `master`. Kontrak T58: item katalog `prohibited: bool`, `detected: true` = melanggar. T57: status API tetap `blocked` Digabung 14-10 (Gemini `02b7164`, rebase → merge). Diverifikasi: 5 berkas sesuai laporan, assessItem larangan benar (pending → larangan → APD), vitest 100, svelte-check 0. **Bagian C (temuan T51-UI: port hardcode di `url.ts`/`Setup.svelte`, tes `formatServerDate` tautologis) tidak dikerjakan & tidak disebut di laporan → sisa Rendah.** |
| T59 — poster/orang lain di koridor mewarisi keputusan | Claude | `claude/t59-phantom-lane` (dari `master`) | selesai | `backend/state_manager.py` (sesi & pemilihan subjek), `backend/config.py`/`messages.py` (tambah), `tests/test_lifecycle.py`, `tests/golden/state_manager.json` | Pengguna 14-10: "2 orang" di jalur kosong = **poster**. Jalur deteksi gerbang melihatnya stabil (keyakinan 0,84–0,90, kaki terpotong → tidak pernah ke VLM), tetapi jalur tidak pernah kosong (zona nonaktif) → sesi pindah ke poster membawa keputusan; **dibuktikan tes: pekerja tanpa helm mewarisi hijau tanpa diperiksa**; sesi yang dimulai poster tidak memberi giliran ke pekerja. Perbaikan (disetujui 14-10): keputusan terikat track subjek (hilang > jeda reset → sesi ditutup), ID baru = orang sama hanya bila belum pernah terlihat bersama subjek + muncul ≤ 0,5 dtk + IoU ≥ 0,6 (jaminan T36c tetap), orang utuh didahulukan sebelum keputusan. Karakterisasi dibangkitkan ulang (perubahan dijelaskan di commit `ab258df`). Biaya 1→2 µs/frame. Uji langsung **dilewati** atas arahan pengguna. Sisa: lokasi berposter sebaiknya mengaktifkan zona titik berdiri; cek apakah poster memicu arahan posisi/suara terus-menerus Digabung 14-10. Pengguna: poster hanya ada di tempat kerja pengembang, tidak di lokasi gerbang → sisa "arahan posisi dari poster" tidak dikerjakan; perbaikan tetap menutup kasus orang antre. |
| T56 — kesehatan VLM lokal (gejala lambat/habis waktu, aplikasi lain di GPU) | Claude | `claude/t56-local-vlm-health` (dari `master`) | selesai | `backend/local_model_guard.py`, `backend/vlm_analyzer.py` (catat latensi cadangan), `backend/api/routes_system.py` (health `local_vlm`), `backend/config.py`/`messages.py`/`.env.example` (tambah), `docs/INSTALASI.md` (persiapan demo GPU), `tests/` | Disetujui 14-10. Uji 14-10: tekanan VRAM 4 GB aktif → semua panggilan Ollama macet 90 dtk padahal `ollama ps` "100% GPU" (penjaga T38 buta); pengaturan NVIDIA "Prefer No Sysmem Fallback" tidak membuatnya terdeteksi; sisa VRAM `nvidia-smi` tidak andal (7,69 GB saat macet ≈ normal). Pengguna memasang mode Hybrid + overclock mati → NVIDIA hanya dipakai explorer & VS Code (262 MB). Kontrak di bawah ("Kontrak T56"). UI → T56-UI (Gemini) setelah backend **Selesai & digabung 14-10**: `local_model_guard` mencatat latensi panggilan utama cadangan lokal (konfirmasi rokok tidak dihitung); `LOCAL_SLOW_STREAK` (2) panggilan ≥ `LOCAL_SLOW_SECONDS` (8) / habis waktu berturut → status `slow`, peringatan log berisi aplikasi lain di GPU (`gpu_processes`, `nvidia-smi --query-compute-apps`), muat ulang paksa (jeda 300 dtk) lalu pemanasan; `GET /api/health` → `local_vlm` sesuai kontrak; pemanasan lokal kini bergambar (inspeksi pertama 13 → 6 dtk). Tes 16 baru. **GPU (keputusan pengguna 14-10)**: gerbang/demo = mode dGPU (OC mati: baca 1,49 dtk, 3,85 dtk/inspeksi), harian = Hybrid (Hybrid menahan clock CUDA: 3,1 dtk) → `docs/INSTALASI.md`. Di dGPU sisa VRAM ±0,5 GB: bench/eval kini memakai satu YOLO (YOLO kedua membuat Ollama macet). **Belum**: T56-UI (Gemini, setelah T60). |
| T60 — sisa T51-UI + indikator "belum masuk" | Gemini | `gemini/t60-ui-cleanup` (dari `master`) | selesai | `web/src/lib/url.ts` (+ tes), `web/src/lib/settings.ts` (port), `web/src/pages/Setup.svelte`, `web/src/lib/formatters.test.ts`, komponen status koneksi di bilah atas (`TopBar.svelte` / `lib/status.ts` + tes), `web/src/lib/messages.ts` (tambah) | Klaim dicatat integrator 14-10. Temuan tinjauan T51-UI putaran 4 + uji UI 14-10: sebelum login (WebSocket belum tersambung karena belum masuk) ikon bilah atas menampilkan "server terputus" — menyesatkan **Digabung 14-10** (ditinjau integrator): port dev server → `settings.ts` `DEV_SERVER`, tes formatter tidak lagi tautologis, chip "Belum masuk" (`lib/connection.ts` + 3 vitest; mutasi tanpa cek login → gagal; dicek di browser dengan DATA_DIR sementara). check.py: 539 pytest + 103 vitest. |
| T56-UI — tampilan kesehatan VLM cadangan | Gemini | `gemini/t56-ui` (dari `master`) | selesai | `web/src/lib/api/types.ts` (tambah tipe `local_vlm`), `web/src/lib/localVlm.ts` (baru, logika murni + tes), `web/src/lib/stores/health.svelte.ts` (baru), `web/src/components/settings/LocalVlmCard.svelte` (baru), `web/src/pages/Pengaturan.svelte`, `web/src/components/TopBar.svelte`, `web/src/App.svelte`, `web/src/lib/messages.ts` & `settings.ts` (tambah) | Selesai di branch: kartu "Kesehatan VLM Cadangan" di Pengaturan (status, porsi GPU, latensi, lambat berturut-turut, daftar proses lain di GPU + petunjuk tutup aplikasi), chip kuning di TopBar hanya saat slow/partial_gpu (tanpa nama penyedia/model); health store polling /api/health tiap 10 dtk saat sesi aktif. Tes: 11 vitest baru (semua lolos; uji mutasi: unknown memunculkan chip -> 2 tes gagal). check.py lolos. **Digabung 14-10** (ditinjau integrator): kartu & chip sesuai kontrak; mutasi "chip untuk unknown" → 2 gagal (diulang integrator); dicek di browser (keadaan lambat/sebagian CPU ditiru). Temuan: (a) daftar aplikasi lain di mode dGPU ±25 proses bawaan Windows → spanduk selalu tampil → **T56b** (Claude, saring proses sistem di backend) + spanduk hanya saat slow/partial_gpu → T61; (b) chip baru ikut terpotong di Monitoring 1440 px → T61 butir 3 dinaikkan; (c) latensi "3.6 dtk" & satuan tertulis di `localVlm.ts` → pakai `seconds()`/`percent()` dari `messages.ts` → T61. |
| T42c — pecah `capture._reader_loop` (cicilan utang kode) | Claude | `claude/t42c-reader-loop-split` (dari `master`) | selesai | `backend/video/capture.py`, `tests/test_capture_characterization.py` (baru) + `tests/golden/capture_reader.json`, `tests/test_code_hygiene.py` (daftar utang) | Diklaim 14-10 (izin pengguna "kerjakan T42"). Risiko **Rendah** (kerapian), tetapi jalur panas kamera: pola T42b — tes karakterisasi & acuan di-commit SEBELUM refaktor, perilaku harus identik. Fungsi terpanjang di daftar utang (199 baris). **Selesai di branch 14-10**: 199 baris → `_reader_loop` 16 baris + 12 langkah bernama ≤23 baris (`_start_reader`, `_handle_requests`, `_optimize_camera`, `_go_idle`, `_restart_reading`, `_mark_lost`, `_next_raw_frame`, `_reconnect_step`, `_read_camera_frame`, `_camera_stalled`, `_publish_raw`, `_set_status_frame`); variabel lokal loop → `_ReaderState`; angka jendela laju 1 dtk → `CAMERA_RATE_WINDOW_SECONDS`. Tes karakterisasi 12 skenario × 1500 putaran (acuan di-commit `6731a8e` sebelum refaktor) identik; 2 mutasi tertangkap. Biaya per putaran 1,1–1,2 → 1,4 µs (tak berarti pada 30 FPS). Keluar dari daftar utang. **Temuan (tidak diubah, perilaku lama)**: "Pindai kamera" sebelum kamera dipilih → status SYNTHETIC "Kamera index None tidak dapat dibuka", bukan tetap IDLE. |
| T42d — pecah `capture._init_camera` (cicilan utang kode) | Claude | `claude/t42d-init-camera-split` (dari `master`) | selesai | `backend/video/capture.py`, `tests/test_capture_characterization.py` + `tests/golden/capture_reader.json`, `tests/test_code_hygiene.py` (daftar utang) | Diklaim 14-10 ("lanjut T42 berikutnya"). Risiko **Rendah**. Pola T42c: tes karakterisasi diperluas (permintaan ukuran ke driver, `CAMERA_AUTO_MODE`) & acuan di-commit SEBELUM refaktor. **Selesai di branch 14-10**: ±90 baris → `_init_camera` 22 baris + 7 langkah ≤14 baris (`_begin_opening`, `_scanned_mode`, `_limit_driver_buffer`, `_requested_size`, `_probe_frame`, `_fall_back_to_synthetic` — dua blok kembar gagal-buka/tanpa-frame disatukan, `_activate`); angka 5 pembacaan → `CAMERA_PROBE_READS`. Karakterisasi diperluas (permintaan ukuran ke driver, `active_mode` utuh, `CAMERA_AUTO_MODE`, ukuran frame per kamera; acuan `2a80c52`) identik; 2 mutasi tertangkap. Bukan jalur panas (hanya saat membuka kamera). Keluar dari daftar utang. |
| T55 — tombol "Tes Merah" di Pengaturan → Lampu & Tes | Claude | `claude/t55-red-light-test` | selesai | `web/src/pages/Pengaturan.svelte`, `web/src/lib/messages.ts` (label tombol) | Permintaan pengguna 13-10 saat uji relay: UI hanya punya uji hijau ("Tes Lampu") & kuning; endpoint sudah mendukung `red`. Label jadi "Tes Hijau / Tes Merah / Tes Kuning". check.py: vitest 84; pytest 404 + 1 `test_shutdown` gagal sekali saat server gerbang berjalan bersamaan (berhenti > 5 dtk), lolos 2x saat diulang sendiri. Digabung 13-10 (tinjauan Gemini menyusul) |
| T54 — lampu gerbang lewat relay USB HID (dcttech USBRelay2), **khusus demo** | Claude | `claude/t54-usb-relay` (dari `master`) | selesai | `backend/notifier.py` + modul relay baru, `backend/supervisor.py` (matikan relay saat server crash), `backend/config.py`/`messages.py`/`.env.example` (tambah), **dependensi `hidapi`** (`backend/requirements*.txt/.lock` — giliran dependensi putaran ini: Claude), `IOT_HARDWARE_SPEC.md`, `docs/INSTALASI.md`, `tests/` | Disetujui 13-10. Perangkat uji pengguna: relay USB 2 kanal (VID 16C0/PID 05DF) + adaptor 12V 1A + lampu LED; **relay 1 = hijau, relay 2 = merah**, kabel ke NO. Hijau hanya APD lengkap, merah hanya APD kurang, selain itu keduanya mati (tanpa kuning). Risiko **Tinggi** (hijau salah menyala). Pengaman: relay dimatikan saat server mulai/berhenti & oleh supervisor saat server crash, status dibaca balik, sambung ulang otomatis. Sisa risiko: server macet tanpa crash (relay tanpa heartbeat) — diterima untuk uji coba demo — **13-10 selesai di branch:** `backend/usb_relay.py` (feature report HID; `write()` diabaikan papan — temuan uji perangkat), baca balik + koreksi tiap 1 dtk, sambung ulang, `supervisor` mematikan relay tiap server keluar. Tes 24 (papan tiruan), 7 mutasi tertangkap. **Uji perangkat nyata (port 8002):** hijau/merah/kuning/mati lewat Pengaturan → relay 0b01/0b10/0b00/0b00; server dibunuh saat hijau TANPA penjaga → hijau tetap (relay mengunci, terbukti); lewat `backend.supervisor` → mati ≤2 dtk lalu server menyala ulang; server baru menyala mematikan sisa hijau. **Cara uji:** `.env` `IOT_ENABLED=true`, `IOT_TYPE=usb_relay`, jalankan `start_system.bat`, Pengaturan → Uji lampu; uji APD lengkap/kurang di depan kamera. **Digabung 13-10** atas persetujuan pengguna sebelum tinjauan Gemini (menyusul): khusus demo, ESP32 (T47) tetap rancangan utama & tidak diubah. **Belum:** uji APD nyata di depan kamera |
| T53 — manajemen log (application/security/audit) & penjaga disk | Claude | `claude/t53-logging` (bercabang dari `claude/t51-accounts`) | selesai | `backend/logging_setup.py`, `backend/security_log.py` (baru), `backend/disk_guard.py` (baru), `backend/supervisor.py` (logging saja), `backend/runtime.py`, `backend/accounts.py` & `backend/vlm_selection.py` (jejak → security log), `backend/api/routes_auth.py` & `deps.py` (kejadian keamanan baru), `backend/api/routes_system.py` (health, tambah `disk`), `backend/config.py`/`messages.py`/`.env.example` (tambah), `docs/INSTALASI.md`/`ARSITEKTUR.md`, `tests/` | Disetujui 08-10 ("gas"). Risiko **Sedang** (mendekati Tinggi: disk penuh = audit gagal tersimpan). Bercabang dari T51 karena jejak akun pindah ke security log; urutan gabung T28 → T51 → T53. Tidak menyentuh `web/` (field `disk` di health untuk UI kelak) Digabung 14-10 (`1c3f0de`). |

### Kontrak T56 — kesehatan VLM lokal di `GET /api/health` (disetujui pengguna 14-10)

```jsonc
"local_vlm": {
  "state": "ok" | "slow" | "partial_gpu" | "unknown",
  //  ok          : panggilan lokal normal, model penuh di GPU
  //  slow        : >= LOCAL_SLOW_STREAK (2) panggilan lokal berturut-turut > LOCAL_SLOW_SECONDS (8) atau habis waktu
  //  partial_gpu : ollama ps melaporkan sebagian model di CPU (penjaga T38)
  //  unknown     : tidak ada VLM lokal / belum pernah dicek
  "gpu_ratio": 1.0,              // porsi model di VRAM 0–1 (ollama ps); null bila tidak diketahui
  "slow_streak": 0,              // panggilan lokal lambat/habis waktu berturut-turut
  "last_latency_s": 3.6,         // panggilan lokal terakhir; null bila belum ada
  "other_gpu_apps": ["Code.exe"] // proses lain di GPU NVIDIA (nama saja, tanpa path); [] bila tidak ada / nvidia-smi tidak tersedia
}
```

- Saat `slow` tercapai: peringatan di log (+ `other_gpu_apps`) dan model dimuat ulang sekali di sela inspeksi (mekanisme T38, dengan jeda).
- UI (T56-UI): Pengaturan admin → kartu "Kesehatan VLM cadangan" (status, porsi GPU, latensi, daftar aplikasi lain + petunjuk "tutup aplikasi ini"); Monitoring operator → chip kuning hanya bila `state` = `slow` atau `partial_gpu` (tanpa nama penyedia/model, §5).
- Diperjelas integrator 14-10: `unknown` (gerbang baru menyala / tanpa VLM lokal) **tidak** memunculkan chip; petunjuk "Power saving" dihapus karena gerbang memakai mode dGPU (`docs/INSTALASI.md`), di mana semua aplikasi memakai GPU NVIDIA.

### Rancangan T28 — ganti penyedia VLM dari dashboard (disetujui 06-10; dikerjakan setelah T30)

**Backend (Claude)**
1. **Key per penyedia di `.env`** (keputusan e): `GEMINI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`,
   `DASHSCOPE_API_KEY` (Qwen), `MOONSHOT_API_KEY` (Kimi), `ANTHROPIC_API_KEY` (Claude). Profil (`vlm_providers/profiles.py`)
   mendapat `key_env`. `VLM_API_KEY`/`VLM_BACKUP_API_KEY` lama tetap menang bila diisi (kompatibel). Dashboard tidak pernah
   menerima, menyimpan, atau menampilkan key; hanya tahu `has_key`.
2. **Hapus** `POST /api/config/vlm-key` + alias `/api/config/gemini-key` (+ `update_api_key`, `setVlmKey` di klien UI):
   bertentangan dengan keputusan (e).
3. **Adaptor Claude** (`vlm_providers/anthropic.py`): Messages API lewat `httpx` (tanpa dependensi baru), gambar base64
   JPEG, `system` = prompt sistem, jawaban teks diurai `parse_json_reply`. Profil `anthropic` (eksperimental, lokasi data
   Anthropic AS). **Profil `kimi`** (Moonshot, OpenAI-compatible, eksperimental); nama model diisi saat uji (tidak ditebak).
4. **Pilihan dari dashboard disimpan** di `runtime_settings` (`vlm_selection`: utama & cadangan = penyedia + model) dan
   menang atas `.env` saat start; `source` = `"env"` | `"dashboard"`. Tombol kembali ke `.env` = hapus pilihan.
5. **Ganti tanpa restart**: engine baru dirakit & dipanaskan dulu; baru ditukar di bawah gembok inspeksi saat **jalur
   kosong** (b). Gagal rakit/panaskan → engine lama tetap dipakai.
6. **Jejak (c)**: setiap pergantian ditulis ke log + `DATA_DIR/reports/vlm_changes.jsonl` (waktu, peran, dari → ke,
   status validasi, sumber sesi admin), ditulis atomik + fsync seperti audit.

**Kontrak API (semua wajib login admin, T30)**
- `GET /api/config/vlm/providers` → `{"current": {"primary": Sel, "backup": Sel | null}, "prompt_version": str,
  "providers": [{"name", "label", "support": "official"|"experimental", "is_local", "has_key", "data_location",
  "default_model", "models": [{"model", "validated": "validated"|"partial"|"outdated"|"unsafe"|"unvalidated",
  "photos", "missed", "false_rejects", "median_seconds"}]}]}`, dengan `Sel = {"provider", "model", "source"}`.
  Daftar `models` = model di daftar validasi + model yang sedang dipakai; model lain boleh diketik bebas.
- `POST /api/config/vlm/test` `{"role", "provider", "model"}` → `{"ok", "latency_ms", "json_ok", "error"}` — 1 panggilan
  ping + 1 panggilan gambar sintetis (memakai kuota penyedia itu).
- `POST /api/config/vlm/apply` `{"primary": {"provider","model"}, "backup": {...} | null, "confirm_unvalidated": bool}` →
  200 bentuk `current`; **409** pekerja di jalur; **400** penyedia tak dikenal / key tidak ada di `.env` / model
  `unsafe` (selalu ditolak) / model belum tervalidasi tanpa `confirm_unvalidated` (bila keputusan d = boleh dengan konfirmasi).
- `DELETE /api/config/vlm/selection` → kembali ke `.env` (aturan 409 sama).

**Rincian kontrak dari implementasi (07-10, tambahan; tidak mengubah butir di atas)**
- Galat 400/409/502 berbentuk `{"detail": {"code", "message"}}`; `message` siap tampil (Bahasa Indonesia).
  `code`: `unknown_provider`, `missing_model`, `missing_key` (key belum ada di `.env`), `missing_base_url`,
  `unsafe_model`, `needs_confirmation` (tampilkan konfirmasi kuning/oranye lalu kirim ulang dengan
  `confirm_unvalidated: true`), `lane_busy` (409), `engine_failed` (**502**: engine baru gagal dirakit/dipanaskan,
  engine lama tetap dipakai).
- `needs_confirmation` berlaku untuk status `unvalidated` **dan** `outdated` (tervalidasi untuk prompt lama);
  `validated`/`partial` tanpa konfirmasi; `unsafe` selalu ditolak.
- `POST /api/config/vlm/test`: `role` = `"primary"` | `"backup"` (bawaan `"primary"`). `ok` = penyedia menjawab
  ping; `json_ok` = jawaban gambar sintetis berupa JSON; `error` = alasan singkat ("" bila berhasil). Engine gerbang
  tidak disentuh. Penyedia ditolak lebih dulu dengan kode 400 yang sama seperti apply (kecuali konfirmasi).
- `has_key` = penyedia siap dipilih tanpa menyunting `.env`: key ada (atau lokal) **dan** alamat diketahui
  (vLLM/openai-compatible butuh `VLM_BASE_URL`). UI cukup menyembunyikan/menonaktifkan yang `false`.
- `missing` (tambahan 08-10, tiap penyedia) = isian `.env` yang masih kurang: `"key"` | `"base_url"` | `null`
  (siap). Key dicek lebih dulu. UI memakai ini untuk teks petunjuk ("isi key" vs "isi alamat"), mis. vLLM lokal
  tidak pernah butuh key.
- `apply` & `DELETE` mengembalikan bentuk `current`. Bila penyedia lokal (Ollama) harus dimuat, `apply` bisa
  berlangsung hingga ±2 menit (pemanasan) — UI menampilkan status "menyiapkan…".
- `GET /api/config/vlm` lama tetap ada (dipakai kartu status); `POST /api/config/vlm-key` & `/api/config/gemini-key`
  **dihapus** (404/405) — `setVlmKey` di `web/src/lib/api/client.ts` dihapus di T28-UI.

**UI (Gemini, setelah kontrak disetujui)**: kartu "VLM" di Pengaturan admin — pilih penyedia (hanya yang `has_key`)
& model untuk utama/cadangan, lencana validasi + angka (akurasi, latensi), lokasi data, tombol Uji & Terapkan,
peringatan **kuning/oranye** (bukan merah) untuk model belum tervalidasi. Operator biasa tidak melihat kartu ini.

**Tes**: tiap rambu (a)–(e) punya tes; adaptor Claude dites dengan server HTTP tiruan (tanpa kuota); pertukaran engine
saat inspeksi berjalan tidak boleh memotong pemeriksaan (tes konkurensi).

**Keputusan (d), 06-10**: model belum tervalidasi **boleh dipilih dengan konfirmasi** (`confirm_unvalidated`) + peringatan
kuning/oranye + tercatat di jejak; model `unsafe` (pernah meloloskan APD kurang) **selalu ditolak**.

### Rancangan T51 — akun pengguna & halaman setup (disetujui 07-10; dikerjakan setelah T28 digabung)

**Latar (keputusan pengguna 07-10):** kata sandi = `ADMIN_TOKEN` di `.env` membingungkan (harus membuka berkas server).
Ganti dengan **akun** (nama pengguna + kata sandi). Untuk demo **satu peran**: admin sekaligus operator. Boleh beberapa
akun (jejak mencatat *siapa*), semuanya `admin`. `ADMIN_TOKEN` & `ALLOW_INSECURE_DEMO` **dihapus seluruhnya**. Akun
pertama dibuat lewat **halaman setup yang hanya bisa diisi dari mesin gerbang (localhost)**.

**Risiko: Tinggi** — mengatur akses ke foto wajah, video, audit, dan pengaturan yang menentukan keputusan APD.

**Rambu**
- (a) Kata sandi tidak pernah disimpan/dicatat/dikirim balik: hash `hashlib.scrypt` (bawaan Python, tanpa dependensi
  baru) + garam acak per akun; perbandingan waktu-konstan; nama pengguna yang tidak ada tetap dihitung hash tiruan
  (waktu jawaban tidak membocorkan nama mana yang ada).
- (b) Tidak ada mode terbuka: sebelum akun pertama dibuat, semua `/api/*` & `/ws` tertutup kecuali `GET /api/session`
  dan `POST /api/setup`. Setup hanya dari `127.0.0.1`/`::1` dan hanya bila belum ada akun (dicek atomik di DB, jadi dua
  permintaan bersamaan tidak membuat dua admin pertama).
- (c) Batas tebak: 5 gagal → jeda 60 dtk **per alamat dan per nama pengguna** (`LOGIN_MAX_FAILURES`,
  `LOGIN_LOCKOUT_SECONDS` yang sudah ada).
- (d) Hapus akun / reset kata sandi / ganti kata sandi → semua sesi akun itu dicabut (ganti sendiri: sesi lain dicabut,
  sesi yang dipakai tetap). Akun terakhir dan akun sendiri tidak bisa dihapus.
- (e) Jejak `DATA_DIR/reports/account_events.jsonl` (fsync): setup, login berhasil/gagal, keluar, buat, hapus, reset,
  ganti kata sandi — waktu, nama pengguna, pelaku, alamat; **tanpa** kata sandi/hash. Jejak T28 `vlm_changes.jsonl`
  mencatat nama pengguna pelaku (bukan hanya alamat).
- (f) Siap peran di masa depan: kolom `role` ada sejak awal (selalu `admin` sekarang); semua endpoint lewat satu pintu
  `require_role(...)`. Peran operator kelak = mengubah daftar hak, bukan alur login.

**Backend (Claude)**
1. `backend/accounts.py` (baru): `DATA_DIR/accounts.db` (SQLite WAL + synchronous FULL, **terpisah dari `audit.db`**
   supaya retensi/ekspor audit tidak menyentuh akun). Tabel `users(username PK, password_hash, role, created_at,
   password_changed_at, last_login_at)`. Nama pengguna 3–32 karakter `a-z 0-9 . _ -` (huruf kecil, tidak peka huruf
   besar); kata sandi minimal `ACCOUNT_PASSWORD_MIN_LENGTH` = **12** (disetujui 07-10), maksimal 128, tidak sama dengan nama pengguna.
2. `backend/auth.py`: sesi menyimpan `(username, role)`; cabut per akun; limiter per nama pengguna; `X-Admin-Token`
   & `password_matches` dihapus. `app.py`: pemeriksaan "jaringan terbuka tanpa token" (T20b) dihapus — tidak ada lagi
   mode terbuka. Peringatan saat start bila `.env` masih berisi `ADMIN_TOKEN` (tidak dipakai lagi).
3. Perintah di mesin gerbang (untuk lupa kata sandi admin terakhir): `python -m backend.accounts list`,
   `reset-password <nama>` (kata sandi diketik tersembunyi, `getpass`), `create <nama>`.
4. Tes: setup hanya localhost & sekali (termasuk dua permintaan bersamaan), login/limiter per nama, cabut sesi, akun
   terakhir, tidak ada kata sandi/hash di respons & log & jejak, semua rute `/api` wajib sesi (penjaga OpenAPI T30
   dipertahankan), `/ws` 4401, perintah reset.

**Kontrak API** (galat berbentuk `{"detail": {"code", "message"}}` seperti T28; 429 tetap `{"detail", "retry_after_s"}`)
- `GET /api/session` (bebas) → `{"authenticated": bool, "setup_required": bool, "setup_allowed": bool,
  "user": {"username", "role"} | null, "expires_in_s": number | null}`. `setup_allowed` = permintaan dari localhost.
  Bidang `auth_required` lama dihapus (login selalu wajib).
- `POST /api/setup` (bebas) `{"username", "password"}` → **201** `{"user", "expires_in_s"}` + cookie (langsung masuk);
  **403** `setup_local_only`; **409** `setup_done`; **400** `invalid_username` / `weak_password`.
- `POST /api/login` `{"username", "password"}` → 200 `{"user", "expires_in_s"}` + cookie; **401** `login_failed`
  (pesan sama untuk nama salah & kata sandi salah); 429.
- `POST /api/logout` → 204 (tetap).
- `POST /api/account/password` `{"current_password", "new_password"}` → 204; **400** `wrong_password` / `weak_password`.
- `GET /api/accounts` → `[{"username", "role", "created_at", "last_login_at"}]`. Waktu = **waktu lokal mesin
  gerbang tanpa zona** (`2026-10-08T00:20:02`, `last_login_at` null bila belum pernah), sama seperti audit. UI
  menampilkannya apa adanya; jangan menambah `Z` (itu membaca waktu lokal sebagai UTC → meleset 7 jam).
- `POST /api/accounts` `{"username", "password"}` → **201** akun; **409** `username_taken`; 400 seperti setup.
- `POST /api/accounts/{username}/password` `{"new_password"}` → 204 (reset oleh admin); **404** `not_found`.
- `DELETE /api/accounts/{username}` → 204; **409** `last_account` / `self_delete`; 404.
- Kode `/ws` 4401 dan cookie sesi tidak berubah.

**UI (Gemini, setelah kontrak disetujui)**: halaman **Setup** (bila `setup_required`; bila `!setup_allowed` tampilkan
"Buka http://localhost:8000 di mesin gerbang"), **Login** dengan nama pengguna, nama pengguna + Keluar + "Ganti kata
sandi" di bilah atas, kartu **Akun** di Pengaturan (daftar, tambah, reset, hapus dengan konfirmasi). **Perbaikan bug
07-10:** katalog APD dimuat ulang setiap kali login berhasil (sekarang hanya sekali saat halaman dibuka → 401 sebelum
login → "APD wajib" kosong setelah login), dengan vitest.

**Ditunda ke rencana jangka panjang**: peran operator terpisah; akun terpusat untuk banyak gerbang (lihat "Akun
terpusat" di bawah).

### Rancangan T53 — manajemen log & penjaga disk (disetujui 08-10)

Tiga jenis log, dipisah karena masa simpan & pembacanya berbeda:

| Jenis | Isi | Tempat | Masa simpan |
| :-- | :-- | :-- | :-- |
| Application | jalannya sistem (kamera, VLM, sesi, galat) | `logs/safeguard.log` (+ `supervisor.log`) | ukuran (`LOG_MAX_BYTES` × `LOG_BACKUP_COUNT`) **dan** umur `LOG_RETENTION_DAYS` |
| Security | login/logout, gagal login, penguncian 429, setup ditolak, akses ditolak (403), akun dibuat/dihapus/reset/ganti sandi, ganti VLM | `logs/security.jsonl` (satu baris JSON per kejadian) | ukuran **dan** umur `SECURITY_LOG_RETENTION_DAYS` |
| Audit | keputusan gerbang per pekerja | SQLite + foto (tetap, retensi T20) | `RETENTION_*` (tidak berubah) |

Pengaman agar log tidak membuat server hang:
- **Asinkron**: semua penulisan log lewat antrean (`QueueHandler` + `QueueListener`); jalur inspeksi tidak pernah
  menunggu disk. Antrean dibatasi `LOG_QUEUE_SIZE`; penuh = catatan dibuang & dihitung, jumlahnya dilaporkan berkala.
- **Pesan berulang** (sama persis) dicatat sekali per `LOG_REPEAT_WINDOW_SECONDS`, lalu "terulang N kali". Security log
  tidak diringkas (setiap kejadian tercatat).
- **Log akses HTTP** rutin di level `LOG_ACCESS_LEVEL` (bawaan WARNING); galat server tetap tercatat.
- **Semua berkas log berbatas** (termasuk `supervisor.log`); salinan lama dihapus menurut umur di siklus retensi.
- **Penjaga disk** (`DISK_CHECK_SECONDS`): sisa ruang `DATA_DIR` < `DISK_WARN_FREE_GB` → log berkas hanya WARNING ke
  atas + peringatan; < `DISK_CRITICAL_FREE_GB` → log berkas aplikasi berhenti (security log tetap). `/api/health`
  bertambah `"disk": {"state": "ok"|"low"|"critical", "free_gb": float}` (tambahan, UI kelak).
- Isi log: tanpa kata sandi, API key, token, foto; alamat IP & nama pengguna = data pribadi → hanya di security log /
  application log dengan masa simpan di atas.

Belum termasuk (diputuskan nanti): unduh log dari dashboard; format JSON + `gate_id` untuk server pusat; tindakan
gerbang saat disk kritis selain log (mis. lampu kuning).

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

### Kontrak API T30 — login admin (disetujui 05-10; **digantikan T51** setelah T51 disetujui & digabung)

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

## Antrean berikutnya (urut menurut risiko — AGENTS.md §2.2a, disusun 27-09, dirapikan 14-10)

| # | Risiko | Task | Alasan risiko / isi |
| :-- | :-- | :-- | :-- |
| 1 | **Tinggi** | **T59 — YOLO menghitung "2 orang" di jalur kosong** (temuan ukur T57 13-10) | Saat jalur kosong, `tools/camera_probe.py` (YOLO `conf=YOLO_CONF`, kelas orang, frame utuh) mencatat 2 orang di 37/37 cuplikan. Bila deteksi itu lolos zona & syarat tubuh utuh, gerbang bisa memeriksa "orang" yang tidak ada (VLM dipanggil, keputusan untuk subjek palsu). Belum diketahui: ada orang/poster di latar, atau deteksi palsu. Langkah 1: cek tanpa kamera apakah lolos zona & pemeriksaan tubuh utuh |
| 2 | ~~Tinggi~~ selesai | ~~T56~~ (selesai 14-10, sisa T56-UI) **+ T38 — penjaga memori GPU & pulih setelah crash Ollama** (naik dari Sedang, temuan bench 14-10) | 13-10: VRAM penuh oleh aplikasi lain → Ollama ±13 dtk / habis waktu 90 dtk, padahal `ollama ps` tetap "100% GPU". 14-10: setelah satu crash Ollama (`no_23`), model dimuat ulang **26% di CPU** (26/29 layer, CLIP di CPU) → 3,6 → 27 dtk per pekerja dan tidak pulih sendiri → antrean tertahan bila utama juga gagal. Isi: deteksi porsi CPU/VRAM sebelum & sesudah panggilan, bongkar-muat ulang model, peringatan operator, panduan menutup aplikasi **Selesai 14-10.** VRAM penuh → T56. Kejadian 26% di CPU terjadi di `bench_vlm` (tidak menjalankan penjaga). Uji nyata penjaga T38 di Ollama sungguhan + YOLO di GPU (mode dGPU): model dipaksa 59% di GPU (`num_gpu` 20) → `check_and_repair` memuat ulang + pemanasan gambar dalam 11 dtk → **100% di GPU**, panggilan berikutnya 1,5 dtk. Di gerbang: diperiksa segera setelah cadangan gagal dan tiap `LOCAL_GPU_CHECK_SECONDS` (60). Sisa: pemulihan setelah crash asli diamati saat uji nyata gabungan (#3) |
| 3 | **Tinggi** | **Uji nyata gabungan (T35 Uji 2 & 3)** | Perubahan besar T36a–d, T37, T38, T39a, T45–T58 + UI T33/T51 belum diuji di gerbang nyata (keputusan, suara, sesi, zona, pemulihan GPU). **Siap dijalankan** |
| 4 | **Tinggi** | **Uji fisik T57 & T58** (ditunda 14-10: pencahayaan kurang) | Kamera terhalang tangan/kardus/kain/plastik, salah alarm jalur kosong; rokok/vape asli + pengecoh (pulpen, sedotan, tangan kotor). Daftar uji di obrolan 14-10, dicatat per jam lalu dicocokkan dengan log & audit **Sebagian 14-10 (uji UI, Gemini utama)**: pengguna memegang rokok asli → 3/3 pemeriksaan MERAH "Membawa Rokok / Vape", dikonfirmasi langkah kedua tiap kali; kamera terhalang 1x tertangkap (kuning, pulih 4 dtk). Waktu putusan kasus rokok ±7 dtk karena jeda kuota Gemini 4 dtk sebelum konfirmasi. Belum: pengecoh (pulpen, sedotan, ponsel, tangan kotor), vape, bungkus di saku, jalur cadangan lokal, kamera tertutup tangan/kain/plastik sistematis |
| 5 | Sedang | **Validasi Gemini untuk prompt T58** — 10 foto 10/10 benar (pagi + sore 14-10, `data/eval/20261014-070915`, `-171309`); sore Gemini lambat (median 5,5 dtk, 4/5 > batas 4 dtk). Sisa: 84 foto penuh bila kuota mengizinkan | Status Gemini kini `outdated` (terakhir diuji T48) → peringatan di log & Pengaturan; uji 10–20 foto dengan jeda RPM |
| 6 | Sedang | **T40 — alternatif mesin VLM lokal** (keputusan setelah uji nyata) | Crash `encoding image` berasal dari llama.cpp (llama.cpp#17422, #17881; ollama#14170), jadi mengganti Ollama dengan llama.cpp langsung kemungkinan tidak menghilangkannya. Bila uji nyata menunjukkan cadangan masih sering bermasalah walau ada penjaga T38: uji coba Qwen2.5-VL 4-bit lewat Transformers (PyTorch) di **proses terpisah** berantarmuka OpenAI-compatible (adaptor sudah mendukung, cukup ganti `.env`), diukur dengan `tools/bench_vlm.py` (akurasi, 0 APD kurang lolos, waktu, VRAM bersama YOLO). vLLM ditinjau untuk produksi Linux/GPU besar (T29). Data sejauh ini: ~2–4 crash per 84 foto. Kriteria tambahan (T48, 05-10): `qwen2.5vl:7b` tidak melihat helm di atas rambut lebat (`apd_10`, salah 4/4; Gemini benar) dan sepatu `apd_4` hanya benar 2/4 — model pengganti harus lolos keduanya |
| 7 | ~~Sedang~~ digabung ke T40 | Helm di atas rambut lebat (`apd_10`) | Pekerja patuh salah ditolak hanya saat cadangan lokal dipakai (Gemini benar). Penyebab (rambut tebal) sudah diketahui sejak T48; 14-10 dicoba ukuran gambar 640/896/1024 → tetap salah (potongan asli < 640 px, token identik). Konfirmasi kedua untuk helm ditolak: bisa meloloskan pekerja tanpa helm. Perbaikan = kemampuan model → syarat model pengganti di T40 (`data/eval/20261014-172106`) |
| 7a | Sedang | **T61 — perbaikan grafik, chip bilah atas & status (Gemini, setelah T56-UI)** (analisa UI/UX 14-10, browser 1440 px & ~400 px, data tiruan) | (1) sumbu Y grafik Laporan: tick ¼/½/¾ dibulatkan → angka dobel (0,1,1,2,2) & garis "4" di 3,5 → pengawas salah baca (`lib/reports.ts` `calculateYAxis`, perlu angka bulat + tes); (2) grafik harian lebar tetap ±1.240 px (`ReportChart` `width`) → halaman Laporan melebar di ponsel, di desktop tidak memenuhi kartu; (3) chip bilah atas terpotong di Laporan/Pengaturan pada 1440 px ("VLM ut…", "admi…"; chip "Gerbang: …" tambahan); (4) lencana validasi "Sebagian" hijau seperti "Teruji" → admin mengira VLM tervalidasi penuh; (5) label grafik "APD terbanyak yang kurang" terpotong padahal batang masih lega. Tambahan dari tinjauan T56-UI 14-10: (6) spanduk "Tutup aplikasi ini" hanya saat `slow`/`partial_gpu`; (7) `localVlm.ts` memakai `seconds()`/`percent()` dari `messages.ts` ("3,6 dtk"); butir (3) kini juga terjadi di Monitoring. Perapian lain (Pengaturan satu kolom, "Belum dinilai" kuning saat siaga, nav sebelum akun dibuat, label y_min, huruf kapital) → T50 |
| 8 | Sedang | Uji fisik tertunda: lampu ESP32 (T47), restart PC sungguhan (T29) | Rancangan diuji tanpa perangkat/simulasi saja |
| 9 | Rendah | Dua orang berdampingan di zona (T36d); T25 sisa latensi | Dicegah batas fisik di lokasi; latensi sudah jauh turun |
| 10 | Rendah | T42 — cicil utang kode (sisa setelah T42a/b) | 24 fungsi > 30 baris (terpanjang `capture._reader_loop` 199, `detector.detect_and_track` 164, `state_manager.update_frame_detections` 101) — daftar di `tests/test_code_hygiene.py`; 8 blok kembar (web: dialog CameraPicker/SnapshotDialog/AdminToken, ZoneSettings/Pengaturan); pesan log di luar `messages.py` (`camera_manager`, `detector`, `audio_engine`, `capture`); angka HUD/resolusi ke config; warna `#000` VideoPanel ke token; nama Indonesia → Inggris saat disentuh |
| 11 | Rendah | T44 — formatter & linter web (audit 28-09) | `ruff format` massal (62 berkas) sebagai commit sendiri; eslint + prettier untuk `web/` (mengubah `web/package*.json`, perlu giliran dependensi) |

Selesai & digabung (dikeluarkan dari antrean 14-10): T51, T57, T58, T46, T47, T45, T30, hapus UI lama + T18, T29, T39b, T41, T28, T43, T42a/b, T48, T53, T54, T55. Gemini antre: T57/T58-UI. Tinjauan Gemini terutang: T45b, T41, T29, T43, T42a, T42b, T48, T53, T54, T55, T57, T58.

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
- **Akun terpusat & peran operator (rencana panjang, keputusan pengguna 07-10):** saat dipasang di banyak gerbang, akun per gerbang merepotkan (karyawan keluar = hapus di setiap gerbang). Arah: akun di server pusat (sejalan dengan basis data terpusat) atau login kantor (SSO/LDAP) bila perusahaan punya; gerbang memeriksa ke pusat dan tetap punya **akun lokal darurat** saat jaringan putus. Peran operator vs admin diaktifkan saat itu (T51 sudah menyiapkan kolom `role` & `require_role`). Risiko dinilai saat rencananya matang.
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

- VRAM puncak 7,6 / 8 GB dengan `qwen2.5vl:7b` + YOLO — risiko OOM bila ada beban GPU lain.
- Ollama kadang crash pada gambar tertentu (ollama/ollama#14170); inspeksi itu jatuh ke jalur gangguan dan diulang.
- Build `web/dist` kini identik antar folder/worktree (akhir baris `web/` dikunci LF lewat `.gitattributes`); kesamaan di Linux CI belum dibuktikan langsung (repo belum punya remote).
- Repo belum punya remote git, jadi CI belum pernah berjalan.
- Monitoring di lebar ~360 px: satu tombol panel video melewati tepi kanan (terpotong, tanpa scroll horizontal) — rapikan di T33 langkah 3.
- Data baca (foto bukti, CSV, riwayat, video langsung) masih terbuka tanpa token di jaringan — ditutup oleh login T30.
