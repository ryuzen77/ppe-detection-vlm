"""Siklus hidup layanan: dinyalakan saat server mulai, dimatikan saat berhenti.

Mengimpor modul `backend` mana pun kini tidak menyentuh disk, GPU, speaker,
atau port serial. Semua itu terjadi di sini, dalam urutan yang disengaja,
supaya pengujian dan alat bantu bisa memakai modul-modulnya tanpa perangkat
keras lengkap.
"""
import logging
import threading

from . import messages
from .config import cfg
from .uptime import uptime_monitor
from .zone import zone_store
from .logging_setup import prune_rotated_logs, setup_logging
from .disk_guard import disk_guard
from .storage import prepare_data_dir
from . import ppe_rules
from .report_manager import SECONDS_PER_DAY, report_mgr
from .audio_engine import audio_player
from .notifier import notifier
from .detector import detector
from .vlm_analyzer import vlm_analyzer
from .video.capture import video_service

logger = logging.getLogger(__name__)

SECONDS_PER_HOUR = 60 * 60

_cleanup_thread = None
_cleanup_stop = threading.Event()

def _prune_logs():
    """Salinan log lama dihapus menurut umur (T53), di siklus yang sama dengan retensi audit."""
    removed = prune_rotated_logs(cfg.LOG_DIR, {
        cfg.LOG_FILE: cfg.LOG_RETENTION_DAYS * SECONDS_PER_DAY,
        cfg.SUPERVISOR_LOG_FILE: cfg.LOG_RETENTION_DAYS * SECONDS_PER_DAY,
        cfg.SECURITY_LOG_FILE: cfg.SECURITY_LOG_RETENTION_DAYS * SECONDS_PER_DAY,
    })
    if removed:
        logger.info(messages.LOG_PRUNED.format(count=removed, path=cfg.LOG_DIR))


def _retention_loop():
    while not _cleanup_stop.is_set():
        report_mgr.cleanup_old_data()
        _prune_logs()
        if cfg.RETENTION_INTERVAL_HOURS <= 0:
            break
        _cleanup_stop.wait(cfg.RETENTION_INTERVAL_HOURS * SECONDS_PER_HOUR)



def _run_startup_checks():
    """Peringatan kesehatan saat menyala (T29); tidak pernah menghentikan server."""
    import torch
    from . import camera_manager, startup_checks
    local = vlm_analyzer._local_engine()
    ollama_url = (getattr(local.provider, "base_url", None) if local is not None and local.provider_name == "ollama"
                  and local.provider is not None else None)
    camera = camera_manager.autostart_target()[0] if cfg.CAMERA_AUTOSTART else ""
    startup_checks.run(torch.cuda.is_available(), ollama_url, camera, camera_manager.list_device_names)


def start():
    # 1. Logging lebih dulu, supaya seluruh langkah berikutnya tercatat
    setup_logging(cfg)
    # 2. DATA_DIR siap dan data lama dipindah sebelum ada yang membaca berkasnya
    prepare_data_dir(cfg)
    # Sisa disk diawasi sejak awal: log & audit sama-sama butuh ruang (T53)
    disk_guard.start()
    # Catat lama gerbang tidak aktif & apakah berhenti rapi sebelumnya (T37)
    uptime_monitor.start()
    # 3. Item APD aktif dimuat sebelum prompt VLM dirakit dari katalog
    ppe_rules.load_settings()
    zone_store.load()
    report_mgr.open()
    audio_player.start()
    notifier.start()
    # 4. Model dimuat sebelum thread inferensi mulai meminta deteksi
    detector.load()
    vlm_analyzer.start()
    # 5. VLM dipanaskan sebelum video berjalan: gerbang baru menerima pekerja
    # setelah panggilan VLM pertama terbukti cepat
    vlm_analyzer.warm_up()
    vlm_analyzer.local_guard.start()
    _run_startup_checks()
    video_service.start()
    
    global _cleanup_thread
    _cleanup_stop.clear()
    _cleanup_thread = threading.Thread(target=_retention_loop, name="RetentionCleanup", daemon=True)
    _cleanup_thread.start()
    
    logger.info("Seluruh layanan siap. Data: %s", cfg.DATA_DIR)


def stop():
    _cleanup_stop.set()
    disk_guard.stop()
    uptime_monitor.stop()
    vlm_analyzer.local_guard.stop()
    video_service.stop()
    audio_player.stop()
    notifier.stop()
