"""Kontrak T80: laporan lintasan harian khusus admin, dengan DB dan identitas sintetis."""

import csv
import io
import sqlite3
from datetime import date
from statistics import median
from time import perf_counter
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend import face_crypto, messages, ppe_rules
from backend.audit import attendance
from backend import worker_store
from backend.api.deps import require_session
from backend.app import app
from backend.auth import SessionUser
from backend.audit.report_manager import ReportManager

DAY = "2026-10-21"
OTHER_DAY = "2026-10-20"
PATHS = ("/api/reports/attendance", "/api/reports/attendance/export")
AUDIT_INSERT = (
    "INSERT INTO worker_inspections "
    "(track_id, timestamp, date_str, time_str, is_complete, worker_id, employee_no, worker_name, "
    "fr_status, department, company) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()
    store = worker_store.SqliteWorkerStore(tmp_path / "workers.db", key=face_crypto.generate_key())
    monkeypatch.setattr(worker_store, "store", store)
    monkeypatch.setattr("backend.api.routes_reports.report_mgr", manager)
    return SimpleNamespace(manager=manager, store=store, client=TestClient(app))


def _worker(env, number="P-001", name="Pekerja Uji", active=True):
    worker = env.store.create(number, name, consent=True, actor="admin-uji", nickname="Uji", gender="male")
    if not active:
        env.store.deactivate(worker.id)
    return worker


def _audit(
    env,
    worker=None,
    clock="08:00:00",
    complete=True,
    status: str | None = "recognized",
    day=DAY,
    name="Nama Audit Uji",
    department: str | None = "Divisi Lama",
    company: str | None = "Perusahaan Uji",
):
    values = (
        1,
        f"{day}T{clock}",
        day,
        clock,
        int(complete),
        worker.id if worker else None,
        worker.employee_no if worker else None,
        name if worker else None,
        status,
        department,
        company,
    )
    with env.manager._get_connection() as conn:
        conn.execute(AUDIT_INSERT, values)


def _report(env, **filters):
    response = env.client.get(PATHS[0], params={"date": DAY, **filters})
    assert response.status_code == 200
    return response.json()


def test_seen_aggregates_and_preserves_latest_audit_snapshot(env):
    worker = _worker(env, name="Nama Sekarang Uji")
    _audit(env, worker, "16:03:40", False, name="Nama Lama Uji", department="Divisi Akhir")
    _audit(env, worker, "07:58:12", name="Nama Awal Uji")
    _audit(env, worker, "12:00:00")
    _audit(env, worker, day=OTHER_DAY)
    report = _report(env)
    assert report["seen"] == [
        {
            "worker_id": worker.id,
            "employee_no": worker.employee_no,
            "name": "Nama Lama Uji",
            "department": "Divisi Akhir",
            "company": "Perusahaan Uji",
            "first_seen": "07:58:12",
            "last_seen": "16:03:40",
            "passes": 3,
            "passed": 2,
            "rejected": 1,
            "last_complete": False,
        }
    ]
    assert report["not_seen"] == []
    assert report["totals"] == {
        "passes": 3,
        "recognized": 3,
        "recognition_rate": 1.0,
        "active_workers": 1,
        "seen_workers": 1,
    }


def test_seen_order_same_second_tie_and_inactive_history(env):
    later = _worker(env)
    earlier = _worker(env, "P-002", active=False)
    _audit(env, later, "09:00:00")
    _audit(env, earlier, "07:00:00")
    _audit(env, later, "09:00:00", False, name="Snapshot Terakhir Uji")
    report = _report(env)
    assert [row["worker_id"] for row in report["seen"]] == [earlier.id, later.id]
    assert report["seen"][1]["name"] == "Snapshot Terakhir Uji"
    assert report["seen"][1]["last_complete"] is False
    assert report["totals"]["active_workers"] == 1


def test_not_seen_is_current_active_workers_sorted_by_name(env):
    seen = _worker(env)
    _worker(env, "P-002", "Zeta Uji")
    _worker(env, "P-003", "Alpha Uji")
    _worker(env, "P-004", "Nonaktif Uji", active=False)
    _audit(env, seen)
    report = _report(env)
    assert [row["name"] for row in report["not_seen"]] == ["Alpha Uji", "Zeta Uji"]
    assert set(report["not_seen"][0]) == {"worker_id", "employee_no", "name", "department", "company"}
    assert report["not_seen"][0]["department"] is None
    assert report["totals"]["active_workers"] == 3


def test_unknown_counts_null_disabled_and_unrecognized_statuses(env):
    worker = _worker(env)
    _audit(env, worker)
    for status, complete in [("unknown", True), ("disabled", False), (None, True)]:
        _audit(env, status=status, complete=complete)
    report = _report(env)
    assert report["unknown"] == {"passes": 3, "passed": 2, "rejected": 1}
    assert report["totals"]["recognition_rate"] == 0.25
    assert report["totals"]["passes"] == 4


def _move_worker(env, worker, department="Divisi Baru", company="Perusahaan Baru"):
    dep = env.store.create_org("departments", department)
    comp = env.store.create_org("companies", company)
    env.store.update_worker(worker.id, department_id=dep["id"], company_id=comp["id"])


@pytest.mark.parametrize(
    "filters",
    [
        {"department": "Divisi Lama"},
        {"company": "Perusahaan Uji"},
        {"department": "Divisi Lama", "company": "Perusahaan Uji"},
    ],
)
def test_filters_use_audit_snapshots_for_seen_and_current_profile_for_not_seen(env, filters):
    seen = _worker(env)
    unseen = _worker(env, "P-002")
    _audit(env, seen)
    _move_worker(env, seen)
    _move_worker(env, unseen, department="Divisi Lama", company="Perusahaan Uji")
    _audit(env, status="unknown")
    _audit(env, status="unknown", department="Lain", company="Lain")
    report = _report(env, **filters)
    assert [row["worker_id"] for row in report["seen"]] == [seen.id]
    assert [row["worker_id"] for row in report["not_seen"]] == [unseen.id]
    assert report["unknown"]["passes"] == 2
    assert report["totals"] == {
        "passes": 3,
        "recognized": 1,
        "recognition_rate": 1 / 3,
        "active_workers": 1,
        "seen_workers": 1,
    }


def test_seen_exclusion_precedes_current_department_filter(env):
    worker = _worker(env)
    _audit(env, worker)
    _move_worker(env, worker)
    report = _report(env, department="Divisi Baru")
    assert report["seen"] == report["not_seen"] == []
    assert report["totals"]["active_workers"] == 1
    assert report["totals"]["recognition_rate"] == 1.0


def test_department_filter_uses_last_snapshot_for_entire_worker_day(env):
    worker = _worker(env)
    _audit(env, worker, department="Divisi Lama")
    _audit(env, worker, clock="16:00:00", department="Divisi Baru")
    assert _report(env, department="Divisi Lama")["seen"] == []
    report = _report(env, department="Divisi Baru")
    assert report["seen"][0]["passes"] == 2
    assert report["seen"][0]["first_seen"] == "08:00:00"


@pytest.mark.parametrize(
    "filters", [{"department": "Tidak Ada"}, {"company": "' OR 1=1 --"}, {"department": "divisi lama"}]
)
def test_filters_are_exact_and_parameterized(env, filters):
    _audit(env, _worker(env))
    report = _report(env, **filters)
    assert report["seen"] == report["not_seen"] == []
    assert report["totals"]["passes"] == 1


@pytest.mark.parametrize(
    "filters,count",
    [
        ({"department": "Divisi A"}, 1),
        ({"company": "Perusahaan A"}, 1),
        ({"department": "Divisi A", "company": "Perusahaan A"}, 1),
        ({"department": "Tidak Ada"}, 0),
    ],
)
def test_recognition_metrics_cover_entire_gate_despite_organization_filters(env, filters, count):
    first, second = _worker(env), _worker(env, "P-002")
    _move_worker(env, first, "Divisi A", "Perusahaan A")
    _move_worker(env, second, "Divisi B", "Perusahaan B")
    _audit(env, first, department="Divisi A", company="Perusahaan A")
    _audit(env, second, department="Divisi B", company="Perusahaan B")
    _audit(env, second, clock="16:00:00", department="Divisi B", company="Perusahaan B")
    _audit(env, status=None, department=None, company=None)
    _audit(env, status="disabled", complete=False, department=None, company=None)
    _audit(env, status="unknown", day=OTHER_DAY)
    baseline, filtered = _report(env), _report(env, **filters)
    assert filtered["unknown"] == baseline["unknown"] == {"passes": 2, "passed": 1, "rejected": 1}
    for key, expected in (("passes", 5), ("recognized", 3), ("recognition_rate", 0.6)):
        assert filtered["totals"][key] == baseline["totals"][key] == expected
    assert len(filtered["seen"]) == filtered["totals"]["seen_workers"] == count
    assert filtered["totals"]["active_workers"] == count
    assert filtered["not_seen"] == []


def test_filtered_report_with_only_unknown_passes_has_zero_recognition_rate(env):
    _audit(env, status="unknown", department=None, company=None)
    report = _report(env, department="Divisi A", company="Perusahaan A")
    assert report["seen"] == report["not_seen"] == []
    assert report["unknown"]["passes"] == report["totals"]["passes"] == 1
    assert report["totals"]["recognized"] == 0
    assert report["totals"]["recognition_rate"] == 0.0


@pytest.mark.parametrize("path", PATHS)
def test_non_admin_forbidden_on_both_attendance_routes(env, path):
    original = app.dependency_overrides[require_session]

    async def operator_session(request: Request):
        user = SessionUser("operator-uji", "operator")
        request.state.user = user
        return user

    app.dependency_overrides[require_session] = operator_session
    try:
        assert env.client.get(path).status_code == 403
        assert env.client.get("/api/reports").status_code == 200
    finally:
        app.dependency_overrides[require_session] = original


@pytest.mark.parametrize("path", PATHS)
def test_unauthenticated_requests_cannot_read_attendance(env, path):
    original = app.dependency_overrides.pop(require_session)
    try:
        assert env.client.get(path).status_code == 401
    finally:
        app.dependency_overrides[require_session] = original


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("invalid", ["2026-02-30", "not-a-date", "20261021", "2026-W43-3"])
def test_invalid_dates_return_400(env, path, invalid):
    response = env.client.get(path, params={"date": invalid})
    assert response.status_code == 400
    assert response.json()["detail"] == messages.API_REPORT_DATE_INVALID


@pytest.mark.parametrize("params", [{}, {"date": ""}])
def test_empty_date_uses_today(env, params):
    response = env.client.get(PATHS[0], params=params)
    assert response.status_code == 200
    assert response.json()["date"] == date.today().isoformat()


def test_empty_day_and_absent_worker_database(env):
    report = _report(env)
    assert report == {
        "date": DAY,
        "seen": [],
        "not_seen": [],
        "unknown": {"passes": 0, "passed": 0, "rejected": 0},
        "totals": {"passes": 0, "recognized": 0, "recognition_rate": None, "active_workers": 0, "seen_workers": 0},
    }
    assert not env.store.path.exists(), "membaca laporan tidak membuat atau memigrasi workers.db"


def test_day_without_audit_still_lists_active_workers(env):
    worker = _worker(env)
    _audit(env, worker, day=OTHER_DAY)
    report = _report(env)
    assert report["seen"] == []
    assert [row["worker_id"] for row in report["not_seen"]] == [worker.id]
    assert report["totals"]["recognition_rate"] is None


def test_worker_attendance_read_omits_templates_and_does_not_write(env, monkeypatch):
    worker = _worker(env)
    revision = env.store.revision
    monkeypatch.setattr(env.store, "_run", lambda *args, **kwargs: pytest.fail("transaksi tulis dipanggil"))
    monkeypatch.setattr(env.store, "_cipher", lambda: pytest.fail("templat dibaca"))
    assert env.store.active_attendance_workers()[0]["worker_id"] == worker.id
    assert env.store.revision == revision


def test_csv_note_headers_seen_not_seen_and_unknown_summary(env):
    worker = _worker(env)
    _worker(env, "P-002", "Belum Terlihat Uji")
    _audit(env, worker, complete=False)
    _audit(env, status="unknown")
    response = env.client.get(PATHS[1], params={"date": DAY})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert messages.ATTENDANCE_CSV_FILENAME.format(date=DAY) in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == [messages.ATTENDANCE_CSV_NOTE]
    assert "bukan absensi resmi" in rows[0][0] and "wajah tidak dikenali" in rows[0][0]
    assert rows[1] == messages.ATTENDANCE_CSV_HEADER
    assert rows[2] == [
        "1",
        "P-001",
        "Nama Audit Uji",
        "Divisi Lama",
        "Perusahaan Uji",
        "Terlihat",
        "08:00:00",
        "08:00:00",
        "1",
        "0",
        "1",
    ]
    assert rows[3][:3] == ["2", "P-002", "Belum Terlihat Uji"]
    assert rows[3][5:] == ["Belum terlihat", "", "", "", "", ""]
    assert rows[4] == ["", "", "", "", "", "Tidak dikenali", "", "", "1", "1", "0"]


def test_csv_filter_and_quoting_preserve_snapshot_text(env):
    worker = _worker(env)
    _audit(env, worker, name='Nama, "Uji"')
    _audit(env, status="unknown", department=None, company=None)
    response = env.client.get(PATHS[1], params={"date": DAY, "company": "Perusahaan Uji"})
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[2][2] == 'Nama, "Uji"'
    assert rows[-1][-3:] == ["1", "1", "0"]


@pytest.mark.parametrize(
    "filters",
    [{"department": "Divisi A"}, {"company": "Perusahaan A"}, {"department": "Divisi A", "company": "Perusahaan A"}],
)
def test_csv_unknown_summary_covers_entire_gate_when_filtered(env, filters):
    _audit(env, _worker(env), department="Divisi B", company="Perusahaan B")
    _audit(env, status="unknown", department=None, company=None)
    _audit(env, status="disabled", complete=False, department=None, company=None)
    response = env.client.get(PATHS[1], params={"date": DAY, **filters})
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 3
    assert rows[-1][5:] == [messages.ATTENDANCE_UNKNOWN, "", "", "2", "1", "1"]


@pytest.mark.parametrize("name", ["=1+1", "+1+1", "-1+1", "@SUM(1)", "  =1+1"])
def test_csv_snapshot_names_cannot_be_spreadsheet_formulas(env, name):
    _audit(env, _worker(env), name=name)
    response = env.client.get(PATHS[1], params={"date": DAY})
    assert list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))[2][2] == "'" + name


def test_empty_day_csv_still_has_note_header_and_unknown_summary(env):
    response = env.client.get(PATHS[1], params={"date": DAY})
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 3
    assert rows[-1][-3:] == ["0", "0", "0"]


@pytest.mark.parametrize("path,header_index", [(PATHS[1], 1), ("/api/reports/export", 0)])
@pytest.mark.parametrize("populated", [False, True])
def test_csv_exports_have_one_utf8_bom_and_preserve_headers(env, catalog_defaults, path, header_index, populated):
    name = "Nama Uji — É"
    if populated:
        _audit(env, _worker(env), name=name)
    response = env.client.get(path, params={"date": DAY})
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.content.count(b"\xef\xbb\xbf") == 1
    text = response.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    expected = (
        messages.ATTENDANCE_CSV_HEADER
        if header_index
        else (
            messages.CSV_HEADER_LEADING
            + [messages.CSV_HEADER_WORKER_NAME, messages.CSV_HEADER_DEPARTMENT, messages.CSV_HEADER_COMPANY]
            + [item.label for item in ppe_rules.get_items()]
            + messages.CSV_HEADER_TRAILING
            + [messages.CSV_HEADER_GATE_HOLD]
        )
    )
    assert rows[header_index] == expected
    if populated:
        assert name in text


def _seed_benchmark(env, size, day):
    rows = [
        (
            i,
            f"{day}T08:00:00",
            day,
            "08:00:00",
            i % 2,
            i % 20,
            f"P-{i % 20}",
            "Pekerja Sintetis Uji",
            "recognized",
            None,
            None,
        )
        for i in range(size)
    ]
    with env.manager._get_connection() as conn:
        conn.executemany(AUDIT_INSERT, rows)


@pytest.mark.parametrize("size", [100, 100_000])
def test_attendance_query_plan_and_benchmark(env, size):
    _seed_benchmark(env, size, DAY)
    with sqlite3.connect(env.manager.db_path) as conn:
        for sql in (attendance._ATTENDANCE_SEEN_SQL, attendance._ATTENDANCE_UNKNOWN_SQL):
            plan = conn.execute("EXPLAIN QUERY PLAN " + sql, (DAY, "recognized")).fetchall()
            details = [row[3] for row in plan]
            assert any("SEARCH worker_inspections USING INDEX idx_date_str" in row for row in details)
            print(f"EXPLAIN {size} {'seen' if sql == attendance._ATTENDANCE_SEEN_SQL else 'unknown'}: {details}")
    durations = []
    for _ in range(5):
        start = perf_counter()
        result = env.manager.get_attendance(DAY)
        durations.append((perf_counter() - start) * 1000)
        assert result["totals"]["recognized"] == size
    print(f"ATTENDANCE {size} total rows median_ms={median(durations):.3f}")
