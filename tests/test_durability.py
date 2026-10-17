"""Ketahanan saat listrik padam/crash (T37): audit, foto bukti, catatan hidup server."""
import json
import logging
import threading
import time

import numpy as np
import pytest

from backend import report_manager as rm_module
from backend import uptime
from backend.report_manager import SNAPSHOT_TMP_SUFFIX, ReportManager

SYNCHRONOUS_FULL = 2


@pytest.fixture
def mgr(tmp_path):
    return ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()


def _save(mgr, crop):
    return mgr.save_inspection(track_id=7, is_complete=True, items={}, missing_items=[], notes="",
                               inference_source="VLM_LIVE:uji/model", inference_time_ms=1.0, crop_img=crop)


# --- Audit ------------------------------------------------------------------------------

def test_koneksi_penulis_audit_memakai_synchronous_full(mgr):
    # Pragma berlaku per koneksi; yang dicek koneksi yang dipakai menulis audit
    conn = mgr._get_connection()
    try:
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == SYNCHRONOUS_FULL
    finally:
        conn.close()


# --- Foto bukti -------------------------------------------------------------------------

def test_foto_bukti_tertulis_utuh_tanpa_berkas_sementara(mgr):
    meta = _save(mgr, np.full((64, 32, 3), 128, np.uint8))
    name = meta["snapshot_filename"]
    assert name and (mgr.snapshots_dir / name).stat().st_size > 0
    assert not list(mgr.snapshots_dir.glob(f"*{SNAPSHOT_TMP_SUFFIX}"))


def test_foto_gagal_ditulis_audit_tidak_merujuk_foto(mgr, monkeypatch):
    # Dulu hasil cv2.imwrite tidak diperiksa: audit menyimpan nama foto yang tak ada
    monkeypatch.setattr(rm_module.cv2, "imencode", lambda *a, **k: (False, None))
    monkeypatch.setattr(rm_module.cv2, "imwrite", lambda *a, **k: False)  # cara lama
    meta = _save(mgr, np.full((64, 32, 3), 128, np.uint8))
    assert meta["snapshot_filename"] == ""
    assert not list(mgr.snapshots_dir.iterdir())


def test_foto_setengah_jadi_dibuang_saat_start(tmp_path):
    snaps = tmp_path / "snapshots"
    snaps.mkdir()
    (snaps / f"worker_1_20260927_100000.jpg{SNAPSHOT_TMP_SUFFIX}").write_bytes(b"sebagian")
    (snaps / "worker_2_20260927_100001.jpg").write_bytes(b"utuh")
    ReportManager(tmp_path / "audit.db", snaps).open()
    assert [p.name for p in snaps.iterdir()] == ["worker_2_20260927_100001.jpg"]


# --- Catatan hidup server ---------------------------------------------------------------

def test_belum_ada_catatan_tidak_melaporkan_apa_pun():
    assert uptime.describe_previous(None, 100.0) is None
    assert uptime.describe_previous({"x": 1}, 100.0) is None


def test_berhenti_rapi_dilaporkan_info_dengan_lama_mati():
    report = uptime.describe_previous({uptime.KEY_LAST_ALIVE: 0.0, uptime.KEY_CLEAN: True}, 125.0)
    assert report is not None
    level, msg = report
    assert level == logging.INFO
    assert "2 menit 5 detik" in msg


def test_berhenti_mendadak_dilaporkan_peringatan():
    report = uptime.describe_previous({uptime.KEY_LAST_ALIVE: 0.0, uptime.KEY_CLEAN: False}, 3 * 3600 + 60)
    assert report is not None
    level, msg = report
    assert level == logging.WARNING
    assert "MENDADAK" in msg and "3 jam 1 menit" in msg


def test_monitor_menandai_hidup_lalu_berhenti_rapi(tmp_path):
    path = tmp_path / "uptime.json"
    m = uptime.UptimeMonitor(path)
    m.start()
    assert json.loads(path.read_text())[uptime.KEY_CLEAN] is False, "selama hidup: belum berhenti rapi"
    m.stop()
    assert json.loads(path.read_text())[uptime.KEY_CLEAN] is True


def test_start_setelah_henti_mendadak_mencatat_peringatan(tmp_path, caplog):
    path = tmp_path / "uptime.json"
    path.write_text(json.dumps({uptime.KEY_LAST_ALIVE: 1.0, uptime.KEY_CLEAN: False}))
    m = uptime.UptimeMonitor(path)
    with caplog.at_level(logging.WARNING, logger=uptime.__name__):
        m.start()
    m.stop()
    assert any("MENDADAK" in r.getMessage() for r in caplog.records)


def test_stop_saat_detak_sedang_menulis_tetap_tercatat_rapi(tmp_path, monkeypatch):
    # Tinjauan T37: detak clean=False yang sedang berjalan tidak boleh menimpa
    # status rapi dari stop(). Detak ditahan di tengah penulisan secara sengaja.
    monkeypatch.setattr(uptime.cfg, "UPTIME_HEARTBEAT_SECONDS", 0.01)
    path = tmp_path / "uptime.json"
    m = uptime.UptimeMonitor(path)
    in_beat, release = threading.Event(), threading.Event()
    original = m._write_unlocked

    def slow_write(clean):
        if not clean and threading.current_thread() is m._thread:
            in_beat.set()
            release.wait(2)
        original(clean)

    monkeypatch.setattr(m, "_write_unlocked", slow_write)
    m.start()
    assert in_beat.wait(2), "detak tidak berjalan"
    stopper = threading.Thread(target=m.stop)
    stopper.start()
    time.sleep(0.1)       # stop() sudah dipanggil saat detak masih menulis
    release.set()
    stopper.join(2)
    assert m._thread is not None
    m._thread.join(2)  # tulisan detak (bila ada) harus sudah terjadi sebelum diperiksa
    assert json.loads(path.read_text())[uptime.KEY_CLEAN] is True
