"""Nama foto bukti tidak boleh kembar (T64).

Dulu nama foto hanya `worker_<id>_<detik>.jpg`: dua inspeksi ID pelacak sama di detik
yang sama memakai nama yang sama, foto pertama tertimpa, dan dua baris audit merujuk
satu foto (bukti salah orang). VLM berjalan paralel, jadi nama juga harus unik
antar-thread.
"""

import threading
import time
import types

import cv2
import numpy as np
import pytest

import backend.audit.report_manager as rm
from backend.audit import db as audit_db

FROZEN = 1_790_000_000.0


@pytest.fixture
def frozen_mgr(tmp_path, monkeypatch):
    clock = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")})
    clock.localtime = lambda t=None: time.gmtime(FROZEN if t is None else t)
    clock.time = lambda: FROZEN
    monkeypatch.setattr(audit_db, "time", clock)
    mgr = rm.ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()
    yield mgr
    mgr._opened = False


def _save(mgr, shade):
    crop = np.full((40, 20, 3), shade, np.uint8)
    return mgr.save_inspection(
        track_id=7,
        is_complete=True,
        items={},
        missing_items=[],
        notes="",
        inference_source="uji",
        inference_time_ms=1.0,
        crop_img=crop,
    )


def _shade(mgr, name):
    image = cv2.imread(str(mgr.snapshots_dir / name))
    assert image is not None, name
    return int(image[..., 0].mean().round())


def test_dua_inspeksi_detik_sama_fotonya_tidak_saling_menimpa(frozen_mgr):
    first, second = _save(frozen_mgr, 40), _save(frozen_mgr, 200)
    assert first["snapshot_filename"] != second["snapshot_filename"]
    # Setiap baris audit menunjuk foto pekerjanya sendiri (JPEG: toleransi kecil)
    assert abs(_shade(frozen_mgr, first["snapshot_filename"]) - 40) <= 3
    assert abs(_shade(frozen_mgr, second["snapshot_filename"]) - 200) <= 3


def test_nama_pertama_tetap_format_lama_lalu_berakhiran_nomor(frozen_mgr):
    slug = time.strftime("%Y%m%d_%H%M%S", time.gmtime(FROZEN))
    names = [_save(frozen_mgr, s)["snapshot_filename"] for s in (10, 20, 30)]
    assert names == [f"worker_7_{slug}.jpg", f"worker_7_{slug}_2.jpg", f"worker_7_{slug}_3.jpg"]
    assert all(frozen_mgr.get_snapshot_path(n) for n in names), "nama baru tetap lolos validasi unduh foto"


def test_simpan_paralel_namanya_unik(frozen_mgr):
    results, barrier = [], threading.Barrier(8)

    def worker(shade):
        barrier.wait()
        results.append(_save(frozen_mgr, shade)["snapshot_filename"])

    threads = [threading.Thread(target=worker, args=(20 * i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 8 and len(set(results)) == 8
    assert len(list(frozen_mgr.snapshots_dir.glob("*.jpg"))) == 8


def test_gagal_tulis_tidak_memakan_nama(frozen_mgr, monkeypatch):
    real = frozen_mgr._write_snapshot
    monkeypatch.setattr(frozen_mgr, "_write_snapshot", lambda path, image: False)
    assert _save(frozen_mgr, 10)["snapshot_filename"] == ""
    monkeypatch.setattr(frozen_mgr, "_write_snapshot", real)
    slug = time.strftime("%Y%m%d_%H%M%S", time.gmtime(FROZEN))
    assert _save(frozen_mgr, 10)["snapshot_filename"] == f"worker_7_{slug}.jpg"
