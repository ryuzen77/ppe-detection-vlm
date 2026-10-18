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
uv pip install numpy opencv-python-headless onnxruntime openvino
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

## Uji akurasi (langkah 3)

Butuh foto relawan dengan persetujuan tertulis; foto tidak di-commit dan tidak diunggah.
