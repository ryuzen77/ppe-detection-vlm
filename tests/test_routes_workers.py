"""API data pekerja (T34b1): kontrak JSON, hak admin, kode galat, security log."""

import numpy as np
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend import face_crypto, security_log, worker_store
from backend.api.deps import require_session
from backend.app import app
from backend.auth import SessionUser
from backend.config import cfg

MODEL = "intel_0095"
WORKER_KEYS = {
    "id",
    "employee_no",
    "name",
    "active",
    "consent",
    "created_at",
    "deactivated_at",
    "delete_after",
    "face_deleted_at",
    "templates",
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    repository = worker_store.SqliteWorkerStore(tmp_path / "workers.db", key=face_crypto.generate_key())
    monkeypatch.setattr(worker_store, "store", repository)
    return repository


@pytest.fixture
def client():
    return TestClient(app)


def _create(client, number="P-001", name="Budi", consent=True):
    return client.post("/api/workers", json={"employee_no": number, "name": name, "consent": consent})


def test_daftar_kosong_dan_status_fitur(client, store):
    body = client.get("/api/workers").json()
    assert body == {
        "face_ready": True,
        "limit": {"tested": cfg.FACE_GALLERY_TESTED_LIMIT, "count": 0, "over": False},
        "workers": [],
    }


def test_buat_pekerja_sesuai_kontrak_tanpa_data_wajah(client, store, security_events):
    r = _create(client)
    assert r.status_code == 201
    worker = r.json()
    assert set(worker) == WORKER_KEYS
    assert worker["consent"] == {"at": worker["created_at"], "by": "admin-uji", "version": cfg.FACE_CONSENT_VERSION}
    assert worker["active"] is True and worker["templates"] == [] and worker["delete_after"] is None
    event = security_events[-1]
    assert (event["event"], event["worker_id"], event["actor"], event["employee_no"]) == (
        security_log.WORKER_CREATED,
        worker["id"],
        "admin-uji",
        "P-001",
    )
    assert "name" not in event, "nama pekerja tidak perlu masuk security log (minimisasi)"


@pytest.mark.parametrize(
    "payload, status, code",
    [
        ({"employee_no": "P-1", "name": "Budi", "consent": False}, 400, "consent_required"),
        ({"employee_no": "P-1", "name": "Budi"}, 400, "consent_required"),
        ({"employee_no": "", "name": "Budi", "consent": True}, 400, "invalid_employee_no"),
        ({"employee_no": "P-1", "name": "", "consent": True}, 400, "invalid_name"),
    ],
)
def test_permintaan_ditolak_dengan_kode_stabil(client, store, payload, status, code):
    r = client.post("/api/workers", json=payload)
    assert r.status_code == status and r.json()["detail"]["code"] == code
    assert r.json()["detail"]["message"]


def test_nomor_ganda_409_dan_tanpa_kunci_503(client, store, monkeypatch):
    _create(client)
    r = _create(client, "p-001", "Orang Lain")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "employee_no_taken"
    monkeypatch.setattr(worker_store, "store", worker_store.SqliteWorkerStore(store.path, key=""))
    r = _create(client, "P-002")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "face_not_ready"
    assert client.get("/api/workers").json()["face_ready"] is False


def test_nonaktif_aktif_dan_jadwal_hapus(client, store, security_events):
    wid = _create(client).json()["id"]
    off = client.post(f"/api/workers/{wid}/deactivate").json()
    assert off["active"] is False and off["delete_after"] is not None
    assert security_events[-1]["event"] == security_log.WORKER_DEACTIVATED
    assert security_events[-1]["delete_after"] == off["delete_after"]
    on = client.post(f"/api/workers/{wid}/activate").json()
    assert on["active"] is True and on["delete_after"] is None
    assert security_events[-1]["event"] == security_log.WORKER_ACTIVATED


def test_hapus_wajah_dan_templat(client, store, security_events):
    wid = _create(client).json()["id"]
    first = store.add_template(wid, "bare", MODEL, np.ones(256, np.float32), "admin-uji")
    store.add_template(wid, "glasses", MODEL, np.ones(256, np.float32), "admin-uji")
    templates = client.get("/api/workers").json()["workers"][0]["templates"]
    assert [set(t) for t in templates] == [{"id", "condition", "model_version", "created_at"}] * 2
    assert client.delete(f"/api/workers/{wid}/templates/{first.id}").status_code == 204
    assert security_events[-1]["template_id"] == first.id
    assert client.delete(f"/api/workers/{wid}/templates/{first.id}").status_code == 404
    assert client.delete(f"/api/workers/{wid}/face").status_code == 204
    assert (security_events[-1]["event"], security_events[-1]["reason"], security_events[-1]["templates"]) == (
        security_log.WORKER_FACE_DELETED,
        "manual",
        1,
    )
    worker = client.get("/api/workers").json()["workers"][0]
    assert worker["templates"] == [] and worker["face_deleted_at"] is not None


def test_pekerja_tidak_ada_404(client, store):
    for method, path in (
        ("post", "/api/workers/99/deactivate"),
        ("post", "/api/workers/99/activate"),
        ("delete", "/api/workers/99/face"),
        ("delete", "/api/workers/99/templates/1"),
    ):
        r = getattr(client, method)(path)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"


def test_lewat_batas_galeri_admin_diberi_peringatan(client, store, monkeypatch, caplog):
    monkeypatch.setattr(cfg, "FACE_GALLERY_TESTED_LIMIT", 1)
    _create(client, "P-1")
    assert client.get("/api/workers").json()["limit"]["over"] is False
    _create(client, "P-2", "Bayu")
    assert client.get("/api/workers").json()["limit"] == {"tested": 1, "count": 2, "over": True}
    assert "melewati batas teruji" in caplog.text


def test_bukan_admin_ditolak(client, store):
    async def operator(request: Request) -> SessionUser:
        user = SessionUser("operator-uji", "operator")
        request.state.user = user
        return user

    app.dependency_overrides[require_session] = operator
    wid = store.create("P-1", "Budi", True, "admin-uji").id
    for method, path in (
        ("get", "/api/workers"),
        ("post", "/api/workers"),
        ("post", f"/api/workers/{wid}/deactivate"),
        ("delete", f"/api/workers/{wid}/face"),
    ):
        assert getattr(client, method)(path).status_code == 403
    assert store.get(wid).active, "tidak ada yang berubah"


@pytest.mark.real_auth
def test_tanpa_login_ditolak(client, store):
    assert client.get("/api/workers").status_code == 401
