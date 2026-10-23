"""Karakterisasi `hud.draw_hud` (T42i).

Sebelum fungsi itu dipecah, keluaran kode lama direkam di `golden/hud.json` sebagai
hash SHA-256 piksel: frame acak berbenih (beberapa resolusi), lorong aktif/mati,
0–20 orang (di dalam/luar lorong, tubuh utuh/terpotong, tanpa atribut
`is_inside_corridor`, kotak di tepi frame), FPS, dan status lampu. Refaktor tidak boleh
mengubah satu piksel pun.

Bila perilaku SENGAJA diubah, bangkitkan ulang acuannya:
    python tests/test_hud_characterization.py --regenerate
"""

import hashlib
import json
import random
import sys
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.video import hud  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden" / "hud.json"
SCENARIOS = 60
SIZES = [(720, 1280), (480, 640), (1080, 1920), (240, 320)]
LIGHTS = ["GREEN", "RED", "YELLOW", "OFF"]
REASONS = ["Kaki terpotong", "Kepala terpotong", "Terlalu dekat"]


def _person(rng: random.Random, h: int, w: int):
    x1, y1 = rng.randint(-20, w - 10), rng.randint(-20, h - 10)
    fields = {
        "bbox": (x1, y1, x1 + rng.randint(5, w // 2), y1 + rng.randint(5, h)),
        "track_id": rng.randint(1, 999),
        "is_full_body": rng.random() < 0.5,
        "reason": rng.choice(REASONS),
    }
    if rng.random() < 0.8:  # sisanya tanpa atribut: draw_hud menganggapnya di dalam lorong
        fields["is_inside_corridor"] = rng.random() < 0.6
    return types.SimpleNamespace(**fields)


def _render(seed: int, monkeypatch) -> str:
    rng = random.Random(seed)
    h, w = rng.choice(SIZES)
    frame = np.random.default_rng(seed).integers(0, 256, (h, w, 3), dtype=np.uint8)
    monkeypatch.setattr(hud.cfg, "ENABLE_SERVER_HUD", True)
    monkeypatch.setattr(hud.cfg, "ENABLE_CORRIDOR_FILTER", rng.random() < 0.7)
    monkeypatch.setattr(hud, "detector", types.SimpleNamespace(device_label=rng.choice(["GPU", "CPU"])))
    monkeypatch.setattr(hud, "notifier", types.SimpleNamespace(current_state=rng.choice(LIGHTS)))
    people = [_person(rng, h, w) for _ in range(rng.choice([0, 1, 2, 5, 20]))]
    before = frame.copy()
    out = hud.draw_hud(frame, people, rng.uniform(0, 60))
    assert np.array_equal(frame, before), "draw_hud tidak boleh mengubah frame masukan"
    return hashlib.sha256(out.tobytes()).hexdigest()


def _record(monkeypatch) -> list[str]:
    return [_render(seed, monkeypatch) for seed in range(SCENARIOS)]


def test_draw_hud_pixels_unchanged(monkeypatch):
    assert _record(monkeypatch) == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_draw_hud_disabled_returns_input(monkeypatch):
    monkeypatch.setattr(hud.cfg, "ENABLE_SERVER_HUD", False)
    frame = np.zeros((4, 4, 3), np.uint8)
    assert hud.draw_hud(frame, [], 30.0) is frame


if __name__ == "__main__" and "--regenerate" in sys.argv:
    import pytest

    mp = pytest.MonkeyPatch()
    try:
        GOLDEN.write_text(json.dumps(_record(mp), indent=1) + "\n", encoding="utf-8")
    finally:
        mp.undo()
    print(f"Acuan ditulis: {GOLDEN}")
