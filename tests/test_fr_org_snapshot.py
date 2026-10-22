"""Jalur snapshot divisi & kontraktor dari galeri FR sampai audit (T79, tinjauan T84a).

Pengganti uji nyata yang tidak bisa diulang: data pekerja (department_id, company_id)
-> galeri `FaceIdentifier` -> `Identity.department/company` -> inspeksi disimpan lewat
`StateManager` -> kolom snapshot `department`/`company` di audit.db. Mesin wajah tiruan
(vektor tetap), tanpa kamera & tanpa model.
"""

import types

import numpy as np
import pytest

import backend.state_manager as sm
from backend import face_crypto, face_identity, worker_store
from backend.config import cfg
from backend.report_manager import ReportManager
from backend.vlm_analyzer import InspectionResult

CROPS = [np.zeros((10, 10, 3), np.uint8)] * 3


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(256).astype(np.float32)
    return v / np.linalg.norm(v)


def _fake_engine(vector: np.ndarray):
    """Setiap potongan menghasilkan vektor yang sama: 3/3 frame sepakat."""
    return types.SimpleNamespace(subject_embeddings=lambda crops: [vector] * len(crops))


@pytest.fixture
def store(tmp_path):
    return worker_store.SqliteWorkerStore(tmp_path / "workers.db", key=face_crypto.generate_key())


@pytest.fixture
def audit(tmp_path, monkeypatch):
    mgr = ReportManager()
    mgr.db_path = tmp_path / "audit.db"
    mgr.snapshots_dir = tmp_path / "snapshots"
    mgr.snapshots_dir.mkdir(parents=True, exist_ok=True)
    mgr._opened = False
    mgr.open()
    monkeypatch.setattr(sm, "report_mgr", mgr)
    return mgr


def _enroll_with_org(store) -> worker_store.Worker:
    dep = store.create_org("departments", "Konstruksi")
    comp = store.create_org("companies", "PT Kontraktor A")
    worker = store.create(
        "P-0001",
        "Budi Santoso",
        True,
        "admin-uji",
        nickname="Budi",
        gender="male",
        department_id=dep["id"],
        company_id=comp["id"],
    )
    store.add_template(worker.id, "bare", cfg.FACE_MODEL_VERSION, _unit(1), "admin-uji")
    return worker


def _audit_row(mgr: ReportManager):
    with mgr._get_connection() as conn:
        return conn.execute(
            "SELECT worker_id, employee_no, worker_name, fr_status, department, company "
            "FROM worker_inspections ORDER BY id DESC LIMIT 1"
        ).fetchone()


def test_identitas_dari_galeri_membawa_nama_divisi_dan_kontraktor(store):
    worker = _enroll_with_org(store)
    who = face_identity.FaceIdentifier(store, _fake_engine(_unit(1))).identify(CROPS, session_id=1)
    assert (who.status, who.worker_id, who.employee_no) == ("recognized", worker.id, "P-0001")
    assert (who.department, who.company) == ("Konstruksi", "PT Kontraktor A")


def test_inspeksi_lewat_state_manager_mengisi_snapshot_audit(store, audit):
    worker = _enroll_with_org(store)
    who = face_identity.FaceIdentifier(store, _fake_engine(_unit(1))).identify(CROPS, session_id=2)
    result = InspectionResult(is_complete=True, inference_source="VLM_LIVE:tiruan")
    sm.StateManager()._save_audit(7, result, np.zeros((24, 12, 3), np.uint8), who)
    row = _audit_row(audit)
    assert (row["worker_id"], row["employee_no"], row["worker_name"], row["fr_status"]) == (
        worker.id,
        "P-0001",
        "Budi Santoso",
        "recognized",
    )
    assert (row["department"], row["company"]) == ("Konstruksi", "PT Kontraktor A")


def test_snapshot_tetap_walau_pekerja_pindah_divisi_setelahnya(store, audit):
    """Riwayat audit memakai nama saat pemeriksaan, bukan data pekerja terbaru."""
    worker = _enroll_with_org(store)
    identifier = face_identity.FaceIdentifier(store, _fake_engine(_unit(1)))
    result = InspectionResult(is_complete=True, inference_source="VLM_LIVE:tiruan")
    sm.StateManager()._save_audit(7, result, np.zeros((24, 12, 3), np.uint8), identifier.identify(CROPS))
    store.update_worker(worker.id, department_id=None)
    assert _audit_row(audit)["department"] == "Konstruksi"
    assert identifier.identify(CROPS).department is None, "galeri dimuat ulang setelah data pekerja berubah"


def test_wajah_tak_dikenal_tanpa_snapshot_organisasi(store, audit):
    _enroll_with_org(store)
    who = face_identity.FaceIdentifier(store, _fake_engine(_unit(9))).identify(CROPS)
    result = InspectionResult(is_complete=True, inference_source="VLM_LIVE:tiruan")
    sm.StateManager()._save_audit(8, result, np.zeros((24, 12, 3), np.uint8), who)
    row = _audit_row(audit)
    assert row["fr_status"] == "unknown"
    assert (row["department"], row["company"]) == (None, None)
