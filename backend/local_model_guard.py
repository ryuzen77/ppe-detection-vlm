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
import time
from typing import Callable, Optional

from . import gpu_processes, messages
from .config import cfg
from .internet_monitor import NORMAL, SLOW, DISCONNECTED

logger = logging.getLogger(__name__)


STATE_OK = "ok"
STATE_SLOW = "slow"
STATE_PARTIAL_GPU = "partial_gpu"
STATE_UNKNOWN = "unknown"
UNLOADED, LOADING, READY, FAILED = "unloaded", "loading", "ready", "failed"


class LocalStandby:
    """Satu operasi model; muat dingin tidak menahan inspeksi lewat API."""

    def __init__(self, inspection_lock, on_change=None, clock=time.monotonic):
        self._inspection_lock, self._on_change, self._clock = inspection_lock, on_change, clock
        self._lock = threading.Lock()
        self.model_lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = self._loader = None
        self.engine = None
        self.state, self.since = UNLOADED, time.strftime(cfg.TELEMETRY_TIME_FORMAT)
        self._wanted = self._primary_ok = False
        self._internet = None
        self._healthy_since = None
        self._retry_at = 0.0

    def status(self) -> dict:
        with self._lock:
            return {"role": self.engine.role if self.engine is not None else None,
                    "state": self.state, "since": self.since}

    def owns(self, engine) -> bool:
        with self._lock:
            return engine is not None and engine is self.engine

    def ready(self, engine) -> bool:
        with self._lock:
            return self.engine is not engine or self.state == READY

    def configure(self, engine):
        with self._lock:
            if self.engine is engine:
                return
            self.engine = engine
            self._wanted = self._primary_ok = False
            self._healthy_since = None
            self._retry_at = 0.0
            self._set_state(UNLOADED)
        self._publish()

    def _set_state(self, state):
        self.state, self.since = state, time.strftime(cfg.TELEMETRY_TIME_FORMAT)

    def _publish(self):
        status = self.status()
        logger.info(messages.LOG_LOCAL_STANDBY_STATE.format(**status))
        if self._on_change is not None:
            self._on_change(status)

    def internet_changed(self, state):
        with self._lock:
            self._internet = state
            self._update_health()
        if state in (SLOW, DISCONNECTED):
            self.request()

    def primary_result(self, ok: bool):
        with self._lock:
            self._primary_ok = ok
            self._update_health()

    def _update_health(self):
        if self._internet != NORMAL or not self._primary_ok:
            self._healthy_since = None
        elif self._healthy_since is None:
            self._healthy_since = self._clock()

    def request(self) -> bool:
        with self._lock:
            if self.engine is None or self._stop.is_set():
                return False
            self._wanted = True
            if (self.state in (LOADING, READY) or self._clock() < self._retry_at
                    or getattr(self.engine, "warm_pending", False)):
                return False
            self._set_state(LOADING)
            self._loader = threading.Thread(target=self._load, args=(self.engine,), name="LocalStandbyLoad", daemon=True)
            self._loader.start()
        self._publish()
        return True

    def _load(self, engine):
        with self.model_lock:
            if self._stop.is_set() or engine is None or self.engine is not engine:
                return
            try:
                ready = engine.warm_up() is not None
            except Exception:
                ready = False
            if self._stop.is_set():
                if ready:
                    try:
                        with self._inspection_lock:
                            engine.provider.unload()
                    except Exception:
                        logger.warning(messages.VLM_LOCAL_UNLOAD_FAILED)
                with self._lock:
                    self._set_state(UNLOADED)
                return
            with self._lock:
                self._set_state(READY if ready else FAILED)
                self._retry_at = self._clock() + cfg.VLM_LOCAL_RETRY_SECONDS if not ready else 0.0
            if not ready:
                logger.warning(messages.LOG_LOCAL_STANDBY_FAILED.format(error=engine.warm_error))
        self._publish()

    def preload(self):
        with self._lock:
            engine = self.engine
            if engine is None or self.state != UNLOADED:
                return
            self._wanted = True
            self._set_state(LOADING)
        self._publish()
        self._load(engine)

    def tick(self):
        with self._lock:
            retry = self.state == FAILED and self._wanted and self._clock() >= self._retry_at
            retire = (self.state == READY and self._healthy_since is not None
                      and self._clock() - self._healthy_since >= cfg.VLM_LOCAL_IDLE_UNLOAD_SECONDS)
        if retry:
            self.request()
        if retire:
            self._retire()

    def _retire(self):
        with self.model_lock, self._inspection_lock:
            with self._lock:
                if (self.state != READY or self.engine is None or self._healthy_since is None
                        or self._clock() - self._healthy_since < cfg.VLM_LOCAL_IDLE_UNLOAD_SECONDS):
                    return
                engine = self.engine
            try:
                engine.provider.unload()
            except Exception:
                logger.warning(messages.VLM_LOCAL_UNLOAD_FAILED)
                return
            with self._lock:
                reload_required = self._internet in (SLOW, DISCONNECTED)
                self._wanted = False
                self._set_state(UNLOADED)
        self._publish()
        if reload_required:
            self.request()

    def ensure_cold(self):
        threading.Thread(target=self._clear_resident, name="LocalStandbyClear", daemon=True).start()

    def _clear_resident(self):
        with self.model_lock, self._inspection_lock:
            with self._lock:
                engine = self.engine if self.state == UNLOADED and not self._wanted else None
            if engine is not None and engine.provider is not None:
                try:
                    if engine.provider.gpu_residency():
                        engine.provider.unload()
                except Exception:
                    pass  # Ollama yang belum berjalan tidak menghalangi siaga dingin.

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="LocalStandby", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.wait(cfg.VLM_LOCAL_STANDBY_POLL_SECONDS):
            self.tick()

    def stop(self):
        self._stop.set()
        for thread in (self._thread, self._loader):
            if thread is not None:
                thread.join(timeout=cfg.THREAD_STOP_TIMEOUT_SECONDS)


class LocalModelGuard:
    def __init__(self, inspection_lock: threading.Lock, engine_getter: Callable[[], Optional[object]],
                 on_start=None, on_stop=None):
        """`engine_getter` mengembalikan VLMEngine lokal yang dijaga (atau None)."""
        self._inspection_lock = inspection_lock
        self._engine_getter = engine_getter
        self._on_start, self._on_stop = on_start, on_stop
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
                if getattr(self._engine_getter(), "provider", None) is not provider:
                    return None
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
        if self._on_start is not None:
            self._on_start()

    def _loop(self):
        while not self._stop.wait(cfg.LOCAL_GPU_CHECK_SECONDS):
            self.other_gpu_apps = gpu_processes.other_gpu_apps()
            self.check_and_repair()

    def stop(self):
        self._stop.set()
        if self._on_stop is not None:
            self._on_stop()
