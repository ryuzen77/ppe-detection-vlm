"""Ringkasan laporan harian/mingguan/bulanan & filter rentang tanggal (T49)."""
import csv
import io
import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import messages, report_summary as rs
from backend.app import app
from backend.report_manager import ReportManager

HELM = "Helm Keselamatan"
SEPATU = "Sepatu Tertutup"


def row(day, time="07:15:00", complete=True, missing=()):
    return rs.AuditRow(day, time, complete, json.dumps(list(missing)))


# --- Rentang periode --------------------------------------------------------------------

def test_rentang_harian_mingguan_bulanan():
    rabu = date(2026, 10, 7)
    assert rs.period_range("day", rabu) == (rabu, rabu)
    assert rs.period_range("week", rabu) == (date(2026, 10, 5), date(2026, 10, 11)), "Senin-Minggu"
    assert rs.period_range("month", rabu) == (date(2026, 10, 1), date(2026, 10, 31))
    assert rs.period_range("month", date(2028, 2, 10))[1] == date(2028, 2, 29), "tahun kabisat"


def test_periode_tidak_dikenal_ditolak():
    with pytest.raises(ValueError):
        rs.period_range("year", date(2026, 10, 7))


# --- Batang grafik ----------------------------------------------------------------------

def test_harian_24_jam_termasuk_yang_nol():
    d = date(2026, 10, 5)
    out = rs.summarize("day", d, d, [row("2026-10-05", "07:10:00"), row("2026-10-05", "07:50:00", False, [HELM]),
                                     row("2026-10-05", "13:00:00")])
    assert len(out["buckets"]) == 24 and out["buckets"][0] == {"start": "00:00", "label": "00", "passed": 0, "rejected": 0}
    assert out["buckets"][7] == {"start": "07:00", "label": "07", "passed": 1, "rejected": 1}
    assert out["totals"] == {"total": 3, "passed": 2, "rejected": 1, "compliance_rate": 66.7}


def test_mingguan_berlabel_hari_dan_bulanan_semua_tanggal():
    week = rs.summarize("week", date(2026, 10, 5), date(2026, 10, 11), [row("2026-10-07")])
    assert [b["label"] for b in week["buckets"]] == list(messages.WEEKDAY_SHORT)
    assert week["buckets"][2]["passed"] == 1
    month = rs.summarize("month", date(2026, 10, 1), date(2026, 10, 31), [])
    assert len(month["buckets"]) == 31 and month["buckets"][-1]["label"] == "31"


def test_tanpa_data_tingkat_kepatuhan_null():
    d = date(2026, 10, 5)
    assert rs.summarize("day", d, d, [])["totals"]["compliance_rate"] is None


def test_baris_di_luar_rentang_diabaikan():
    d = date(2026, 10, 5)
    assert rs.summarize("week", d, date(2026, 10, 11), [row("2026-10-12")])["totals"]["total"] == 0


# --- Item APD paling sering kurang ------------------------------------------------------

def test_item_kurang_urut_terbanyak_dengan_kunci_katalog():
    d = date(2026, 10, 5)
    rows = [row("2026-10-05", complete=False, missing=[HELM, SEPATU]), row("2026-10-05", complete=False, missing=[HELM]),
            row("2026-10-05", complete=False, missing=["Label lama"]),
            rs.AuditRow("2026-10-05", "07:00:00", False, "{rusak")]
    ranking = rs.summarize("day", d, d, rows)["missing_items"]
    assert ranking[0] == {"key": "helm", "label": HELM, "count": 2}
    assert {"key": None, "label": "Label lama", "count": 1} in ranking, "label tak dikenal tetap dihitung"
    assert sum(r["count"] for r in ranking) == 4, "JSON rusak dilewati, tidak menggagalkan laporan"


# --- Basis data & API -------------------------------------------------------------------

@pytest.fixture
def mgr(tmp_path, monkeypatch):
    m = ReportManager(db_path=tmp_path / "audit.db", snapshots_dir=tmp_path / "snap")
    m.save_inspection(1, True, {}, [], "", "VLM_LIVE:x", 1.0)          # buat tabel
    with sqlite3.connect(tmp_path / "audit.db") as c:
        c.execute("DELETE FROM worker_inspections")
        for day, t, ok, missing in (("2026-10-05", "07:00:00", 1, []), ("2026-10-06", "08:00:00", 0, [HELM]),
                                    ("2026-10-12", "09:00:00", 1, []), ("2026-11-02", "10:00:00", 0, [SEPATU])):
            c.execute("INSERT INTO worker_inspections (track_id, timestamp, date_str, time_str, is_complete, "
                      "items_json, missing_items) VALUES (1, ?, ?, ?, ?, '{}', ?)",
                      (f"{day}T{t}", day, t, ok, json.dumps(missing)))
    import backend.api.routes_reports as routes
    monkeypatch.setattr(routes, "report_mgr", m)
    return m


def test_ringkasan_memakai_indeks_tanggal(mgr):
    with sqlite3.connect(mgr.db_path) as c:
        plan = " ".join(str(r) for r in c.execute(
            "EXPLAIN QUERY PLAN SELECT date_str FROM worker_inspections WHERE date_str BETWEEN ? AND ?", ("a", "b")))
    assert "idx_date_str" in plan


def test_api_ringkasan_mingguan(mgr):
    r = TestClient(app).get("/api/reports/summary", params={"period": "week", "date": "2026-10-07"})
    body = r.json()
    assert r.status_code == 200 and body["range"] == {"from": "2026-10-05", "to": "2026-10-11"}
    assert body["totals"]["total"] == 2 and body["missing_items"][0]["key"] == "helm"


@pytest.mark.parametrize("params", [{"period": "year"}, {"period": "day", "date": "07-10-2026"}])
def test_api_ringkasan_masukan_salah_400(mgr, params):
    assert TestClient(app).get("/api/reports/summary", params=params).status_code == 400


def test_tabel_dan_csv_mengikuti_rentang(mgr):
    client = TestClient(app)
    data = client.get("/api/reports", params={"from": "2026-10-05", "to": "2026-10-11"}).json()
    assert data["filtered_total"] == 2
    r = client.get("/api/reports/export", params={"from": "2026-10-05", "to": "2026-10-11"})
    assert "2026-10-05_2026-10-11" in r.headers["content-disposition"]
    assert len(list(csv.reader(io.StringIO(r.text)))) == 1 + 2, "header + 2 baris dalam rentang"
    assert client.get("/api/reports", params={"from": "kemarin"}).status_code == 400


def test_indeks_baru_dibuat_di_database_lama(tmp_path):
    """Temuan 06-10: DB yang skemanya sudah terbaru tidak pernah mendapat idx_date_str."""
    db = tmp_path / "audit.db"
    m = ReportManager(db_path=db, snapshots_dir=tmp_path / "snap")
    m.save_inspection(1, True, {}, [], "", "VLM_LIVE:x", 1.0)
    with sqlite3.connect(db) as c:
        c.execute("DROP INDEX idx_date_str")          # meniru DB yang dibuat sebelum T49
    ReportManager(db_path=db, snapshots_dir=tmp_path / "snap").open()
    with sqlite3.connect(db) as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_date_str" in names
