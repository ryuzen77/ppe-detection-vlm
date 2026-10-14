"""Karakterisasi thread pembaca kamera `VideoCaptureService._reader_loop` (T42c).

Sebelum fungsi ±200 baris itu dipecah, perilaku kode lama direkam di
`golden/capture_reader.json`: ribuan putaran dengan jam & kamera tiruan, diselingi
kejadian acak berbenih (operator pindah kamera / optimasi / lepas kamera, kamera
dicabut & dicolok ulang dengan indeks berubah, gambar membeku, laju baca ambruk,
gagal baca, kamera tidak terbuka / tanpa frame, daftar perangkat gagal dibaca, galat).
Refaktor tidak boleh mengubahnya.

Bila perilaku SENGAJA diubah, bangkitkan ulang acuannya:
    python tests/test_capture_characterization.py --regenerate
"""
import json
import sys
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOLDEN = Path(__file__).resolve().parent / "golden" / "capture_reader.json"
SCENARIOS, STEPS = 12, 1500
DEVICES = ["Integrated Camera", "HD Pro Webcam C920", "OBS Virtual Camera"]
BEHAVIORS = ["ok", "ok", "ok", "slow", "fail", "noopen", "noframes"]
READ_SECONDS, SLOW_READ_SECONDS = 0.04, 0.5


class _Cap:
    """cv2.VideoCapture tiruan; perilakunya mengikuti keadaan dunia saat dibaca."""

    def __init__(self, world, name):
        self.world, self.name, self.open = world, name, name is not None and world.behavior[name] != "noopen"

    def isOpened(self):
        return self.open

    def set(self, prop, value):
        return True

    def release(self):
        self.open = False

    def read(self):
        w = self.world
        if w.raise_next:
            w.raise_next = False
            raise RuntimeError("galat driver tiruan")
        behavior = w.behavior[self.name]
        w.now += SLOW_READ_SECONDS if behavior == "slow" else READ_SECONDS
        if not self.open or self.name not in w.visible or behavior in ("fail", "noframes"):
            return False, None
        return True, np.full((3, 4, 1), 100 + DEVICES.index(self.name), np.uint8)


class _World:
    def __init__(self, seed, capture_mod, monkeypatch):
        from backend import camera_manager
        from backend.camera_manager import CameraMode
        self.rng = np.random.default_rng(seed)
        self.seed, self.now, self.raise_next, self.enum_fails = seed, 1000.0, False, False
        self.visible = list(DEVICES)
        self.behavior = {name: "ok" for name in DEVICES}
        self.resets, self.saved, self.messages = 0, [], []
        mode = CameraMode(64, 48, 30.0, "MJPG", 640, 480)

        def names():
            if self.enum_fails:
                raise OSError("enumerasi gagal")
            return list(self.visible)

        def probe(index):
            self.now += 2.0
            return [mode] if self.rng.random() < 0.7 else []

        def synthetic(width, height, message):
            if message not in self.messages:
                self.messages.append(message)
            return np.full((2, 2, 1), self.messages.index(message), np.uint8)

        def sleep(seconds):
            self.now += seconds

        monkeypatch.setattr(capture_mod, "time", types.SimpleNamespace(time=lambda: self.now, sleep=sleep))
        monkeypatch.setattr(camera_manager, "list_device_names", names)
        monkeypatch.setattr(camera_manager, "open_capture",
                            lambda i: _Cap(self, self.visible[i] if i is not None and 0 <= i < len(self.visible)
                                           else None))  # seperti OpenCV: indeks None/tak ada = tidak terbuka
        monkeypatch.setattr(camera_manager, "probe_modes", probe)
        monkeypatch.setattr(camera_manager, "save_selection", lambda i, m, n="": self.saved.append([i, n]))
        monkeypatch.setattr(camera_manager, "autostart_target",
                            lambda: (DEVICES[1], {"width": 64, "height": 48, "req_width": 800, "req_height": 600}, 1))
        monkeypatch.setattr(capture_mod.camera_mgr, "get_device",
                            lambda i: {"selected_mode": {"width": 64, "height": 48}} if i == 2 else None)
        monkeypatch.setattr(capture_mod.camera_mgr, "record_device_modes", lambda *a: None)
        monkeypatch.setattr(capture_mod.state_mgr, "reset_all", self._reset)
        monkeypatch.setattr(capture_mod.hud, "draw_synthetic_frame", synthetic)

    def _reset(self):
        self.resets += 1

    def inject(self, svc):
        """Kejadian acak di antara dua putaran pembaca."""
        from backend import messages
        r = self.rng.random
        if r() < 0.004:
            svc.request_camera(int(self.rng.integers(0, 4)), None if r() < 0.5 else {"width": 64, "height": 48})
        if r() < 0.002:
            svc.request_optimize()
        if r() < 0.002:
            svc.request_idle()
        if r() < 0.003:
            svc._missing_reason = messages.CAMERA_FROZEN if r() < 0.5 else messages.CAMERA_UNPLUGGED
            svc._device_missing = True
        name = DEVICES[int(self.rng.integers(0, len(DEVICES)))]
        if name in self.visible and r() < 0.004:
            self.visible.remove(name)                       # dicabut
        elif name not in self.visible and r() < 0.02:
            self.visible.insert(int(self.rng.integers(0, len(self.visible) + 1)), name)  # dicolok, indeks bisa berubah
        if r() < 0.004:
            self.behavior[name] = BEHAVIORS[int(self.rng.integers(0, len(BEHAVIORS)))]
        if r() < 0.002:
            self.enum_fails = not self.enum_fails
        if self.seed % 6 == 5 and r() < 0.0007:
            self.raise_next = True


def _snapshot(svc, world):
    raw = svc.latest_raw
    return [svc.camera_status, svc.camera_error, svc.camera_index, svc.camera_name, svc.camera_name_verified,
            svc.use_synthetic, None if svc.active_mode is None else svc.active_mode.get("req_width"),
            svc.frame_width, svc.frame_height, None if raw is None else int(raw.flat[0]),
            world.resets, len(world.saved), svc._device_missing]


def run_scenarios(monkeypatch):
    from backend.config import cfg
    from backend.video import capture
    out = []
    for seed in range(SCENARIOS):
        monkeypatch.setattr(cfg, "CAMERA_AUTOSTART", seed % 2 == 1)
        world = _World(seed, capture, monkeypatch)
        rows, step = [], [0]

        class Driven(capture.VideoCaptureService):
            @property
            def is_running(self):
                snap = _snapshot(self, world)
                if not rows or rows[-1][2:] != snap:
                    rows.append([step[0], round(world.now, 3)] + snap)
                step[0] += 1
                if step[0] > STEPS:
                    return False
                world.inject(self)
                return True

            @is_running.setter
            def is_running(self, value):
                pass

        svc = Driven()
        if seed % 4 == 0:
            svc.request_camera(1)
        svc._reader_loop()
        rows.append(["akhir", round(world.now, 3), svc.raw_seq, world.saved, world.messages, step[0]]
                    + _snapshot(svc, world))
        out.append(rows)
    return out


def test_pembaca_kamera_tidak_berubah(monkeypatch):
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(run_scenarios(monkeypatch)))
    for seed, (a, e) in enumerate(zip(actual, expected)):
        first = next((i for i, (x, y) in enumerate(zip(a, e)) if x != y), None)
        assert len(a) == len(e) and first is None, (
            f"skenario {seed} berubah di baris {first}: {a[first] if first is not None else len(a)} "
            f"vs {e[first] if first is not None else len(e)}")
    assert len(actual) == len(expected)


def test_acuan_mencakup_semua_jalur():
    scenarios = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rows = [r for s in scenarios for r in s if r[0] != "akhir"]
    assert {"IDLE", "OK", "LOST", "SYNTHETIC"} <= {r[2] for r in rows}
    from backend import messages
    errors = {r[3] for r in rows}
    for expected in (messages.CAMERA_STALLED, messages.CAMERA_DISCONNECTED, messages.CAMERA_FROZEN,
                     messages.CAMERA_UNPLUGGED):
        assert expected in errors, expected
    finals = [s[-1] for s in scenarios]
    assert any(f[7] == "galat driver tiruan" for f in finals), "jalur galat tak terduga"
    assert all(f[5] > 100 for f in finals), "skenario tidak boleh berhenti terlalu dini (kecuali jalur galat)"


if __name__ == "__main__" and "--regenerate" in sys.argv:
    import conftest  # noqa: F401
    import pytest
    mp = pytest.MonkeyPatch()
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(run_scenarios(mp)), encoding="utf-8")
    mp.undo()
    print(f"acuan ditulis: {GOLDEN}")
