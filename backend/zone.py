"""Zona titik berdiri (T36d): siapa yang sedang berdiri di titik pemeriksaan.

Kamera dipasang di atas gerbang dan menghadap pekerja yang datang, jadi makin
dekat seseorang ke gerbang, makin ke bawah posisi kakinya di gambar. Zona adalah
pita posisi kaki (relatif tinggi gambar, 0 = atas, 1 = bawah). Orang di belakang
zona (antrean) tidak dihitung, sehingga pekerja berikutnya bisa maju begitu
subjek keluar zona.

Logika murni tanpa kamera/GPU; status aktif dipegang `ZoneStore` dan disimpan
di runtime_settings.
"""

import threading
from dataclasses import asdict, dataclass
from typing import Optional

from . import messages, runtime_settings
from . import pose_keypoints as kp
from .config import cfg

# Indeks titik pose COCO untuk pergelangan kaki kiri & kanan
SETTINGS_KEY = "zone"
SOURCE_DEFAULT, SOURCE_CALIBRATED, SOURCE_MANUAL = "bawaan", "kalibrasi", "manual"


@dataclass(frozen=True)
class Zone:
    enabled: bool
    y_min: float
    y_max: float
    source: str = SOURCE_DEFAULT


def default_zone() -> Zone:
    # Nonaktif sampai dikalibrasi di lokasi: perilaku gerbang tidak berubah
    # sebelum kamera dipasang dan diatur.
    return Zone(False, cfg.ZONE_Y_MIN_DEFAULT, cfg.ZONE_Y_MAX_DEFAULT, SOURCE_DEFAULT)


def _relative(y: float, frame_h: int) -> float:
    return min(1.0, max(0.0, y / frame_h))


def ankle_y(keypoints, frame_h: int) -> Optional[float]:
    """Posisi kaki dari pergelangan kaki yang cukup yakin; None bila tidak terlihat.

    Diambil yang PALING BAWAH di gambar, bukan rata-rata: saat melangkah satu kaki
    terangkat dan rata-rata "tertarik mundur", sehingga orang yang masuk/keluar
    zona tampak berkedip (temuan tinjauan T36d). Kaki paling bawah adalah kaki yang
    menapak dan paling dekat ke gerbang.
    """
    if frame_h <= 0:
        return None
    ys = []
    for idx in (kp.LEFT_ANKLE, kp.RIGHT_ANKLE):
        try:
            _, y, conf = keypoints[idx][:3]
        except (TypeError, IndexError, ValueError):
            continue
        if conf >= cfg.KEYPOINT_CONF_THRESHOLD:
            ys.append(float(y))
    return _relative(max(ys), frame_h) if ys else None


def box_bottom_y(bbox, frame_h: int) -> Optional[float]:
    """Tepi bawah kotak tubuh: perkiraan kasar posisi kaki. Bila badan bawah
    tertutup orang lain, kotak berhenti di pinggang, jadi hanya dipakai sebagai
    pilihan terakhir (lihat FootMemory)."""
    if frame_h <= 0 or not bbox:
        return None
    return _relative(float(bbox[3]), frame_h)


class FootMemory:
    """Posisi kaki terakhir yang terlihat jelas per ID pelacak.

    Bila pergelangan kaki subjek tertutup (mis. orang lewat di depannya), posisi
    terakhir yang jelas dipakai selama FOOT_MEMORY_SECONDS, bukan tepi bawah kotak
    yang bisa melompat ke pinggang dan membuat subjek dianggap keluar zona di
    tengah pemeriksaan (temuan tinjauan T36d).
    """

    def __init__(self):
        self._last: dict[int, tuple[float, float]] = {}

    def resolve(self, track_id: int, ankle: Optional[float], box: Optional[float], now: float) -> Optional[float]:
        for tid, (at, _) in list(self._last.items()):
            if now - at > cfg.FOOT_MEMORY_SECONDS:
                del self._last[tid]
        if ankle is not None:
            self._last[track_id] = (now, ankle)
            return ankle
        remembered = self._last.get(track_id)
        return remembered[1] if remembered else box

    def clear(self):
        self._last.clear()


def in_zone(y: Optional[float], zone: Zone) -> bool:
    """Zona nonaktif = semua orang dihitung (perilaku sebelum T36d)."""
    if not zone.enabled:
        return True
    return y is not None and zone.y_min <= y <= zone.y_max


def validated(y_min: float, y_max: float) -> tuple[float, float]:
    if not (0.0 <= y_min < y_max <= 1.0):
        raise ValueError(messages.ZONE_INVALID_RANGE)
    if y_max - y_min < cfg.ZONE_MIN_HEIGHT:
        raise ValueError(messages.ZONE_TOO_NARROW.format(min=cfg.ZONE_MIN_HEIGHT))
    return y_min, y_max


def calibrated(y: float) -> Zone:
    """Pita di sekitar posisi kaki orang yang berdiri di titik pemeriksaan."""
    m = cfg.ZONE_CALIBRATE_MARGIN
    return Zone(True, max(0.0, y - m), min(1.0, y + m), SOURCE_CALIBRATED)


class ZoneStore:
    """Zona aktif, aman diakses dari thread kamera dan API."""

    def __init__(self):
        self._lock = threading.Lock()
        self._zone = default_zone()

    def load(self):
        saved = runtime_settings.load().get(SETTINGS_KEY)
        if isinstance(saved, dict):
            try:
                y_min, y_max = validated(float(saved["y_min"]), float(saved["y_max"]))
                zone = Zone(bool(saved.get("enabled")), y_min, y_max, str(saved.get("source", SOURCE_MANUAL)))
            except (KeyError, TypeError, ValueError):
                zone = default_zone()  # berkas rusak: kembali ke bawaan, jangan gagal start
            with self._lock:
                self._zone = zone

    def get(self) -> Zone:
        with self._lock:
            return self._zone

    def set(self, zone: Zone) -> Zone:
        with self._lock:
            self._zone = zone
        runtime_settings.update(SETTINGS_KEY, asdict(zone))
        return zone

    def update(
        self, enabled: Optional[bool] = None, y_min: Optional[float] = None, y_max: Optional[float] = None
    ) -> Zone:
        current = self.get()
        lo = current.y_min if y_min is None else float(y_min)
        hi = current.y_max if y_max is None else float(y_max)
        lo, hi = validated(lo, hi)
        changed_band = (lo, hi) != (current.y_min, current.y_max)
        return self.set(
            Zone(
                current.enabled if enabled is None else bool(enabled),
                lo,
                hi,
                SOURCE_MANUAL if changed_band else current.source,
            )
        )


zone_store = ZoneStore()
