"""Pemeriksaan kesehatan saat server menyala (T29).

Gerbang yang menyala sendiri setelah listrik padam tidak diawasi siapa pun saat
start, jadi kondisi yang diam-diam memperburuk pemeriksaan dicatat jelas di log
dan `/api/health`:
- YOLO jatuh ke CPU (CUDA tidak tersedia) -> frame sangat lambat;
- versi Ollama berbeda dari versi tempat model lokal divalidasi (06-10: Ollama
  sempat memperbarui diri sendiri; validasi & kecepatan tidak lagi terjamin);
- kamera yang harus dibuka otomatis belum terlihat sistem.

Tidak ada yang menghentikan server: gerbang tetap berjalan, peringatan saja.
"""
import logging
from typing import Callable, Optional

from . import messages
from .config import cfg

logger = logging.getLogger(__name__)

warnings: list[str] = []


def check_cuda(cuda_available: bool) -> Optional[str]:
    return None if cuda_available else messages.STARTUP_NO_CUDA


def check_ollama_version(version: Optional[str]) -> Optional[str]:
    if version is None:
        return messages.STARTUP_OLLAMA_UNREACHABLE
    if cfg.OLLAMA_VALIDATED_VERSION and version != cfg.OLLAMA_VALIDATED_VERSION:
        return messages.STARTUP_OLLAMA_VERSION.format(found=version, expected=cfg.OLLAMA_VALIDATED_VERSION)
    return None


def check_camera(target: str, visible: list[str]) -> Optional[str]:
    if not target or target in visible:
        return None
    return messages.STARTUP_CAMERA_MISSING.format(name=target, seen=", ".join(visible) or "-")


def ollama_version(base_url: str, get: Callable = None) -> Optional[str]:
    """Versi server Ollama lewat /api/version; None bila tidak terjangkau."""
    import httpx
    root = base_url[:-3] if base_url.rstrip("/").endswith("/v1") else base_url.rstrip("/")
    try:
        response = (get or httpx.get)(f"{root}/api/version", timeout=cfg.STARTUP_CHECK_TIMEOUT_SECONDS)
        return response.json().get("version")
    except Exception:
        return None


def run(cuda_available: bool, ollama_base_url: Optional[str], camera_target: str,
        visible_cameras: Callable[[], list[str]]) -> list[str]:
    """Menjalankan semua pemeriksaan; hasilnya disimpan di `warnings` & dicatat di log."""
    results = [check_cuda(cuda_available)]
    if ollama_base_url:
        results.append(check_ollama_version(ollama_version(ollama_base_url)))
    if camera_target:
        results.append(check_camera(camera_target, visible_cameras()))
    warnings[:] = [r for r in results if r]
    for w in warnings:
        logger.warning(w)
    if not warnings:
        logger.info(messages.STARTUP_ALL_OK)
    return list(warnings)
