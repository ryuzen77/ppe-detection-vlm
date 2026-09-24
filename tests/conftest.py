"""Lingkungan uji yang terisolasi dari data, kuota API, dan perangkat keras sungguhan.

Semua pengaturan di bawah WAJIB terjadi sebelum modul `backend` mana pun
diimpor: `config` membaca variabel lingkungan dan menyiapkan DATA_DIR saat
diimpor. `load_dotenv` tidak menimpa variabel yang sudah ada, jadi nilai di
sini menang atas `backend/.env`.
"""
import os
import shutil
import tempfile

import pytest

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
