# Uji kandidat pengenalan wajah (T34m)

Alat ukur sebelum memilih model FR untuk gerbang. Rencana, kandidat, kriteria,
dan hasil ada di `docs/RENCANA.md` (T34m). Kode gerbang tidak memakai folder ini.

## Env terpisah `fr_eval`

Runtime kandidat (onnxruntime, OpenVINO, dlib) tidak dipasang di env gerbang
`ppe_detection` supaya dependensi produksi tidak berubah sebelum model dipilih.
dlib dikunci ke build CPU; build bawaan conda-forge menarik CUDA/cuDNN (GB).

```bash
conda create -n fr_eval -c conda-forge --override-channels python=3.12 "dlib=20.0.1=cpu_*" uv
conda activate fr_eval
uv pip install numpy opencv-python onnxruntime openvino
```

Selalu jalankan setelah `conda activate fr_eval`: memanggil `python.exe` env langsung tanpa
aktivasi membuat numpy (MKL) crash di Windows (`0xc06d007f`, DLL Intel OpenMP tidak ditemukan).

## Model

Bobot diunduh ke `~/.cache/depro_fr_eval/models/` (ganti dengan `FR_EVAL_MODELS_DIR`),
tidak ke repo. URL, lisensi, dan SHA-256 tercatat di `models.json`; berkas yang
hash-nya berbeda ditolak.

```bash
python tools/fr_eval/fetch_models.py
```

## Uji kecepatan (langkah 2)

Gambar acak berbenih, tanpa foto orang (waktu inferensi tidak bergantung isi gambar).

```bash
python tools/fr_eval/bench_speed.py --threads 0 --threads 2 --out <berkas>.json
```

`--threads 2` meniru CPU yang dibagi dengan gerbang yang sedang berjalan.
Estimasi sesi = percobaan × (YuNet + align + embedding) + pencarian 10.000 wajah.

## Uji akurasi pada LFW (langkah 3a)

LFW (foto berita tokoh publik) dipakai untuk MEMILIH model tanpa relawan. Diunduh
oleh `fetch_models.py` dari mirror figshare yang dipakai scikit-learn (situs UMass
tidak merespons; checksum dari sumber scikit-learn) ke `~/.cache/depro_fr_eval/datasets/lfw/`.
Lisensi LFW tidak tertulis: hanya evaluasi internal, tidak di-commit/diunggah,
tidak untuk melatih model.

```bash
python tools/fr_eval/eval_lfw.py --only sface intel_0095 sface_int8 --out <berkas>.json
```

- Akurasi 10-fold protokol resmi (`pairs.txt`): dibandingkan dengan angka publikasi
  untuk memastikan align & praproses benar.
- FAR/FRR dari semua pasangan (maks 20 foto per orang): ambang pada FAR 0,1% dan
  0,01%, lalu FRR di ambang itu. Foto tanpa wajah terdeteksi dihitung terpisah.

## Uji 1:N — pekerja terdaftar vs orang asing

Gerbang mencari wajah di seluruh daftar pekerja, jadi ambang 1:1 tidak cukup:
orang asing dibandingkan dengan semua pekerja sekaligus. Separuh tokoh LFW yang
punya > 3 foto "didaftarkan" (3 foto, templat rata-rata), sisanya orang asing;
galeri bisa diperbesar dengan `--distractors`. Juga mengukur waktu foto → keputusan
untuk pekerja dan orang asing secara terpisah. Embedding di-cache (kunci = kode
align + entri model).

```bash
python tools/fr_eval/eval_openset.py --only sface intel_0095 sface_int8 --distractors 0 3000
```

## Uji wajah di kamera gerbang (T34a)

Server gerbang harus mati (kamera hanya untuk satu proses). Jendela pratinjau
(cermin) menampilkan hitung mundur, kotak wajah, ukuran wajah, dan skor kemiripan;
kondisi pertama = acuan pendaftaran sementara (hanya di memori). Tidak ada foto
atau embedding yang disimpan. Butuh `opencv-python` (bukan `-headless`) di env `fr_eval`.

```bash
python tools/fr_eval/face_probe.py --size 1920x1080
python tools/fr_eval/face_probe.py --size 854x480 --conditions "kacamata,helm + kacamata,helm"
```

## Uji nyata (langkah 3b)

Setelah model dipilih: foto relawan berpersetujuan tertulis lewat kamera gerbang
(helm, masker, jarak); foto tidak di-commit dan tidak diunggah.
