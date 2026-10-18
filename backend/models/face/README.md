# Model pengenalan wajah (T34)

Ikut repo supaya gerbang tanpa internet tetap bisa mengenali pekerja. Dipilih lewat
uji nyata T34m (kecepatan CPU), T34m2 (akurasi LFW 1:1 & 1:N), dan T34a (kamera
gerbang); hasilnya di `docs/RENCANA.md` → Rancangan T34.

| Berkas | Model | Sumber | Lisensi | SHA-256 |
| :-- | :-- | :-- | :-- | :-- |
| `face_detection_yunet_2023mar.onnx` | YuNet (deteksi + 5 landmark) | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT (`LICENSE-yunet-MIT.txt`) | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `face-reidentification-retail-0095.xml` | Intel face-reidentification-retail-0095, FP32 (embedding 256 dimensi) | [Open Model Zoo 2023.0](https://storage.openvinotoolkit.org/repositories/open_model_zoo/2023.0/models_bin/1/face-reidentification-retail-0095/FP32/) | Apache-2.0 (`LICENSE-open_model_zoo-Apache-2.0.txt`) | `6cf60c341452155e35c467510c6c50a96ade5b2bd8f88c5a90902e905d8a80c3` |
| `face-reidentification-retail-0095.bin` | (bobot model di atas) | sama | sama | `21319b95e54181857f99e22dc32ec89770eca2969a1432cfa1594bffc94edd62` |

Mengganti model = ganti `FACE_MODEL_VERSION` di `backend/config.py` dan daftarkan
ulang semua pekerja (templat lama terikat versi model lewat enkripsi).
