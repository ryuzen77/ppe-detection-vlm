"""Menentukan kapan pekerja siap dipotret untuk VLM (T46).

Uji nyata 28-09: 12 dari 20 sesi dipotret 0,08 dtk setelah sesi dimulai, saat
pekerja masih melangkah masuk. Syarat lama dihitung dalam frame (3 frame ≈ 0,1
dtk di 30 FPS), dan gerak antar-frame 30 ms tampak nol walau orang berjalan.
Karena itu kesiapan diukur dalam WAKTU: tubuh utuh, menghadap kamera, dan tidak
bergeser dari posisi awal jendela selama `READY_HOLD_SECONDS`. Pergeseran
dibandingkan dengan frame pertama jendela (bukan frame sebelumnya), sehingga
langkah pelan pun terhitung.
"""
from typing import Optional

from . import frame_quality
from . import pose_keypoints as kp
from .config import cfg


def shoulders_visible(keypoints: Optional[list]) -> bool:
    """Kedua bahu terlihat = pekerja menghadap (atau membelakangi) kamera, tidak miring.

    Tanpa data pose (detektor jatuh ke kotak saja) syarat ini tidak bisa dinilai,
    jadi tidak menahan pemotretan.
    """
    if not keypoints or len(keypoints) <= kp.RIGHT_SHOULDER:
        return True
    return all(keypoints[i][kp.CONFIDENCE] >= cfg.KEYPOINT_CONF_THRESHOLD
               for i in (kp.LEFT_SHOULDER, kp.RIGHT_SHOULDER))


def drift(bbox: list, anchor: list) -> float:
    """Pergeseran relatif tubuh terhadap awal jendela: titik tengah atau perubahan tinggi.

    Perubahan tinggi menangkap pekerja yang berjalan lurus ke arah kamera, yang
    titik tengahnya nyaris tidak bergeser.
    """
    anchor_height = max(anchor[3] - anchor[1], 1)
    height_change = abs((bbox[3] - bbox[1]) - anchor_height) / anchor_height
    return max(frame_quality.motion(bbox, anchor), height_change)


class ReadinessTracker:
    """Satu jendela diam per sesi. `update` dipanggil untuk setiap frame tubuh-utuh."""

    def __init__(self):
        self.anchor: Optional[list] = None
        self.hold_started: Optional[float] = None
        self.restarts = 0

    def reset(self):
        self.anchor = None
        self.hold_started = None

    @property
    def holding(self) -> bool:
        """False = belum ada jendela (mis. tidak menghadap kamera); frame ini bukan kandidat."""
        return self.anchor is not None

    def held_seconds(self, now: float) -> float:
        return 0.0 if self.hold_started is None else now - self.hold_started

    def update(self, bbox: list, keypoints: Optional[list], now: float) -> bool:
        """Memperbarui jendela; True bila jendela dimulai ulang (kandidat lama harus dibuang)."""
        facing = shoulders_visible(keypoints) or not cfg.READY_REQUIRE_SHOULDERS
        moved = self.anchor is not None and drift(bbox, self.anchor) > cfg.READY_MAX_DRIFT
        if self.anchor is not None and not moved and facing:
            return False
        if self.anchor is not None:
            self.restarts += 1
        # Tidak menghadap kamera: jendela belum boleh berjalan sama sekali
        self.anchor, self.hold_started = (list(bbox), now) if facing else (None, None)
        return True

    def ready(self, now: float) -> bool:
        return self.holding and self.held_seconds(now) >= cfg.READY_HOLD_SECONDS
