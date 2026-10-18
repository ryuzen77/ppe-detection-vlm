"""Align wajah 5 titik (T34): satu sumber untuk gerbang dan alat uji `tools/fr_eval`.

Logika murni (numpy + OpenCV), tanpa konfigurasi atau I/O, supaya alat evaluasi
memakai matematika yang persis sama dengan gerbang.
"""

import cv2
import numpy as np

# Titik acuan 5 landmark (mata kanan, mata kiri, hidung, sudut mulut kanan & kiri; urutan
# YuNet) sebagai pecahan lebar/tinggi potongan wajah. arcface: templat 112x112 ArcFace/SFace.
# omz: templat demo face_recognition Open Model Zoo untuk Intel 0095 (templat 96x112 dinormalisasi).
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


def template_points(kind: str, size: int) -> np.ndarray:
    return (ALIGN_TEMPLATES[kind] * size).astype(np.float32)


def similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Matriks 2x3 kemiripan (geser, putar, skala) kuadrat terkecil atas SEMUA titik (Umeyama 1991).

    Bukan `cv2.estimateAffinePartial2D`: bawaannya RANSAC, yang dengan 5 titik bisa
    membuang landmark; pada LFW itu menurunkan akurasi SFace 99,35% -> 99,07% (T34m2).
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


def interocular_px(landmarks: np.ndarray) -> float:
    """Jarak antar-mata (landmark 0 & 1): ukuran wajah yang tidak terpengaruh helm/rambut."""
    return float(np.linalg.norm(landmarks[0] - landmarks[1]))
