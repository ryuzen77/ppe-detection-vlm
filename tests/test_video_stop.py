"""Layanan video menunggu thread-nya berhenti sebelum shutdown berlanjut.

Tanpa itu, interpreter bisa mulai menutup saat thread inferensi masih di dalam
torch, dan proses sesekali mati dengan "pybind11::handle::dec_ref()
PyGILState_Check() failure" (kode keluar 134).
"""

import threading
import time

from backend.config import cfg
from backend.video.capture import VideoCaptureService


def _loop_sampai_berhenti(svc, selesai: list, jeda: float):
    # Meniru thread inferensi: bekerja selama is_running, satu langkah butuh `jeda`
    while svc.is_running:
        time.sleep(jeda)
    time.sleep(jeda)  # langkah terakhir yang sedang berjalan saat stop() dipanggil
    selesai.append(True)


def test_stop_menunggu_thread_inferensi_dan_pembaca_selesai():
    svc = VideoCaptureService()
    svc.is_running = True
    selesai = []
    svc.thread = threading.Thread(target=_loop_sampai_berhenti, args=(svc, selesai, 0.2), daemon=True)
    svc.reader_thread = threading.Thread(target=_loop_sampai_berhenti, args=(svc, selesai, 0.1), daemon=True)
    svc.thread.start()
    svc.reader_thread.start()

    svc.stop()

    assert not svc.thread.is_alive() and not svc.reader_thread.is_alive()
    assert len(selesai) == 2


def test_stop_tidak_menggantung_bila_thread_macet(monkeypatch):
    monkeypatch.setattr(cfg, "THREAD_STOP_TIMEOUT_SECONDS", 0.2)
    svc = VideoCaptureService()
    svc.is_running = True
    lepas = threading.Event()
    svc.thread = threading.Thread(target=lepas.wait, daemon=True)  # tidak peduli is_running
    svc.thread.start()
    try:
        mulai = time.time()
        svc.stop()
        assert time.time() - mulai < 2
    finally:
        lepas.set()


def test_stop_tanpa_start_tidak_galat():
    VideoCaptureService().stop()
