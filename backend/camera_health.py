"""Kesehatan gambar kamera (T45): lensa tertutup/gelap dan gambar membeku.

Pencabutan kamera sudah terdeteksi oleh `video/capture.py` (perangkat hilang,
gagal baca, laju ambruk). Dua kasus berikut lolos dari semua pemeriksaan itu
karena frame tetap mengalir dengan laju normal:

- **Tertutup**: tangan/benda di depan lensa, lensa kotor/berembun, atau ruangan
  gelap. Gambar menjadi sangat gelap, sangat terang, nyaris seragam, atau buram
  tanpa detail (T57); gerbang lalu diam tanpa penjelasan karena tidak ada orang
  yang terdeteksi.
- **Membeku**: driver terus mengirim frame yang sama persis. Bila membeku saat
  lampu hijau, sesi tidak pernah dianggap kosong dan hijau bisa tertahan untuk
  pekerja berikutnya.

Satu frame buruk tidak dihitung: kondisi harus bertahan beberapa detik
(angka di `config.py`), dan pulih juga harus stabil sebentar, supaya kedipan
lampu atau orang yang lewat sangat dekat tidak memicu gangguan.
"""
from typing import Optional

import cv2
import numpy as np

from .config import cfg

FAULT_BLOCKED = "blocked"
FAULT_FROZEN = "frozen"


def detail_gray(frame: np.ndarray) -> np.ndarray:
    """Gambar abu-abu ukuran tetap untuk mengukur detail: ketajaman tidak bergantung resolusi kamera."""
    small = cv2.resize(frame, (cfg.CAMERA_DETAIL_WIDTH, cfg.CAMERA_DETAIL_HEIGHT), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small


def image_detail(gray: np.ndarray) -> tuple[float, float]:
    """(ketajaman = variansi Laplacian, porsi piksel tepi Canny) dari `detail_gray`."""
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    edges = cv2.Canny(gray, cfg.CAMERA_CANNY_LOW, cfg.CAMERA_CANNY_HIGH)
    return sharpness, float(np.count_nonzero(edges)) / edges.size


def is_dark_or_uniform(gray: np.ndarray) -> bool:
    """Terlalu gelap, terlalu terang, atau nyaris seragam (ambang T45, gambar 64x36)."""
    small = cv2.resize(gray, (cfg.CAMERA_HEALTH_SAMPLE_WIDTH, cfg.CAMERA_HEALTH_SAMPLE_HEIGHT),
                       interpolation=cv2.INTER_AREA)
    mean, std = float(small.mean()), float(small.std())
    return mean < cfg.CAMERA_DARK_MEAN or mean > cfg.CAMERA_BRIGHT_MEAN or std < cfg.CAMERA_UNIFORM_STD


def is_blurred(gray: np.ndarray) -> bool:
    """Tanpa detail: benda menempel di lensa, lensa berembun/diplastik (T57).

    Uji C920 13-10: pemandangan jelas (jalur kosong, orang, orang 0,5 m) ketajaman
    >= 368 & tepi >= 0,08; tertutup tangan/kardus/kain/plastik ketajaman <= 17 &
    tepi ~0. Buram terang lolos dari ambang gelap/seragam, karena itu perlu ini.
    Dua syarat sekaligus supaya dinding polos yang masih bertepi tidak dianggap buram.
    """
    sharpness, edges = image_detail(gray)
    return sharpness < cfg.CAMERA_MIN_SHARPNESS and edges < cfg.CAMERA_MIN_EDGE_RATIO


def is_blocked(frame: np.ndarray) -> bool:
    """Kamera tidak bisa melihat jalur: gelap/terang/seragam (T45) atau buram/terhalang (T57)."""
    gray = detail_gray(frame)
    return is_dark_or_uniform(gray) or is_blurred(gray)


def sample(frame: np.ndarray) -> np.ndarray:
    """Cuplikan berjarak TANPA dirata-rata: derau sensor tetap terlihat, sehingga dua
    frame kamera hidup hampir tidak pernah identik walau pemandangannya diam."""
    step = cfg.CAMERA_FROZEN_SAMPLE_STEP
    return frame[::step, ::step].copy()


class CameraHealth:
    """Satu pemantau per sumber kamera. `update` dipanggil untuk tiap frame baru."""

    def __init__(self):
        self.reset()

    def reset(self, carry: Optional[str] = None):
        """`carry` = gangguan yang masih berlaku setelah kamera dibuka ulang: baru dianggap
        selesai setelah gambar sehat CAMERA_HEALTHY_SECONDS (uji fisik 06-10)."""
        self._previous: Optional[np.ndarray] = None
        self._since: dict[str, Optional[float]] = {FAULT_BLOCKED: None, FAULT_FROZEN: None}
        self._healthy_since: Optional[float] = None
        self.fault: Optional[str] = carry

    def _track(self, name: str, present: bool, now: float) -> bool:
        """True bila kondisi `name` sudah bertahan cukup lama."""
        if not present:
            self._since[name] = None
            return False
        start = self._since[name] = self._since[name] or now
        hold = cfg.CAMERA_BLOCKED_SECONDS if name == FAULT_BLOCKED else cfg.CAMERA_FROZEN_SECONDS
        return now - start >= hold

    def update(self, frame: np.ndarray, now: float) -> Optional[str]:
        """Gangguan yang sedang berlaku (FAULT_*), atau None bila gambar sehat."""
        current = sample(frame)
        blocked = is_blocked(frame)
        # Gambar tertutup rapat (hitam pekat) memang identik antar-frame tanpa derau:
        # itu bukan driver macet. Uji fisik 06-10: dulu dinilai "membeku" dan kamera
        # dibuka ulang berulang-ulang. Membeku hanya dinilai pada gambar berdetail.
        frozen = not blocked and self._previous is not None and np.array_equal(current, self._previous)
        self._previous = current
        detected = (FAULT_FROZEN if self._track(FAULT_FROZEN, frozen, now)
                    else FAULT_BLOCKED if self._track(FAULT_BLOCKED, blocked, now) else None)
        if detected is not None:
            self.fault, self._healthy_since = detected, None
        elif self.fault is not None:
            # Pulih harus stabil sebentar supaya gangguan tidak berkedip-kedip
            self._healthy_since = self._healthy_since or now
            if now - self._healthy_since >= cfg.CAMERA_HEALTHY_SECONDS:
                self.fault = None
        return self.fault
