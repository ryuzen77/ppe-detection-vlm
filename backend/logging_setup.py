"""Logging (T53): application log & security log, asinkron dan berbatas.

- **Application log** (`LOG_FILE`): jalannya sistem. Logger dipasang di root supaya
  log uvicorn ikut tercatat di berkas yang sama; satu berkas cukup untuk menelusuri
  urutan kejadian setelah insiden.
- **Security log** (`SECURITY_LOG_FILE`, lewat `security_log.py`): logger terpisah
  (`propagate=False`) supaya tidak ikut diringkas, dihentikan saat disk kritis, atau
  tergusur rotasi application log.
- **Audit** inspeksi bukan di sini (SQLite + foto, retensi T20).

Log yang tidak dikelola bisa menghentikan gerbang, jadi:
- penulisan lewat antrean (`QueueHandler` → `QueueListener`): thread kamera/VLM dan
  event loop tidak pernah menunggu disk; antrean penuh = catatan dibuang & dihitung;
- pesan yang sama persis diringkas per jendela waktu (banjir galat per frame);
- tiap berkas berotasi menurut ukuran, salinan lama dihapus menurut umur (`prune_rotated_logs`);
- penjaga disk (`disk_guard.py`) menaikkan level log berkas lewat `set_file_level`.
"""
import atexit
import logging
import os
import queue
import sys
import threading
import time
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from typing import Callable, Optional

from . import messages

APP_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
SECURITY_LOGGER = "security"
ACCESS_LOGGER = "uvicorn.access"

# Pustaka pihak ketiga yang mencatat detail internal di level INFO
_QUIET_LIBRARIES = ("comtypes",)

_configured = False
_listeners: list[QueueListener] = []
_queue_handlers: list["DroppingQueueHandler"] = []
_app_file_handlers: list[logging.Handler] = []


class DroppingQueueHandler(QueueHandler):
    """Antrean penuh = catatan dibuang & dihitung; pemanggil tidak pernah menunggu.

    QueueHandler bawaan memanggil handleError (mencetak traceback ke stderr) untuk
    setiap catatan saat antrean penuh — justru menambah beban saat banjir log."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__(log_queue)
        self.dropped = 0

    def enqueue(self, record: logging.LogRecord):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1   # perkiraan cukup; tanpa kunci supaya tetap murah


class DrainingQueueListener(QueueListener):
    """QueueListener bawaan memasukkan penanda berhenti dengan `put_nowait`: saat
    antrean penuh (banjir log) `stop()` melempar queue.Full dan server gagal berhenti
    rapi. Di sini penanda menunggu tempat; listener sendiri yang mengosongkannya."""

    def enqueue_sentinel(self):
        self.queue.put(self._sentinel)


class RepeatFilter(logging.Filter):
    """Pesan yang sama persis (logger, level, teks) lolos sekali per jendela.

    Pengulangan berikutnya dalam jendela hanya dihitung; kemunculan pertama setelah
    jendela berakhir membawa jumlahnya ("terulang N kali"). Pengulangan terakhir yang
    tidak disusul pesan yang sama memang tidak dilaporkan (cukup untuk mencegah banjir)."""

    def __init__(self, window_seconds: float, max_keys: int, clock: Callable[[], float] = time.monotonic):
        super().__init__()
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._seen: dict[tuple, list] = {}   # kunci -> [waktu lolos terakhir, jumlah ditahan]
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        if self._window <= 0:
            return True
        text = record.getMessage()
        key = (record.name, record.levelno, text)
        now = self._clock()
        with self._lock:
            entry = self._seen.get(key)
            if entry is not None and now - entry[0] < self._window:
                entry[1] += 1
                return False
            held, since = (entry[1], now - entry[0]) if entry else (0, 0.0)
            self._seen[key] = [now, 0]
            if len(self._seen) > self._max_keys:
                self._forget_expired(now)
        if held:
            record.msg = messages.LOG_REPEATED.format(message=text, count=held, seconds=since)
            record.args = None
        return True

    def _forget_expired(self, now: float):
        for key in [k for k, (at, _) in self._seen.items() if now - at >= self._window]:
            del self._seen[key]
        if len(self._seen) > self._max_keys:   # semua masih baru: buang separuh tertua
            for key in sorted(self._seen, key=lambda k: self._seen[k][0])[: len(self._seen) // 2]:
                del self._seen[key]


class DurableRotatingFileHandler(RotatingFileHandler):
    """Untuk security log: tiap kejadian di-fsync. Kejadiannya jarang, dan fsync
    berjalan di thread listener, bukan di jalur permintaan HTTP."""

    def emit(self, record: logging.LogRecord):
        super().emit(record)
        if self.stream is not None:
            try:
                os.fsync(self.stream.fileno())
            except OSError:
                pass   # disk penuh / berkas dikunci: catatan sudah di-flush, jangan hentikan listener


def rotating_file(path: Path, formatter: logging.Formatter, cfg,
                  handler_class: type = RotatingFileHandler) -> Optional[logging.Handler]:
    """Berkas berotasi menurut ukuran; None (+ peringatan konsol) bila tidak bisa dibuka."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = handler_class(path, maxBytes=cfg.LOG_MAX_BYTES, backupCount=cfg.LOG_BACKUP_COUNT,
                                encoding="utf-8")
    except OSError as e:
        # Berkas log yang tidak bisa dibuka tidak boleh menghentikan gerbang
        print(messages.LOG_FILE_DISABLED.format(path=path, error=e), file=sys.stderr)
        return None
    handler.setFormatter(formatter)
    return handler


def _queued(handlers: list[logging.Handler], cfg, log_filter: Optional[logging.Filter]) -> DroppingQueueHandler:
    log_queue: queue.Queue = queue.Queue(maxsize=cfg.LOG_QUEUE_SIZE)
    queue_handler = DroppingQueueHandler(log_queue)
    if log_filter is not None:
        queue_handler.addFilter(log_filter)
    listener = DrainingQueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()
    _listeners.append(listener)
    _queue_handlers.append(queue_handler)
    return queue_handler


def _setup_application_log(cfg):
    formatter = logging.Formatter(APP_FORMAT)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    handlers: list[logging.Handler] = [console]
    if cfg.LOG_TO_FILE:
        app_file = rotating_file(cfg.LOG_DIR / cfg.LOG_FILE, formatter, cfg)
        if app_file is not None:
            handlers.append(app_file)
            _app_file_handlers.append(app_file)
    root = logging.getLogger()
    root.setLevel(cfg.LOG_LEVEL)
    root.addHandler(_queued(handlers, cfg, RepeatFilter(cfg.LOG_REPEAT_WINDOW_SECONDS, cfg.LOG_REPEAT_MAX_KEYS)))


def setup_security_log(cfg):
    """Juga dipakai sendiri oleh perintah terminal (python -m backend.accounts)."""
    security = logging.getLogger(SECURITY_LOGGER)
    security.propagate = False
    security.setLevel(logging.INFO)
    handler = rotating_file(cfg.LOG_DIR / cfg.SECURITY_LOG_FILE, logging.Formatter("%(message)s"), cfg,
                            DurableRotatingFileHandler)
    if handler is not None:
        security.addHandler(_queued([handler], cfg, None))


def setup_logging(cfg):
    """Idempoten: pemanggilan kedua tidak menambah handler ganda."""
    global _configured
    if _configured:
        return
    _configured = True
    _setup_application_log(cfg)
    setup_security_log(cfg)
    for name in _QUIET_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger(ACCESS_LOGGER).setLevel(cfg.LOG_ACCESS_LEVEL)
    atexit.register(stop_logging)


def stop_logging():
    """Kosongkan antrean ke berkas lalu lepas semua handler (berhenti rapi & tes)."""
    global _configured
    for listener in _listeners:
        listener.stop()
    for name in ("", SECURITY_LOGGER):
        logger = logging.getLogger(name)
        for handler in [h for h in logger.handlers if h in _queue_handlers]:
            logger.removeHandler(handler)
    for listener in _listeners:
        for handler in listener.handlers:
            handler.close()
    _listeners.clear()
    _queue_handlers.clear()
    _app_file_handlers.clear()
    _configured = False


def set_file_level(level: int):
    """Level minimum application log berkas (penjaga disk). Konsol & security log tidak berubah."""
    for handler in _app_file_handlers:
        handler.setLevel(level)


def take_dropped() -> int:
    """Jumlah catatan yang dibuang sejak panggilan terakhir (dilaporkan penjaga disk)."""
    total = 0
    for handler in _queue_handlers:
        total += handler.dropped
        handler.dropped = 0
    return total


def prune_rotated_logs(log_dir: Path, max_age_seconds: dict[str, float], now: Optional[float] = None) -> int:
    """Hapus salinan rotasi (`<berkas>.<n>`) yang lebih tua dari masa simpannya.

    Berkas aktif tidak pernah dihapus (masih dibuka handler). Umur <= 0 = tanpa batas umur."""
    now = time.time() if now is None else now
    removed = 0
    for name, max_age in max_age_seconds.items():
        if max_age <= 0:
            continue
        for path in log_dir.glob(f"{name}.*"):
            if not path.suffix[1:].isdigit():
                continue
            try:
                if now - path.stat().st_mtime >= max_age:
                    path.unlink()
                    removed += 1
            except OSError:
                pass   # sedang dibuka/dirotasi proses lain (Windows): dicoba lagi di siklus berikutnya
    return removed
