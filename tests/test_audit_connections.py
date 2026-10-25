"""Koneksi audit harus ditutup deterministik, termasuk saat query atau migrasi gagal."""

import inspect
import sqlite3
from contextlib import closing
from datetime import date
from types import SimpleNamespace
from typing import cast

import pytest

from backend.audit import db, queries, report_manager, retention
from backend import worker_store
from backend.config import cfg
import test_audit_schema_characterization as schema_tests

legacy_audit = schema_tests.legacy_audit

CALLS = 20
DAY = date.today().isoformat()
EMPTY_ATTENDANCE = {"seen": [], "not_seen": [], "unknown": {"passes": 0, "passed": 0, "rejected": 0}}
OPERATIONS = {
    "open": lambda manager: manager.open(),
    "save_inspection": lambda manager: manager.save_inspection(1, True, {}, [], "uji", "VLM_LIVE:tiruan", 1.0),
    "recognition_rate": lambda manager: manager.recognition_rate(7),
    "get_reports": lambda manager: manager.get_reports(),
    "get_summary": lambda manager: manager.get_summary("day", DAY),
    "get_attendance": lambda manager: manager.get_attendance(DAY),
    "iter_attendance_csv": lambda manager: list(manager.iter_attendance_csv(EMPTY_ATTENDANCE)),
    "iter_csv_chunks": lambda manager: list(manager.iter_csv_chunks()),
    "export_csv_text": lambda manager: manager.export_csv_text(),
    "get_last_seen_batch": lambda manager: manager.get_last_seen_batch([1]),
    "get_last_seen": lambda manager: manager.get_last_seen(1),
    "get_worker_inspections": lambda manager: manager.get_worker_inspections(1),
    "get_snapshot_path": lambda manager: manager.get_snapshot_path("photo.jpg"),
    "cleanup_old_data": lambda manager: manager.cleanup_old_data(),
}


@pytest.fixture
def tracked_connections(monkeypatch):
    opened, events, failures = [], [], {"commit": False, "pragma": False}
    real_connect = sqlite3.connect

    class TrackedConnection(sqlite3.Connection):
        closed = False

        def execute(self, sql, *args, **kwargs):
            if failures["pragma"] and sql.startswith("PRAGMA synchronous"):
                raise sqlite3.OperationalError("PRAGMA gagal tiruan")
            return super().execute(sql, *args, **kwargs)

        def commit(self):
            if failures["commit"]:
                raise sqlite3.OperationalError("commit gagal tiruan")
            return super().commit()

        def close(self):
            super().close()
            self.closed = True
            events.append("CLOSE")

    def connect(*args, **kwargs):
        connection = cast(TrackedConnection, real_connect(*args, **kwargs, factory=TrackedConnection))
        opened.append(connection)  # Referensi kuat: GC tidak boleh menyembunyikan kebocoran.
        connection.set_trace_callback(events.append)
        return connection

    monkeypatch.setattr(db.sqlite3, "connect", connect)
    yield SimpleNamespace(opened=opened, events=events, failures=failures, real_connect=real_connect)
    for connection in opened:
        if not connection.closed:
            connection.close()


@pytest.fixture
def audit_env(tmp_path, monkeypatch, tracked_connections):
    manager = report_manager.ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()
    monkeypatch.setattr(worker_store.store, "active_attendance_workers", lambda: [])
    with closing(manager._get_connection()) as conn, conn:
        conn.execute(
            "INSERT INTO worker_inspections(track_id,timestamp,date_str,time_str,is_complete,worker_id,fr_status) "
            "VALUES (1,?,?,?,?,1,'recognized')",
            (DAY + "T08:00:00", DAY, "08:00:00", 1),
        )
    return SimpleNamespace(manager=manager, tracking=tracked_connections)


def assert_closed(tracking):
    assert not [connection for connection in tracking.opened if not connection.closed], "koneksi audit tertinggal"


def test_every_public_method_has_connection_coverage():
    public = {
        name
        for name, _ in inspect.getmembers(report_manager.ReportManager, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public == set(OPERATIONS)


@pytest.mark.parametrize("method", OPERATIONS)
def test_repeated_public_calls_do_not_accumulate_connections(audit_env, method):
    assert_closed(audit_env.tracking)
    for _ in range(CALLS):
        OPERATIONS[method](audit_env.manager)
        assert_closed(audit_env.tracking)


@pytest.mark.parametrize(
    "helper,method",
    [("get_reports", "get_reports"), ("summary_rows", "get_summary"), ("recognition_counts", "recognition_rate")],
)
def test_query_failure_also_closes_connections(audit_env, monkeypatch, helper, method):
    def fail(*args, **kwargs):
        raise RuntimeError("kueri gagal tiruan")

    monkeypatch.setattr(queries, helper, fail)
    for _ in range(CALLS):
        with pytest.raises(RuntimeError, match="kueri gagal tiruan"):
            OPERATIONS[method](audit_env.manager)
        assert_closed(audit_env.tracking)


@pytest.mark.parametrize("fault", ["after_insert", "commit"])
def test_write_failure_rolls_back_before_close(audit_env, monkeypatch, fault):
    tracking = audit_env.tracking
    insert = db.insert_inspection

    def fail(conn, values):
        insert(conn, values)
        raise RuntimeError("insert gagal tiruan")

    if fault == "after_insert":
        monkeypatch.setattr(db, "insert_inspection", fail)
    else:
        tracking.failures["commit"] = True
    for _ in range(CALLS):
        tracking.events.clear()
        with pytest.raises((RuntimeError, sqlite3.OperationalError)):
            OPERATIONS["save_inspection"](audit_env.manager)
        assert tracking.events[-2:] == ["ROLLBACK", "CLOSE"]
        assert_closed(tracking)
    with closing(tracking.real_connect(audit_env.manager.db_path)) as observer:
        assert observer.execute("SELECT COUNT(*) FROM worker_inspections").fetchone()[0] == 1


def test_retention_failure_rolls_back_and_keeps_photo(audit_env, monkeypatch):
    manager, tracking = audit_env.manager, audit_env.tracking
    photo = manager.snapshots_dir / "photo.jpg"
    photo.write_bytes(b"foto-tiruan")
    with closing(tracking.real_connect(manager.db_path)) as conn, conn:
        conn.execute("UPDATE worker_inspections SET timestamp='2000-01-01T00:00:00',snapshot_filename='photo.jpg'")
    monkeypatch.setattr(cfg, "RETENTION_AUDIT_DAYS", 1)
    expire = retention._expire_audits

    def fail(conn, now):
        expire(conn, now)
        raise RuntimeError("retensi gagal tiruan")

    monkeypatch.setattr(retention, "_expire_audits", fail)
    for _ in range(CALLS):
        manager.cleanup_old_data()
        assert_closed(tracking)
    assert photo.exists()
    with closing(tracking.real_connect(manager.db_path)) as observer:
        assert observer.execute("SELECT COUNT(*) FROM worker_inspections").fetchone()[0] == 1


def test_failed_pragma_does_not_leave_half_open_connection(audit_env):
    audit_env.tracking.failures["pragma"] = True
    with pytest.raises(sqlite3.OperationalError, match="PRAGMA gagal tiruan"):
        audit_env.manager.get_reports()
    assert_closed(audit_env.tracking)


def test_backup_destination_failure_closes_source(tracked_connections, legacy_audit, tmp_path, monkeypatch):
    path, _ = legacy_audit

    def fail(*args):
        raise OSError("tujuan cadangan gagal tiruan")

    monkeypatch.setattr(db, "backup_connection", fail)
    with pytest.raises(OSError, match="tujuan cadangan gagal tiruan"):
        report_manager.ReportManager(path, tmp_path / "snapshots").open()
    assert_closed(tracked_connections)


def test_migration_failure_closes_all_connections(tracked_connections, legacy_audit, tmp_path, monkeypatch):
    path, _ = legacy_audit
    manager = report_manager.ReportManager(path, tmp_path / "snapshots")

    def fail(*args):
        raise RuntimeError("migrasi gagal tiruan")

    monkeypatch.setattr(manager, "_upgrade_schema", fail)
    with pytest.raises(RuntimeError, match="migrasi gagal tiruan"):
        manager.open()
    assert_closed(tracked_connections)


@pytest.mark.parametrize("consume_rows", [False, True])
def test_cancelled_csv_keeps_only_active_stream_connection(audit_env, consume_rows):
    stream = audit_env.manager.iter_csv_chunks()
    next(stream)  # Header belum membuka koneksi.
    assert_closed(audit_env.tracking)
    if consume_rows:
        next(stream)
        assert sum(not connection.closed for connection in audit_env.tracking.opened) == 1
    stream.close()
    assert_closed(audit_env.tracking)
