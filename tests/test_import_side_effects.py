"""Mengimpor aplikasi tidak boleh menyentuh disk, GPU, speaker, atau port serial (T16).

Dijalankan di proses terpisah supaya tidak terpengaruh modul yang sudah dimuat
oleh tes lain.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_PROBE = r"""
import json, sys
import backend.app  # seluruh aplikasi: router, layanan, singleton
import torch, pygame
from backend.detector import detector
from backend.notifier import notifier
from backend.audio_engine import audio_player
from backend.vlm_analyzer import vlm_analyzer
from backend.report_manager import report_mgr
from backend.video.capture import video_service
try:
    mixer_on = bool(pygame.mixer.get_init())
except NotImplementedError:
    # Modul mixer tidak tersedia (pustaka sistem audio tidak ada) = pasti belum aktif
    mixer_on = False
print(json.dumps({
    "cuda_initialized": torch.cuda.is_initialized(),
    "yolo_loaded": detector.model is not None,
    "mixer_initialized": mixer_on,
    "audio_thread": audio_player.worker is not None,
    "serial_open": notifier.link is not None and (notifier.link._conn is not None
                                                  or notifier.link._thread is not None),
    "vlm_provider": vlm_analyzer.provider is not None,
    "db_opened": report_mgr._opened,
    "video_running": video_service.is_running,
}))
"""


def test_impor_aplikasi_bebas_efek_samping(tmp_path):
    data_dir = tmp_path / "data_belum_ada"
    env = {
        **os.environ,
        "DATA_DIR": str(data_dir),
        "LOG_TO_FILE": "true",
        # Walau IoT serial dan API key diisi, impor tidak boleh membuka keduanya
        "IOT_ENABLED": "true",
        "IOT_TYPE": "serial",
        "IOT_SERIAL_PORT": "COM_TIDAK_ADA",
        "VLM_PROVIDER": "gemini",
        "VLM_API_KEY": "kunci-palsu",
        "PYGAME_HIDE_SUPPORT_PROMPT": "1",
    }
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=REPO_ROOT, env=env,
                         capture_output=True, text=True, timeout=180)
    assert out.returncode == 0, out.stderr[-2000:]
    state = json.loads(out.stdout.strip().splitlines()[-1])

    assert state == {k: False for k in state}, f"Efek samping saat impor: {state}"
    assert not data_dir.exists(), "DATA_DIR (log, basis data, pengaturan) tidak boleh dibuat saat impor"
