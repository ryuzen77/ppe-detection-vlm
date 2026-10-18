"""Security log (T53): satu baris JSON per kejadian keamanan di `LOG_DIR/SECURITY_LOG_FILE`.

Isinya siapa melakukan apa dari mana: login/logout, gagal login, penguncian,
setup ditolak, akses ditolak, perubahan akun, dan pergantian VLM. Tidak pernah
berisi kata sandi, hash, token, atau API key.

Menggantikan `account_events.jsonl` (T51) dan `vlm_changes.jsonl` (T28) supaya
semua kejadian keamanan punya satu tempat, satu bentuk, satu masa simpan.
Ditulis lewat logger `security` (antrean + fsync di thread listener, lihat
`logging_setup.py`), jadi pemanggil di jalur permintaan tidak menunggu disk.
"""
import json
import logging
import time

from .logging_setup import SECURITY_LOGGER

logger = logging.getLogger(SECURITY_LOGGER)

# Nama kejadian baru (kejadian akun lama memakai nama dari pemanggilnya: login, setup, ...)
LOCKOUT_STARTED = "lockout_started"
SETUP_DENIED = "setup_denied"
FORBIDDEN = "forbidden"
VLM_CHANGE = "vlm_change"
# Data pekerja & templat wajah (T34b); tidak pernah berisi embedding
WORKER_CREATED = "worker_created"
WORKER_TEMPLATE_ADDED = "worker_template_added"
WORKER_TEMPLATE_DELETED = "worker_template_deleted"
WORKER_DEACTIVATED = "worker_deactivated"
WORKER_ACTIVATED = "worker_activated"
WORKER_FACE_DELETED = "worker_face_deleted"
FACE_KEY_ERROR = "face_key_error"


def record(event: str, **fields):
    """Waktu lokal mesin gerbang tanpa zona, sama seperti audit (kontrak T51)."""
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **fields}
    logger.info(json.dumps(entry, ensure_ascii=False))
