"""Manajemen log (T53): asinkron, berbatas, diringkas, dan penjaga disk.

Log yang tidak dikelola bisa menghentikan gerbang (disk penuh, disk lambat menahan
thread kamera/VLM, banjir galat per frame). Tes ini membuktikan tiap pengaman.
"""

import json
import logging
import os
import queue
import time
from types import SimpleNamespace

import pytest

from backend import disk_guard, logging_setup, messages, security_log
from backend.config import cfg

GB = disk_guard.BYTES_PER_GB


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def make_record(text: str, level: int = logging.WARNING, name: str = "backend.uji") -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, text, None, None)


@pytest.fixture
def log_cfg(tmp_path):
    return SimpleNamespace(
        LOG_LEVEL="INFO",
        LOG_TO_FILE=True,
        LOG_DIR=tmp_path / "logs",
        LOG_FILE="app.log",
        SECURITY_LOG_FILE="security.jsonl",
        LOG_MAX_BYTES=1_000_000,
        LOG_BACKUP_COUNT=2,
        LOG_QUEUE_SIZE=1_000,
        LOG_REPEAT_WINDOW_SECONDS=60,
        LOG_REPEAT_MAX_KEYS=100,
        LOG_ACCESS_LEVEL="WARNING",
    )


@pytest.fixture
def configured(log_cfg):
    """setup_logging sungguhan ke folder sementara; dipulihkan setelah tes."""
    root = logging.getLogger()
    security = logging.getLogger(logging_setup.SECURITY_LOGGER)
    saved = (root.level, security.level, security.propagate, logging.getLogger(logging_setup.ACCESS_LOGGER).level)
    logging_setup.setup_logging(log_cfg)
    yield log_cfg
    logging_setup.stop_logging()
    root.setLevel(saved[0])
    security.setLevel(saved[1])
    security.propagate = saved[2]
    logging.getLogger(logging_setup.ACCESS_LOGGER).setLevel(saved[3])


def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


# --- Pesan berulang ---------------------------------------------------------------------


def test_pesan_sama_diringkas_per_jendela():
    clock = Clock()
    f = logging_setup.RepeatFilter(window_seconds=60, max_keys=100, clock=clock)
    assert f.filter(make_record("kamera hilang"))
    assert [f.filter(make_record("kamera hilang")) for _ in range(500)] == [False] * 500
    assert f.filter(make_record("pesan lain")), "pesan berbeda tidak ikut ditahan"
    assert f.filter(make_record("kamera hilang", level=logging.ERROR)), "level berbeda = pesan berbeda"
    clock.now += 60
    record = make_record("kamera hilang")
    assert f.filter(record)
    assert record.getMessage() == messages.LOG_REPEATED.format(message="kamera hilang", count=500, seconds=60)


def test_kunci_pesan_dibatasi_supaya_memori_tidak_tumbuh():
    clock = Clock()
    f = logging_setup.RepeatFilter(window_seconds=60, max_keys=50, clock=clock)
    for i in range(1_000):
        f.filter(make_record(f"galat #{i}"))
    assert len(f._seen) <= 50


# --- Antrean: pemanggil tidak pernah menunggu disk ------------------------------------------


def test_antrean_penuh_membuang_tanpa_galat(capsys):
    handler = logging_setup.DroppingQueueHandler(queue.Queue(maxsize=3))
    for i in range(10):
        handler.handle(make_record(f"m{i}"))
    assert handler.dropped == 7
    assert "Traceback" not in capsys.readouterr().err, "QueueHandler bawaan mencetak traceback per catatan"


def test_disk_lambat_tidak_menahan_pemanggil(configured):
    class SlowHandler(logging.Handler):
        def emit(self, record):
            time.sleep(0.02)

    listener_handlers = logging_setup._listeners[0].handlers
    logging_setup._listeners[0].handlers = (*listener_handlers, SlowHandler())
    started = time.perf_counter()
    for i in range(100):
        logging.getLogger("backend.uji").warning("baris %d", i)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5, (
        f"100 log dengan disk 20 ms/baris (2 dtk bila sinkron) harus tetap instan, butuh {elapsed:.2f} dtk"
    )


def test_berhenti_saat_antrean_penuh_tidak_galat(configured, log_cfg):
    """Regresi: QueueListener bawaan melempar queue.Full di stop() saat banjir log."""
    logging_setup.stop_logging()
    log_cfg.LOG_QUEUE_SIZE, log_cfg.LOG_REPEAT_WINDOW_SECONDS = 5, 0
    logging_setup.setup_logging(log_cfg)
    for i in range(200):
        logging.getLogger("backend.uji").warning("banjir %d", i)
    logging_setup.stop_logging()  # tidak boleh melempar queue.Full
    assert logging_setup.take_dropped() == 0, "penghitung ikut dibersihkan saat berhenti"


def test_jumlah_dibuang_dilaporkan_lalu_direset(monkeypatch):
    handler = logging_setup.DroppingQueueHandler(queue.Queue(maxsize=1))
    monkeypatch.setattr(logging_setup, "_queue_handlers", [handler])
    for i in range(4):
        handler.handle(make_record(f"m{i}"))
    assert logging_setup.take_dropped() == 3
    assert logging_setup.take_dropped() == 0


# --- Application log vs security log ---------------------------------------------------------


def test_application_dan_security_log_terpisah(configured):
    logging.getLogger("backend.uji").warning("kamera tersambung lagi")
    security_log.record("login", username="admin-uji", client="10.0.0.5", ok=True)
    logging_setup.stop_logging()  # kosongkan antrean ke berkas
    app_text = read(configured.LOG_DIR / configured.LOG_FILE)
    security_lines = read(configured.LOG_DIR / configured.SECURITY_LOG_FILE).splitlines()
    assert "kamera tersambung lagi" in app_text and "admin-uji" not in app_text
    assert len(security_lines) == 1
    entry = json.loads(security_lines[0])
    assert entry["event"] == "login" and entry["username"] == "admin-uji" and entry["ok"] is True
    assert len(entry["time"]) == len("2026-10-08T00:20:02"), "waktu lokal tanpa zona, seperti audit"


def test_security_log_tidak_diringkas(configured):
    for _ in range(5):
        security_log.record("login", username="admin-uji", client="10.0.0.5", ok=False)
    logging_setup.stop_logging()
    assert len(read(configured.LOG_DIR / configured.SECURITY_LOG_FILE).splitlines()) == 5


def test_log_akses_rutin_tidak_masuk_berkas(configured):
    logging.getLogger(logging_setup.ACCESS_LOGGER).info('127.0.0.1 - "GET /api/cameras HTTP/1.1" 200')
    logging.getLogger(logging_setup.ACCESS_LOGGER).warning("akses bermasalah")
    logging_setup.stop_logging()
    text = read(configured.LOG_DIR / configured.LOG_FILE)
    assert "/api/cameras" not in text and "akses bermasalah" in text


def test_uvicorn_tidak_menimpa_level_log_akses(monkeypatch):
    """Temuan smoke 08-10: uvicorn.Config menyetel uvicorn.access ke LOG_LEVEL (INFO)
    setelah setup_logging, sehingga log akses rutin tetap memenuhi berkas."""
    from backend import app as app_module

    access = logging.getLogger(logging_setup.ACCESS_LOGGER)
    monkeypatch.setattr(access, "level", access.level)  # dipulihkan setelah tes
    monkeypatch.setattr(cfg, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(cfg, "LOG_ACCESS_LEVEL", "WARNING")
    app_module.server_config()
    assert access.level == logging.WARNING


def test_setup_idempoten(configured):
    handlers = list(logging.getLogger().handlers)
    logging_setup.setup_logging(configured)
    assert logging.getLogger().handlers == handlers


def test_level_berkas_naik_saat_disk_menipis(configured):
    logging_setup.set_file_level(logging.WARNING)
    logging.getLogger("backend.uji").info("info biasa")
    logging.getLogger("backend.uji").warning("peringatan penting")
    logging_setup.stop_logging()
    text = read(configured.LOG_DIR / configured.LOG_FILE)
    assert "info biasa" not in text and "peringatan penting" in text


# --- Batas ukuran & umur -----------------------------------------------------------------------


def test_berkas_log_berbatas_ukuran(configured, log_cfg):
    logging_setup.stop_logging()
    log_cfg.LOG_MAX_BYTES, log_cfg.LOG_REPEAT_WINDOW_SECONDS = 2_000, 0
    logging_setup.setup_logging(log_cfg)
    for i in range(2_000):
        logging.getLogger("backend.uji").warning("baris panjang nomor %05d %s", i, "x" * 40)
    logging_setup.stop_logging()
    files = list(log_cfg.LOG_DIR.glob(f"{log_cfg.LOG_FILE}*"))
    assert len(files) == log_cfg.LOG_BACKUP_COUNT + 1
    assert sum(f.stat().st_size for f in files) <= (log_cfg.LOG_BACKUP_COUNT + 1) * (log_cfg.LOG_MAX_BYTES + 200)


def test_salinan_lama_dihapus_menurut_umur(tmp_path):
    now = 1_000_000_000.0
    day = 86_400
    for name, age_days in (
        ("app.log", 100),
        ("app.log.1", 2),
        ("app.log.2", 40),
        ("app.log.lock", 400),
        ("security.jsonl.1", 40),
        ("security.jsonl.2", 100),
    ):
        path = tmp_path / name
        path.write_text("x", encoding="utf-8")
        os.utime(path, (now - age_days * day, now - age_days * day))
    removed = logging_setup.prune_rotated_logs(tmp_path, {"app.log": 30 * day, "security.jsonl": 90 * day}, now=now)
    assert removed == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app.log", "app.log.1", "app.log.lock", "security.jsonl.1"]
    assert logging_setup.prune_rotated_logs(tmp_path, {"app.log": 0}, now=now) == 0, "0 = tanpa batas umur"


def test_supervisor_log_berotasi(monkeypatch, tmp_path):
    from logging.handlers import RotatingFileHandler

    from backend import supervisor

    captured = {}
    monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: captured.update(kw))
    supervisor._setup_logging()
    files = [h for h in captured["handlers"] if isinstance(h, logging.FileHandler)]
    assert files and all(isinstance(h, RotatingFileHandler) and h.maxBytes == cfg.LOG_MAX_BYTES for h in files)
    for h in files:
        h.close()


# --- Penjaga disk ------------------------------------------------------------------------------


@pytest.mark.parametrize("free_gb,state", [(50, "ok"), (5, "ok"), (4.9, "low"), (1, "low"), (0.5, "critical")])
def test_keadaan_disk(free_gb, state):
    assert disk_guard.disk_state(free_gb, warn_gb=5, critical_gb=1) == state


def test_penjaga_disk_mengatur_log_berkas(monkeypatch, caplog):
    free = {"gb": 50.0}
    levels = []
    monkeypatch.setattr(cfg, "DISK_WARN_FREE_GB", 5.0)
    monkeypatch.setattr(cfg, "DISK_CRITICAL_FREE_GB", 1.0)
    monkeypatch.setattr(logging_setup, "set_file_level", levels.append)
    guard = disk_guard.DiskGuard(free_bytes=lambda _path: int(free["gb"] * GB))
    with caplog.at_level(logging.WARNING, logger="backend.disk_guard"):
        guard.check()
        assert guard.status() == {"state": "ok", "free_gb": 50.0} and levels == []
        free["gb"] = 3.0
        guard.check()
        guard.check()  # keadaan sama: tidak dicatat ulang
        free["gb"] = 0.4
        guard.check()
        free["gb"] = 20.0
        guard.check()
    assert levels == [logging.WARNING, logging.CRITICAL, logging.NOTSET]
    texts = [r.getMessage() for r in caplog.records]
    assert texts == [
        messages.DISK_LOW.format(free_gb=3.0, limit_gb=5.0),
        messages.DISK_CRITICAL.format(free_gb=0.4, limit_gb=1.0),
        messages.DISK_OK.format(free_gb=20.0),
    ]
    assert [r.levelno for r in caplog.records] == [logging.WARNING, logging.CRITICAL, logging.WARNING]


def test_pesan_disk_kritis_tetap_tertulis_walau_log_berkas_dihentikan(configured, monkeypatch):
    monkeypatch.setattr(cfg, "DISK_CRITICAL_FREE_GB", 1.0)
    guard = disk_guard.DiskGuard(free_bytes=lambda _path: int(0.2 * GB))
    guard.check()
    logging.getLogger("backend.uji").error("galat biasa saat disk kritis")
    logging_setup.stop_logging()
    text = read(configured.LOG_DIR / configured.LOG_FILE)
    assert messages.DISK_CRITICAL.format(free_gb=0.2, limit_gb=1.0) in text and "galat biasa" not in text


def test_disk_tidak_terbaca_tidak_menghentikan_penjaga(caplog):
    def broken(_path):
        raise OSError("perangkat tidak siap")

    guard = disk_guard.DiskGuard(free_bytes=broken)
    with caplog.at_level(logging.WARNING, logger="backend.disk_guard"):
        guard.check()
    assert guard.status() == {"state": "ok", "free_gb": None} and "perangkat tidak siap" in caplog.text


def test_health_memuat_status_disk():
    from fastapi.testclient import TestClient

    from backend.app import app

    body = TestClient(app).get("/api/health").json()
    assert body["disk"].keys() == {"state", "free_gb"}


def test_perintah_terminal_tercatat_di_security_log(security_events, monkeypatch, tmp_path):
    from backend import accounts

    monkeypatch.setattr(accounts, "store", accounts.AccountStore(tmp_path / "accounts.db"))
    monkeypatch.setattr(cfg, "PASSWORD_SCRYPT_N", 2**4)
    monkeypatch.setattr(accounts, "_ask_password", lambda _name: "kata-sandi-uji-panjang")
    assert accounts.main(["create", "admin-uji"]) == 0
    assert [(e["event"], e["actor"]) for e in security_events] == [("create", "terminal")]
    assert "kata-sandi-uji-panjang" not in json.dumps(security_events)
