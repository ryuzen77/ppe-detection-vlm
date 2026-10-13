"""Penjaga proses server gerbang (T29): `python -m backend.supervisor`.

Server dijalankan sebagai proses anak. Bila berhenti dengan kode bukan 0 (crash,
dibunuh, galat fatal), ia dinyalakan ulang sendiri, sehingga gerbang tidak
menunggu operator setelah gangguan. Berhenti rapi (Ctrl+C, kode 0) = berhenti.

Crash beruntun (mis. salah konfigurasi) memperpanjang jeda sampai batas atas,
supaya log tidak dibanjiri dan GPU tidak terus-menerus memuat model.
Linux produksi memakai systemd (deploy/safeguard.service) untuk peran yang sama.
"""
import logging
import subprocess
import sys
import time
from typing import Callable, Optional, Sequence

from . import messages
from .config import cfg

logger = logging.getLogger("backend.supervisor")


def restart_delay(consecutive_crashes: int) -> float:
    """Jeda sebelum menyalakan ulang: crash pertama jeda dasar, crash beruntun berlipat."""
    delay = cfg.SUPERVISOR_RESTART_DELAY_SECONDS * 2 ** max(consecutive_crashes - 1, 0)
    return min(delay, cfg.SUPERVISOR_MAX_DELAY_SECONDS)


def lights_off_after_exit(code: int):
    """Relay USB (T54) mengunci keadaannya: bila server crash saat hijau, hijau tetap
    menyala. Penjaga ini proses terpisah, jadi masih hidup untuk mematikannya."""
    if cfg.IOT_ENABLED and cfg.IOT_TYPE == "usb_relay":
        from . import usb_relay
        usb_relay.all_off(messages.IOT_RELAY_REASON_EXIT.format(code=code))


def supervise(command: Sequence[str], run: Callable[[Sequence[str]], int] = subprocess.call,
              sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
              max_runs: Optional[int] = None, on_exit: Callable[[int], None] = lights_off_after_exit) -> int:
    """Menjalankan `command` berulang sampai keluar rapi. Mengembalikan kode keluar terakhir."""
    crashes = 0      # crash beruntun: server mati sebelum stabil SUPERVISOR_STABLE_SECONDS
    runs = 0
    while True:
        runs += 1
        started = clock()
        try:
            code = run(command)
        except KeyboardInterrupt:
            logger.info(messages.SUPERVISOR_STOPPED)
            return 0
        on_exit(code)      # sebelum jeda & nyala ulang: lampu tidak tertinggal menyala
        if code == 0:
            logger.info(messages.SUPERVISOR_CLEAN_EXIT)
            return 0
        ran = clock() - started
        crashes = 1 if ran >= cfg.SUPERVISOR_STABLE_SECONDS else crashes + 1
        delay = restart_delay(crashes)
        logger.warning(messages.SUPERVISOR_RESTART.format(code=code, ran=ran, delay=delay))
        if max_runs is not None and runs >= max_runs:
            return code
        try:
            sleep(delay)
        except KeyboardInterrupt:
            logger.info(messages.SUPERVISOR_STOPPED)
            return code


def _setup_logging():
    log_dir = cfg.DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / cfg.SUPERVISOR_LOG_FILE,
                                                                                encoding="utf-8")])


if __name__ == "__main__":
    _setup_logging()
    logger.info(messages.SUPERVISOR_START)
    sys.exit(supervise([sys.executable, "-m", "backend"]))
