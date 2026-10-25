"""Koneksi pinjaman dan urutan commit tetap dimiliki fasad setelah pemisahan audit."""

import sqlite3
from contextlib import closing
from typing import Any

import pytest

from backend.audit import (
    db as audit_db,
    queries as audit_queries,
    export as audit_export,
    attendance,
    report_manager,
    retention,
    snapshots as snapshot_store,
)
from backend.config import cfg
from backend.disk_guard import BYTES_PER_GB


class BorrowedConnection:
    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        assert name not in {"close", "commit", "rollback", "backup"}, f"helper took ownership: {name}"
        return getattr(self.connection, name)

    def execute(self, sql, *args):
        assert sql.split()[0].upper() not in {"BEGIN", "COMMIT", "ROLLBACK"}
        return self.connection.execute(sql, *args)


def test_helpers_keep_borrowed_connection_open_and_uncommitted(tmp_path, monkeypatch):
    manager = report_manager.ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()
    manager.save_inspection(1, True, {}, [], "uji", "VLM_LIVE:tiruan", 1.0)
    monkeypatch.setattr(cfg, "RETENTION_AUDIT_DAYS", 1)
    with closing(manager._get_connection()) as connection:
        borrowed: Any = BorrowedConnection(connection)
        assert audit_queries.get_reports(borrowed)["total_all"] == 1
        assert attendance.read_seen(borrowed, "2000-01-01") == []
        assert attendance._attendance_unknown(borrowed, "2000-01-01")["passes"] == 0
        audit_db._ensure_indexes(borrowed)
        stream = audit_export.iter_csv_chunks(borrowed, [], [], [])
        assert next(stream)
        stream.close()
        connection.execute("UPDATE worker_inspections SET timestamp='2000-01-01T00:00:00'")
        connection.commit()
        assert retention._expire_audits(borrowed, 2_000_000_000.0) == (1, [])
        assert connection.in_transaction
        connection.rollback()
        assert connection.execute("SELECT COUNT(*) FROM worker_inspections").fetchone()[0] == 1


@pytest.mark.parametrize("step", ["audits", "photos", "quota"])
def test_facade_commits_references_before_deleting_photos(tmp_path, monkeypatch, step):
    manager = report_manager.ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()
    manager.save_inspection(1, True, {}, [], "uji", "VLM_LIVE:tiruan", 1.0)
    photo = manager.snapshots_dir / "worker.jpg"
    photo.write_bytes(b"foto-tiruan-tanpa-data-pribadi")
    with closing(manager._get_connection()) as conn, conn:
        conn.execute("UPDATE worker_inspections SET timestamp='2000-01-01T00:00:00',snapshot_filename='worker.jpg'")
    monkeypatch.setattr(cfg, "RETENTION_AUDIT_DAYS", 1 if step == "audits" else 0)
    monkeypatch.setattr(cfg, "RETENTION_PHOTO_DAYS", 1 if step == "photos" else 0)
    monkeypatch.setattr(cfg, "RETENTION_MAX_PHOTO_GB", 1 / BYTES_PER_GB if step == "quota" else 0)
    deleted = []
    delete = snapshot_store._delete_photos

    def observe(directory, names):
        if names:
            with closing(sqlite3.connect(manager.db_path)) as observer:
                count = observer.execute(
                    "SELECT COUNT(*) FROM worker_inspections WHERE snapshot_filename='worker.jpg'"
                ).fetchone()[0]
            assert count == 0, "foto dihapus sebelum perubahan referensi di-commit"
            deleted.extend(names)
        return delete(directory, names)

    monkeypatch.setattr(snapshot_store, "_delete_photos", observe)
    manager.cleanup_old_data()
    assert deleted == ["worker.jpg"]
    assert not photo.exists()


@pytest.mark.parametrize("name", ["time", "os", "cv2", "sqlite3", "_ATTENDANCE_SEEN_SQL", "_ATTENDANCE_UNKNOWN_SQL"])
def test_patch_names_are_not_reexported_from_facade(name):
    assert not hasattr(report_manager, name)
