"""Memilih frame terbaik untuk dikirim ke VLM (T25a).

Hanya satu gambar yang menentukan keputusan gerbang, jadi gambar itu diambil
dari beberapa frame tubuh-utuh berturut-turut, bukan sekadar frame pertama yang
lolos. Frame pertama sering tertangkap saat pekerja masih melangkah (buram,
miring). Semua penilaian murah (~1-2 ms per frame) dan memakai data yang sudah
dihitung YOLO, sehingga tambahan waktunya hanya menunggu frame kandidat.
"""
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

# Titik COCO yang menentukan apakah APD terlihat jelas: kepala (helm), bahu
# (rompi), lutut (celana), pergelangan kaki (sepatu)
_POSE_POINTS = (0, 1, 2, 5, 6, 13, 14, 15, 16)
# Tinggi normalisasi ketajaman: crop dari jarak berbeda dinilai pada skala sama
_SHARPNESS_HEIGHT = 256
# Bobot skor akhir. Ketajaman paling menentukan mutu bacaan VLM.
W_SHARPNESS, W_STILLNESS, W_POSE = 0.6, 0.25, 0.15


@dataclass(eq=False)   # dibandingkan berdasarkan identitas: berisi array gambar
class FrameCandidate:
    crop: np.ndarray
    bbox: list
    keypoints: Optional[list]
    track_id: int
    sharpness: float = 0.0
    motion: float = 0.0          # pergeseran relatif terhadap frame sebelumnya
    pose: float = 0.0
    score: float = 0.0


def sharpness(crop: np.ndarray) -> float:
    """Variance of Laplacian pada crop yang dinormalisasi tingginya. Makin besar makin tajam."""
    if crop is None or crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    h, w = gray.shape[:2]
    scale = _SHARPNESS_HEIGHT / float(h)
    gray = cv2.resize(gray, (max(int(w * scale), 1), _SHARPNESS_HEIGHT), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def motion(bbox: list, prev_bbox: Optional[list]) -> float:
    """Pergeseran titik tengah kotak tubuh, relatif terhadap tinggi tubuh (0 = diam)."""
    if prev_bbox is None:
        return 0.0
    x1, y1, x2, y2 = bbox
    px1, py1, px2, py2 = prev_bbox
    height = max(y2 - y1, 1)
    dx = ((x1 + x2) - (px1 + px2)) / 2.0
    dy = ((y1 + y2) - (py1 + py2)) / 2.0
    return float(np.hypot(dx, dy) / height)


def pose_clarity(keypoints: Optional[list]) -> float:
    """Rata-rata keyakinan titik kepala, bahu, lutut, dan pergelangan kaki (0..1)."""
    if not keypoints:
        return 0.0
    confs = [keypoints[i][2] for i in _POSE_POINTS if i < len(keypoints) and len(keypoints[i]) > 2]
    return float(np.mean(confs)) if confs else 0.0


def choose_best(candidates: list[FrameCandidate], prev_bbox: Optional[list] = None) -> FrameCandidate:
    """Menilai kandidat dan mengembalikan yang skornya tertinggi.

    Ketajaman dinilai relatif terhadap kandidat lain di jendela yang sama, jadi
    tidak perlu ambang mutlak yang bergantung pada kamera dan pencahayaan.
    Bila skor sama, frame paling akhir dipilih (pekerja paling lama berdiri).
    """
    if not candidates:
        raise ValueError("Tidak ada frame kandidat")
    previous = prev_bbox
    for c in candidates:
        c.sharpness = sharpness(c.crop)
        c.motion = motion(c.bbox, previous)
        c.pose = pose_clarity(c.keypoints)
        previous = c.bbox
    best_sharp = max(c.sharpness for c in candidates) or 1.0
    for c in candidates:
        stillness = 1.0 / (1.0 + 20.0 * c.motion)   # 5% tinggi tubuh bergeser -> 0,5
        c.score = W_SHARPNESS * (c.sharpness / best_sharp) + W_STILLNESS * stillness + W_POSE * c.pose
    best = candidates[0]
    for c in candidates[1:]:
        if c.score >= best.score:
            best = c
    return best
