"""Skema lama direkam mandiri; migrasi gagal tidak boleh meninggalkan DDL setengah jadi."""

import sqlite3
from contextlib import closing

import pytest

from backend.audit.report_manager import ReportManager, SCHEMA_VERSION

LEGACY_BASE_COLUMNS = """
    id INTEGER PRIMARY KEY AUTOINCREMENT, track_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL, date_str TEXT NOT NULL, time_str TEXT NOT NULL,
    is_complete INTEGER NOT NULL, items_json TEXT NOT NULL DEFAULT '{}',
    missing_items TEXT, notes TEXT, inference_source TEXT,
    inference_time_ms REAL, snapshot_filename TEXT
"""
LEGACY_IDENTITY_COLUMNS = (
    "worker_id INTEGER",
    "employee_no TEXT",
    "worker_name TEXT",
    "fr_status TEXT",
    "fr_score REAL",
)
LEGACY_ORGANIZATION_COLUMNS = ("department TEXT", "company TEXT")


@pytest.fixture(params=[1, 2, 3])
def legacy_audit(tmp_path, request):
    version = request.param
    path = tmp_path / "legacy.db"
    columns = [LEGACY_BASE_COLUMNS]
    if version >= 2:
        columns.extend(LEGACY_IDENTITY_COLUMNS)
    if version >= 3:
        columns.extend(LEGACY_ORGANIZATION_COLUMNS)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(f"CREATE TABLE worker_inspections ({','.join(columns)})")
        conn.execute(f"PRAGMA user_version = {version}")
        conn.execute(
            "INSERT INTO worker_inspections (id,track_id,timestamp,date_str,time_str,is_complete,items_json) "
            "VALUES (7,42,'2026-01-01T08:00:00','2026-01-01','08:00:00',1,?)",
            ('{"helm":{"detected":true}}',),
        )
        conn.execute("UPDATE sqlite_sequence SET seq=12 WHERE name='worker_inspections'")
        if version >= 2:
            conn.execute("UPDATE worker_inspections SET worker_id=9, worker_name='Pekerja Uji', fr_status='recognized'")
        if version >= 3:
            conn.execute("UPDATE worker_inspections SET department='Divisi Uji', company='Perusahaan Uji'")
    return path, version


def schema_state(path):
    with closing(sqlite3.connect(path)) as conn:
        return {
            "version": conn.execute("PRAGMA user_version").fetchone()[0],
            "columns": conn.execute("PRAGMA table_info(worker_inspections)").fetchall(),
            "rows": conn.execute("SELECT * FROM worker_inspections").fetchall(),
            "sequence": conn.execute("SELECT seq FROM sqlite_sequence WHERE name='worker_inspections'").fetchone(),
            "indexes": conn.execute("PRAGMA index_list(worker_inspections)").fetchall(),
        }


def test_old_schema_rows_backup_and_sequence_are_preserved(legacy_audit, tmp_path):
    path, version = legacy_audit
    before = schema_state(path)
    manager = ReportManager(path, tmp_path / "snapshots").open()
    after = schema_state(path)
    assert after["version"] == SCHEMA_VERSION
    assert len(after["rows"]) == 1
    assert after["rows"][0][: len(before["rows"][0])] == before["rows"][0]
    assert after["rows"][0][-1] is None  # gate_hold baru tidak mengubah hasil APD
    assert after["sequence"] == (12,)
    assert schema_state(path.with_name(f"legacy.v{version}.bak")) == before
    saved = manager.save_inspection(1, True, {}, [], "uji", "VLM_LIVE:tiruan", 1.0)
    assert saved["id"] == 13


def test_migration_failure_rolls_back_schema_rows_and_indexes(legacy_audit, tmp_path, monkeypatch):
    path, version = legacy_audit
    before = schema_state(path)
    manager = ReportManager(path, tmp_path / "snapshots")
    upgrade = manager._upgrade_schema

    def fail_after_upgrade(*args):
        upgrade(*args)
        raise RuntimeError("galat migrasi tiruan")

    monkeypatch.setattr(manager, "_upgrade_schema", fail_after_upgrade)
    with pytest.raises(RuntimeError, match="galat migrasi tiruan"):
        manager.open()
    assert schema_state(path) == before
    assert schema_state(path.with_name(f"legacy.v{version}.bak")) == before
    assert not manager._opened
