"""T77b: thread inferensi pulih sendiri setelah galat, dan gerbang aman selama galat.

Dulu satu galat (mis. VRAM habis saat YOLO) menghentikan `_capture_loop` selamanya; bila lampu
hijau sedang menyala, sesi tidak pernah berakhir sehingga hijau bisa bertahan tanpa pemeriksaan.
"""

import time
import types
from pathlib import Path

import numpy as np

from backend import messages
from backend.camera_health import FAULT_BLOCKED, FAULT_FROZEN, FAULT_SYSTEM
from backend.config import cfg
from backend.video import capture


def _run_inference(monkeypatch, failures: int, frames: int):
    """`frames` frame baru; deteksi melempar galat pada `failures` frame pertama."""
    faults, delays, calls = [], [], [0]

    def detect(frame):
        calls[0] += 1
        if calls[0] <= failures:
            raise MemoryError("CUDA out of memory (tiruan)")
        return []

    monkeypatch.setattr(capture.detector, "detect_and_track", detect)
    monkeypatch.setattr(capture.state_mgr, "set_camera_fault", faults.append)
    monkeypatch.setattr(capture.state_mgr, "update_frame_detections", lambda d: None)
    monkeypatch.setattr(capture.hud, "draw_hud", lambda frame, d, fps: frame)
    # Hanya jam milik modul capture yang diganti (time.sleep global tetap utuh)
    monkeypatch.setattr(capture, "time", types.SimpleNamespace(time=time.time, sleep=delays.append))
    monkeypatch.setattr(cfg, "CAMERA_ERROR_BACKOFF_SECONDS", 1.0)
    monkeypatch.setattr(cfg, "CAMERA_ERROR_BACKOFF_MAX_SECONDS", 30.0)
    fed = [0]

    class Driven(capture.VideoCaptureService):
        @property
        def is_running(self):
            if fed[0] >= frames:
                return False
            fed[0] += 1
            with self.raw_lock:  # satu frame baru per putaran
                self.latest_raw = np.zeros((8, 8, 3), np.uint8)
                self.raw_seq += 1
            return True

        @is_running.setter
        def is_running(self, value):
            pass

    svc = Driven()
    monkeypatch.setattr(svc, "_camera_fault", lambda frame, now: None)
    svc._capture_loop()
    return svc, faults, delays


def test_galat_inferensi_tidak_menghentikan_thread(monkeypatch):
    svc, _, delays = _run_inference(monkeypatch, failures=3, frames=6)
    assert delays == [1.0, 2.0, 4.0], "jeda berlipat per galat beruntun"
    assert svc.current_frame_bytes is not None, "frame kembali diolah & dialirkan setelah galat"


def test_gerbang_kuning_selama_galat_lalu_pulih(monkeypatch):
    _, faults, _ = _run_inference(monkeypatch, failures=2, frames=4)
    first_error = faults.index(FAULT_SYSTEM)
    assert faults[:first_error] == [None], "sebelum galat gerbang normal"
    last_system = len(faults) - 1 - faults[::-1].index(FAULT_SYSTEM)
    # Selama galat beruntun gangguan tidak pernah dilepas (tidak naik-turun per frame)
    assert None not in faults[first_error : last_system + 1]
    assert faults[last_system + 1 :] and all(f is None for f in faults[last_system + 1 :]), (
        "gangguan selesai setelah satu frame berhasil diolah"
    )


def test_gangguan_system_punya_teks_lampu_dan_suara():
    """state_manager memakai kedua kamus ini untuk SETIAP jenis gangguan."""
    audio_dir = Path(capture.__file__).resolve().parents[1] / "audio"
    for fault in ("lost", FAULT_BLOCKED, FAULT_FROZEN, FAULT_SYSTEM):
        assert fault in messages.LIGHT_CAMERA_FAULT
        sound = messages.CAMERA_FAULT_SOUND[fault]
        assert sound in messages.VOICE_TEXTS
        assert (audio_dir / f"{sound}.mp3").exists()
