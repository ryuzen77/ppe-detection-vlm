"""Pengenalan pekerja dalam sesi (T34c1): voting 2 dari 3, galeri dimuat ulang, gagal = tanpa nama."""

import numpy as np
import pytest

from backend import face_crypto, face_identity, security_log, worker_store
from backend.config import cfg

THR = 0.55


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(256).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.mark.parametrize(
    "matches, expected",
    [
        ([(1, 0.8), (1, 0.7), (2, 0.9)], (1, 0.75)),  # 2 dari 3 sepakat
        ([(1, 0.8), (1, 0.5), (2, 0.9)], None),  # hanya 1 di atas ambang
        ([(1, 0.8), None, None], None),  # wajah tak terlihat di 2 frame
        ([(1, 0.8), (1, 0.8), (2, 0.9), (2, 0.9)], None),  # dua orang sama-sama lolos = ragu
        ([(3, 0.9), (3, 0.6), (3, 0.56)], (3, (0.9 + 0.6 + 0.56) / 3)),
    ],
)
def test_voting(matches, expected):
    result = face_identity.vote(matches, THR, 2)
    if expected is None:
        assert result is None
    else:
        assert result is not None and result[0] == expected[0] and result[1] == pytest.approx(expected[1])


def test_kecocokan_terbaik_dari_semua_templat():
    a1, a2, b = _unit(1), _unit(2), _unit(3)
    gallery = face_identity.GalleryView(np.array([7, 7, 9]), np.stack([a1, a2, b]), {})
    worker, score = face_identity.best_match(a2, gallery) or (0, 0)
    assert worker == 7 and score == pytest.approx(1.0, abs=1e-5)
    empty = face_identity.GalleryView(np.zeros(0, np.int64), np.zeros((0, 0), np.float32), {})
    assert face_identity.best_match(a1, empty) is None


class FakeEngine:
    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = 0

    def subject_embeddings(self, crops):
        self.calls += 1
        if isinstance(self.vectors, Exception):
            raise self.vectors
        return self.vectors[: len(crops)]


@pytest.fixture
def store(tmp_path):
    return worker_store.SqliteWorkerStore(tmp_path / "w.db", key=face_crypto.generate_key())


def _enroll(store, number, name, vector):
    worker = store.create(number, name, True, "admin-uji")
    store.add_template(worker.id, "bare", cfg.FACE_MODEL_VERSION, vector, "admin-uji")
    return worker


CROPS = [np.zeros((10, 10, 3), np.uint8)] * 3


def test_dikenali_bila_dua_frame_sepakat(store):
    budi = _enroll(store, "P-1", "Budi", _unit(1))
    _enroll(store, "P-2", "Ani", _unit(2))
    noisy = _unit(1) * 0.9 + _unit(5) * 0.1
    engine = FakeEngine([_unit(1), noisy / np.linalg.norm(noisy), None])
    who = face_identity.FaceIdentifier(store, engine).identify(CROPS, session_id=4)
    assert (who.status, who.worker_id, who.name, who.employee_no) == ("recognized", budi.id, "Budi", "P-1")
    assert who.payload() == {
        "status": "recognized",
        "name": "Budi",
        "employee_no": "P-1",
        "score": round(who.score or 0, 3),
    }


def test_orang_asing_tidak_diberi_nama(store):
    _enroll(store, "P-1", "Budi", _unit(1))
    who = face_identity.FaceIdentifier(store, FakeEngine([_unit(8), _unit(9), None])).identify(CROPS)
    assert who.status == "unknown" and who.name is None and who.payload()["name"] is None


def test_tanpa_kunci_atau_galat_mesin_tanpa_nama_dan_tidak_melempar(store, tmp_path, caplog):
    no_key = worker_store.SqliteWorkerStore(tmp_path / "w2.db", key="")
    engine = FakeEngine([_unit(1)] * 3)
    assert face_identity.FaceIdentifier(no_key, engine).identify(CROPS).status == "disabled"
    assert engine.calls == 0, "tanpa kunci, model tidak dijalankan"
    _enroll(store, "P-1", "Budi", _unit(1))
    broken = face_identity.FaceIdentifier(store, FakeEngine(RuntimeError("model rusak")))
    assert broken.identify(CROPS).status == "disabled"
    assert "Pengenalan wajah gagal" in caplog.text
    assert face_identity.FaceIdentifier(store, engine).identify([]).status == "disabled"


def test_galeri_dimuat_ulang_saat_data_pekerja_berubah(store):
    identifier = face_identity.FaceIdentifier(store, FakeEngine([_unit(1)] * 3))
    budi = _enroll(store, "P-1", "Budi", _unit(1))
    assert identifier.identify(CROPS).status == "recognized"
    first = identifier.gallery()
    assert identifier.gallery() is first, "tanpa perubahan, galeri tidak dimuat ulang"
    store.deactivate(budi.id)
    assert identifier.identify(CROPS).status == "unknown", "pekerja nonaktif tidak dikenali lagi"
    store.activate(budi.id)
    store.delete_face(budi.id)
    assert identifier.identify(CROPS).status == "unknown", "wajah terhapus tidak dikenali"


def test_templat_tak_terbaca_dicatat(store, security_events):
    _enroll(store, "P-1", "Budi", _unit(1))
    other_key = worker_store.SqliteWorkerStore(store.path, key=face_crypto.generate_key())
    who = face_identity.FaceIdentifier(other_key, FakeEngine([_unit(1)] * 3)).identify(CROPS)
    assert who.status == "unknown"
    assert security_events[-1]["event"] == security_log.FACE_KEY_ERROR and security_events[-1]["unreadable"] == 1
