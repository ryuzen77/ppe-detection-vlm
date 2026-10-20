"""Data pekerja & templat wajah terenkripsi (T34b1): enkripsi, persetujuan, retensi, hak hapus."""

import sqlite3
import time

import numpy as np
import pytest

from backend import face_crypto, security_log, worker_store
from backend.config import cfg

MODEL = "intel_0095"


@pytest.fixture
def key():
    return face_crypto.generate_key()


@pytest.fixture
def store(tmp_path, key):
    return worker_store.SqliteWorkerStore(tmp_path / "workers.db", key=key)


def _vector(seed: int, dim: int = 256) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _worker(store, number="P-001", name="Budi Santoso"):
    return store.create(number, name, consent=True, actor="admin-uji", nickname="Budi", gender="male")


def _raw_bytes(store) -> bytes:
    """Seluruh isi berkas basis data + WAL, seperti yang bisa dibaca orang yang menyalin folder data."""
    files = [store.path, store.path.with_name(store.path.name + "-wal")]
    return b"".join(f.read_bytes() for f in files if f.exists())


# --- Enkripsi ---


def test_kunci_kosong_berarti_fitur_mati_kunci_rusak_ditolak():
    assert face_crypto.parse_key("") is None and face_crypto.parse_key("   ") is None
    with pytest.raises(face_crypto.FaceKeyError):
        face_crypto.parse_key("bukan-base64!!")
    with pytest.raises(face_crypto.FaceKeyError):
        face_crypto.parse_key("c2luZ2thdA==")  # base64 sah tetapi bukan 32 byte
    assert len(face_crypto.parse_key(face_crypto.generate_key()) or b"") == face_crypto.KEY_BYTES


def test_enkripsi_bolak_balik_dan_terikat_ke_pekerja(key):
    cipher = face_crypto.FaceCipher(face_crypto.parse_key(key) or b"")
    vector = _vector(1)
    nonce, sealed = cipher.encrypt(vector, face_crypto.template_aad(7, MODEL))
    assert np.array_equal(cipher.decrypt(nonce, sealed, face_crypto.template_aad(7, MODEL), 256), vector)
    with pytest.raises(face_crypto.FaceKeyError):
        cipher.decrypt(nonce, sealed, face_crypto.template_aad(8, MODEL), 256)  # dipindah ke pekerja lain
    with pytest.raises(face_crypto.FaceKeyError):
        cipher.decrypt(nonce, sealed, face_crypto.template_aad(7, "sface"), 256)  # versi model lain
    assert cipher.encrypt(vector, b"x")[0] != cipher.encrypt(vector, b"x")[0], "nonce baru tiap templat"


def test_templat_tersimpan_terenkripsi(store):
    worker = _worker(store)
    vector = _vector(2)
    store.add_template(worker.id, "bare", MODEL, vector, "admin-uji")
    raw = _raw_bytes(store)
    assert vector.tobytes() not in raw and vector[:8].tobytes() not in raw


# --- Pendaftaran ---


def test_persetujuan_wajib_dicentang(store):
    for consent in (False, None, "true", 1):
        with pytest.raises(worker_store.WorkerError) as e:
            store.create("P-001", "Budi", consent=consent, actor="admin-uji")  # type: ignore[arg-type]
        assert e.value.code == "consent_required"
    assert store.all() == []


def test_persetujuan_dicatat_per_pekerja(store, monkeypatch):
    monkeypatch.setattr(cfg, "FACE_CONSENT_VERSION", "HR-2026-01")
    worker = _worker(store)
    assert (worker.consent_by, worker.consent_version) == ("admin-uji", "HR-2026-01")
    assert worker.consent_at == worker.created_at and worker.active


@pytest.mark.parametrize(
    "number, name, code",
    [
        ("P#001", "Budi", "invalid_employee_no"),
        ("P 001", "Budi", "invalid_employee_no"),
        ("P" * 33, "Budi", "invalid_employee_no"),
        ("P-001", "   ", "invalid_name"),
        ("P-001", "B" * 81, "invalid_name"),
        ("P-001", "Budi\x00", "invalid_name"),
    ],
)
def test_data_pekerja_divalidasi(store, number, name, code):
    with pytest.raises(worker_store.WorkerError) as e:
        store.create(number, name, consent=True, actor="admin-uji", nickname="Budi", gender="male")
    assert e.value.code == code


def test_nomor_pegawai_otomatis_saat_kosong(store):
    w = store.create("", "Budi", consent=True, actor="admin-uji", nickname="Budi", gender="male")
    assert w.employee_no == "P-0001"


def test_nomor_pegawai_unik_tanpa_peduli_huruf_besar(store):
    _worker(store, "p-001")
    with pytest.raises(worker_store.WorkerError) as e:
        _worker(store, "P-001", "Orang Lain")
    assert e.value.code == "employee_no_taken"


def test_tanpa_kunci_pendaftaran_ditolak(tmp_path):
    store = worker_store.SqliteWorkerStore(tmp_path / "w.db", key="")
    assert not store.face_ready()
    with pytest.raises(worker_store.WorkerError) as e:
        _worker(store)
    assert e.value.code == "face_not_ready"
    rusak = worker_store.SqliteWorkerStore(tmp_path / "w.db", key="bukan kunci")
    assert not rusak.face_ready()


def test_nama_dirapikan(store):
    assert _worker(store, name="  Budi   Santoso ").name == "Budi Santoso"


# --- Templat & galeri ---


def test_kondisi_foto_dibatasi_dan_pekerja_nonaktif_ditolak(store):
    worker = _worker(store)
    with pytest.raises(worker_store.WorkerError) as e:
        store.add_template(worker.id, "kacamata_hitam", MODEL, _vector(1), "admin-uji")
    assert e.value.code == "invalid_condition"
    store.deactivate(worker.id)
    with pytest.raises(worker_store.WorkerError) as e:
        store.add_template(worker.id, "bare", MODEL, _vector(1), "admin-uji")
    assert e.value.code == "inactive"


def test_galeri_hanya_pekerja_aktif_dan_versi_model_sama(store):
    a, b = _worker(store, "A-1", "Ani"), _worker(store, "B-1", "Bayu")
    for i, condition in enumerate(("bare", "glasses")):
        store.add_template(a.id, condition, MODEL, _vector(10 + i), "admin-uji")
    store.add_template(b.id, "bare", MODEL, _vector(20), "admin-uji")
    store.add_template(b.id, "bare", "sface", _vector(21, 128), "admin-uji")
    gallery = store.load_gallery(MODEL)
    assert gallery.worker_ids.tolist() == [a.id, a.id, b.id] and gallery.unreadable == 0
    assert np.allclose(gallery.vectors[0], _vector(10))
    store.deactivate(b.id)
    assert store.load_gallery(MODEL).worker_ids.tolist() == [a.id, a.id]
    assert [t.condition for t in store.get(a.id).templates] == ["bare", "glasses"]


def test_kunci_berbeda_templat_dilewati_tanpa_menghentikan_server(store, tmp_path):
    worker = _worker(store)
    store.add_template(worker.id, "bare", MODEL, _vector(1), "admin-uji")
    other = worker_store.SqliteWorkerStore(store.path, key=face_crypto.generate_key())
    gallery = other.load_gallery(MODEL)
    assert gallery.unreadable == 1 and gallery.vectors.shape[0] == 0


# --- Nonaktif, retensi, hak hapus ---


def test_nonaktif_menjadwalkan_hapus_30_hari_dan_diulang_tidak_memperpanjang(store, monkeypatch):
    worker = _worker(store)
    first = store.deactivate(worker.id)
    deactivated = time.mktime(time.strptime(first.deactivated_at or "", worker_store.TIME_FORMAT))
    expected = worker_store._format(deactivated + cfg.FACE_RETENTION_DAYS * worker_store.SECONDS_PER_DAY)
    assert not first.active and first.delete_after == expected
    monkeypatch.setattr(worker_store, "_now", lambda: "2099-01-01T00:00:00")
    assert store.deactivate(worker.id).deactivated_at == first.deactivated_at
    again = store.activate(worker.id)
    assert again.active and again.deactivated_at is None and again.delete_after is None


def test_retensi_menghapus_templat_setelah_masa_simpan(store, security_events):
    keep, expire = _worker(store, "A-1", "Ani"), _worker(store, "B-1", "Bayu")
    secret = _vector(5)
    store.add_template(expire.id, "bare", MODEL, secret, "admin-uji")
    store.add_template(keep.id, "bare", MODEL, _vector(6), "admin-uji")
    store.deactivate(expire.id)
    days = cfg.FACE_RETENTION_DAYS * worker_store.SECONDS_PER_DAY
    assert store.purge_expired(now=time.time() + days - 60) == [], "belum genap masa simpan"
    sealed = _sealed_bytes(store, expire.id)
    assert store.purge_expired(now=time.time() + days + 60) == [expire.id]
    gone = store.get(expire.id)
    assert gone.templates == () and gone.face_deleted_at is not None and gone.delete_after is None
    assert len(store.get(keep.id).templates) == 1, "pekerja aktif tidak tersentuh"
    assert sealed not in _raw_bytes(store), "ciphertext tidak tertinggal di berkas (secure_delete + checkpoint)"


def _sealed_bytes(store, worker_id: int) -> bytes:
    with sqlite3.connect(store.path) as conn:
        return conn.execute("SELECT ciphertext FROM face_templates WHERE worker_id = ?", (worker_id,)).fetchone()[0]


def test_retensi_runtime_dicatat_di_security_log(store, security_events, monkeypatch):
    worker = _worker(store)
    store.add_template(worker.id, "bare", MODEL, _vector(1), "admin-uji")
    store.deactivate(worker.id)
    monkeypatch.setattr(cfg, "FACE_RETENTION_DAYS", 0)
    assert worker_store.run_retention(store) == [worker.id]
    assert security_events[-1] | {"time": ""} == {
        "time": "",
        "event": security_log.WORKER_FACE_DELETED,
        "worker_id": worker.id,
        "reason": "retention",
        "actor": "system",
        "ok": True,
    }


def test_retensi_gagal_tidak_menghentikan_siklus(tmp_path, caplog):
    class Broken(worker_store.SqliteWorkerStore):
        def purge_expired(self, now=None):
            raise sqlite3.DatabaseError("berkas rusak")

    assert worker_store.run_retention(Broken(tmp_path / "w.db", key="")) == []
    assert "Retensi data wajah gagal" in caplog.text


def test_aktif_lagi_setelah_terhapus_butuh_foto_ulang(store):
    worker = _worker(store)
    store.add_template(worker.id, "bare", MODEL, _vector(1), "admin-uji")
    store.deactivate(worker.id)
    store.purge_expired(now=time.time() + (cfg.FACE_RETENTION_DAYS + 1) * worker_store.SECONDS_PER_DAY)
    back = store.activate(worker.id)
    assert back.active and back.templates == () and back.face_deleted_at is not None
    store.add_template(worker.id, "bare", MODEL, _vector(2), "admin-uji")
    assert store.get(worker.id).face_deleted_at is None


def test_hapus_wajah_manual_dan_satu_templat(store):
    worker = _worker(store)
    first = store.add_template(worker.id, "bare", MODEL, _vector(1), "admin-uji")
    store.add_template(worker.id, "glasses", MODEL, _vector(2), "admin-uji")
    store.delete_template(worker.id, first.id)
    assert [t.condition for t in store.get(worker.id).templates] == ["glasses"]
    with pytest.raises(worker_store.WorkerError) as e:
        store.delete_template(worker.id, first.id)
    assert e.value.code == "template_not_found"
    assert store.delete_face(worker.id) == 1
    assert store.get(worker.id).templates == () and store.load_gallery(MODEL).worker_ids.size == 0


def test_pekerja_tidak_ada(store):
    for action in (store.get, store.deactivate, store.activate, store.delete_face):
        with pytest.raises(worker_store.WorkerError) as e:
            action(999)
        assert e.value.code == "not_found"


def test_status_batas_galeri(monkeypatch):
    monkeypatch.setattr(cfg, "FACE_GALLERY_TESTED_LIMIT", 2)
    assert worker_store.gallery_limit(2) == {"tested": 2, "count": 2, "over": False}
    assert worker_store.gallery_limit(3)["over"] is True


def test_status_kunci_saat_menyala_tanpa_mencetak_kunci(monkeypatch, caplog):
    caplog.set_level("INFO")
    monkeypatch.setattr(cfg, "FACE_DATA_KEY", "")
    worker_store.log_key_status()
    assert "FACE_DATA_KEY kosong" in caplog.text
    caplog.clear()
    monkeypatch.setattr(cfg, "FACE_DATA_KEY", "kunci-uji-rusak")
    worker_store.log_key_status()
    assert "tidak valid" in caplog.text and "kunci-uji-rusak" not in caplog.text
