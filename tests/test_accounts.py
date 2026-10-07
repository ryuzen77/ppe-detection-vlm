"""Penyimpanan akun, hash kata sandi, dan perintah terminal (T51)."""
import sqlite3

import pytest

from backend import accounts
from backend.config import cfg

PASSWORD = "kata-sandi-uji-panjang"


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = accounts.AccountStore(tmp_path / "accounts.db")
    monkeypatch.setattr(accounts, "store", s)
    return s


def test_hash_produksi_scrypt_bergaram_dan_terverifikasi():
    first, second = accounts.hash_password(PASSWORD), accounts.hash_password(PASSWORD)
    assert first != second, "garam acak per hash"
    assert first.startswith(f"scrypt${cfg.PASSWORD_SCRYPT_N}${cfg.PASSWORD_SCRYPT_R}${cfg.PASSWORD_SCRYPT_P}$")
    assert PASSWORD not in first
    assert accounts.verify_password(PASSWORD, first)
    assert not accounts.verify_password(PASSWORD + "x", first)


@pytest.mark.parametrize("stored", ["", "rusak", "bcrypt$1$2$3$YQ==$YQ==", "scrypt$x$8$1$YQ==$YQ=="])
def test_hash_rusak_tidak_pernah_cocok(stored):
    assert accounts.verify_password(PASSWORD, stored) is False


def test_basis_data_hanya_menyimpan_hash(store):
    store.create("admin-uji", PASSWORD)
    (stored,) = sqlite3.connect(store.path).execute("SELECT password_hash FROM users").fetchone()
    assert PASSWORD not in stored and accounts.verify_password(PASSWORD, stored)


def test_nama_tidak_peka_huruf_besar(store):
    store.create("Admin-Uji", PASSWORD)
    assert store.authenticate("ADMIN-UJI", PASSWORD).username == "admin-uji"
    with pytest.raises(accounts.AccountError) as e:
        store.create("admin-uji", PASSWORD)
    assert e.value.code == "username_taken"


def test_login_mencatat_waktu_tetapi_verifikasi_tidak(store):
    store.create("admin-uji", PASSWORD)
    assert store.verify("admin-uji", PASSWORD).last_login_at is None
    assert store.all()[0].last_login_at is None
    assert store.authenticate("admin-uji", PASSWORD).last_login_at is not None
    assert store.all()[0].last_login_at is not None


def test_nama_tak_terdaftar_tetap_menghitung_hash(store, monkeypatch):
    """Lama jawaban tidak membocorkan nama yang terdaftar: scrypt tetap dijalankan."""
    calls = []
    real = accounts.verify_password
    monkeypatch.setattr(accounts, "verify_password", lambda p, s: calls.append(s) or real(p, s))
    assert store.authenticate("tidak-ada", PASSWORD) is None
    assert calls and calls[0].startswith("scrypt$")


def test_cli_buat_dan_reset_kata_sandi(store, monkeypatch, capsys):
    answers = iter([PASSWORD, PASSWORD, "sandi-baru-panjang", "sandi-baru-panjang"])
    monkeypatch.setattr(accounts.getpass, "getpass", lambda prompt="": next(answers))
    assert accounts.main(["create", "admin-uji"]) == 0
    assert accounts.main(["reset-password", "admin-uji"]) == 0
    assert store.authenticate("admin-uji", "sandi-baru-panjang") is not None
    out = capsys.readouterr().out
    assert PASSWORD not in out and "sandi-baru" not in out
    assert accounts.main(["list"]) == 0 and "admin-uji" in capsys.readouterr().out


def test_cli_menolak_ulangan_berbeda_dan_akun_tak_ada(store, monkeypatch):
    answers = iter([PASSWORD, PASSWORD + "x"])
    monkeypatch.setattr(accounts.getpass, "getpass", lambda prompt="": next(answers))
    with pytest.raises(SystemExit):
        accounts.main(["create", "admin-uji"])
    assert store.count() == 0
    monkeypatch.setattr(accounts.getpass, "getpass", lambda prompt="": PASSWORD)
    with pytest.raises(SystemExit):
        accounts.main(["reset-password", "tidak-ada"])
