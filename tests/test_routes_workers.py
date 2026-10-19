"""API data pekerja (T34b1): kontrak JSON, hak admin, kode galat, security log."""

import numpy as np
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend import face_crypto, face_engine, face_identity, messages, security_log, worker_store
from backend.audio_engine import audio_player
from backend.api.deps import require_session
from backend.app import app
from backend.auth import SessionUser
from backend.config import cfg
from backend.state_manager import state_mgr
from backend.video.capture import video_service

MODEL = "intel_0095"
WORKER_KEYS = {
    "nickname",  # T34d
    "gender",
    "salutation",
    "voice_ready",
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
    # Galeri FR disimpan per revisi; store baru tiap tes bisa memakai nomor revisi yang sama (T76)
    monkeypatch.setattr(face_identity.identifier, "_revision", -1)
    return repository


@pytest.fixture
def client():
    return TestClient(app)


def _create(client, number="P-001", name="Budi", consent=True):
    return client.post("/api/workers", json={"employee_no": number, "name": name, "consent": consent, "nickname": "Budi", "gender": "male"})


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
    # suara nama dibuat di latar (T34d), jadi kejadian terakhir belum tentu worker_created
    event = next(e for e in security_events if e["event"] == security_log.WORKER_CREATED)
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
    wid = store.create("P-1", "Budi", True, "admin-uji", nickname="Budi", gender="male").id
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


# --- Foto pendaftaran dari kamera (T34b2) ---


class FakeEngine:
    """Mesin FR tiruan: mencatat frame yang diterima, mengembalikan sampel atau galat yang diatur tes."""

    def __init__(self, error=None):
        self.frames = []
        self.error = error

    def detect(self, frame):
        self.frames.append(frame)
        row = np.array([[100, 100, 80, 100, 120, 120, 160, 120, 140, 140, 125, 160, 155, 160, 0.93]], np.float32)
        return face_engine.parse_detections(row, 0.6)

    def enrollment_sample(self, frame):
        self.frames.append(frame)
        if self.error:
            raise face_engine.FaceEngineError(self.error, "pesan uji")
        row = np.array([[100, 100, 80, 100, 120, 120, 160, 120, 140, 140, 125, 160, 155, 160, 0.93]], np.float32)
        detection = face_engine.parse_detections(row, 0.6)[0]
        return face_engine.FaceSample(detection, np.ones(256, np.float32) / 16)


@pytest.fixture
def camera(monkeypatch):
    """Kamera aktif berisi satu frame, jalur inspeksi kosong, mesin FR tiruan."""
    frame = np.zeros((cfg.ENROLLMENT_MIN_FRAME_HEIGHT, 1920, 3), np.uint8)
    engine = FakeEngine()
    monkeypatch.setattr(video_service, "camera_frame", lambda: frame)
    monkeypatch.setattr(state_mgr, "session", None)
    monkeypatch.setattr(face_engine, "engine", engine)
    return engine


def _photo(client, wid, condition="bare"):
    return client.post(f"/api/workers/{wid}/templates", json={"condition": condition})


def test_foto_pendaftaran_menjadi_templat_terenkripsi(client, store, camera, security_events):
    wid = _create(client).json()["id"]
    r = _photo(client, wid, "glasses")
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "condition", "model_version", "created_at", "quality"}
    assert body["condition"] == "glasses" and body["model_version"] == cfg.FACE_MODEL_VERSION
    assert body["quality"] == {"face_width_px": 80, "interocular_px": 40.0, "det_score": pytest.approx(0.93)}
    gallery = store.load_gallery(cfg.FACE_MODEL_VERSION)
    assert gallery.worker_ids.tolist() == [wid] and np.allclose(gallery.vectors[0], 1 / 16)
    event = security_events[-1]
    assert event["event"] == security_log.WORKER_TEMPLATE_ADDED and event["condition"] == "glasses"
    assert not any(isinstance(v, list) and len(v) > 10 for v in event.values()), "tanpa embedding di log"


@pytest.mark.parametrize(
    "code, status",
    [("no_face", 422), ("multiple_faces", 422), ("face_too_small", 422), ("face_too_close", 422), ("camera_low_resolution", 409)],
)
def test_foto_tidak_layak_tidak_menyimpan_apa_pun(client, store, camera, code, status):
    wid = _create(client).json()["id"]
    camera.error = code
    r = _photo(client, wid)
    assert r.status_code == status and r.json()["detail"]["code"] == code
    assert store.get(wid).templates == ()


def test_kamera_tidak_dipakai_saat_jalur_terisi_atau_kamera_mati(client, store, camera, monkeypatch):
    wid = _create(client).json()["id"]
    monkeypatch.setattr(state_mgr, "session", object())
    r = _photo(client, wid)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "camera_busy"
    monkeypatch.setattr(state_mgr, "session", None)
    monkeypatch.setattr(video_service, "camera_frame", lambda: None)
    r = _photo(client, wid)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "camera_unavailable"
    assert camera.frames == [] and store.get(wid).templates == ()


def test_permintaan_pasti_ditolak_dicek_sebelum_kamera(client, store, camera, monkeypatch):
    wid = _create(client).json()["id"]
    r = _photo(client, wid, "kacamata_hitam")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_condition"
    client.post(f"/api/workers/{wid}/deactivate")
    r = _photo(client, wid)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "inactive"
    assert _photo(client, 999).status_code == 404
    monkeypatch.setattr(worker_store, "store", worker_store.SqliteWorkerStore(store.path, key=""))
    assert _photo(client, wid).json()["detail"]["code"] == "face_not_ready"
    assert camera.frames == [], "kamera tidak disentuh untuk permintaan yang pasti ditolak"


def test_foto_pendaftaran_khusus_admin(client, store, camera):
    async def operator(request: Request) -> SessionUser:
        user = SessionUser("operator-uji", "operator")
        request.state.user = user
        return user

    app.dependency_overrides[require_session] = operator
    wid = store.create("P-1", "Budi", True, "admin-uji", nickname="Budi", gender="male").id
    assert _photo(client, wid).status_code == 403 and camera.frames == []


# --- Mode pendaftaran wajah (T75) ---


@pytest.fixture
def enrollment():
    state_mgr.release_enrollment()
    yield
    state_mgr.release_enrollment()


def test_jeda_pendaftaran_membuat_foto_bisa_diambil(client, store, camera, security_events, enrollment, monkeypatch):
    """Uji nyata 19-10: orang yang difoto memulai sesi sehingga foto selalu camera_busy."""
    wid = _create(client).json()["id"]
    monkeypatch.setattr(state_mgr, "session", object())
    assert _photo(client, wid).status_code == 409
    r = client.post("/api/workers/enrollment")
    assert r.status_code == 200 and r.json() == {"active": True, "hold_s": cfg.ENROLLMENT_HOLD_SECONDS}
    assert _photo(client, wid).status_code == 201
    client.post("/api/workers/enrollment")  # denyut
    assert client.delete("/api/workers/enrollment").status_code == 204
    assert client.delete("/api/workers/enrollment").status_code == 204
    events = [(e["event"], e["actor"]) for e in security_events if e["event"].startswith("enrollment_")]
    assert events == [(security_log.ENROLLMENT_STARTED, "admin-uji"), (security_log.ENROLLMENT_ENDED, "admin-uji")]


def test_jeda_pendaftaran_khusus_admin(client, enrollment):
    async def operator(request: Request) -> SessionUser:
        user = SessionUser("operator-uji", "operator")
        request.state.user = user
        return user

    app.dependency_overrides[require_session] = operator
    assert client.post("/api/workers/enrollment").status_code == 403
    assert client.delete("/api/workers/enrollment").status_code == 403
    assert state_mgr.get_telemetry()["enrollment"]["active"] is False


# --- Pendaftaran terpandu (T76) ---


def test_rencana_pendaftaran_dari_config(client):
    plan = client.get("/api/workers/enrollment/plan").json()
    assert plan == {
        "shots_per_condition": cfg.ENROLLMENT_SHOTS_PER_CONDITION,
        "poses": list(cfg.ENROLLMENT_POSES),
        "condition_sets": {"no_glasses": ["bare", "helmet"], "glasses": ["glasses", "helmet_glasses"]},
        "interocular": {"min_px": cfg.FACE_MIN_INTEROCULAR_PX, "max_ratio": cfg.ENROLLMENT_MAX_INTEROCULAR_RATIO},
        "min_frame_height": cfg.ENROLLMENT_MIN_FRAME_HEIGHT,
        "prompts": messages.ENROLLMENT_PROMPT_KEYS,
    }
    prompts = plan["prompts"]
    used = {*plan["poses"], prompts["condition_switch"], prompts["done"], *prompts["fit"].values()}
    assert used <= set(messages.ENROLLMENT_VOICE_TEXTS), "setiap petunjuk punya suara"
    assert {c for pair in plan["condition_sets"].values() for c in pair} == set(cfg.FACE_CONDITIONS)


def test_pratinjau_dan_suara_hanya_selama_jeda(client, store, camera, enrollment, monkeypatch):
    """Kamera gerbang bukan alat pantau: tanpa jeda pendaftaran keduanya ditolak."""
    played = []
    monkeypatch.setattr(audio_player, "play", lambda name, *a, **k: played.append(name))
    assert client.get("/api/workers/enrollment/preview").json()["detail"]["code"] == "enrollment_inactive"
    assert client.post("/api/workers/enrollment/prompt", json={"prompt": "daftar_kiri"}).status_code == 409
    assert camera.frames == [] and played == []
    client.post("/api/workers/enrollment")
    assert client.get("/api/workers/enrollment/preview").json() == {"fit": "ok", "faces": 1, "interocular_px": 40.0}
    assert client.post("/api/workers/enrollment/prompt", json={"prompt": "daftar_kiri"}).status_code == 204
    r = client.post("/api/workers/enrollment/prompt", json={"prompt": "lengkap"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_prompt", "hanya suara pendaftaran"
    assert played == ["daftar_kiri"]


def test_pratinjau_kamera_resolusi_rendah(client, camera, enrollment, monkeypatch):
    """Uji nyata 19-10: kamera 720p -> pendamping diberi tahu sebelum memotret, bukan setelah gagal dikenali."""
    low = np.zeros((cfg.ENROLLMENT_MIN_FRAME_HEIGHT - 360, 1280, 3), np.uint8)
    monkeypatch.setattr(video_service, "camera_frame", lambda: low)
    client.post("/api/workers/enrollment")
    assert client.get("/api/workers/enrollment/preview").json()["fit"] == "low_resolution"


def test_wajah_pekerja_lain_ditolak_saat_pendaftaran(client, store, camera):
    """Satu orang dua ID membuat setiap pengenalan ragu (tanpa nama)."""
    first = _create(client, "P-001").json()["id"]
    assert _photo(client, first).status_code == 201
    assert _photo(client, first, "helmet").status_code == 201, "foto tambahan orang yang sama boleh"
    second = _create(client, "P-002", "Budi Lain").json()["id"]
    r = _photo(client, second)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "face_matches_other"
    assert "P-001" in r.json()["detail"]["message"] and store.get(second).templates == ()
