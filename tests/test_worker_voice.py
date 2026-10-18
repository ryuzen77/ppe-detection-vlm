"""Suara nama pekerja saat lolos (T34d): profil Pak/Bu + nama panggilan, data yang dikirim ke
layanan suara, pemutaran hanya saat lolos & dikenali, penghapusan bersama data wajah."""

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import audio_engine, face_crypto, face_identity, security_log, worker_store, worker_voice
from backend.app import app
from backend.config import cfg
from backend.state_manager import GateSession, StateManager
from backend.vlm_analyzer import InspectionResult


@pytest.fixture
def store(tmp_path, monkeypatch):
    repository = worker_store.SqliteWorkerStore(tmp_path / "workers.db", key=face_crypto.generate_key())
    monkeypatch.setattr(worker_store, "store", repository)
    monkeypatch.setattr(cfg, "VOICE_DIR", tmp_path / "voices")
    return repository


def _wait(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# --- Profil ---


def test_jenis_kelamin_wajib_dan_menentukan_sapaan(store):
    with pytest.raises(worker_store.WorkerError) as e:
        store.create("P-1", "Budi Santoso", True, "admin-uji")
    assert e.value.code == "invalid_gender"
    budi = store.create("P-1", "Budi Santoso", True, "admin-uji", gender="male")
    sari = store.create("P-2", "Sari Dewi", True, "admin-uji", nickname="Sari", gender="FEMALE")
    assert (budi.nickname, budi.salutation) == ("Budi", "Pak"), "nama panggilan bawaan = kata pertama"
    assert (sari.gender, sari.salutation) == ("female", "Bu")


def test_nama_panggilan_divalidasi_dan_profil_bisa_diubah(store):
    with pytest.raises(worker_store.WorkerError) as e:
        store.create("P-1", "Budi", True, "admin-uji", nickname="x" * 31, gender="male")
    assert e.value.code == "invalid_nickname"
    worker = store.create("P-1", "Budi Santoso", True, "admin-uji", gender="male")
    revision = store.revision
    changed = store.update_profile(worker.id, nickname="  Pak   Budi ")
    assert changed.nickname == "Pak Budi" and changed.gender == "male" and store.revision > revision
    assert store.update_profile(worker.id, gender="female").salutation == "Bu"
    with pytest.raises(worker_store.WorkerError) as e:
        store.update_profile(worker.id, gender="lainnya")
    assert e.value.code == "invalid_gender"


def test_basis_data_t34b1_tanpa_kolom_profil_ditambah_kolomnya(tmp_path):
    db = tmp_path / "lama.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE workers (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_no TEXT NOT NULL UNIQUE "
        "COLLATE NOCASE, name TEXT NOT NULL, active INTEGER NOT NULL, consent_at TEXT NOT NULL, consent_by "
        "TEXT NOT NULL, consent_version TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL, "
        "deactivated_at TEXT, face_deleted_at TEXT)"
    )
    conn.execute(
        "INSERT INTO workers (employee_no, name, active, consent_at, consent_by, consent_version, created_at,"
        " created_by) VALUES ('P-9', 'Lama', 1, 't', 'a', '1', 't', 'a')"
    )
    conn.commit()
    conn.close()
    old = worker_store.SqliteWorkerStore(db, key=face_crypto.generate_key()).all()[0]
    assert old.name == "Lama" and old.nickname is None and old.salutation is None
    assert worker_voice.voice_text(old) is None, "pekerja lama tanpa profil = suara umum"


# --- Pembuatan suara ---


def test_yang_dikirim_ke_layanan_suara_hanya_sapaan_dan_nama_panggilan(store, security_events):
    worker = store.create("P-001", "Budi Santoso", True, "admin-uji", gender="male")
    sent = []

    def record(text: str, path: Path) -> None:
        sent.append(text)
        path.write_bytes(b"x")

    assert worker_voice.synthesize(worker, save=record)
    assert sent == ["APD lengkap. Silakan masuk, Pak Budi."]
    assert "Santoso" not in sent[0] and "P-001" not in sent[0]
    assert worker_voice.voice_ready(worker.id) and not worker_voice.voice_path(worker.id).with_suffix(".part").exists()
    event = security_events[-1]
    assert (event["event"], event["worker_id"], event["provider"], event["ok"]) == (
        security_log.WORKER_VOICE_CREATED,
        worker.id,
        "gtts",
        True,
    )


def test_layanan_suara_gagal_tanpa_berkas_setengah_jadi(store, security_events, caplog):
    worker = store.create("P-1", "Budi", True, "admin-uji", gender="male")

    def offline(text, path):
        path.write_bytes(b"setengah")
        raise OSError("tidak ada internet")

    assert worker_voice.synthesize(worker, save=offline) is False
    assert not worker_voice.voice_ready(worker.id) and not list(cfg.VOICE_DIR.glob("*"))
    assert security_events[-1]["ok"] is False and "gagal dibuat" in caplog.text


def test_hapus_suara(store):
    worker = store.create("P-1", "Budi", True, "admin-uji", gender="male")
    worker_voice.synthesize(worker)
    assert worker_voice.delete([worker.id, 999]) == 1 and not worker_voice.voice_ready(worker.id)


# --- API ---


def test_api_pendaftaran_profil_dan_hapus_wajah(store, no_cloud_voice):
    client = TestClient(app)
    r = client.post(
        "/api/workers", json={"employee_no": "P-1", "name": "Sari Dewi", "consent": True, "gender": "female"}
    )
    assert r.status_code == 201 and (r.json()["nickname"], r.json()["salutation"]) == ("Sari", "Bu")
    wid = r.json()["id"]
    assert _wait(lambda: worker_voice.voice_ready(wid)), "suara dibuat di latar"
    assert no_cloud_voice[-1] == "APD lengkap. Silakan masuk, Bu Sari."
    assert client.get("/api/workers").json()["workers"][0]["voice_ready"] is True
    r = client.patch(f"/api/workers/{wid}", json={"nickname": "Dewi"})
    assert r.status_code == 200 and r.json()["nickname"] == "Dewi"
    assert _wait(lambda: no_cloud_voice[-1] == "APD lengkap. Silakan masuk, Bu Dewi.")
    assert client.patch(f"/api/workers/{wid}", json={"gender": "x"}).json()["detail"]["code"] == "invalid_gender"
    assert client.post("/api/workers", json={"employee_no": "P-2", "name": "Ani", "consent": True}).status_code == 400
    assert client.delete(f"/api/workers/{wid}/face").status_code == 204
    assert not worker_voice.voice_ready(wid), "MP3 nama ikut terhapus bersama data wajah"


# --- Pemutaran ---


def _session(identity):
    session = GateSession(1, time.time())
    session.identity = identity
    return session


def _result(complete):
    return InspectionResult(is_complete=complete, missing_items=[] if complete else ["Helm Keselamatan"])


def test_suara_bernama_hanya_saat_lolos_dan_dikenali(store):
    worker = store.create("P-1", "Budi", True, "admin-uji", gender="male")
    worker_voice.synthesize(worker)
    known = face_identity.Identity("recognized", worker.id, "Budi", "P-1", 0.8)
    assert StateManager._named_voice(_session(known), _result(True)) == {
        "named_voice": worker_voice.voice_path(worker.id)
    }
    assert StateManager._named_voice(_session(known), _result(False)) == {}, "ditolak = tanpa nama"
    assert StateManager._named_voice(_session(face_identity.Identity("unknown")), _result(True)) == {}
    assert StateManager._named_voice(_session(None), _result(True)) == {}
    other = face_identity.Identity("recognized", 999, "X", "P-9", 0.8)
    assert StateManager._named_voice(_session(other), _result(True)) == {}, "tanpa MP3 = suara umum"


def test_mesin_audio_memakai_suara_bernama_hanya_saat_lolos(tmp_path, monkeypatch):
    engine = audio_engine.AudioEngine()
    played = []
    monkeypatch.setattr(engine, "play", lambda sound, **kw: played.append(sound))
    voice = tmp_path / "worker_1.mp3"
    voice.write_bytes(b"x")
    engine.play_result(True, [], named_voice=voice)
    engine.play_result(False, ["Helm Keselamatan"], named_voice=voice)
    engine.play_result(True, [], named_voice=tmp_path / "hilang.mp3")
    assert played[0] == voice and played[1] != voice and played[2] == "lengkap"
    assert isinstance(played[0], Path)
