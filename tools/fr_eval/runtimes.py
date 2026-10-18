"""Pemuat model kandidat FR & align wajah, dipakai uji kecepatan dan uji akurasi (T34m).

Runtime selain OpenCV diimpor saat dipakai: hanya ada di env `fr_eval`.
"""

from collections.abc import Callable
from pathlib import Path

import sys

import cv2
import numpy as np

# Align dari gerbang (satu sumber, T34b2): alat uji memakai matematika yang sama persis
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.face_align import ALIGN_TEMPLATES, align_face, similarity_transform, template_points  # noqa: E402,F401
from stats import model_files, models_dir  # noqa: E402

Embedder = Callable[[np.ndarray], np.ndarray]


def model_path(name: str, filename: str) -> Path:
    path = models_dir() / name / filename
    return path.with_suffix("") if path.suffix == ".bz2" else path


def entry_paths(entry: dict) -> list[Path]:
    return [model_path(entry["name"], mf.filename) for mf in model_files(entry)]


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
