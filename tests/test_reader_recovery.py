"""T77: thread pembaca kamera pulih sendiri setelah galat tak terduga.

Uji T75 (19-10): RAM habis -> `cap.read()` melempar `_ArrayMemoryError` -> thread pembaca
berhenti selamanya; gerbang buta sampai operator memilih ulang kamera. Kamera & jam tiruan
dipinjam dari tes karakterisasi pembaca (`_World`), tanpa kejadian acak.
"""
from test_capture_characterization import _World

from backend import messages
from backend.config import cfg
from backend.video import capture


def _service(world, steps, error_at):
    """Layanan dengan putaran terbatas; `cap.read()` melempar galat sekali di putaran `error_at`."""
    trace = []

    class Driven(capture.VideoCaptureService):
        @property
        def is_running(self):
            trace.append((self.camera_status, self.camera_error, self.raw_seq))
            if len(trace) == error_at:
                world.raise_next = True
            return len(trace) <= steps

        @is_running.setter
        def is_running(self, value):
            pass

    return Driven(), trace


def test_galat_baca_tidak_menghentikan_pembaca(monkeypatch):
    monkeypatch.setattr(cfg, "CAMERA_AUTOSTART", False)
    world = _World(0, capture, monkeypatch)
    svc, trace = _service(world, steps=400, error_at=50)
    svc.request_camera(1)
    svc._reader_loop()

    expected_error = messages.CAMERA_READER_ERROR.format(error="galat driver tiruan")
    lost_at = next(i for i, t in enumerate(trace) if t[:2] == ("LOST", expected_error))
    assert trace[lost_at - 1][0] == "OK", "sebelum galat kamera berjalan normal"
    assert trace[-1][0] == "OK", "pembaca menyambung ulang kamera setelah galat"
    assert trace[-1][2] > trace[lost_at][2], "frame kembali mengalir"
    assert svc._reader.error_streak == 0, "hitungan galat beruntun direset setelah putaran berhasil"


def test_jeda_berlipat_dan_dibatasi(monkeypatch):
    _World(0, capture, monkeypatch)
    delays = []
    monkeypatch.setattr(capture.time, "sleep", delays.append)
    monkeypatch.setattr(cfg, "CAMERA_ERROR_BACKOFF_SECONDS", 1.0)
    monkeypatch.setattr(cfg, "CAMERA_ERROR_BACKOFF_MAX_SECONDS", 30.0)
    svc = capture.VideoCaptureService()
    for _ in range(7):
        svc._recover_reader(MemoryError("Unable to allocate 6.2 MiB"))
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_galat_tanpa_kamera_tidak_memvonis_lepas(monkeypatch):
    """Belum ada kamera dipilih: tidak ada yang disambung ulang, layar pemilihan tetap."""
    _World(0, capture, monkeypatch)
    monkeypatch.setattr(capture.time, "sleep", lambda s: None)
    svc = capture.VideoCaptureService()
    svc._recover_reader(RuntimeError("galat tiruan"))
    assert (svc.camera_status, svc.camera_error) == ("IDLE", "")
