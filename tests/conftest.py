"""Lingkungan uji yang terisolasi dari data, kuota API, dan perangkat keras sungguhan.

Semua pengaturan di bawah WAJIB terjadi sebelum modul `backend` mana pun
diimpor: `config` membaca variabel lingkungan dan menyiapkan DATA_DIR saat
diimpor. `load_dotenv` tidak menimpa variabel yang sudah ada, jadi nilai di
sini menang atas `backend/.env`.
"""
import json
import logging
import os
import shutil
import tempfile

import pytest
from fastapi import Request

from helpers import PROVIDER_KEY_ENVS

_TEST_ROOT = tempfile.mkdtemp(prefix="safeguard_test_")

# Audit, foto, dan pengaturan uji ditulis ke folder sementara, bukan data/
os.environ["DATA_DIR"] = os.path.join(_TEST_ROOT, "data")
# Tanpa API key dan tanpa cadangan: tidak ada kuota VLM terpakai dan tidak ada
# panggilan ke Ollama sungguhan; tes yang butuh VLM memasang penyedia tiruan.
# Semua variabel VLM ditulis eksplisit supaya isi backend/.env tidak ikut terbaca
# (load_dotenv tidak menimpa variabel yang sudah ada, termasuk yang kosong).
os.environ["VLM_PROVIDER"] = "gemini"
os.environ["VLM_BACKUP_PROVIDER"] = "none"
for _nama in ("VLM_API_KEY", "VLM_MODEL", "VLM_BASE_URL", "GEMINI_API_KEY", "GEMINI_MODEL",
              "VLM_MIN_INTERVAL_SECONDS", "VLM_CLOUD_TIMEOUT_SECONDS", "VLM_LOCAL_TIMEOUT_SECONDS",
              "VLM_BACKUP_MODEL", "VLM_BACKUP_BASE_URL", "VLM_BACKUP_API_KEY",
              "VLM_PRIMARY_FAILURES_BEFORE_DOWN", "VLM_PRIMARY_RETRY_AFTER_SECONDS", "VLM_SYSTEM_RETRY_SECONDS"):
    os.environ[_nama] = ""
for _nama in PROVIDER_KEY_ENVS:
    os.environ[_nama] = ""
# Tidak membuka port serial / HTTP ke lampu gerbang sungguhan
os.environ["IOT_ENABLED"] = "false"
os.environ["ADMIN_TOKEN"] = ""
# Log hanya ke konsol (ditangkap pytest); berkas log yang terbuka menghalangi
# penghapusan folder sementara di Windows
os.environ["LOG_TO_FILE"] = "false"

# Pemindahan data lama (storage.py) diarahkan ke folder kosong. Sejak T16 ia
# hanya berjalan di runtime.start(), tetapi pengaman ini tetap dipasang: bila
# sebuah tes kelak memanggilnya, audit asli di backend/ tidak boleh terpindah
# ke folder sementara yang dihapus di akhir sesi.
from backend import storage  # noqa: E402

storage.LEGACY_DIR = storage.Path(_TEST_ROOT) / "legacy_kosong"

from backend import ppe_rules  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)


@pytest.fixture
def catalog_defaults(monkeypatch):
    """Item APD aktif kembali ke bawaan katalog, lalu dipulihkan setelah tes."""
    monkeypatch.setattr(ppe_rules, "_active_overrides", {})
    return ppe_rules


@pytest.fixture(autouse=True)
def logged_in_admin(request):
    """Tes API biasa berjalan sebagai admin yang sudah login (T51: login selalu wajib).

    Tes yang menguji login itu sendiri memakai penanda `real_auth` sehingga
    `require_session` asli berlaku (lihat test_auth.py).
    """
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    from backend.accounts import ROLE_ADMIN
    from backend.api.deps import require_session
    from backend.app import app
    from backend.auth import SessionUser

    user = SessionUser("admin-uji", ROLE_ADMIN)

    async def fake_session(request_: Request) -> SessionUser:
        request_.state.user = user
        return user
    app.dependency_overrides[require_session] = fake_session
    yield
    app.dependency_overrides.pop(require_session, None)


class _SecurityCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events: list[dict] = []

    def emit(self, record):
        self.events.append(json.loads(record.getMessage()))


@pytest.fixture
def security_events():
    """Kejadian security log (T53) sebagai daftar dict, tanpa berkas atau antrean."""
    from backend.logging_setup import SECURITY_LOGGER
    logger = logging.getLogger(SECURITY_LOGGER)
    capture, previous = _SecurityCapture(), logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)
    yield capture.events
    logger.removeHandler(capture)
    logger.setLevel(previous)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_auth: tes memakai pemeriksaan login sungguhan (tanpa admin tiruan)")
