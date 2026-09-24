"""Pemindahan data dari tata letak lama (backend/) ke DATA_DIR."""
from types import SimpleNamespace

import pytest

from backend import storage


def _cfg(data):
    reports = data / "reports"
    return SimpleNamespace(
        DATA_DIR=data, REPORTS_DIR=reports, SNAPSHOTS_DIR=reports / "snapshots",
        DB_PATH=reports / "audit.db", CAMERA_STATE_PATH=data / "camera_state.json",
        RUNTIME_SETTINGS_PATH=data / "runtime_settings.json",
    )


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    """backend/ tiruan berisi data tata letak lama, plus satu berkas kode."""
    root = tmp_path / "backend"
    (root / "reports" / "snapshots").mkdir(parents=True)
    for name in ["audit.db", "audit.db-wal", "audit.db-shm", "audit.v0.bak"]:
        (root / "reports" / name).write_text(name)
    for i in range(3):
        (root / "reports" / "snapshots" / f"w{i}.jpg").write_text(str(i))
    (root / "camera_state.json").write_text("kamera")
    (root / "runtime_settings.json").write_text("pengaturan")
    (root / "kode.py").write_text("kode")
    monkeypatch.setattr(storage, "LEGACY_DIR", root)
    return root


def test_seluruh_data_dipindah_dan_kode_tidak_disentuh(legacy, tmp_path):
    cfg = _cfg(tmp_path / "data")
    moved, skipped = storage.migrate_legacy_data(cfg)

    assert (len(moved), skipped) == (9, [])
    for name in ["audit.db", "audit.db-wal", "audit.db-shm", "audit.v0.bak"]:
        assert (cfg.REPORTS_DIR / name).read_text() == name
    assert sorted(p.name for p in cfg.SNAPSHOTS_DIR.iterdir()) == ["w0.jpg", "w1.jpg", "w2.jpg"]
    assert cfg.CAMERA_STATE_PATH.read_text() == "kamera"
    assert cfg.RUNTIME_SETTINGS_PATH.read_text() == "pengaturan"
    assert not (legacy / "reports").exists(), "Folder laporan lama yang kosong dibersihkan"
    assert (legacy / "kode.py").exists()


def test_jalan_kedua_tidak_melakukan_apa_pun(legacy, tmp_path):
    cfg = _cfg(tmp_path / "data")
    storage.migrate_legacy_data(cfg)
    assert storage.migrate_legacy_data(cfg) == ([], [])


def test_berkas_di_tujuan_tidak_pernah_ditimpa(legacy, tmp_path):
    cfg = _cfg(tmp_path / "data")
    cfg.SNAPSHOTS_DIR.mkdir(parents=True)
    cfg.DB_PATH.write_text("BARU")
    (cfg.SNAPSHOTS_DIR / "w1.jpg").write_text("BARU")

    moved, skipped = storage.migrate_legacy_data(cfg)

    assert cfg.DB_PATH.read_text() == "BARU"
    assert (cfg.SNAPSHOTS_DIR / "w1.jpg").read_text() == "BARU"
    assert (cfg.SNAPSHOTS_DIR / "w0.jpg").exists()
    # Yang bentrok tetap di tempat lama dan dilaporkan
    assert (legacy / "reports" / "audit.db").exists()
    assert (legacy / "reports" / "snapshots" / "w1.jpg").exists()
    assert len(skipped) == 2


def test_wal_tidak_dipindah_tanpa_basis_datanya(legacy, tmp_path):
    # Menempelkan -wal lama ke audit.db lain akan merusak basis data tujuan
    cfg = _cfg(tmp_path / "data")
    cfg.REPORTS_DIR.mkdir(parents=True)
    cfg.DB_PATH.write_text("BARU")
    storage.migrate_legacy_data(cfg)
    assert not (cfg.REPORTS_DIR / "audit.db-wal").exists()
    assert (legacy / "reports" / "audit.db-wal").exists()


def test_data_dir_menunjuk_backend_sendiri_tidak_memindah(legacy):
    assert storage.migrate_legacy_data(_cfg(legacy)) == ([], [])
