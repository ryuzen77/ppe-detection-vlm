"""Konfigurasi logging: konsol + berkas berotasi di DATA_DIR/logs.

Logger dipasang pada root supaya log uvicorn (permintaan HTTP, galat server)
ikut tercatat di berkas yang sama dengan log aplikasi. Setelah insiden di
lapangan, satu berkas ini cukup untuk menelusuri urutan kejadiannya.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"

# Pustaka pihak ketiga yang mencatat detail internal di level INFO
_QUIET_LIBRARIES = ("comtypes",)
_configured = False


def setup_logging(cfg):
    """Idempoten: pemanggilan kedua tidak menambah handler ganda."""
    global _configured
    if _configured:
        return
    _configured = True

    formatter = logging.Formatter(_FORMAT)
    root = logging.getLogger()
    root.setLevel(cfg.LOG_LEVEL)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    for name in _QUIET_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)

    if cfg.LOG_TO_FILE:
        try:
            cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                cfg.LOG_DIR / "safeguard.log",
                maxBytes=cfg.LOG_MAX_BYTES,
                backupCount=cfg.LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as e:
            # Berkas log yang tidak bisa dibuka tidak boleh menghentikan gerbang
            logging.getLogger(__name__).warning("Log berkas nonaktif, hanya konsol: %s", e)
