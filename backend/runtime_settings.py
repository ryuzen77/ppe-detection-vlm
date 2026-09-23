"""Pengaturan yang diubah operator saat sistem berjalan dan bertahan setelah restart.

Mengikuti pola `camera_state.json`: satu berkas JSON kecil per mesin. Berkas yang
hilang atau rusak tidak boleh menghentikan sistem — nilai bawaan dipakai.
"""

import json
import threading
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent / "runtime_settings.json"

_lock = threading.Lock()


def load() -> dict:
    """Seluruh pengaturan tersimpan; dict kosong bila belum ada atau rusak."""
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as e:
        print(f"[RuntimeSettings] Gagal membaca {SETTINGS_PATH.name}: {e}")
    return {}


def update(key: str, value) -> bool:
    """Menyimpan satu kunci tanpa menimpa kunci lain. True bila berhasil ditulis."""
    with _lock:
        data = load()
        data[key] = value
        try:
            # Tulis ke berkas sementara lalu ganti, supaya listrik padam di tengah
            # penulisan tidak meninggalkan JSON setengah jadi.
            tmp = SETTINGS_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(SETTINGS_PATH)
            return True
        except Exception as e:
            print(f"[RuntimeSettings] Gagal menyimpan {SETTINGS_PATH.name}: {e}")
            return False
