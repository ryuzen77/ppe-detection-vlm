# Rencana DEPRO — status, antrean, dan keputusan

Rencana bersama untuk semua agen (lihat [`AGENTS.md`](../AGENTS.md)). Perbarui
berkas ini setiap kali status task atau keputusan berubah. Riwayat rinci ada di
pesan commit (`git log`).

Terakhir diperbarui: 18-10-2026. Task `selesai`, kontrak/rancangan task selesai, dan catatan lama dipindah ke [`arsip/RENCANA-selesai.md`](arsip/RENCANA-selesai.md) (tidak perlu dibaca rutin; cari di sana bila butuh angka uji atau alasan keputusan lama).

## Papan tugas

Aturan klaim & penggabungan: [`AGENTS.md` §2](../AGENTS.md). Klaim dulu (isi
Pemilik, Branch, Status `dikerjakan`, Area berkas), commit papan ini sendirian,
baru mulai. Status: `antre` → `dikerjakan` → `tinjau` → `selesai`.

| Task | Pemilik | Branch | Status | Area berkas | Catatan |
| :-- | :-- | :-- | :-- | :-- | :-- |

### Rancangan T34 — identitas wajah (FR) untuk audit per pekerja (disusun 18-10; sedang dikerjakan: T34m/m2/a selesai, T34b1/b2 tinjau)

**Risiko: Tinggi** — data biometrik = data pribadi **spesifik** (UU PDP No. 27/2022); salah kenal = audit menunjuk orang yang salah.

**Tujuan (pengguna 18-10):** audit per pekerja, supaya pelanggaran APD bisa ditindaklanjuti (teguran / arahan K3) ke
orangnya. Kartu ID saja tidak cukup (bisa dipinjamkan). Setelah keputusan APD, suara menyebut nama:
"Anda lolos, silakan masuk, <Nama>".

**Batas yang tidak berubah (AGENTS.md §5):** keputusan APD tetap 100% oleh VLM. FR hanya menentukan *siapa*; tidak
pernah mengubah lampu hijau/merah. Pekerja yang tidak dikenali tetap diperiksa APD-nya seperti biasa.

**Alur:**

```text
Masuk jalur → tubuh utuh & diam (jendela kesiapan T46, sudah ada)
   ├─ FR: wajah dari frame-frame diam → embedding → cocokkan → identitas DIKUNCI per sesi
   └─ VLM menilai APD (tidak bergantung FR)
→ keputusan → suara (+ nama bila lolos & dikenali) → audit: pekerja + keyakinan FR + hasil APD
```

FR dikerjakan di dalam jendela diam yang sudah ada, jadi tidak menambah waktu antre. Bila FR belum yakin saat
keputusan APD keluar: suara tanpa nama, audit "tidak dikenali". FR **tidak pernah menunggu tanpa batas** (penyebab
lambat pada sistem absensi pengguna sebelumnya): skor tertinggi di bawah ambang = "tidak dikenali" seketika.

**Keputusan pengguna (18-10, mengikuti usulan integrator):**

1. Lolos: nama disebut. Ditolak: suara hanya menyebut item yang kurang; nama tercatat di audit untuk supervisor
   (tidak diumumkan di depan orang lain).
2. Tidak dikenali (belum terdaftar / wajah tertutup / ragu): APD tetap diperiksa, suara tanpa nama, audit "tidak dikenali".
3. Pendaftaran oleh admin di Pengaturan: 3–5 foto lewat kamera gerbang, setelah persetujuan tertulis pekerja.
4. Yang disimpan hanya **embedding** (bukan foto wajah pendaftaran). Ganti model FR = daftar ulang.
5. Persetujuan, DPIA, dan kebijakan dari HR/Legal perusahaan (di luar kode; wajib sebelum dipakai sungguhan).
6. **Satu gerbang dulu, SQLite terenkripsi** (bukan PostgreSQL/pgvector). pgvector untuk server pusat banyak gerbang
   sudah direncanakan (18-10, lihat "PostgreSQL + pgvector untuk data wajah terpusat"); T34b menyiapkan antarmukanya.

**Teknis:**

- Model ringan, CPU (VRAM 8 GB sudah penuh oleh YOLO + VLM cadangan): kandidat **YuNet** (deteksi) + **SFace**
  (embedding 128 dimensi) dari OpenCV Zoo. **Lisensi diperiksa dulu**; model InsightFace tidak dipakai (bobotnya
  non-komersial). Target: ≤ 50 ms FR per sesi di CPU (diukur, bukan ditebak).
- Pencarian: semua embedding dimuat ke memori sebagai matriks numpy saat server menyala, cosine `matriks @ wajah`.
  Terukur 18-10 di laptop pengembang: 1.000 pekerja 0,008 ms, 10.000 pekerja 0,084 ms, 100.000 pekerja 0,8 ms per
  pencarian (128 dimensi) → tidak perlu indeks vektor untuk satu gerbang.
- Keyakinan: voting beberapa frame terbaik (jumlah dibatasi, angka di `config.py`), ambang ketat. Salah nama lebih
  buruk daripada tanpa nama: ragu → "tidak dikenali". Ambang awal ditetapkan dari data uji pendaftaran nyata.
- Suara nama: MP3 per pekerja dibuat **sekali saat pendaftaran** (gTTS butuh internet saat itu saja), diputar offline.

**Penyimpanan & enkripsi (SQLite di `DATA_DIR`):**

- Tabel baru (nama final saat implementasi): pekerja (id, nama, nomor pegawai, aktif, tanggal & versi persetujuan,
  didaftarkan oleh) dan embedding (id pekerja, embedding **terenkripsi AES-GCM** + nonce, versi model).
- Kunci enkripsi di luar `DATA_DIR` (usul: variabel baru di `backend/.env`, sehingga salinan/cadangan `data/` saja
  tidak membuka data wajah). Kunci hilang = semua pekerja didaftarkan ulang. Disarankan juga enkripsi disk mesin
  gerbang (BitLocker / LUKS).
- Dependensi baru kemungkinan `cryptography` → satu putaran dependensi (AGENTS.md §2.3).
- Audit `worker_inspections`: kolom baru id pekerja + keyakinan FR (migrasi skema bernomor seperti sebelumnya).
  Laporan & CSV: kolom nama, filter per pekerja.

**Pemetaan UU PDP:**

| Kewajiban | Pemenuhan di rancangan |
| :-- | :-- |
| Persetujuan jelas & spesifik (Pasal 20) | Formulir persetujuan; tanggal & versinya disimpan per pekerja |
| Minimisasi | Hanya embedding, tanpa foto wajah pendaftaran |
| Keamanan data spesifik | Embedding terenkripsi AES-GCM, kunci di luar `DATA_DIR`, enkripsi disk |
| Pembatasan akses | Hanya admin (akun & peran T51) yang mendaftar/melihat/menghapus |
| Jejak akses | Daftar/hapus/akses data pekerja dicatat di `security.jsonl` (T53) |
| Hak hapus & masa simpan | Tombol hapus data wajah (embedding + MP3 nama); **hapus otomatis 30 hari setelah pekerja nonaktif** (keputusan 18-10) |
| DPIA & kebijakan | Dokumen HR/Legal (di luar kode) |

**Risiko & mitigasi:** salah kenal (ambang ketat + voting; ragu = tidak dikenali); masker/kacamata gelap menurunkan
akurasi (diukur di T34a); wajah terlalu kecil di kamera tubuh utuh 1280×720 (diukur di T34a; mungkin perlu 1080p atau
kamera kedua setinggi wajah); foto/layar dipakai menyamar (FR hanya untuk audit, bukan kunci akses; deteksi
*liveness* ditinjau bila kelak dipakai untuk akses); nama terdengar orang lain (hanya saat lolos).

**Tahapan (masing-masing task sendiri, klaim di papan):**

0. **T34m — evaluasi model nyata SEBELUM dipakai di proyek (keputusan pengguna 18-10).** Tidak ada model yang dipasang
   ke gerbang sebelum lolos evaluasi ini. Alat ukur sendiri di `tools/` (pola `tools/bench_vlm.py`), hasilnya ditulis
   di sini. Diukur per kandidat (YuNet + SFace dan kandidat lain yang lisensinya boleh dipakai komersial):
   - **Kecepatan** di CPU laptop gerbang: median & p95 deteksi + embedding per wajah, dan waktu total FR per sesi;
     dampak ke laju YOLO/VLM yang berjalan bersamaan.
   - **Akurasi:** tingkat salah terima (FAR, orang lain dikenali sebagai pekerja) dan salah tolak (FRR, pekerja
     terdaftar tidak dikenali) pada beberapa ambang → pilih ambang dengan FAR sangat rendah (salah nama lebih buruk
     daripada tanpa nama).
   - **Ketahanan:** dengan helm, masker, kacamata, wajah miring, cahaya kurang, dan ukuran wajah kecil (jarak kamera
     gerbang).
   - **Data uji:** relawan yang memberi persetujuan tertulis; foto uji **tidak di-commit, tidak diunggah** (aturan sama
     dengan `picture_test/`); dataset publik hanya bila lisensinya mengizinkan.
   - **Kriteria lolos** ditetapkan pengguna sebelum pengukuran (mis. FAR target, FRR maksimum, waktu FR maksimum).
   - **Kandidat (analisa internet 18-10; detektor sama untuk semua: YuNet, MIT):**

     | # | Pengenal | Lisensi bobot | Beban | Akurasi dilaporkan | Catatan |
     | :-- | :-- | :-- | :-- | :-- | :-- |
     | 1 | SFace (OpenCV Zoo) | Apache-2.0 | ringan, 128-d, sudah ada di OpenCV terpasang | LFW ±99,4–99,6% | patokan dasar |
     | 2 | Intel `face-reidentification-retail-0095` (OpenVINO) | **Apache-2.0 (dikonfirmasi 18-10: `model.yml` → LICENSE repo)** | sangat ringan (MobileNetV2, 1,1 jt param), 256-d | LFW 99,47% | kemungkinan tercepat; format OpenVINO IR (butuh runtime OpenVINO); data latih tidak disebut; repo *maintenance mode* (tidak diperbarui) |
     | 3 | AuraFace-v1 | Apache-2.0 (data latih "berlisensi komersial", tidak dirinci) | berat (ResNet100) | CFP-FP 95,18 (ArcFace 98,87) | alternatif ArcFace komersial |
     | 4 | dlib ResNet | bobot *public domain* (data latih VGG/FaceScrub perlu dicek) | sedang, 128-d | LFW 99,38% | model 2017; pasang dlib di Windows bisa sulit |
     | ~~5~~ | ~~AdaFace IR101 (versi NVIDIA)~~ | **GUGUR (dicek 18-10)** | — | — | NVIDIA menyatakan bukan buatannya; versi NGC = kemasan TensorRT dari CVLFace AdaFace IR101 WebFace12M; kartu model sumber tanpa lisensi ("ikuti lisensi dataset"); WebFace12M disebut hanya untuk riset akademik |

     Kandidat tersisa 4 (1–4). Pengganti #5 opsional: varian SFace terkuantisasi int8 (lisensi sama) sebagai pembanding kecepatan.
     Semua kandidat dilatih dari data wajah web; ketentuan dataset latih (kecuali AuraFace yang menyebut data berlisensi komersial)
     tetap ditanyakan ke HR/Legal sebelum produksi.
     Gugur karena lisensi bobot: InsightFace (`buffalo_l`/ArcFace, non-komersial), EdgeFace (CC BY-NC-SA 4.0),
     AdaFace asli WebFace4M/12M (dataset non-komersial), facenet-pytorch VGGFace2 (tidak jelas / dataset riset).
   - **Kriteria lolos (DISETUJUI pengguna 18-10):** FAR ≤ 0,1% (salah nama paling dihindari); FRR ≤ 5% tanpa
     masker (kondisi bermasker dicatat terpisah); FR total ≤ 50 ms per sesi di CPU.
   - **Usul data uji:** ≥ 10 relawan berpersetujuan tertulis, foto lewat kamera gerbang dalam kondisi tanpa helm /
     helm / helm + masker / kacamata / dekat & jauh, ditambah beberapa orang "tidak terdaftar" untuk mengukur FAR.
   - **Lingkungan uji:** env conda terpisah (mis. `fr_eval`) karena kandidat butuh paket berbeda (onnxruntime,
     openvino, dlib); hanya model pemenang yang masuk kunci dependensi proyek. Lisensi tiap kandidat dipastikan dari
     berkas lisensinya sebelum diuji serius; data latih kandidat 3 & 4 ditanyakan ke HR/Legal sebelum produksi.
   - **Hasil langkah 2 — kecepatan CPU (18-10, `tools/fr_eval/`, laptop i7-13620H, gambar acak berbenih, 200 putaran).**
     Sesi = deteksi YuNet pada potongan 640×640 + align + embedding + cari 10.000 wajah (1 percobaan), p95:

     | Kandidat | MB | dim | emb p95 (bawaan / 2 thread) | sesi p95 (bawaan / 2 thread) | ≤ 50 ms |
     | :-- | --: | --: | --: | --: | :-- |
     | Intel 0095 | 4,7 | 256 | 2,5 / 4,1 ms | 13,8 / 16,9 ms | ya |
     | SFace | 38,7 | 128 | 4,5 / 10,2 ms | 15,7 / 23,0 ms | ya |
     | SFace int8 | 9,9 | 128 | 19,3 / 25,7 ms | 30,5 / 38,5 ms | ya (lebih lambat dari fp32 di OpenCV 5) |
     | AuraFace | 260,7 | 512 | 50,6 / 104,4 ms | 61,8 / 117,3 ms | **tidak** |
     | dlib | 31,6 | 128 | 226 / 231 ms | 237 / 244 ms | **tidak** (build conda-forge CPU tanpa BLAS) |

     YuNet p95: 1280×720 = 24,8 ms, 640×640 = 11,0 ms (2 thread: 29,0 / 12,6). Pencarian 10.000 wajah < 0,3 ms
     (SQLite + numpy cukup). Deteksi pada frame penuh 720p menambah ±14 ms → tetap pakai potongan badan atas.
     **Lolos kecepatan: Intel 0095, SFace, SFace int8.** AuraFace & dlib gugur di kriteria kecepatan (AuraFace masih
     bisa dipakai bila ada GPU, tetapi kriteria disepakati CPU). Belum diukur: dampak ke laju YOLO/VLM saat berjalan
     bersamaan (diukur di T34a dengan kamera). Catatan env: jalankan setelah `conda activate fr_eval`; tanpa aktivasi,
     numpy MKL crash (`0xc06d007f`, DLL Intel OpenMP tidak ditemukan).
   - **Hasil langkah 3a — akurasi pada LFW (18-10, T34m2, `tools/fr_eval/eval_lfw.py` & `eval_openset.py`).**
     Semua 13.233 foto terdeteksi YuNet. Align = kemiripan kuadrat terkecil 5 titik (Umeyama, sama dengan
     `alignCrop` OpenCV); versi awal dengan `estimateAffinePartial2D` (RANSAC) menurunkan SFace 99,35% → 99,07%.

     | Kandidat | Akurasi 10-fold (publikasi) | FRR @ FAR 1:1 0,1% | FRR @ FAR 1:1 0,01% |
     | :-- | --: | --: | --: |
     | SFace | 99,35% (±99,4%) | 1,01% | 2,14% |
     | Intel 0095 | 99,42% (99,47%) | 1,03% | 2,85% |
     | SFace int8 | 99,13% | 1,25% | 3,00% |

     **Uji 1:N (yang berlaku di gerbang):** 3 foto pendaftaran per pekerja; orang asing = tokoh tak terdaftar.
     Ambang 1:1 (FAR 0,1%) **tidak layak**: 32–40% orang asing diberi nama pekerja pada galeri 305, 86–88% pada
     galeri 3.305. Ambang harus dipatok dari FPIR (orang asing diberi nama ≤ 0,1%):

     | Kandidat | Galeri 305: ambang / tak dikenali / salah nama | Galeri 3.305: ambang / tak dikenali / salah nama |
     | :-- | :-- | :-- |
     | Intel 0095 | 0,547 / **2,1%** / 0,05% | 0,771 / **49,5%** / 0,00% |
     | SFace | 0,553 / 2,7% / 0,05% | 0,770 / 59,0% / 0,00% |
     | SFace int8 | 0,566 / 4,2% / 0,05% | 0,744 / 51,9% / 0,00% |

     **Waktu foto → keputusan** (300 pekerja + 300 orang asing, CPU, p50/p95): Intel 0095 4,7/6,4 ms vs asing
     4,9/6,4 ms; SFace 7,8/8,5 vs 7,9/9,3 ms; SFace int8 19,1/22,3 vs 18,6/21,3 ms. **Orang tak dikenal tidak
     lebih lama** (satu perkalian matriks ke seluruh galeri, lalu banding ambang; tanpa ulang/tunggu). Deteksi di sini
     pada foto 250×250 (±2 ms); di gerbang potongan 640×640 ±11 ms → ±14–16 ms per sesi.
     **Kesimpulan sementara:** Intel 0095 unggul (tercepat, FNIR 1:N terendah). Galeri ±300 orang memenuhi kriteria
     (FPIR 0,1%, FNIR ≤ 5%); galeri ribuan tidak (separuh pekerja tak dikenali) → ukuran galeri per gerbang
     menentukan, perlu keputusan pengguna (jumlah pekerja; atau model lebih kuat di GPU). Batasan: LFW = foto berita
     tak terkontrol (pendaftaran di kamera gerbang biasanya memberi skor pekerja lebih tinggi); galeri 3.305 diisi
     orang berfoto pendaftaran 1; tanpa helm/masker → uji nyata tetap wajib.
   - **Keputusan pengguna 18-10: asumsi ±300 pekerja per gerbang → model terpilih Intel 0095** (OpenVINO, CPU;
     SFace sebagai cadangan bila OpenVINO bermasalah). Ambang awal dari LFW galeri 305 ≈ 0,55 (FPIR 0,1%), dikalibrasi
     ulang dengan foto nyata di T34a/uji relawan. Konsekuensi untuk T34b: jumlah pekerja terdaftar dipantau — bila jauh
     melewati batas yang teruji (nilai di `config.py`), admin diberi peringatan karena orang tak dikenali naik tajam
     (galeri 3.305 di LFW: separuh pekerja tak dikenali); saat itu evaluasi ulang (model GPU atau galeri per shift).
   - **Kebijakan pendaftaran (pengguna 18-10):** pekerja tanpa masker; **kacamata biasa boleh dan WAJIB didaftarkan
     dengan kacamata**; **kacamata hitam tidak boleh**. Usul T34b: simpan beberapa templat per pekerja (mis. dengan &
     tanpa kacamata, dengan & tanpa helm) dan ambil skor tertinggi, bukan satu templat rata-rata.
   - **Hasil T34a (18-10, kamera Logitech HD Pro C920 1080p, `tools/fr_eval/face_probe.py`, 1 orang, Intel 0095,
     acuan = kondisi pertama tanpa helm, ambang 0,55; median per kondisi):**

     | Resolusi | Kondisi | Wajah terdeteksi | Lebar wajah / jarak mata | Mirip acuan | Frame ≥ 0,55 |
     | :-- | :-- | --: | --: | --: | --: |
     | 1920×1080 | tanpa helm (acuan) | 100% | 56 / 26 px | 0,87 | 90% |
     | 1920×1080 | helm | 97% | 66 / 30 px | 0,79 | 93% |
     | 1920×1080 | kacamata | 100% | 71 / 33 px | 0,55 | 47% |
     | 1920×1080 | helm + kacamata | 97% | 76 / 33 px | 0,40 | 0% |
     | 864×480 | tanpa helm (acuan) | 100% | 43 / 20 px | 0,96 | 100% |
     | 864×480 | helm | 100% | 35 / 16 px | 0,73 | 100% |
     | 864×480 | kacamata | 99% | 40 / 18 px | 0,62 | 79% |
     | 864×480 | helm + kacamata | 100% | 40 / 18 px | 0,63 | 100% |
     | 1920×1080, **acuan berkacamata** | kacamata (acuan) | 100% | 70 / 32 px | 0,98 | 100% |
     | 1920×1080, acuan berkacamata | helm + kacamata | 100% | 68 / 31 px | 0,96 | 100% |
     | 1920×1080, acuan berkacamata | helm (kacamata dilepas) | 100% | 70 / 32 px | 0,80 | 100% |
     | 1920×1080, acuan berkacamata | tanpa helm & kacamata | 100% | 67 / 32 px | 0,70 | 97% |

     Helm tidak menurunkan skor; kacamata yang tidak didaftarkan menurunkan tajam, sedangkan **pendaftaran dengan
     kacamata lolos di semua kondisi** (0,70–0,98) → kebijakan di atas terbukti pada 1 orang. Di 480p jarak
     mata 16–20 px (di bawah ±30 px yang umum dibutuhkan FR); skor tinggi di 480p tidak berarti aman karena acuan diambil
     di momen yang sama dan risiko orang LAIN mirip naik pada wajah kecil → **FR memakai potongan kepala dari frame
     resolusi penuh** (YOLO boleh tetap di frame kecil). YuNet frame penuh 1080p ±43 ms → di gerbang hanya pada potongan.
     Laju kamera 6–10 fps di 720p/1080p (ruangan redup; kamera menurunkan fps saat gelap) perlu dicek dengan cahaya cukup.
1. **T34a — uji ukuran wajah (fisik, perlu pengguna di depan kamera):** ukur piksel wajah dari posisi kamera
   sekarang dengan/tanpa helm, masker, kacamata; ukur waktu YuNet + SFace di CPU. **Tidak menyimpan data wajah.**
   Hasilnya menentukan kamera cukup atau perlu tambahan.
2. **T34b — pendaftaran & penyimpanan terenkripsi** (backend): tabel, enkripsi, daftar/hapus, log keamanan, tes.
   **Keputusan pengguna 18-10:**
   - **Persetujuan = admin mencentang** "persetujuan tertulis sudah ditandatangani" saat mendaftar; disimpan per
     pekerja: waktu, admin yang mencentang, versi formulir (teks & versi di `messages.py`/`config.py`). Pendaftaran
     ditolak tanpa centang. Formulir kertasnya tetap dari HR/Legal.
   - **Hapus otomatis 30 hari setelah pekerja dinonaktifkan:** embedding + MP3 nama dihapus permanen, baris pekerja
     disisakan tanpa data wajah (riwayat audit tetap bernama). Angka di `config.py`; berjalan di pembersihan retensi
     yang sudah ada (T20); setiap penghapusan dicatat di `security.jsonl`. Hapus manual oleh admin tetap tersedia
     (langsung, tanpa menunggu 30 hari).
   - **Disiapkan untuk PostgreSQL + pgvector** (rencana panjang di bawah): akses data pekerja lewat satu antarmuka
     repository (`WorkerStore`: daftar, tambah templat, nonaktifkan, hapus, muat galeri); T34b hanya membuat
     implementasi SQLite. Tiap templat menyimpan versi model & dimensi supaya bisa dipindah tanpa salah tafsir.

   **Rancangan & kontrak API T34b (DISETUJUI pengguna 18-10).** Dipecah dua:
   **T34b1** = penyimpanan, persetujuan, retensi, log keamanan, API admin (tanpa kamera/model, tanpa dependensi baru;
   `cryptography` sudah terkunci di `requirements.lock`). **T34b2** = mesin FR di gerbang (YuNet + Intel 0095, dependensi
   baru `openvino`, berkas model ±5 MB ikut repo dengan berkas lisensinya supaya gerbang tanpa internet tetap jalan) +
   ambil foto pendaftaran dari kamera.

   - **Penyimpanan:** SQLite terpisah `DATA_DIR/workers.db` (terpisah dari audit & akun: cadangan audit tidak ikut
     membawa data wajah). Tabel `workers` (id, `employee_no` unik, `name`, `active`, `consent_at`, `consent_by`,
     `consent_version`, `created_at`, `created_by`, `deactivated_at`, `face_deleted_at`) dan `face_templates` (id,
     `worker_id`, `condition`, `model_version`, `dim`, `nonce`, `ciphertext`, `created_at`, `created_by`).
   - **Enkripsi:** AES-256-GCM per templat; data tambahan terautentikasi = `worker_id` + `model_version` (templat tidak
     bisa dipindah ke baris lain). Kunci `FACE_DATA_KEY` (base64 32 byte) di `backend/.env`, **tidak pernah dibuat
     otomatis ke `DATA_DIR`**. Kunci kosong → fitur FR mati dengan pesan jelas (`face_ready=false`); gerbang tetap
     berjalan seperti sekarang. Kunci salah → templat gagal dibuka, dicatat, tidak membuat server mati.
   - **Kondisi foto** (kunci API Inggris, label UI di `messages.ts`): `bare` (tanpa helm/kacamata), `glasses`,
     `helmet`, `helmet_glasses`. Pekerja berkacamata wajib punya `glasses` (aturan di UI + peringatan API).
   - **Retensi:** nonaktif → `delete_after = deactivated_at + FACE_RETENTION_DAYS (30)`; pembersihan retensi (T20)
     menghapus templat & MP3 nama, mengisi `face_deleted_at`. Aktif lagi sebelum terhapus = penghapusan batal.
   - **Log keamanan** (`security.jsonl`, tanpa embedding): `worker_created`, `worker_template_added`,
     `worker_template_deleted`, `worker_deactivated`, `worker_activated`, `worker_face_deleted` (`reason`:
     `manual`/`retention`), `face_key_error`.
   - **Batas galeri:** `FACE_GALLERY_TESTED_LIMIT = 300` (T34m2); lewat batas → `limit.over=true` + peringatan di log.

   Endpoint (semua `require_admin`; galat memakai bentuk `{"detail": {"code": "...", "message": "..."}}` seperti T51):

   | Metode & jalur | Tahap | Badan permintaan | Jawaban |
   | :-- | :-- | :-- | :-- |
   | `GET /api/workers` | b1 | — | `{"face_ready": bool, "limit": {"tested": 300, "count": n, "over": bool}, "workers": [Worker]}` |
   | `POST /api/workers` | b1 | `{"employee_no": str, "name": str, "consent": true}` | 201 `Worker`; 400 `consent_required` / `invalid_name` / `invalid_employee_no`; 409 `employee_no_taken`; 503 `face_not_ready` |
   | `POST /api/workers/{id}/deactivate` | b1 | — | 200 `Worker` (`delete_after` terisi) |
   | `POST /api/workers/{id}/activate` | b1 | — | 200 `Worker`; bila wajah sudah terhapus retensi: tetap 200, `face_deleted_at` terisi & `templates` kosong → UI meminta foto ulang (diubah dari usul 409 saat implementasi T34b1: dengan 409 pekerja itu tidak bisa diaktifkan lagi karena nomor pegawainya sudah terpakai) |
   | `DELETE /api/workers/{id}/face` | b1 | — | 204 (hapus data wajah segera, hak hapus UU PDP) |
   | `DELETE /api/workers/{id}/templates/{template_id}` | b1 | — | 204 |
   | `POST /api/workers/{id}/templates` | b2 | `{"condition": "bare"\|"glasses"\|"helmet"\|"helmet_glasses"}` | 201 `Template` + `{"quality": {"face_width_px", "interocular_px", "det_score"}}`; 422 `no_face` / `multiple_faces` / `face_too_small`; 409 `camera_busy` (jalur inspeksi terisi) / `camera_unavailable` (kamera belum aktif atau frame sintetis — ditambahkan saat implementasi T34b2); 400 `invalid_condition`; 409 `inactive`; 404 `not_found`; 503 `face_not_ready` |

   `Worker` = `{"id", "employee_no", "name", "active", "consent": {"at", "by", "version"}, "created_at",
   "deactivated_at": str|null, "delete_after": str|null, "face_deleted_at": str|null, "templates": [Template]}`;
   `Template` = `{"id", "condition", "model_version", "created_at"}` (tanpa embedding, tanpa foto). Waktu = format
   lokal gerbang seperti audit (`YYYY-MM-DDTHH:MM:SS`). Foto pendaftaran (b2) hanya di memori untuk dihitung lalu
   dibuang; tidak ada pratinjau tersimpan.
3. **T34c — pengenalan dalam sesi + audit** (backend): FR di jendela diam, kunci identitas per sesi, kolom audit,
   tes karakterisasi state machine diperluas.
4. **T34d — suara nama** (backend): MP3 per pekerja saat daftar, diputar setelah "lolos".
   **Keputusan pengguna 18-10:**
   - Kalimat saat lolos & dikenali: **"APD lengkap. Silakan masuk, Pak <nama panggilan>."** (struktur sama dengan suara
     sekarang, nama di akhir). Tidak dikenali / FR belum selesai saat keputusan keluar = suara umum "APD lengkap. Silakan
     masuk." (suara tidak pernah menunggu FR). **Ditolak = tanpa nama** (nama hanya di audit untuk teguran K3).
   - Yang diucapkan **nama panggilan**, bukan nama lengkap, dengan sapaan hormat.
   - **Sapaan Pak/Bu dari jenis kelamin** (keputusan pengguna 19-10): admin mengisi jenis kelamin (`male`/`female`) saat
     mendaftar; `male` = "Pak", `female` = "Bu" (pemetaan satu tempat di `messages.py`). Jenis kelamin = data pribadi (bukan
     spesifik), dipakai untuk sapaan; disebut di formulir persetujuan.
   - **Formulir persetujuan wajib menyebut** bahwa nama panggilan pekerja akan **diucapkan keras di gerbang** saat lolos
     (teks formulir dari HR/Legal; versi formulir dicatat per pekerja lewat `FACE_CONSENT_VERSION`).
   - **Mesin suara = gTTS (opsi A, keputusan pengguna 19-10)**: kalimat dikirim ke layanan suara Google (Translate TTS)
     sekali saat pendaftaran/ubah. **Yang dikirim hanya sapaan + nama panggilan** (bukan nama lengkap, nomor pegawai, atau
     wajah). **Formulir persetujuan wajib menyebut** bahwa nama panggilan diproses layanan suara Google (transfer data ke
     luar negeri, UU PDP) — perlu persetujuan HR/Legal sebelum dipakai sungguhan. Setiap pembuatan suara dicatat di
     `security.jsonl` (bukti akuntabilitas). Pilihan lain yang ditimbang: suara OS offline (Linux robotik), Piper (lisensi
     suara Indonesia tidak jelas: model card "See URL"), tanpa suara nama.
   - Teknis: satu MP3 utuh per pekerja dibuat sekali saat pendaftaran/ubah nama panggilan (gTTS; butuh internet hanya saat
     itu — gagal = pekerja tetap terdaftar, suara umum dipakai, bisa dibuat ulang); diputar offline; ikut terhapus bersama
     data wajah (hapus manual & retensi 30 hari).
   - **Perubahan kontrak (additive) untuk T34e:** `POST /api/workers` + `nickname` (**WAJIB** sejak 19-10; 400 `invalid_nickname`) &
     `gender` (`"male"`|`"female"`, WAJIB; 400 `invalid_gender`); `Worker` + `nickname`, `gender`, `salutation` (teks sapaan
     hasil turunan, hanya-baca), `voice_ready` (bool: MP3 nama ada);
     endpoint baru `PATCH /api/workers/{id}` untuk mengubah nama panggilan/sapaan (MP3 dibuat ulang).
5. **T34e — UI** (Gemini): halaman pendaftaran pekerja + persetujuan, laporan & filter per pekerja.

**Pertanyaan terbuka:** isi formulir persetujuan (HR/Legal); perlu atau tidak tampilan nama di layar Monitoring.
(Terjawab 18-10: yang mendaftarkan = admin, persetujuan = centang admin, masa simpan = 30 hari setelah nonaktif.)

## Antrean berikutnya (urut menurut risiko — AGENTS.md §2.2a, disusun 27-09, dirapikan 14-10)

| # | Risiko | Task | Alasan risiko / isi |
| :-- | :-- | :-- | :-- |
| 3 | **Tinggi** | **Uji nyata gabungan (T35 Uji 2 & 3)** | Perubahan besar T36a–d, T37, T38, T39a, T45–T58 + UI T33/T51 belum diuji di gerbang nyata (keputusan, suara, sesi, zona, pemulihan GPU). **Siap dijalankan** **Uji 2 sebagian 20-10 (18:51–19:08, 30 sesi, 9 keputusan):** APD lengkap hijau 4/4, tanpa helm & tanpa rompi merah dengan item benar, FR P003 0,60–0,81 & orang lain tak dikenali, kamera ditutup → kuning 7 dtk lalu pulih, relay putus sekali & pulih 2 dtk; **gagal: rokok di mulut lolos (→ T86)**; VLM timeout > 4 dtk 2× lalu utama dilewati 60 dtk (→ T87). Belum: cabut kamera, setengah badan, berjalan lewat, 1080p sejak awal (kamera sempat terbuka 1280×720 lalu 1080p). **Status 22-10:** penyebab gagal 20-10 sudah ditutup (T86 rokok di mulut, T87 utama tidak dilewati). Belum diuji di gerbang: T72 jaringan (cabut LAN/Wi-Fi → langsung lokal, hotspot lemah → lambat, colok lagi → utama, bongkar setelah 10 menit), T88 lampu fisik relay, VLM lokal darurat, plus sisa lama (cabut kamera, setengah badan, berjalan lewat). **Diblokir:** perangkat dipakai demo (22-10). |
| 4 | **Tinggi** | **Uji fisik T57 & T58** (ditunda 14-10: pencahayaan kurang) | Kamera terhalang tangan/kardus/kain/plastik, salah alarm jalur kosong; rokok/vape asli + pengecoh (pulpen, sedotan, tangan kotor). Daftar uji di obrolan 14-10, dicatat per jam lalu dicocokkan dengan log & audit **Sebagian 14-10 (uji UI, Gemini utama)**: pengguna memegang rokok asli → 3/3 pemeriksaan MERAH "Membawa Rokok / Vape", dikonfirmasi langkah kedua tiap kali; kamera terhalang 1x tertangkap (kuning, pulih 4 dtk). Waktu putusan kasus rokok ±7 dtk karena jeda kuota Gemini 4 dtk sebelum konfirmasi. Belum: pengecoh (pulpen, sedotan, ponsel, tangan kotor), vape, bungkus di saku, jalur cadangan lokal, kamera tertutup tangan/kain/plastik sistematis **Uji luring 22-10** (foto bukti tersimpan, jalur gerbang di `master` setelah T72): 13/14 benar — 9/10 rokok tertangkap termasuk rokok di mulut (baris 121), 0/4 merah palsu; terlewat baris 84 = foto 480p 146×412 px (rokok ±4–5 px menyatu latar putih), dibatalkan konfirmasi T58 — kebijakan "ragu = tidak ada" tetap. Sisa uji fisik tidak berubah. |
| 4b | **Tinggi** | **T74 — rokok/benda kecil terlihat VLM** (temuan uji 19-10) | Uji CPU only 19-10: rokok dipegang pekerja **tidak terdeteksi** di 3 sesi (lampu hijau; VLM `rokok.detected=false`). Potongan tubuh ke VLM hanya ~110–132 × 346–384 px (kamera 864×480) → rokok ±1–2 px; pengguna: foto bukti buram/tidak jelas. FR juga gagal ("0/3 frame berwajah cukup besar"). Langkah: (1) gabung T34c2 (1080p) lalu uji ulang rokok (dipegang & di mulut) + FR + beban CPU; (2) `VLM_IMAGE_MAX_SIZE=640` memperkecil lagi potongan 1080p (~850 px) — tinjau angka setelah cek cara Gemini menghitung gambar (kuota free tier per permintaan); (3) bila masih lolos: potongan resolusi penuh sekitar tangan & mulut (titik pose pergelangan & hidung) dikirim dalam panggilan VLM yang sama **Uji 1080p CPU only 19-10 (setelah T34c2 digabung):** rokok terdeteksi **4 dari 5** inspeksi (di tangan maupun di mulut; 480p: 0 dari 3); 1 lolos (sesi #6, potongan 298×734 px → diperkecil ke 640). FR: wajah cukup besar 2–3/3 frame (480p: 0/3). CPU ~8,5 dari 16 inti, RAM 1,1 GB. Larangan memakai panggilan konfirmasi (T58) + jeda kuota 4 dtk → keputusan rokok ~7 dtk & 2 kuota; pekerja yang keluar sebelum itu tidak mendapat lampu merah, tetapi pelanggaran **tetap masuk audit** (hasil terlambat dicatat). Sisa langkah: cek `VLM_IMAGE_MAX_SIZE` 640 → 768 (satu petak Gemini 768×768 = 258 token, kuota free tier per permintaan) & `media_resolution` (belum dipakai), lalu uji ulang; potongan tangan/mulut hanya bila masih ada yang lolos. **Langkah 1–2 selesai 19-10 tanpa perubahan kode** (lihat arsip): batas gambar & `media_resolution` (bawaan Gemini 3 sudah setara HIGH) tidak membantu, perbesaran tangan juga tidak — akar masalah: **area tangan buram** padahal skor ketajaman frame tinggi (1423; diukur atas seluruh tubuh, gerak dari kotak tubuh saja). **Lanjutan (diblokir uji fisik, ditunda pengguna 19-10):** (a) uji ulang dengan cahaya tambahan — bila terdeteksi, syarat pencahayaan masuk spesifikasi pemasangan; (b) pemilih frame peka tangan (ketajaman area pergelangan dari titik pose); (c) 2–3 frame terbaik dalam satu panggilan; (d) eksposur kamera dikunci (pilihan terakhir). **Status 22-10:** foto 1080p (19–20-10) 7/7 rokok tertangkap pada uji luring T86; risiko tetap Tinggi sampai uji kamera langsung (19-10 masih 1/5 lolos karena tangan buram). Uji ulang: rokok di tangan setinggi pinggang berlatar putih (kasus baris 84) di 1080p. |
| 5 | Sedang | **Validasi Gemini untuk prompt T58** — 10 foto 10/10 benar (pagi + sore 14-10, `data/eval/20261014-070915`, `-171309`); sore Gemini lambat (median 5,5 dtk, 4/5 > batas 4 dtk). Sisa: 84 foto penuh bila kuota mengizinkan | Status Gemini kini `outdated` (terakhir diuji T48) → peringatan di log & Pengaturan; uji 10–20 foto dengan jeda RPM |
| 6 | Sedang | **T40 — alternatif mesin VLM lokal** (keputusan setelah uji nyata) | Crash `encoding image` berasal dari llama.cpp (llama.cpp#17422, #17881; ollama#14170), jadi mengganti Ollama dengan llama.cpp langsung kemungkinan tidak menghilangkannya. Bila uji nyata menunjukkan cadangan masih sering bermasalah walau ada penjaga T38: uji coba Qwen2.5-VL 4-bit lewat Transformers (PyTorch) di **proses terpisah** berantarmuka OpenAI-compatible (adaptor sudah mendukung, cukup ganti `.env`), diukur dengan `tools/bench_vlm.py` (akurasi, 0 APD kurang lolos, waktu, VRAM bersama YOLO). vLLM ditinjau untuk produksi Linux/GPU besar (T29). Data sejauh ini: ~2–4 crash per 84 foto. Kriteria tambahan (T48, 05-10): `qwen2.5vl:7b` tidak melihat helm di atas rambut lebat (`apd_10`, salah 4/4; Gemini benar) dan sepatu `apd_4` hanya benar 2/4 — model pengganti harus lolos keduanya |
| 7f | **Tinggi** (rencana) | **T81 — absensi resmi** (arah produk pengguna 19-10: "absensi + pemeriksaan APD") | Hanya bila tingkat pengenalan FR di gerbang terbukti tinggi & HR/Legal setuju (tujuan baru data wajah → persetujuan pekerja & DPIA diperbarui). Butuh jam masuk/pulang, shift, koreksi manual HR; kesalahan berdampak ke gaji/disiplin. Rancangan dimatangkan & risiko dinilai ulang sebelum dikerjakan |
| 7g | **Tinggi** (rencana) | **T83 — setelan "Wajib terdaftar"** (pertanyaan pengguna 20-10: orang tak terdaftar lolos?) | Kini orang tak terdaftar lolos bila APD lengkap (FR hanya nama di audit, "Tidak dikenali"). Usul: setelan admin bawaan MATI; bila aktif & wajah tidak dikenali → lampu **kuning** + suara "wajah belum terdaftar, hubungi petugas" (merah tetap hanya APD/larangan, AGENTS §5), audit "ditahan: tidak terdaftar". Tinggi: pekerja patuh bisa tertahan bila FR gagal (bayangan helm, menoleh, cahaya) → syarat: tingkat pengenalan terukur dari 50–100 lintasan nyata (T80) & persetujuan HR; ditinjau bersama T81 |
| 8 | Sedang | Uji fisik tertunda: lampu ESP32 (T47), restart PC sungguhan (T29) | Rancangan diuji tanpa perangkat/simulasi saja |
| 9 | Rendah | Dua orang berdampingan di zona (T36d); T25 sisa latensi | Dicegah batas fisik di lokasi; latensi sudah jauh turun |
| 10 | Rendah | T42 — cicil utang kode (sisa setelah T42a/b) | 24 fungsi > 30 baris (terpanjang `capture._reader_loop` 199, `detector.detect_and_track` 164, `state_manager.update_frame_detections` 101) — daftar di `tests/test_code_hygiene.py`; 8 blok kembar (web: dialog CameraPicker/SnapshotDialog/AdminToken, ZoneSettings/Pengaturan); pesan log di luar `messages.py` (`camera_manager`, `detector`, `audio_engine`, `capture`); angka HUD/resolusi ke config; warna `#000` VideoPanel ke token; nama Indonesia → Inggris saat disentuh |
| 11 | Rendah | T44 — formatter & linter web (audit 28-09) | `ruff format` massal (62 berkas) sebagai commit sendiri; eslint + prettier untuk `web/` (mengubah `web/package*.json`, perlu giliran dependensi) |
| 13 | Rendah | **T91 — `test_shutdown` tanpa API key asli** (temuan 22-10) | Server uji di `tests/test_shutdown.py` mewarisi `os.environ` + `backend/.env` → tiap jalan memanaskan VLM cloud (kuota Gemini terpakai). Usul: kosongkan key VLM / set penyedia tiruan di `env` server uji; tes tetap menguji berhenti bersih. Rendah: hanya kuota & kerapian tes. Area: `tests/` (bawaan Codex) |
| 12 | **Tinggi** (rencana) | **T34 — identitas wajah (FR) untuk audit per pekerja** (rancangan 18-10, lihat "Rancangan T34") | Mulai dari T34a (uji ukuran wajah di gerbang, perlu pengguna di depan kamera); T34b–e menyusul. Persetujuan & DPIA dari HR/Legal sebelum dipakai sungguhan |


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
