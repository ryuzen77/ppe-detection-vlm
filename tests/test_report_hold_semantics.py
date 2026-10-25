"""T96: penahanan terpisah dari lolos/ditolak, dan hitungan mengikuti periode/identitas."""

import csv
import io
import sqlite3
from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from backend import messages, worker_store
from backend.api import routes_reports
from backend.app import app
from backend.audit.report_manager import BACKUP_SOURCE_PREFIX, ReportManager
from backend.vlm.selection import LOCAL_FALLBACK_SOURCE_PREFIX

DAY = "2026-10-24"
OTHER_DAY = "2026-09-24"
PRIMARY = "VLM_LIVE:tiruan/model-uji"
BACKUP = BACKUP_SOURCE_PREFIX + "tiruan/model-uji"
EMERGENCY = LOCAL_FALLBACK_SOURCE_PREFIX + "tiruan/model-uji"


def insert(manager, day=DAY, worker_id=1, department="Divisi Uji", company="Perusahaan Uji", **values):
    defaults = {"complete": True, "hold": None, "source": PRIMARY, "fr_status": "recognized"}
    defaults.update(values)
    with manager._get_connection() as conn:
        conn.execute(
            "INSERT INTO worker_inspections (track_id,timestamp,date_str,time_str,is_complete,gate_hold,"
            "inference_source,fr_status,worker_id,department,company) VALUES (1,?,?, '08:00:00',?,?,?,?,?,?,?)",
            (
                day + "T08:00:00",
                day,
                int(defaults["complete"]),
                defaults["hold"],
                defaults["source"],
                defaults["fr_status"],
                worker_id,
                department,
                company,
            ),
        )


@pytest.fixture
def manager(tmp_path, monkeypatch):
    report = ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()
    monkeypatch.setattr(routes_reports, "report_mgr", report)
    monkeypatch.setattr(worker_store.store, "active_attendance_workers", lambda: [])
    return report


def seed_outcomes(manager, **identity):
    insert(manager, source=PRIMARY, **identity)
    insert(manager, complete=False, source=BACKUP, **identity)
    insert(manager, hold="unregistered", source=BACKUP, **identity)
    insert(manager, hold="fr_unavailable", source=EMERGENCY, **identity)


@pytest.mark.parametrize("period", ["day", "week", "month"])
def test_summary_counts_held_in_total_and_apd_only(manager, period):
    seed_outcomes(manager)
    out = TestClient(app).get("/api/reports/summary", params={"period": period, "date": DAY}).json()
    assert out["totals"] == {"total": 4, "passed": 1, "rejected": 1, "compliance_rate": 75.0}
    assert sum(bucket["passed"] for bucket in out["buckets"]) == 1
    assert sum(bucket["rejected"] for bucket in out["buckets"]) == 1
    assert set(out["totals"]) == {"total", "passed", "rejected", "compliance_rate"}


def test_only_held_is_neither_passed_nor_rejected_but_fully_compliant(manager):
    insert(manager, hold="unregistered")
    summary = manager.get_summary("day", DAY)
    assert summary["totals"] == {"total": 1, "passed": 0, "rejected": 0, "compliance_rate": 100.0}
    assert manager.get_reports()["compliance_rate"] == 100.0


@pytest.mark.parametrize("status,expected", [("all", 4), ("complete", 1), ("incomplete", 1), ("held", 2)])
def test_page_status_excludes_held_from_complete_and_incomplete(manager, status, expected):
    seed_outcomes(manager)
    page = TestClient(app).get("/api/reports", params={"status": status, "date": DAY}).json()
    assert page["filtered_total"] == len(page["page_records"]) == expected
    if status == "complete":
        assert page["page_records"][0]["gate_hold"] is None
    assert (page["backup_count"], page["local_fallback_count"], page["held_count"]) == (2, 1, 2)


def test_attendance_counts_held_only_as_passes_for_recognized_and_unknown(manager):
    seed_outcomes(manager)
    seed_outcomes(manager, worker_id=None, fr_status="unknown")
    report = manager.get_attendance(DAY)
    seen = report["seen"][0]
    assert (seen["passes"], seen["passed"], seen["rejected"]) == (4, 1, 1)
    assert seen["last_complete"] is True  # Tetap hasil APD, sesuai kontrak lama.
    assert report["unknown"] == {"passes": 4, "passed": 1, "rejected": 1}
    assert report["totals"]["passes"] == 8 and report["totals"]["recognition_rate"] == 0.5


@pytest.mark.parametrize(
    "filters",
    [
        {"date_filter": DAY},
        {"date_from": DAY, "date_to": DAY},
        {"worker_id": 1},
        {"department": "Divisi Uji"},
        {"company": "Perusahaan Uji"},
        {"date_from": DAY, "date_to": DAY, "worker_id": 1, "department": "Divisi Uji", "company": "Perusahaan Uji"},
    ],
)
def test_decision_counts_follow_context_not_page_size(manager, filters):
    seed_outcomes(manager)
    seed_outcomes(manager, day=OTHER_DAY, worker_id=2, department="Divisi Lain", company="Perusahaan Lain")
    report = manager.get_reports(limit=1, offset=1, **filters)
    assert report["filtered_total"] == 4
    assert (report["backup_count"], report["local_fallback_count"], report["held_count"]) == (2, 1, 2)


def test_empty_period_has_zero_decision_counts(manager):
    seed_outcomes(manager)
    page = TestClient(app).get("/api/reports", params={"from": OTHER_DAY, "to": OTHER_DAY}).json()
    assert page["filtered_total"] == 0
    assert (page["backup_count"], page["local_fallback_count"], page["held_count"]) == (0, 0, 0)


def test_identity_count_query_uses_worker_index(manager):
    seed_outcomes(manager)
    with manager._get_connection() as conn:
        traces = []
        conn.set_trace_callback(traces.append)
        assert manager._decision_counts(conn, ["worker_id = ?"], [1])["held_count"] == 2
        plan = conn.execute("EXPLAIN QUERY PLAN " + traces[0]).fetchall()
    assert "idx_worker_id" in str([tuple(row) for row in plan])
    print(f"T96 identity: plan={[tuple(row) for row in plan]}")


def test_csv_held_status_never_says_access_granted(manager):
    seed_outcomes(manager)
    response = TestClient(app).get("/api/reports/export")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[1][4] == messages.CSV_STATUS_COMPLETE
    assert rows[2][4] == messages.CSV_STATUS_INCOMPLETE
    assert [row[4] for row in rows[3:]] == [messages.CSV_STATUS_HELD] * 2
    assert all("Akses Diizinkan" not in row[4] for row in rows[3:])


@pytest.mark.parametrize("size", [100, 100_000])
def test_filtered_report_performance_and_indexes(manager, size):
    with manager._get_connection() as conn:
        conn.executemany(
            "INSERT INTO worker_inspections (track_id,timestamp,date_str,time_str,is_complete,gate_hold,"
            "inference_source,worker_id) VALUES (1,?,?, '08:00:00',1,'unregistered',?,?)",
            ((DAY, DAY if i % 2 else OTHER_DAY, EMERGENCY, i % 2 + 1) for i in range(size)),
        )
    queries = []
    original = manager._get_connection

    def connect():
        conn = original()
        conn.set_trace_callback(queries.append)
        return conn

    manager._get_connection = connect
    report = manager.get_reports(limit=0, date_filter=DAY)
    elapsed = []
    for _ in range(5):
        started = perf_counter()
        report = manager.get_reports(limit=0, date_filter=DAY)
        elapsed.append((perf_counter() - started) * 1000)
    assert report["held_count"] == report["local_fallback_count"] == size // 2
    count_queries = [
        query
        for query in queries
        if "AS local_fallback_count" in query or "COUNT(*) FROM worker_inspections WHERE gate_hold" in query
    ]
    with sqlite3.connect(manager.db_path) as conn:
        plans = [conn.execute("EXPLAIN QUERY PLAN " + query).fetchall() for query in count_queries[:2]]
    assert all("idx_date_str" in str(plan) for plan in plans)
    print(f"T96 counts {size}: median={median(elapsed):.3f} ms; plans={plans}")
    started = perf_counter()
    summary = manager.get_summary("day", DAY)
    elapsed_ms = (perf_counter() - started) * 1000
    assert summary["totals"] == {"total": size // 2, "passed": 0, "rejected": 0, "compliance_rate": 100.0}
    print(f"T96 summary {size}: elapsed={elapsed_ms:.3f} ms")
