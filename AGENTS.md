# Aturan untuk agen AI (Claude Code, Gemini/Antigravity, dan lainnya)

Berkas ini adalah satu-satunya sumber aturan kerja agen di repo ini. Claude Code
membacanya lewat `CLAUDE.md`; Antigravity membacanya langsung. Rencana, status
task, dan keputusan produk ada di [`docs/RENCANA.md`](docs/RENCANA.md) — baca
sebelum mulai.

**DEPRO — Digital Safety Protection**: gerbang pemeriksaan APD. Kamera → YOLO26
pose (tubuh utuh) → VLM menilai APD → lampu, suara, audit. Backend Python 3.12 +
FastAPI (`backend/`), UI Svelte 5 + TypeScript (`web/`), UI lama (`frontend/`,
dihapus setelah redesign selesai).

## 1. Cara kerja

- **Balas pengguna dalam Bahasa Indonesia.**
- **Satu task per giliran**: kerjakan, verifikasi, laporkan, lalu berhenti sampai
  pengguna memberi aba-aba.
- **Jangan lanjut dengan celah terbuka**: bug atau verifikasi yang tertunda
  ditutup (atau dilaporkan jujur) sebelum menawarkan task berikutnya.
- **Galat baru → cari ke internet dulu** (pesan galat persis, isu GitHub,
  dokumentasi resmi), baru satu tes terarah untuk membuktikan dugaan. Jangan
  menebak lewat banyak putaran eksperimen.
- **Laporkan apa adanya**: tes gagal ditulis gagal, langkah yang dilewati
  disebutkan.
- **Commit ke `master` hanya atas izin pengguna** (commit di branch task sendiri boleh, lihat §2.4). Jangan push.

## 2. Bekerja bersama agen lain (paralel)

Claude Code dan Gemini (Antigravity) boleh bekerja **bersamaan**, dengan aturan:

### 2.1 Ruang kerja terpisah

| Agen | Folder (git worktree) | Branch | Port server |
| :-- | :-- | :-- | :-- |
| **Claude** — juga **integrator** | `ppe_detection_vlm/` (folder utama) | `master` + `claude/<task>` | 8000 |
| **Gemini** | `ppe_detection_vlm-gemini/` (di sebelah folder utama) | `gemini/<task>` | **8001** (`PORT=8001`) |

- **Jangan pernah menyunting folder agen lain.**
- **Cek folder kerja sebelum mulai** (setiap sesi, sebelum perintah git atau
  menyunting berkas): jalankan `git worktree list` dan `git branch --show-current`,
  lalu pastikan folder yang terbuka di IDE adalah folder milikmu di tabel atas.
  Salah folder → berhenti, jangan commit/checkout/reset apa pun, laporkan ke
  pengguna. (Kejadian 25-09-2026: Gemini sempat bekerja di folder utama karena
  Antigravity membuka `ppe_detection_vlm/`, bukan `ppe_detection_vlm-gemini/`.)
- Jangan `checkout`/`reset`/`rebase` branch milik agen lain.
- Worktree Gemini **tidak punya `backend/.env`** (sengaja): server Gemini jalan
  tanpa API key gerbang, jadi kuota VLM cloud aman. Uji VLM memakai penyedia
  tiruan (tes) atau VLM lokal Ollama.
- Worktree Gemini punya `data/` kosong sendiri (audit asli tidak tersentuh).
- **Kamera hanya bisa dipakai satu server.** Uji dengan kamera sungguhan
  dilakukan bergiliran; di luar itu uji tanpa kamera.

### 2.2 Papan tugas — klaim dulu, baru kerjakan

- Papan tugas ada di `docs/RENCANA.md` bagian **"Papan tugas"**. Sebelum mulai,
  agen **mengklaim** task: isi kolom Pemilik, Branch, Status `dikerjakan`, dan
  **Area berkas** yang akan disentuh — commit perubahan papan itu sendirian
  (`docs: klaim <task>`) supaya agen lain melihatnya.
- **Klaim selalu dicatat di `master`**, bukan di branch task: branch lain tidak
  melihat isi branch-mu. Karena `master` ada di folder integrator, agen lain
  menyampaikan klaimnya lewat pengguna dan **integrator (Claude) yang
  meng-commit** perubahan papan itu (hanya `docs/RENCANA.md`). Perubahan status
  berikutnya (`tinjau`) boleh ditulis di branch task, lalu ikut saat digabung.
- Setelah klaim tercatat, buat/pindah ke branch task di foldermu sendiri
  dari `master` terbaru (`git rebase master` bila branch sudah ada).
- **Satu agen hanya mengerjakan satu task** pada satu waktu.
- Task yang area berkasnya **beririsan** dengan task yang sedang dikerjakan agen
  lain tidak boleh diklaim — pilih task lain atau tunggu.
- Pembagian bawaan: **Claude = UI (`web/`)**, **Gemini = backend (`backend/`,
  `tests/`, `tools/`)**, kecuali pengguna menentukan lain.

### 2.2a Prioritas: risiko tertinggi dikerjakan lebih dulu

Setiap task baru, dan setiap kali rencana disusun ulang, diberi **tingkat risiko**
dengan alasan satu kalimat. Urutan kerja: **Tinggi → Sedang → Rendah**; dalam
tingkat yang sama, task yang memblokir task lain lebih dulu. Pengguna boleh
menimpa urutan. Risiko dinilai ulang setelah ada hasil uji atau temuan baru.

| Tingkat | Kapan |
| :-- | :-- |
| **Tinggi** | Bisa membuat gerbang meloloskan APD kurang atau keputusan yang tidak tervalidasi; kebocoran data pribadi / akses tanpa hak; hilang atau rusaknya data audit; gerbang tidak berfungsi |
| **Sedang** | Pekerja patuh salah ditolak; antrean lambat; keandalan menurun tetapi ada jalan pintas manual; salah konfigurasi yang terdeteksi |
| **Rendah** | Tampilan, kerapian kode, dokumentasi, fitur baru yang belum dipakai |

Fitur besar yang masih tahap perencanaan (mis. identitas wajah, IoT/palang) dinilai
risikonya saat rencananya matang, sebelum dikerjakan.

### 2.3 Berkas bersama (titik rawan bentrok)

Berkas ini dipakai hampir semua task. Aturannya: **hanya menambah** (entri baru
di bagian yang sesuai), tidak mengubah atau memindah entri milik task lain, dan
perubahan dijelaskan di pesan commit.

- `backend/config.py`, `backend/messages.py`, `backend/.env.example`,
  `backend/ppe_rules.py`
- `web/src/lib/messages.ts`, `web/src/lib/settings.ts`,
  `web/src/lib/api/types.ts`, `web/src/styles/tokens.css`
- `docs/RENCANA.md`, `README.md`, `AGENTS.md`

Khusus:

- **Kontrak API dulu.** Bila backend (Gemini) membuat/mengubah endpoint yang
  dipakai UI (Claude), bentuk JSON-nya ditulis dulu di `docs/RENCANA.md` (atau
  sebagai tipe di `web/src/lib/api/types.ts`) dan disetujui, baru dikerjakan.
- **Dependensi** (`backend/requirements*.txt/.lock`, `web/package*.json`): hanya
  satu agen per putaran yang boleh mengubahnya, dan wajib ditulis di papan tugas.
- **`web/dist/` hanya dibangun ulang oleh integrator** setelah penggabungan.
  Branch agen tidak meng-commit `web/dist` (menghindari bentrok berkas hasil build).
  `scripts/check.py` ikut membangunnya — di branch agen, batalkan perubahan itu
  sebelum commit: `git restore --staged --worktree web/dist`.

### 2.4 Selesai → tinjau → gabung

1. Agen menyelesaikan task di branch-nya sendiri, `python scripts/check.py`
   lolos, lalu commit **di branch itu** (boleh tanpa menunggu izin, karena belum
   menyentuh `master`).
2. Status di papan tugas diubah ke `tinjau`, disertai ringkasan & cara uji.
3. **Agen lain meninjau diff** (hanya membaca, temuan ditulis untuk pengguna).
4. **Penggabungan ke `master` hanya atas persetujuan pengguna**, dikerjakan
   integrator di folder utama: rebase/merge branch → `python scripts/check.py`
   → `npm run build` → commit `web/dist` → status `selesai`.
5. Setelah `master` berubah, agen lain **rebase branch-nya ke `master`** sebelum
   melanjutkan (di folder masing-masing).

### 2.5 Komunikasi

Agen tidak bisa saling memanggil; pengguna yang mengoper pesan. Catatan serah
terima, pertanyaan untuk agen lain, dan keputusan kecil ditulis di kolom
**Catatan** papan tugas, bukan hanya di obrolan.

## 3. Larangan

- **Jangan membaca, grep, atau menyunting `backend/.env`** (berisi API key).
  Gunakan `backend/.env.example` dan `backend/config.py`. Jangan pernah mencetak
  API key ke log, terminal, atau pesan.
- **`picture_test/` berisi foto orang sungguhan**: jangan di-commit, disalin
  keluar, atau diunggah.
- **Jangan menyunting `iot/wokwi_simulation/README.md`** (catatan simulasi, di
  luar lingkup).
- Jangan menghapus atau menimpa `data/` (audit & foto bukti produksi). Larangan ini
  untuk agen; pembersihan otomatis fitur retensi (T20, angka di `config.py`) tetap
  berjalan. Uji retensi hanya di folder sementara pytest.
- Jangan menjalankan panggilan VLM cloud berulang tanpa perlu: kuota free tier
  API gerbang terbatas (~15 RPM, ~500/hari per project).

## 4. Aturan kode

- **Tanpa hard code.** Nilai, teks, warna, kunci item, dan pemetaan diambil
  dari satu sumber:
  - backend: `backend/config.py` (lewat `.env`), `backend/messages.py` (teks &
    prompt), katalog `backend/ppe_rules.py` (item APD, label, ikon, suara);
  - frontend: `web/src/lib/messages.ts` (teks), `web/src/lib/settings.ts`
    (angka UI), `web/src/styles/tokens.css` (warna, tipografi, jarak), katalog
    APD dari API.
- **Clean code**: fungsi kecil bertanggung jawab tunggal, nama jelas, tanpa
  duplikasi, logika terpisah dari tampilan (logika murni di `web/src/lib/`,
  komponen hanya merakit).
- **Perubahan logika wajib disertai tes** (pytest di `tests/`, vitest di
  `web/src/**/*.test.ts`).
- **Bahasa kode: Inggris.** Nama variabel, fungsi, kelas, berkas, kunci
  konfigurasi, dan kunci JSON/API **baru** berbahasa Inggris. Komentar &
  docstring boleh Bahasa Indonesia. Teks untuk pengguna (UI, suara, prompt,
  pesan log) tetap di `messages.py` / `messages.ts` dalam bahasa produk
  (Indonesia). Nama lama berbahasa Indonesia diganti bertahap saat berkasnya
  disentuh; kunci yang sudah tersimpan atau jadi kontrak (kolom DB,
  `runtime_settings`, JSON VLM `orang_nyata`, endpoint) hanya diganti lewat
  task sendiri dengan migrasi.
- Ikuti gaya di sekitarnya: komentar & docstring jelaskan *mengapa*, bukan *apa*.

### 4.1 Daftar periksa kode (setiap perubahan, sebelum `tinjau`)

Berlaku untuk kode **baru atau yang disentuh**; utang lama dicicil lewat antrean
risiko (§2.2a), bukan dirombak sekaligus di luar task.

1. **Efisiensi**
   - Jalur panas = per frame (`detector`, `state_manager`, telemetri) dan per
     inspeksi (VLM, audit). Perubahan di jalur ini diukur dulu (`cProfile` /
     `time.perf_counter`) dengan beban kecil dan besar (1 vs 20 orang; 100 vs
     100.000 baris audit), angkanya ditulis di laporan task.
   - Hindari loop bersarang atas orang/ID/baris audit bila ada struktur
     O(1)/O(n) (dict, set, indeks SQLite). Kueri baru ke `worker_inspections`
     dicek memakai indeks (`EXPLAIN QUERY PLAN`).
2. **Clean code**
   - `ruff check` lolos (lewat `scripts/check.py`); fungsi baru ≤ 30 baris
     badan — lebih panjang dipecah atau diberi alasan di laporan.
   - Tidak menyalin blok ≥ 6 baris: angkat ke fungsi/komponen bersama.
   - Nama jelas; fungsi satu tanggung jawab; logika murni terpisah dari I/O & UI.
   - Formatter: `ruff format` hanya untuk berkas **baru** (format massal berkas
     lama menunggu task sendiri supaya diff tinjauan tetap terbaca).
3. **Hardcode & rahasia**
   - Angka/teks/warna ke sumber tunggal (daftar di atas); konstanta modul
     bernama (mis. `LEFT_ANKLE`) boleh untuk fakta tetap (indeks COCO, kode
     HTTP), tapi **satu definisi** — jangan diulang di beberapa modul.
   - Tidak ada API key, token, password, atau path mesin di kode/berkas yang
     di-commit; nilai uji memakai tiruan jelas (`kunci-uji`).
   - `tests/test_code_hygiene.py` menjaga: tidak ada pola rahasia di berkas
     terlacak, `backend/.env` tidak terlacak, warna hex UI hanya di
     `tokens.css`, dan fungsi Python panjang tidak bertambah (daftar utang
     hanya boleh menyusut).

## 5. Keputusan produk yang tidak boleh dilanggar

- **Semua keputusan APD oleh VLM.** Utama = VLM cloud (penyedia bebas, bawaan
  Gemini), cadangan = VLM lokal (Ollama `qwen2.5vl:7b`), peralihan otomatis.
  Heuristik OpenCV sudah dibuang — jangan dihidupkan lagi.
- **Lampu/warna merah hanya untuk APD kurang.** Arahan posisi & peringatan =
  kuning; bila VLM utama & cadangan gagal pekerja *diminta menunggu*, bukan
  ditolak.
- Keputusan terkunci per sesi sampai jalur inspeksi kosong.
- **Nama penyedia/model VLM tidak tampil di UI operator** — cukup "VLM utama /
  cadangan / gangguan"; nama lengkap hanya di log dan Pengaturan admin.
- Operator hanya menjalankan & mengatur; tidak ada tombol yang mengubah cara
  gerbang memutuskan saat berjalan.
- OS produksi belum tentu Windows: rancangan netral OS (produksi Linux/Docker).

## 6. Perintah

Environment Python (sekali): lihat README "Prasyarat Lingkungan"
(`uv venv` + `uv pip sync --torch-backend cu132 backend/requirements-dev.lock`).

```bash
python -m backend                 # server (dari akar repo)
python scripts/check.py           # WAJIB lolos sebelum commit: ruff + pytest + web (cek tipe, vitest, build)
cd web && npm ci                  # sekali, bila mengubah UI baru
cd web && npm run dev             # Vite http://localhost:5173 (proxy ke backend :8000)
cd web && npm run build           # lalu commit web/dist (gerbang tidak punya Node.js)
```

## 7. Kebersihan proses (mesin pengembang: RAM 16 GB, disk sempit)

- Jalankan pekerjaan berat per langkah, bukan satu skrip latar panjang.
- Setelah proses latar dihentikan, periksa & matikan proses yatim (server
  `-m backend`, skrip evaluasi) — di Windows, mematikan shell induk tidak
  mematikan anaknya.
- Bongkar model Ollama yang dipakai uji (`ollama stop <model>`).
