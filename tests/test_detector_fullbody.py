"""Karakterisasi pemeriksaan tubuh-utuh `detector.detect_and_track` (T41).

Logika kepala/kaki terpotong belum pernah dites. Sebelum indeks pose & rasio
dipindah ke satu sumber (T41), keluaran kode lama untuk ratusan orang buatan
direkam di `golden/detector_fullbody.json`; refaktor tidak boleh mengubahnya.

Bila perilaku SENGAJA diubah, bangkitkan ulang acuannya:
    python tests/test_detector_fullbody.py --regenerate
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.detector import PersonDetector  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden" / "detector_fullbody.json"
FRAME_W, FRAME_H = 864, 480
CASES = 400


class _T:
    """Pengganti tensor torch secukupnya untuk detect_and_track."""

    def __init__(self, a):
        self.a = np.asarray(a)

    def cpu(self):
        return self

    def numpy(self):
        return self.a

    def int(self):
        return _T(self.a.astype(int))


class _Boxes:
    def __init__(self, xyxy, ids, conf):
        self.xyxy, self.id, self.conf = _T(xyxy), _T(ids), _T(conf)


class _Kpts:
    def __init__(self, data):
        self.data = _T(data)


class _Result:
    def __init__(self, xyxy, ids, conf, kpts):
        self.boxes = _Boxes(xyxy, ids, conf)
        self.keypoints = None if kpts is None else _Kpts(kpts)


class _Model:
    def __init__(self):
        self.next: object = None

    def track(self, **_):
        return [self.next]


def _person(rng):
    """Kotak & 17 titik pose acak, sengaja sering menyentuh tepi & berkeyakinan rendah."""
    y1 = int(rng.integers(0, FRAME_H // 2)) if rng.random() < 0.8 else 0
    y2 = int(rng.integers(y1 + 40, FRAME_H + 1)) if rng.random() < 0.8 else FRAME_H
    x1 = int(rng.integers(0, FRAME_W - 120))
    x2 = int(rng.integers(x1 + 60, min(FRAME_W, x1 + 400) + 1))
    kpts = np.zeros((17, 3))
    kpts[:, 0] = rng.uniform(x1, x2, 17)
    kpts[:, 1] = np.sort(rng.uniform(y1 - 20, y2 + 10, 17))  # kepala di atas, kaki di bawah
    kpts[:, 2] = rng.choice([0.05, 0.2, 0.34, 0.36, 0.6, 0.95], 17)
    return [x1, y1, x2, y2], kpts


def _head_near_top(rng):
    """Kepala dekat tepi atas, hidung & bahu yakin: menguji ruang helm (POSE_HELMET_HEADROOM_FACTOR)."""
    y1 = int(rng.integers(5, 30))
    y2 = int(rng.integers(300, FRAME_H - 20))
    x1 = int(rng.integers(FRAME_W // 3, FRAME_W // 2 - 60))
    x2 = x1 + int(rng.integers(100, 160))
    kpts = np.zeros((17, 3))
    kpts[:, 0] = (x1 + x2) / 2
    kpts[:, 1] = np.linspace(y1 + 10, y2 - 5, 17)
    kpts[:, 2] = 0.9
    kpts[0, 1] = rng.uniform(y1 + 2, y1 + 60)  # hidung
    kpts[5, 1] = kpts[6, 1] = kpts[0, 1] + rng.uniform(30, 120)  # bahu
    return [x1, y1, x2, y2], kpts


def run_cases():
    rng = np.random.default_rng(41)
    detector = PersonDetector()
    model = _Model()
    detector.model = model  # pyright: ignore[reportAttributeAccessIssue]
    frame = np.zeros((FRAME_H, FRAME_W, 3), np.uint8)
    out = []
    for i in range(CASES):
        bbox, kpts = _head_near_top(rng) if i % 4 == 0 else _person(rng)
        with_pose = i % 4 == 0 or rng.random() > 0.1
        model.next = _Result([bbox], [i + 1], [0.9], [kpts] if with_pose else None)
        d = detector.detect_and_track(frame)[0]
        assert d.crop_img is not None
        out.append(
            [
                d.is_full_body,
                d.reason,
                getattr(d, "clip_type", ""),
                list(d.crop_img.shape[:2]),
                None if d.foot_y is None else round(d.foot_y, 6),
            ]
        )
    return out


def test_perilaku_tubuh_utuh_tidak_berubah():
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(run_cases()))
    diffs = [i for i, (a, e) in enumerate(zip(actual, expected)) if a != e]
    assert len(actual) == len(expected) and not diffs, f"{len(diffs)} kasus berubah, mis. #{diffs[:5]}"


def test_acuan_mencakup_semua_cabang():
    """Acuan bermakna hanya bila semua jenis hasil benar-benar muncul."""
    kinds = {row[2] for row in json.loads(GOLDEN.read_text(encoding="utf-8"))}
    assert {"OPTIMAL", "HEAD_CLIPPED", "FEET_CLIPPED", "TOO_FAR", "OUTSIDE_CORRIDOR", "NOT_STANDING"} <= kinds, kinds


if __name__ == "__main__" and "--regenerate" in sys.argv:
    import conftest  # noqa: F401  lingkungan uji (tanpa .env asli)

    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(run_cases()), encoding="utf-8")
    print(f"acuan ditulis: {GOLDEN}")
