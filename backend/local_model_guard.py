"""Penjaga model VLM lokal (T38): pastikan model tetap sepenuhnya di GPU.

Qwen2.5-VL di Ollama sesekali crash saat menyandikan gambar tertentu (masalah
hulu: ollama#14170, llama.cpp#17422). Ollama lalu memuat ulang model, dan kadang
pencarian GPU-nya habis waktu sehingga sebagian model jatuh ke CPU: tiap
inspeksi cadangan menjadi ~31 dtk (terukur 27-09) sampai model dimuat ulang.
Crash-nya tidak bisa diperbaiki dari sini; dampaknya bisa: porsi GPU diperiksa
setelah cadangan gagal dan berkala, lalu model dimuat ulang bila perlu.

Muat ulang dilakukan di latar dan hanya di antara inspeksi (memegang gembok
inspeksi VLM), supaya tidak memutus pekerja yang sedang diperiksa.
"""
import logging
import threading
from typing import Callable, Optional

from . import messages
from .config import cfg

logger = logging.getLogger(__name__)


class LocalModelGuard:
    def __init__(self, inspection_lock: threading.Lock, engine_getter: Callable[[], Optional[object]]):
        """`engine_getter` mengembalikan VLMEngine lokal yang dijaga (atau None)."""
        self._inspection_lock = inspection_lock
        self._engine_getter = engine_getter
        self._busy = threading.Lock()          # satu pemeriksaan/perbaikan pada satu waktu
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # --- Pemeriksaan -------------------------------------------------------------------

    def check_and_repair(self) -> Optional[bool]:
        """True = model sudah/kini penuh di GPU; False = gagal dipulihkan;
        None = tidak ada yang diperiksa (bukan model lokal, sedang diperiksa, atau gerbang sibuk)."""
        engine = self._engine_getter()
        provider = getattr(engine, "provider", None) if engine is not None else None
        if provider is None or not self._busy.acquire(blocking=False):
            return None
        try:
            ratio = provider.gpu_residency()
            if ratio is None or ratio >= cfg.LOCAL_MIN_GPU_RATIO:
                return None if ratio is None else True
            # Tunggu jeda antar-inspeksi; jangan memuat ulang di tengah pemeriksaan
            if not self._inspection_lock.acquire(timeout=cfg.LOCAL_GPU_REPAIR_WAIT_SECONDS):
                return None
            try:
                logger.warning(messages.LOCAL_MODEL_PARTIAL_GPU.format(who=engine.who, pct=round(ratio * 100)))
                provider.reload()
                after = provider.gpu_residency()
            finally:
                self._inspection_lock.release()
            ok = after is not None and after >= cfg.LOCAL_MIN_GPU_RATIO
            pct = "?" if after is None else round(after * 100)
            if ok:
                logger.info(messages.LOCAL_MODEL_RELOADED.format(who=engine.who, pct=pct))
            else:
                logger.error(messages.LOCAL_MODEL_RELOAD_FAILED.format(who=engine.who, pct=pct))
            return ok
        except Exception as e:
            logger.warning(messages.LOCAL_MODEL_CHECK_FAILED.format(error=str(e)[:160]))
            return False
        finally:
            self._busy.release()

    def trigger(self):
        """Periksa di latar (mis. setelah VLM cadangan gagal); tidak menahan inspeksi."""
        threading.Thread(target=self.check_and_repair, name="LocalModelCheck", daemon=True).start()

    # --- Pemeriksaan berkala -----------------------------------------------------------

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="LocalModelGuard", daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(cfg.LOCAL_GPU_CHECK_SECONDS):
            self.check_and_repair()

    def stop(self):
        self._stop.set()
