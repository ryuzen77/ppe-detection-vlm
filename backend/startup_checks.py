"""Pemeriksaan kesehatan saat server menyala (T29).

Gerbang yang menyala sendiri setelah listrik padam tidak diawasi siapa pun saat
start, jadi kondisi yang diam-diam memperburuk pemeriksaan dicatat jelas di log
dan `/api/health`:
- YOLO jatuh ke CPU (CUDA tidak tersedia) -> frame sangat lambat;
- versi Ollama berbeda dari versi tempat model lokal divalidasi (06-10: Ollama
  sempat memperbarui diri sendiri; validasi & kecepatan tidak lagi terjamin);
- kamera yang harus dibuka otomatis belum terlihat sistem;
- belum ada akun (admin pertama dibuat dari mesin gerbang) atau ADMIN_TOKEN lama masih di .env (T51).

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


def check_backup(has_backup: bool) -> Optional[str]:
    """Tanpa cadangan (bawaan sejak T71) aman tetapi gerbang berhenti menerima pekerja
    saat VLM utama gangguan; admin perlu tahu sebelum itu terjadi."""
    return None if has_backup else messages.STARTUP_NO_BACKUP


def check_camera(target: str, visible: list[str]) -> Optional[str]:
    if not target or target in visible:
        return None
    return messages.STARTUP_CAMERA_MISSING.format(name=target, seen=", ".join(visible) or "-")


def check_legacy_admin_token(is_set: bool) -> Optional[str]:
    """T51: ADMIN_TOKEN tidak dipakai lagi; sisanya di .env menyesatkan pengelola."""
    return messages.STARTUP_ADMIN_TOKEN_UNUSED if is_set else None


def check_accounts(count: int) -> Optional[str]:
    return messages.STARTUP_NO_ACCOUNT.format(port=cfg.PORT) if count == 0 else None


def account_created():
    """Setup admin pertama berhasil: peringatan "belum ada akun" tidak berlaku lagi."""
    stale = check_accounts(0)
    warnings[:] = [w for w in warnings if w != stale]


def ollama_version(base_url: str, get: Optional[Callable] = None) -> Optional[str]:
    """Versi server Ollama lewat /api/version; None bila tidak terjangkau."""
    import httpx
    root = base_url[:-3] if base_url.rstrip("/").endswith("/v1") else base_url.rstrip("/")
    try:
        response = (get or httpx.get)(f"{root}/api/version", timeout=cfg.STARTUP_CHECK_TIMEOUT_SECONDS)
        return response.json().get("version")
    except Exception:
        return None


def run(cuda_available: bool, ollama_base_url: Optional[str], camera_target: str,
        visible_cameras: Callable[[], list[str]], has_backup: bool = True) -> list[str]:
    """Menjalankan semua pemeriksaan; hasilnya disimpan di `warnings` & dicatat di log."""
    from .accounts import store
    results = [check_cuda(cuda_available), check_legacy_admin_token(cfg.LEGACY_ADMIN_TOKEN_SET),
               check_accounts(store.count()), check_backup(has_backup)]
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
