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

from . import gpu_processes, messages
from .config import cfg

logger = logging.getLogger(__name__)


STATE_OK = "ok"
STATE_SLOW = "slow"
STATE_PARTIAL_GPU = "partial_gpu"
STATE_UNKNOWN = "unknown"


class LocalModelGuard:
    def __init__(self, inspection_lock: threading.Lock, engine_getter: Callable[[], Optional[object]]):
        """`engine_getter` mengembalikan VLMEngine lokal yang dijaga (atau None)."""
        self._inspection_lock = inspection_lock
        self._engine_getter = engine_getter
        self._busy = threading.Lock()          # satu pemeriksaan/perbaikan pada satu waktu
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Kesehatan untuk /api/health (T56)
        self._state_lock = threading.Lock()
        self.gpu_ratio: Optional[float] = None
        self.slow_streak = 0
        self.last_latency_s: Optional[float] = None
        self.other_gpu_apps: list[str] = []
        self._last_slow_reload = float("-inf")

    # --- Pemeriksaan -------------------------------------------------------------------

    def check_and_repair(self, force: bool = False) -> Optional[bool]:
        """True = model sudah/kini penuh di GPU; False = gagal dipulihkan;
        None = tidak ada yang diperiksa (bukan model lokal, sedang diperiksa, atau gerbang sibuk).
        `force` = muat ulang walau porsi GPU penuh (gejala lambat, T56)."""
        engine = self._engine_getter()
        provider = getattr(engine, "provider", None) if engine is not None else None
        if provider is None or not self._busy.acquire(blocking=False):
            return None
        try:
            ratio = self.gpu_ratio = provider.gpu_residency()
            if ratio is None or (ratio >= cfg.LOCAL_MIN_GPU_RATIO and not force):
                return None if ratio is None else True
            # Tunggu jeda antar-inspeksi; jangan memuat ulang di tengah pemeriksaan
            if not self._inspection_lock.acquire(timeout=cfg.LOCAL_GPU_REPAIR_WAIT_SECONDS):
                return None
            try:
                return self._reload(engine, provider, ratio, force)
            finally:
                self._inspection_lock.release()
        except Exception as e:
            logger.warning(messages.LOCAL_MODEL_CHECK_FAILED.format(error=str(e)[:160]))
            return False
        finally:
            self._busy.release()

    def _reload(self, engine, provider, ratio: float, force: bool) -> bool:
        if not force:
            logger.warning(messages.LOCAL_MODEL_PARTIAL_GPU.format(who=engine.who, pct=round(ratio * 100)))
        provider.reload()
        # Model yang baru dimuat "dingin": panaskan dengan gambar sebelum pekerja berikutnya (T56)
        warm = getattr(engine, "warm_up", None)
        if warm is not None:
            warm()
        after = self.gpu_ratio = provider.gpu_residency()
        ok = after is not None and after >= cfg.LOCAL_MIN_GPU_RATIO
        pct = "?" if after is None else round(after * 100)
        if ok:
            logger.info(messages.LOCAL_MODEL_RELOADED.format(who=engine.who, pct=pct))
        else:
            logger.error(messages.LOCAL_MODEL_RELOAD_FAILED.format(who=engine.who, pct=pct))
        return ok

    def trigger(self, force: bool = False):
        """Periksa di latar (mis. setelah VLM cadangan gagal); tidak menahan inspeksi."""
        threading.Thread(target=self.check_and_repair, kwargs={"force": force},
                         name="LocalModelCheck", daemon=True).start()

    # --- Gejala & status (T56) ---------------------------------------------------------

    def record_call(self, latency_s: Optional[float], now: float):
        """Satu panggilan VLM lokal selesai (`latency_s`) atau gagal/habis waktu (None)."""
        slow = latency_s is None or latency_s > cfg.LOCAL_SLOW_SECONDS
        with self._state_lock:
            self.last_latency_s = None if latency_s is None else round(latency_s, 2)
            self.slow_streak = self.slow_streak + 1 if slow else 0
            streak = self.slow_streak
            due = (streak >= cfg.LOCAL_SLOW_STREAK
                   and now - self._last_slow_reload >= cfg.LOCAL_SLOW_RELOAD_COOLDOWN_SECONDS)
            if due:
                self._last_slow_reload = now
        if due:
            self._warn_slow(streak, latency_s)
            self.trigger(force=True)

    def _warn_slow(self, streak: int, latency_s: Optional[float]):
        engine = self._engine_getter()
        self.other_gpu_apps = gpu_processes.other_gpu_apps()
        latency = messages.LOCAL_LATENCY_TIMEOUT if latency_s is None else f"{latency_s:.1f} dtk"
        logger.warning(messages.LOCAL_MODEL_SLOW.format(
            who=getattr(engine, "who", "lokal"), n=streak, latency=latency,
            apps=", ".join(self.other_gpu_apps) or "-"))

    def status(self) -> dict:
        """Kontrak `local_vlm` di GET /api/health (docs/RENCANA.md, Kontrak T56)."""
        with self._state_lock:
            return {"state": self._state(), "gpu_ratio": self.gpu_ratio, "slow_streak": self.slow_streak,
                    "last_latency_s": self.last_latency_s, "other_gpu_apps": list(self.other_gpu_apps)}

    def _state(self) -> str:
        if self._engine_getter() is None or (self.gpu_ratio is None and self.last_latency_s is None
                                             and self.slow_streak == 0):
            return STATE_UNKNOWN
        if self.gpu_ratio is not None and self.gpu_ratio < cfg.LOCAL_MIN_GPU_RATIO:
            return STATE_PARTIAL_GPU
        return STATE_SLOW if self.slow_streak >= cfg.LOCAL_SLOW_STREAK else STATE_OK

    # --- Pemeriksaan berkala -----------------------------------------------------------

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="LocalModelGuard", daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(cfg.LOCAL_GPU_CHECK_SECONDS):
            self.other_gpu_apps = gpu_processes.other_gpu_apps()
            self.check_and_repair()

    def stop(self):
        self._stop.set()
