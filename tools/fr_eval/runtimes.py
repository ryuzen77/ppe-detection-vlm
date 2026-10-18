"""Pemuat model kandidat FR & align wajah, dipakai uji kecepatan dan uji akurasi (T34m).

Runtime selain OpenCV diimpor saat dipakai: hanya ada di env `fr_eval`.
"""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from stats import model_files, models_dir

Embedder = Callable[[np.ndarray], np.ndarray]

# Titik acuan 5 landmark (mata kanan, mata kiri, hidung, sudut mulut kanan & kiri;
# urutan YuNet) sebagai pecahan lebar/tinggi potongan wajah.
# arcface: templat 112x112 ArcFace/SFace. omz: templat demo face_recognition Open
# Model Zoo untuk Intel 0095 (templat 96x112 yang dinormalisasi).
ALIGN_TEMPLATES = {
    "arcface": np.array(
        [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]]
    )
    / 112.0,
    "omz": np.array(
        [[30.2946, 51.6963], [65.5318, 51.5014], [48.0252, 71.7366], [33.5493, 92.3655], [62.7299, 92.2041]]
    )
    / np.array([96.0, 112.0]),
}


def model_path(name: str, filename: str) -> Path:
    path = models_dir() / name / filename
    return path.with_suffix("") if path.suffix == ".bz2" else path


def entry_paths(entry: dict) -> list[Path]:
    return [model_path(entry["name"], mf.filename) for mf in model_files(entry)]


def template_points(kind: str, size: int) -> np.ndarray:
    return (ALIGN_TEMPLATES[kind] * size).astype(np.float32)


def similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Matriks 2x3 kemiripan (geser, putar, skala) kuadrat terkecil atas SEMUA titik (Umeyama 1991).

    Bukan `cv2.estimateAffinePartial2D`: bawaannya RANSAC, yang dengan 5 titik bisa
    membuang landmark; pada LFW itu menurunkan akurasi SFace 99,35% -> 99,07%.
    Cara ini sama dengan `FaceRecognizerSF.alignCrop` OpenCV.
    """
    src, dst = src.astype(np.float64), dst.astype(np.float64)
    src_c, dst_c = src - src.mean(axis=0), dst - dst.mean(axis=0)
    u, s, vt = np.linalg.svd(dst_c.T @ src_c / len(src))
    d = np.diag([1.0, np.sign(np.linalg.det(u) * np.linalg.det(vt))])
    rotation = u @ d @ vt
    scale = np.trace(np.diag(s) @ d) / (src_c**2).sum(axis=1).mean()
    shift = dst.mean(axis=0) - scale * rotation @ src.mean(axis=0)
    return np.hstack([scale * rotation, shift[:, None]])


def align_face(image: np.ndarray, landmarks: np.ndarray, kind: str, size: int) -> np.ndarray:
    """Potongan wajah ter-align: 5 landmark dipetakan ke templat model."""
    matrix = similarity_transform(landmarks, template_points(kind, size))
    return cv2.warpAffine(image, matrix, (size, size))


def load_detector(catalog: dict, width: int, height: int, score: float = 0.6):
    entry = catalog["detector"]
    path = model_path(entry["name"], model_files(entry)[0].filename)
    return cv2.FaceDetectorYN.create(str(path), "", (width, height), score)


def _opencv_sface(paths: list[Path], threads: int) -> Embedder:
    rec = cv2.FaceRecognizerSF.create(str(paths[0]), "")
    return lambda crop: rec.feature(crop)


def _openvino(paths: list[Path], threads: int) -> Embedder:
    import openvino as ov

    config = {"INFERENCE_NUM_THREADS": threads} if threads else {}
    request = ov.Core().compile_model(str(paths[0]), "CPU", config).create_infer_request()
    # IR Intel 0095: BGR mentah 0..255, NCHW
    return lambda crop: request.infer({0: crop.transpose(2, 0, 1)[None].astype(np.float32)})[0]


def _onnxruntime(paths: list[Path], threads: int) -> Embedder:
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    session = ort.InferenceSession(str(paths[0]), opts, providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name

    def embed(crop: np.ndarray) -> np.ndarray:
        # Praproses ArcFace/InsightFace: RGB, (x - 127.5) / 127.5, NCHW
        blob = cv2.dnn.blobFromImage(crop, 1 / 127.5, crop.shape[1::-1], (127.5,) * 3, swapRB=True)
        return session.run(None, {name: blob})[0]

    return embed


def _dlib(paths: list[Path], threads: int) -> Embedder:
    import dlib

    rec = dlib.face_recognition_model_v1(str(paths[0]))
    # Overload potongan wajah 150x150 ter-align (tanpa landmark); RGB
    return lambda crop: np.asarray(rec.compute_face_descriptor(crop[..., ::-1].copy()))


RUNTIMES: dict[str, Callable[[list[Path], int], Embedder]] = {
    "opencv_sface": _opencv_sface,
    "openvino": _openvino,
    "onnxruntime": _onnxruntime,
    "dlib": _dlib,
}


def load_recognizer(entry: dict, threads: int = 0) -> Embedder:
    return RUNTIMES[entry["runtime"]](entry_paths(entry), threads)
