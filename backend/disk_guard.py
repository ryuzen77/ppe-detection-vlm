"""Penjaga sisa disk DATA_DIR (T53).

Disk penuh = audit & foto bukti gagal disimpan, jadi gerbang tidak lagi bisa
membuktikan keputusannya. Log adalah pengisi disk yang paling mudah dikorbankan:
- sisa < DISK_WARN_FREE_GB  → application log berkas hanya WARNING ke atas;
- sisa < DISK_CRITICAL_FREE_GB → application log berkas hanya CRITICAL (konsol & security
  log tetap; security log kecil dan justru dibutuhkan saat insiden).
Setiap perubahan keadaan dicatat sekali. Penjaga yang sama melaporkan catatan
log yang dibuang karena antrean penuh (lihat logging_setup).
"""

import logging
import shutil
import threading
from pathlib import Path
from typing import Callable, Optional

from . import logging_setup, messages
from .config import cfg

logger = logging.getLogger(__name__)

STATE_OK = "ok"
STATE_LOW = "low"
STATE_CRITICAL = "critical"
BYTES_PER_GB = 1024**3

# Level minimum application log berkas per keadaan disk. Kritis = hanya CRITICAL (praktis berhenti;
# pesan alasan berhentinya sendiri CRITICAL, jadi tetap tertulis)
FILE_LEVEL = {STATE_OK: logging.NOTSET, STATE_LOW: logging.WARNING, STATE_CRITICAL: logging.CRITICAL}


def disk_state(free_gb: float, warn_gb: float, critical_gb: float) -> str:
    if free_gb < critical_gb:
        return STATE_CRITICAL
    if free_gb < warn_gb:
        return STATE_LOW
    return STATE_OK


class DiskGuard:
    def __init__(self, free_bytes: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free):
        self._free_bytes = free_bytes
        self.state = STATE_OK
        self.free_gb: Optional[float] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def status(self) -> dict:
        return {"state": self.state, "free_gb": None if self.free_gb is None else round(self.free_gb, 1)}

    def check(self):
        """Satu putaran: ukur disk, sesuaikan log berkas, laporkan log yang dibuang."""
        try:
            free_gb = self._free_bytes(cfg.DATA_DIR) / BYTES_PER_GB
        except OSError as e:
            logger.warning(messages.DISK_CHECK_FAILED.format(path=cfg.DATA_DIR, error=e))
            return
        self.free_gb = free_gb
        self._apply(disk_state(free_gb, cfg.DISK_WARN_FREE_GB, cfg.DISK_CRITICAL_FREE_GB))
        dropped = logging_setup.take_dropped()
        if dropped:
            logger.warning(messages.LOG_DROPPED.format(count=dropped))

    def _apply(self, state: str):
        if state == self.state:
            return
        self.state = state
        logging_setup.set_file_level(FILE_LEVEL[state])
        if state == STATE_OK:
            text = messages.DISK_OK.format(free_gb=self.free_gb)
        elif state == STATE_LOW:
            text = messages.DISK_LOW.format(free_gb=self.free_gb, limit_gb=cfg.DISK_WARN_FREE_GB)
        else:
            text = messages.DISK_CRITICAL.format(free_gb=self.free_gb, limit_gb=cfg.DISK_CRITICAL_FREE_GB)
        # Level pesan >= level berkas yang baru, jadi alasan perubahannya selalu tertulis
        logger.log(max(logging.WARNING, FILE_LEVEL[state]), text)

    def _loop(self):
        while not self._stop.is_set():
            self.check()
            self._stop.wait(cfg.DISK_CHECK_SECONDS)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="DiskGuard", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()


disk_guard = DiskGuard()
