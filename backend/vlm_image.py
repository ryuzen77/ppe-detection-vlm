"""Gambar untuk VLM: tubuh utuh + panel perbesaran kepala & tangan (T86).

Uji nyata 20-10: rokok di mulut lolos karena crop tubuh diperkecil ke `VLM_IMAGE_MAX_SIZE`
(kepala ±80 px, rokok ±3-4 px) walau kamera 1080p menangkapnya. Panel di kanan dipotong dari
crop resolusi asli di sekitar titik pose, lalu diperbesar, sehingga benda kecil di wajah/tangan
terbaca. Tetap SATU gambar: semua penyedia VLM (cloud, lokal) menerimanya tanpa perubahan.
Logika murni (tanpa I/O); dipakai `detector` (jendela crop) dan `vlm_analyzer` (gambar).
"""

from typing import Optional, Sequence

import cv2
import numpy as np

from . import pose_keypoints as kp
from .config import cfg

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (x1/y1 eksklusif)
_HEAD_POINTS = (kp.NOSE, kp.LEFT_EYE, kp.RIGHT_EYE, kp.LEFT_EAR, kp.RIGHT_EAR)
_ARMS = ((kp.LEFT_WRIST, kp.LEFT_ELBOW), (kp.RIGHT_WRIST, kp.RIGHT_ELBOW))


def crop_window(frame_height: int, frame_width: int, box: Sequence[int]) -> Box:
    """Jendela potongan orang untuk VLM: kotak YOLO + tepi untuk konteks helm & sepatu.

    Satu definisi bersama: `detector` memotong dengan ini, dan titik pose (koordinat frame)
    digeser ke koordinat crop dengan asal jendela yang sama.
    """
    x1, y1, x2, y2 = box
    margin_y = int((y2 - y1) * cfg.CROP_MARGIN_Y_RATIO)
    margin_x = int((x2 - x1) * cfg.CROP_MARGIN_X_RATIO)
    return (
        max(0, x1 - margin_x),
        max(0, y1 - margin_y),
        min(frame_width, x2 + margin_x),
        min(frame_height, y2 + margin_y),
    )


def to_crop_coords(keypoints: Optional[list], window: Box) -> Optional[list]:
    """Titik pose dari koordinat frame ke koordinat crop (keyakinan tetap)."""
    if not keypoints:
        return None
    x0, y0 = window[0], window[1]
    return [[p[kp.X] - x0, p[kp.Y] - y0, p[kp.CONFIDENCE]] for p in keypoints]


def _point(keypoints: list, index: int) -> Optional[np.ndarray]:
    """Titik yang cukup yakin, atau None."""
    if index >= len(keypoints) or keypoints[index][kp.CONFIDENCE] < cfg.KEYPOINT_CONF_THRESHOLD:
        return None
    return np.array(keypoints[index][:2], dtype=float)


def _square(center: np.ndarray, side: float, shape: tuple) -> Optional[Box]:
    """Kotak persegi di sekitar `center`, dipotong ke batas gambar; None bila tak bersisa."""
    h, w = shape[:2]
    half = side / 2.0
    x0, y0 = max(0, int(center[0] - half)), max(0, int(center[1] - half))
    x1, y1 = min(w, int(center[0] + half)), min(h, int(center[1] + half))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


def head_box(keypoints: Optional[list], shape: tuple) -> Optional[Box]:
    """Kotak kepala: rata-rata titik wajah yang yakin (hidung, mata, telinga)."""
    points = [p for p in (_point(keypoints, i) for i in _HEAD_POINTS) if p is not None] if keypoints else []
    if not points:
        return None
    return _square(np.mean(points, axis=0), shape[0] * cfg.VLM_ZOOM_HEAD_RATIO, shape)


def hand_boxes(keypoints: Optional[list], shape: tuple) -> list[Optional[Box]]:
    """Kotak tangan, urut dari kiri gambar ke kanan; None untuk tangan tanpa titik yakin.

    Pusat digeser dari pergelangan searah lengan bawah (siku -> pergelangan), karena benda
    yang dipegang ada di telapak/jari, bukan di pergelangan.
    """
    if not keypoints:
        return [None, None]
    found = []
    for wrist_i, elbow_i in _ARMS:
        wrist = _point(keypoints, wrist_i)
        if wrist is None:
            found.append((float("inf"), None))
            continue
        elbow = _point(keypoints, elbow_i)
        center = wrist if elbow is None else wrist + (wrist - elbow) * cfg.VLM_ZOOM_HAND_REACH
        found.append((wrist[0], _square(center, shape[0] * cfg.VLM_ZOOM_HAND_RATIO, shape)))
    return [box for _, box in sorted(found, key=lambda item: item[0])]


def _panel(crop: np.ndarray, box: Optional[Box], side: int) -> np.ndarray:
    """Isi satu panel persegi: potongan yang diperbesar, atau abu-abu polos bila tanpa kotak."""
    if box is None:
        return np.full((side, side, 3), cfg.VLM_ZOOM_FILL_BGR, np.uint8)
    x0, y0, x1, y1 = box
    return cv2.resize(crop[y0:y1, x0:x1], (side, side), interpolation=cv2.INTER_CUBIC)


def fit_body(crop: np.ndarray) -> np.ndarray:
    """Tubuh utuh diperkecil (tidak pernah diperbesar) ke sisi terpanjang `VLM_IMAGE_MAX_SIZE`."""
    h, w = crop.shape[:2]
    max_dim = cfg.VLM_IMAGE_MAX_SIZE
    if max(h, w) <= max_dim:
        return crop
    scale = max_dim / float(max(h, w))
    return cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def compose(crop: np.ndarray, keypoints: Optional[list]) -> np.ndarray:
    """Gambar gabungan: tubuh utuh di kiri; kepala (atas) & dua tangan (bawah) di kolom kanan.

    `keypoints` dalam koordinat crop (lihat `to_crop_coords`). Panel dipotong dari `crop`
    resolusi asli, bukan dari tubuh yang sudah diperkecil.
    """
    body = fit_body(crop)
    side = cfg.VLM_ZOOM_PANEL_WIDTH
    half = side // 2
    hands = cfg.VLM_ZOOM_HAND_PANELS
    bh, bw = body.shape[:2]
    canvas = np.full((max(bh, side + (half if hands else 0)), bw + side, 3), cfg.VLM_ZOOM_FILL_BGR, np.uint8)
    canvas[:bh, :bw] = body
    canvas[:side, bw:] = _panel(crop, head_box(keypoints, crop.shape), side)
    if hands:
        for i, box in enumerate(hand_boxes(keypoints, crop.shape)):
            canvas[side : side + half, bw + i * half : bw + (i + 1) * half] = _panel(crop, box, half)
    return canvas
