"""Catatan hidup server (T37): kapan terakhir hidup dan apakah berhenti rapi.

Saat menyala, server membaca catatan sebelumnya dan mencatat di log berapa lama
gerbang tidak aktif, serta apakah ia berhenti rapi (Ctrl+C/restart) atau
mendadak (listrik padam, crash). Selama hidup, waktu terakhir diperbarui
berkala, jadi lama mati setelah henti mendadak bisa diperkirakan.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from . import messages
from .config import cfg

logger = logging.getLogger(__name__)

KEY_LAST_ALIVE = "last_alive"
KEY_CLEAN = "clean_shutdown"


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return messages.DURATION_HOURS.format(h=hours, m=minutes)
    if minutes:
        return messages.DURATION_MINUTES.format(m=minutes, s=secs)
    return messages.DURATION_SECONDS.format(s=secs)


def describe_previous(state: Optional[dict], now: float) -> Optional[tuple[int, str]]:
    """(level log, pesan) tentang berhentinya server sebelumnya; None bila belum ada catatan."""
    if not isinstance(state, dict) or not isinstance(state.get(KEY_LAST_ALIVE), (int, float)):
        return None
    last = state[KEY_LAST_ALIVE]
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last))
    down = format_duration(now - last)
    if state.get(KEY_CLEAN):
        return logging.INFO, messages.UPTIME_CLEAN_RESTART.format(since=since, down=down)
    # Waktu terakhir diperbarui tiap UPTIME_HEARTBEAT_SECONDS, jadi server bisa
    # mati hingga selang itu setelah catatan terakhir
    return logging.WARNING, messages.UPTIME_UNCLEAN_RESTART.format(since=since, down=down)


class UptimeMonitor:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else cfg.UPTIME_STATE_PATH
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Thread detak dan stop() menulis berkas yang sama; tanpa gembok, tulisan
        # clean=False dari detak bisa selesai SETELAH clean=True dari stop() dan
        # server yang dimatikan rapi tercatat "berhenti mendadak" (tinjauan T37)
        self._write_lock = threading.Lock()

    def _read(self) -> Optional[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _write(self, clean: bool):
        # Berkas sementara lalu ganti nama: listrik padam di tengah penulisan
        # tidak meninggalkan JSON setengah jadi
        with self._write_lock:
            self._write_unlocked(clean)

    def _write_unlocked(self, clean: bool):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({KEY_LAST_ALIVE: time.time(), KEY_CLEAN: clean}), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as e:
            logger.warning(messages.UPTIME_WRITE_FAILED.format(error=e))

    def start(self):
        described = describe_previous(self._read(), time.time())
        if described:
            logger.log(*described)
        self._write(clean=False)
        self._stop.clear()
        self._thread = threading.Thread(target=self._beat, name="UptimeHeartbeat", daemon=True)
        self._thread.start()

    def _beat(self):
        while not self._stop.wait(cfg.UPTIME_HEARTBEAT_SECONDS):
            self._write(clean=False)

    def stop(self):
        self._stop.set()
        # Detak terakhir yang sedang berjalan harus selesai dulu, supaya status
        # rapi pasti menjadi tulisan terakhir
        if self._thread is not None:
            self._thread.join(timeout=cfg.THREAD_STOP_TIMEOUT_SECONDS)
        self._write(clean=True)


uptime_monitor = UptimeMonitor()
