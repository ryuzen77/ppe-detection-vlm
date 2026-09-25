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
- **Commit hanya bila diminta pengguna.** Jangan push.

## 2. Bekerja bergantian dengan agen lain

- **Satu agen aktif pada satu waktu** di folder repo ini. Sebelum serah terima,
  pekerjaan di-commit (atas izin pengguna) supaya agen berikutnya mulai dari
  pohon kerja bersih.
- Bila harus paralel: agen kedua bekerja di **git worktree/branch terpisah**;
  penggabungan dilakukan satu pihak setelah `python scripts/check.py` lolos.
- Perbarui `docs/RENCANA.md` saat status task atau keputusan berubah.

## 3. Larangan

- **Jangan membaca, grep, atau menyunting `backend/.env`** (berisi API key).
  Gunakan `backend/.env.example` dan `backend/config.py`. Jangan pernah mencetak
  API key ke log, terminal, atau pesan.
- **`picture_test/` berisi foto orang sungguhan**: jangan di-commit, disalin
  keluar, atau diunggah.
- **Jangan menyunting `iot/wokwi_simulation/README.md`** (catatan simulasi, di
  luar lingkup).
- Jangan menghapus atau menimpa `data/` (audit & foto bukti produksi).
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
- Ikuti gaya di sekitarnya: komentar & docstring berbahasa Indonesia, jelaskan
  *mengapa*, bukan *apa*.

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
