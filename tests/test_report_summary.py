"""Ringkasan laporan harian/mingguan/bulanan & filter rentang tanggal (T49)."""

import csv
import io
import json
import sqlite3
import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import messages
from backend.audit import summary as rs
from backend.app import app
from backend.audit.report_manager import CSV_BOM, ReportManager

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
    out = rs.summarize(
        "day",
        d,
        d,
        [row("2026-10-05", "07:10:00"), row("2026-10-05", "07:50:00", False, [HELM]), row("2026-10-05", "13:00:00")],
    )
    assert len(out["buckets"]) == 24 and out["buckets"][0] == {
        "start": "00:00",
        "label": "00",
        "passed": 0,
        "rejected": 0,
    }
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
    rows = [
        row("2026-10-05", complete=False, missing=[HELM, SEPATU]),
        row("2026-10-05", complete=False, missing=[HELM]),
        row("2026-10-05", complete=False, missing=["Label lama"]),
        rs.AuditRow("2026-10-05", "07:00:00", False, "{rusak"),
    ]
    ranking = rs.summarize("day", d, d, rows)["missing_items"]
    assert ranking[0] == {"key": "helm", "label": HELM, "count": 2}
    assert {"key": None, "label": "Label lama", "count": 1} in ranking, "label tak dikenal tetap dihitung"
    assert sum(r["count"] for r in ranking) == 4, "JSON rusak dilewati, tidak menggagalkan laporan"


# --- Basis data & API -------------------------------------------------------------------


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    m = ReportManager(db_path=tmp_path / "audit.db", snapshots_dir=tmp_path / "snap")
    m.save_inspection(1, True, {}, [], "", "VLM_LIVE:x", 1.0)  # buat tabel
    with sqlite3.connect(tmp_path / "audit.db") as c:
        c.execute("DELETE FROM worker_inspections")
        for day, t, ok, missing in (
            ("2026-10-05", "07:00:00", 1, []),
            ("2026-10-06", "08:00:00", 0, [HELM]),
            ("2026-10-12", "09:00:00", 1, []),
            ("2026-11-02", "10:00:00", 0, [SEPATU]),
        ):
            c.execute(
                "INSERT INTO worker_inspections (track_id, timestamp, date_str, time_str, is_complete, "
                "items_json, missing_items) VALUES (1, ?, ?, ?, ?, '{}', ?)",
                (f"{day}T{t}", day, t, ok, json.dumps(missing)),
            )
    import backend.api.routes_reports as routes

    monkeypatch.setattr(routes, "report_mgr", m)
    return m


def test_ringkasan_memakai_indeks_tanggal(mgr):
    with sqlite3.connect(mgr.db_path) as c:
        plan = " ".join(
            str(r)
            for r in c.execute(
                "EXPLAIN QUERY PLAN SELECT date_str FROM worker_inspections WHERE date_str BETWEEN ? AND ?", ("a", "b")
            )
        )
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
    assert len(list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))) == 1 + 2, "header + 2 baris dalam rentang"
    assert client.get("/api/reports", params={"from": "kemarin"}).status_code == 400


def test_indeks_baru_dibuat_di_database_lama(tmp_path):
    """Temuan 06-10: DB yang skemanya sudah terbaru tidak pernah mendapat idx_date_str."""
    db = tmp_path / "audit.db"
    m = ReportManager(db_path=db, snapshots_dir=tmp_path / "snap")
    m.save_inspection(1, True, {}, [], "", "VLM_LIVE:x", 1.0)
    with sqlite3.connect(db) as c:
        c.execute("DROP INDEX idx_date_str")  # meniru DB yang dibuat sebelum T49
    ReportManager(db_path=db, snapshots_dir=tmp_path / "snap").open()
    with sqlite3.connect(db) as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert "idx_date_str" in names


# --- Ekspor CSV bertahap (T43) --------------------------------------------------------------


def test_ekspor_dikirim_per_potongan_dengan_nomor_berlanjut(mgr, monkeypatch):
    from backend.config import cfg

    monkeypatch.setattr(cfg, "CSV_EXPORT_BATCH_ROWS", 2)
    chunks = list(mgr.iter_csv_chunks())
    assert len(chunks) == 1 + 2, "header + 2 potongan untuk 4 baris"
    assert chunks[0].startswith(CSV_BOM) and all(CSV_BOM not in chunk for chunk in chunks[1:])
    rows = list(csv.reader(io.StringIO("".join(chunks).removeprefix(CSV_BOM))))
    assert [r[0] for r in rows[1:]] == ["1", "2", "3", "4"], "nomor urut tidak mulai ulang tiap potongan"
    assert "".join(chunks) == mgr.export_csv_text()


def test_api_ekspor_mengalir_sama_dengan_teks_utuh(mgr):
    r = TestClient(app).get("/api/reports/export", params={"from": "2026-10-01", "to": "2026-10-31"})
    assert r.status_code == 200 and r.text == mgr.export_csv_text("2026-10-01", "2026-10-31")


def _next_in_new_thread(gen):
    """Ambil satu potongan dari thread baru, seperti pool thread Starlette (iterate_in_threadpool)."""
    out = {}

    def step():
        try:
            out["chunk"] = next(gen)
        except StopIteration:
            out["done"] = True
        except Exception as e:  # dicatat supaya tes menampilkan galat aslinya
            out["error"] = e

    worker = threading.Thread(target=step)
    worker.start()
    worker.join()
    if "error" in out:
        raise out["error"]
    return out.get("chunk")


def test_ekspor_tetap_utuh_walau_tiap_potongan_dari_thread_berbeda(mgr, monkeypatch):
    # T68: koneksi SQLite dibuat di generator lalu dipakai thread lain -> ProgrammingError,
    # CSV terpotong diam-diam setelah potongan pertama.
    from backend.config import cfg

    monkeypatch.setattr(cfg, "CSV_EXPORT_BATCH_ROWS", 1)
    gen = mgr.iter_csv_chunks()
    chunks = []
    while (chunk := _next_in_new_thread(gen)) is not None:
        chunks.append(chunk)
    assert "".join(chunks) == mgr.export_csv_text()
    assert len(chunks) == 1 + 4, "header + 4 potongan satu baris"


def test_unduhan_dibatalkan_koneksi_ekspor_ditutup(mgr, monkeypatch):
    from backend.config import cfg
    from backend.audit import db as audit_db

    monkeypatch.setattr(cfg, "CSV_EXPORT_BATCH_ROWS", 1)
    opened = []
    real_connect = audit_db.sqlite3.connect

    def spy(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(audit_db.sqlite3, "connect", spy)
    gen = mgr.iter_csv_chunks()
    next(gen)  # header
    next(gen)  # potongan pertama, lalu klien memutus
    gen.close()
    assert opened, "ekspor membuka koneksi"
    with pytest.raises(sqlite3.ProgrammingError):
        opened[-1].execute("SELECT 1")  # koneksi sudah ditutup
