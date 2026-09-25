"""Siklus hidup layanan: dinyalakan saat server mulai, dimatikan saat berhenti.

Mengimpor modul `backend` mana pun kini tidak menyentuh disk, GPU, speaker,
atau port serial. Semua itu terjadi di sini, dalam urutan yang disengaja,
supaya pengujian dan alat bantu bisa memakai modul-modulnya tanpa perangkat
keras lengkap.
"""
import logging
import threading

from .config import cfg
from .logging_setup import setup_logging
from .storage import prepare_data_dir
from . import ppe_rules
from .report_manager import report_mgr
from .audio_engine import audio_player
from .notifier import notifier
from .detector import detector
from .vlm_analyzer import vlm_analyzer
from .video.capture import video_service

logger = logging.getLogger(__name__)

_cleanup_thread = None
_cleanup_stop = threading.Event()

def _retention_loop():
    while not _cleanup_stop.is_set():
        report_mgr.cleanup_old_data()
        _cleanup_stop.wait(86400)  # Cek setiap 24 jam



def start():
    # 1. Logging lebih dulu, supaya seluruh langkah berikutnya tercatat
    setup_logging(cfg)
    # 2. DATA_DIR siap dan data lama dipindah sebelum ada yang membaca berkasnya
    prepare_data_dir(cfg)
    # 3. Item APD aktif dimuat sebelum prompt VLM dirakit dari katalog
    ppe_rules.load_settings()
    report_mgr.open()
    audio_player.start()
    notifier.start()
    # 4. Model dimuat sebelum thread inferensi mulai meminta deteksi
    detector.load()
    vlm_analyzer.start()
    # 5. VLM dipanaskan sebelum video berjalan: gerbang baru menerima pekerja
    # setelah panggilan VLM pertama terbukti cepat
    vlm_analyzer.warm_up()
    video_service.start()
    
    global _cleanup_thread
    _cleanup_stop.clear()
    _cleanup_thread = threading.Thread(target=_retention_loop, name="RetentionCleanup", daemon=True)
    _cleanup_thread.start()
    
    logger.info("Seluruh layanan siap. Data: %s", cfg.DATA_DIR)


def stop():
    _cleanup_stop.set()
    video_service.stop()
    audio_player.stop()
    notifier.stop()
