"""Migrasi skema audit.db dan alur simpan-baca-ekspor laporan."""
import csv
import io
import json
import sqlite3

import numpy as np
import pytest

from backend import messages
from backend.report_manager import SCHEMA_VERSION, ReportManager

# Skema versi 0 persis seperti sebelum T4: sebelas kolom tetap per item
_CREATE_V0 = """
    CREATE TABLE worker_inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        date_str TEXT NOT NULL,
        time_str TEXT NOT NULL,
        is_complete INTEGER NOT NULL,
        helm_detected INTEGER NOT NULL,
        helm_desc TEXT,
        rompi_detected INTEGER NOT NULL,
        rompi_color TEXT,
        rompi_valid INTEGER NOT NULL,
        rompi_desc TEXT,
        celana_detected INTEGER NOT NULL,
        celana_desc TEXT,
        sepatu_detected INTEGER NOT NULL,
        sepatu_closed INTEGER NOT NULL,
        sepatu_desc TEXT,
        missing_items TEXT,
        notes TEXT,
        inference_source TEXT,
        inference_time_ms REAL,
        snapshot_filename TEXT
    )
"""


def _buat_db_v0(path, baris_dihapus=True):
    conn = sqlite3.connect(str(path))
    conn.execute(_CREATE_V0)
    rows = [
        # id, track, lengkap?, helm, rompi, warna, valid, celana, sepatu, tertutup
        (1, 101, 1, 1, 1, "orange", 1, 1, 1, 1),
        (2, 102, 0, 0, 1, "biru", 0, 1, 1, 0),
        (3, 103, 1, 1, 1, "kuning", 1, 1, 1, 1),
    ]
    for (id_, track, ok, helm, rompi, warna, valid, celana, sepatu, tertutup) in rows:
        conn.execute(
            "INSERT INTO worker_inspections VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (id_, track, f"2026-09-2{id_}T08:00:00", f"2026-09-2{id_}", "08:00:00", ok,
             helm, "helm", rompi, warna, valid, "rompi", celana, "celana", sepatu, tertutup, "sepatu",
             json.dumps([] if ok else ["Helm Keselamatan"]), "catatan", "GEMINI_LIVE", 700.0,
             f"worker_{track}.jpg"),
        )
    if baris_dihapus:
        # Baris terakhir dihapus: id 3 tidak boleh dipakai ulang setelah migrasi
        conn.execute("DELETE FROM worker_inspections WHERE id = 3")
    conn.commit()
    conn.close()


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "audit.db", tmp_path / "snapshots"


def _version(db):
    return sqlite3.connect(str(db)).execute("PRAGMA user_version").fetchone()[0]


# --- Migrasi skema ----------------------------------------------------------------

def test_migrasi_v0_ke_v1_mempertahankan_semua_baris(paths):
    db, snaps = paths
    _buat_db_v0(db)
    assert _version(db) == 0

    mgr = ReportManager(db_path=db, snapshots_dir=snaps).open()

    assert _version(db) == SCHEMA_VERSION
    records = mgr.get_reports(limit=10)["page_records"]
    assert sorted(r["track_id"] for r in records) == [101, 102]

    lama = next(r for r in records if r["track_id"] == 102)
    items = lama["items"]
    assert items["rompi"] == {"detected": True, "color": "biru", "is_valid_color": False, "description": "rompi"}
    assert items["sepatu"]["is_closed_shoes"] is False
    assert items["helm"]["detected"] is False


def test_migrasi_membuat_cadangan_versi_lama(paths):
    db, snaps = paths
    _buat_db_v0(db)
    ReportManager(db_path=db, snapshots_dir=snaps).open()

    cadangan = db.with_name("audit.v0.bak")
    assert cadangan.exists()
    assert _version(cadangan) == 0
    n = sqlite3.connect(str(cadangan)).execute("SELECT COUNT(*) FROM worker_inspections").fetchone()[0]
    assert n == 2


def test_migrasi_tidak_memakai_ulang_id_yang_pernah_dihapus(paths):
    db, snaps = paths
    _buat_db_v0(db)
    mgr = ReportManager(db_path=db, snapshots_dir=snaps).open()
    rec = mgr.save_inspection(track_id=200, is_complete=True, items={}, missing_items=[],
                              notes="", inference_source="LOCAL_FAST_PASS", inference_time_ms=1.0)
    assert rec["id"] == 4


def test_migrasi_idempoten(paths):
    db, snaps = paths
    _buat_db_v0(db)
    ReportManager(db_path=db, snapshots_dir=snaps).open()
    mgr = ReportManager(db_path=db, snapshots_dir=snaps).open()
    assert mgr.get_reports()["total_all"] == 2


def test_database_baru_langsung_versi_terkini(paths):
    db, snaps = paths
    mgr = ReportManager(db_path=db, snapshots_dir=snaps).open()
    assert _version(db) == SCHEMA_VERSION
    assert mgr.get_reports()["total_all"] == 0
    assert not db.with_name("audit.v0.bak").exists()


def test_database_dari_versi_aplikasi_lebih_baru_ditolak(paths):
    db, snaps = paths
    conn = sqlite3.connect(str(db))
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(RuntimeError):
        ReportManager(db_path=db, snapshots_dir=snaps).open()


# --- Simpan, baca, ekspor ------------------------------------------------------------

def test_simpan_baca_dan_ekspor_csv(paths, catalog_defaults):
    db, snaps = paths
    mgr = ReportManager(db_path=db, snapshots_dir=snaps).open()
    items = {
        "helm": {"detected": True},
        "rompi": {"detected": True, "color": "orange", "is_valid_color": True},
        "celana": {"detected": False},
        "sepatu": {"detected": True, "is_closed_shoes": True},
    }
    crop = np.full((100, 50, 3), 120, dtype=np.uint8)
    rec = mgr.save_inspection(track_id=7, is_complete=False, items=items,
                              missing_items=["Celana Panjang"], notes="uji",
                              inference_source="LOCAL_FAST_PASS", inference_time_ms=12.5,
                              crop_img=crop)

    assert (snaps / rec["snapshot_filename"]).exists()
    assert mgr.get_snapshot_path(rec["snapshot_filename"]) is not None

    stats = mgr.get_reports()
    assert (stats["total_all"], stats["violation_count"]) == (1, 1)

    rows = list(csv.reader(io.StringIO(mgr.export_csv_text())))
    header, row = rows[0], rows[1]
    assert header[:len(messages.CSV_HEADER_LEADING)] == messages.CSV_HEADER_LEADING
    kolom = dict(zip(header, row))
    assert kolom["ID Pekerja"] == messages.CSV_WORKER_ID.format(track_id=7)
    assert kolom["Status Kelulusan"] == messages.CSV_STATUS_INCOMPLETE
    assert kolom["Rompi Keselamatan"] == "OK (orange)"
    assert kolom["Kacamata Safety"] == messages.CSV_ITEM_NOT_ASSESSED


def test_statistik_menghitung_keputusan_vlm_cadangan(paths):
    # T27: laporan membedakan keputusan oleh VLM cadangan. Baris lama (sebelum
    # T27) dengan label lain tidak ikut terhitung.
    db, snaps = paths
    mgr = ReportManager(db_path=db, snapshots_dir=snaps).open()
    for source in ("VLM_LIVE:gemini/gemini-3.5-flash-lite", "VLM_CADANGAN:ollama/qwen2.5vl:7b",
                   "VLM_CADANGAN:ollama/qwen2.5vl:7b", "VLM_GAGAL", "LOCAL_FAST_PASS"):
        mgr.save_inspection(track_id=1, is_complete=True, items={}, missing_items=[], notes="",
                            inference_source=source, inference_time_ms=1.0, crop_img=None)
    stats = mgr.get_reports()
    assert stats["total_all"] == 5 and stats["backup_count"] == 2


def test_label_vlm_cadangan_cocok_dengan_prefiks_laporan():
    from backend.report_manager import BACKUP_SOURCE_PREFIX
    from backend.vlm_analyzer import VLMEngine
    engine = VLMEngine("cadangan", "ollama", "qwen2.5vl:7b")
    assert engine.label.startswith(BACKUP_SOURCE_PREFIX)
    engine.executor.shutdown(wait=False)


@pytest.mark.parametrize("nama", ["../audit.db", "..\\audit.db", "sub/x.jpg", ""])
def test_snapshot_menolak_path_traversal(paths, nama):
    db, snaps = paths
    mgr = ReportManager(db_path=db, snapshots_dir=snaps).open()
    assert mgr.get_snapshot_path(nama) is None


def test_konstruktor_tidak_menyentuh_disk(tmp_path):
    db = tmp_path / "belum" / "audit.db"
    ReportManager(db_path=db, snapshots_dir=tmp_path / "belum" / "snapshots")
    assert not (tmp_path / "belum").exists()


def test_akses_pertama_membuka_database_otomatis(paths):
    db, snaps = paths
    mgr = ReportManager(db_path=db, snapshots_dir=snaps)
    assert mgr.get_reports()["total_all"] == 0
    assert _version(db) == SCHEMA_VERSION
