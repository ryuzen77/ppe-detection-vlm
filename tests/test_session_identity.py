"""Identitas pekerja dalam sesi gerbang (T34c1): nama di telemetri, riwayat & audit; FR tidak
pernah menghambat keputusan APD."""

# Fixture `gerbang` & `vlm` dipakai ulang dari test_lifecycle (pytest mengenalinya lewat impor);
# ruff menganggap parameter tes dengan nama itu sebagai definisi ulang.
# ruff: noqa: F811

import sqlite3
import threading
import time
from typing import Any

import pytest

from backend import face_identity, messages
from backend.config import cfg
from backend.report_manager import ReportManager, SCHEMA_VERSION
from backend.state_manager import state_mgr
from test_lifecycle import _analisa_selesai, _wait_for, gerbang, vlm  # noqa: F401 (fixture)

BUDI = face_identity.Identity("recognized", 5, "Budi Santoso", "P-001", 0.81)


class FakeIdentifier:
    """Pengganti `face_identity.identifier`: kunci siap, hasil & lama proses diatur tes."""

    def __init__(self, identity, delay=0.0, ready=True):
        self.identity, self.delay = identity, delay
        self.store = type("Store", (), {"face_ready": staticmethod(lambda: ready)})()
        self.calls = []
        self.release = threading.Event()

    def identify(self, crops, session_id=0):
        self.calls.append((len(crops), session_id))
        if self.delay:
            self.release.wait(self.delay)
        return self.identity


@pytest.fixture
def identifier(monkeypatch):
    def install(identity, **kwargs):
        fake = FakeIdentifier(identity, **kwargs)
        monkeypatch.setattr(face_identity, "identifier", fake)
        return fake

    return install


def _active():
    return state_mgr.get_telemetry()["active_track"]


def test_nama_masuk_telemetri_riwayat_dan_audit(gerbang, vlm, identifier):
    fake = identifier(BUDI)
    _analisa_selesai(gerbang)
    assert _wait_for(lambda: (_active() or {}).get("identity") is not None)
    assert _active()["identity"] == {
        "status": "recognized",
        "name": "Budi Santoso",
        "employee_no": "P-001",
        "score": 0.81,
    }
    assert fake.calls and fake.calls[0][0] <= cfg.FACE_VOTE_FRAMES, "FR memakai frame terbaik jendela diam"
    latest = state_mgr.inspection_history[0]
    assert (latest["worker_name"], latest["employee_no"], latest["fr_status"]) == (
        "Budi Santoso",
        "P-001",
        "recognized",
    )
    row = state_mgr_report_row()
    assert (row["worker_id"], row["worker_name"], row["employee_no"], row["fr_status"]) == (
        5,
        "Budi Santoso",
        "P-001",
        "recognized",
    )
    assert row["fr_score"] == pytest.approx(0.81)


def state_mgr_report_row():
    from backend.report_manager import report_mgr

    return report_mgr.get_reports(limit=1)["page_records"][0]


def test_fr_lambat_tidak_menunda_keputusan_apd(gerbang, vlm, identifier, monkeypatch):
    monkeypatch.setattr(cfg, "FACE_IDENTIFY_TIMEOUT_SECONDS", 0.3)
    fake = identifier(BUDI, delay=5.0)
    started = time.time()
    _analisa_selesai(gerbang)
    assert time.time() - started < 3.0, "keputusan keluar walau FR belum selesai"
    latest = state_mgr.inspection_history[0]
    assert latest["fr_status"] == "unknown" and latest["worker_name"] is None, "lewat batas = tanpa nama di audit"
    fake.release.set()


def test_tanpa_kunci_fr_tidak_dijalankan(gerbang, vlm, identifier):
    fake = identifier(BUDI, ready=False)
    _analisa_selesai(gerbang)
    assert fake.calls == [] and _active()["identity"] is None
    assert state_mgr.inspection_history[0]["fr_status"] is None


def test_hasil_fr_untuk_sesi_lama_tidak_menempel_ke_sesi_baru(gerbang, vlm, identifier):
    fake = identifier(BUDI, delay=5.0)
    _analisa_selesai(gerbang)
    state_mgr.reset_all()  # sesi berakhir sebelum FR selesai
    fake.release.set()
    time.sleep(0.2)
    assert state_mgr.session is None


class SequencedIdentifier(FakeIdentifier):
    """Sesi pertama: FR tertahan lalu menjawab BUDI. Sesi berikutnya: mencatat identitas yang
    SUDAH menempel di sesi itu saat FR-nya baru mulai (harus belum ada), lalu menjawab ANI."""

    def __init__(self):
        super().__init__(BUDI)
        self.first = None
        self.seen_at_start = []

    def identify(self, crops, session_id=0):
        if self.first is None:
            self.first = session_id
        if session_id == self.first:
            self.release.wait(5.0)
            return BUDI
        self.seen_at_start.append(state_mgr.session.identity if state_mgr.session else "tanpa sesi")
        return ANI


ANI = face_identity.Identity("recognized", 6, "Ani", "P-002", 0.77)


def test_nama_sesi_lama_tidak_menempel_ke_sesi_baru_yang_sudah_berjalan(gerbang, vlm, monkeypatch):
    monkeypatch.setattr(cfg, "FACE_IDENTIFY_TIMEOUT_SECONDS", 0.2)
    fake = SequencedIdentifier()
    monkeypatch.setattr(face_identity, "identifier", fake)
    _analisa_selesai(gerbang)            # sesi pertama: FR tertahan
    state_mgr.reset_all()                # pekerja pertama pergi
    _analisa_selesai(gerbang, track_id=77)   # pekerja kedua, sesi baru
    fake.release.set()                   # hasil FR sesi pertama baru tiba sekarang
    assert _wait_for(lambda: fake.seen_at_start)
    assert fake.seen_at_start == [None], "nama pekerja sebelumnya tidak boleh menempel ke sesi baru"
    assert _wait_for(lambda: state_mgr.session is not None and state_mgr.session.identity == ANI)


# --- Audit skema v2 ---


def _v1_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE worker_inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, track_id INTEGER NOT NULL, "
        "timestamp TEXT NOT NULL, date_str TEXT NOT NULL, time_str TEXT NOT NULL, is_complete INTEGER NOT NULL, "
        "items_json TEXT NOT NULL DEFAULT '{}', missing_items TEXT, notes TEXT, inference_source TEXT, "
        "inference_time_ms REAL, snapshot_filename TEXT)"
    )
    conn.execute(
        "INSERT INTO worker_inspections (track_id, timestamp, date_str, time_str, is_complete, items_json, "
        "missing_items, notes, inference_source, inference_time_ms, snapshot_filename) VALUES "
        "(3, '2026-10-01T08:00:00', '2026-10-01', '08:00:00', 1, '{}', '[]', '', 'VLM_LIVE:x', 1.0, '')"
    )
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()


def test_migrasi_v1_ke_v2_mempertahankan_baris_dan_mencadangkan(tmp_path, caplog):
    caplog.set_level("INFO")
    db = tmp_path / "audit.db"
    _v1_db(db)
    mgr = ReportManager(db_path=db, snapshots_dir=tmp_path / "snap").open()
    assert sqlite3.connect(db).execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 3
    assert (tmp_path / "audit.v1.bak").exists()
    old = mgr.get_reports(limit=5)["page_records"][0]
    assert old["track_id"] == 3 and old["worker_name"] is None and old["fr_status"] is None
    assert "Migrasi skema v1 -> v2" in caplog.text
    indexes = {r[1] for r in sqlite3.connect(db).execute("PRAGMA index_list(worker_inspections)")}
    assert "idx_worker_id" in indexes


def test_csv_memuat_nama_pekerja(tmp_path, catalog_defaults):
    mgr = ReportManager(db_path=tmp_path / "a.db", snapshots_dir=tmp_path / "s").open()
    base: dict[str, Any] = dict(
        is_complete=True, items={}, missing_items=[], notes="", inference_source="VLM_LIVE:x", inference_time_ms=1.0
    )
    mgr.save_inspection(
        track_id=1,
        identity={"worker_id": 5, "employee_no": "P-001", "name": "Budi", "status": "recognized", "score": 0.8},
        **base,
    )
    mgr.save_inspection(
        track_id=2,
        identity={"worker_id": None, "employee_no": None, "name": None, "status": "unknown", "score": None},
        **base,
    )
    mgr.save_inspection(track_id=3, **base)
    text = mgr.export_csv_text()
    header, *rows = [line for line in text.splitlines() if line]
    assert messages.CSV_HEADER_WORKER_NAME in header
    column = header.split(",").index(messages.CSV_HEADER_WORKER_NAME)
    assert [r.split(",")[column] for r in rows] == ["Budi (P-001)", messages.CSV_FACE_UNKNOWN, messages.CSV_EMPTY]
