import time
import threading
from typing import Dict, Any
from collections import deque

from .config import cfg

class APIMonitor:
    """Monitors Gemini Cloud API health, tracks real-time round-trip latency,
    detects degradation/jamming (macet), and manages Online vs Offline engine modes."""

    def __init__(self):
        self.lock = threading.Lock()
        
        # Engine Mode: "HYBRID_AUTO" (Cloud + Auto Fallback) or "FORCE_LOCAL" (100% Offline GPU)
        self.engine_mode: str = "HYBRID_AUTO"

        # Status: "ONLINE", "DEGRADED", "OFFLINE"
        self.status: str = "INITIALIZING"
        self.latency_ms: float = 0.0
        self.latency_history: deque = deque(maxlen=cfg.API_LATENCY_HISTORY)
        self.avg_latency_ms: float = 0.0

        # Metrics
        self.total_cloud_calls: int = 0
        self.total_local_calls: int = 0
        self.total_timeouts: int = 0
        self.total_rate_limited: int = 0
        self.total_errors: int = 0
        self.consecutive_errors: int = 0

        self.last_checked_time: str = "-"
        self.last_error_message: str = ""
        self.is_locked: bool = False

    def set_engine_mode(self, mode: str) -> str:
        with self.lock:
            if mode in ["HYBRID_AUTO", "FORCE_LOCAL"]:
                self.engine_mode = mode
                if mode == "FORCE_LOCAL":
                    self.status = "OFFLINE_FORCED"
                return self.engine_mode
            return self.engine_mode

    def record_success(self, duration_ms: float):
        with self.lock:
            self.total_cloud_calls += 1
            self.consecutive_errors = 0
            self.latency_ms = round(duration_ms, 1)
            self.latency_history.append(self.latency_ms)
            self.avg_latency_ms = round(sum(self.latency_history) / len(self.latency_history), 1)
            self.last_checked_time = time.strftime("%H:%M:%S")
            self.last_error_message = ""

            # Classify condition: if latency > 1800ms, mark as DEGRADED (Macet / Lambat)
            if self.latency_ms > 1800.0:
                self.status = "DEGRADED"
            else:
                self.status = "ONLINE"

    def record_timeout(self, timeout_sec: float):
        with self.lock:
            self.total_timeouts += 1
            self.consecutive_errors += 1
            self.latency_ms = round(timeout_sec * 1000, 1)
            self.last_checked_time = time.strftime("%H:%M:%S")
            self.last_error_message = f"Timeout > {timeout_sec}s (Macet, otomatis dialihkan ke GPU)"
            self.status = "DEGRADED" if self.consecutive_errors < 3 else "OFFLINE"

    def record_error(self, err_msg: str):
        with self.lock:
            self.total_errors += 1
            self.consecutive_errors += 1
            self.last_checked_time = time.strftime("%H:%M:%S")
            self.last_error_message = str(err_msg)[:cfg.ERROR_MESSAGE_MAX_CHARS]
            if "429" in err_msg or "quota" in err_msg.lower():
                self.total_rate_limited += 1
                self.status = "DEGRADED"
            else:
                self.status = "OFFLINE"

    def record_local_call(self, is_rate_guard: bool = False):
        with self.lock:
            self.total_local_calls += 1
            if is_rate_guard:
                self.total_rate_limited += 1

    def set_locked(self, locked: bool):
        with self.lock:
            self.is_locked = locked

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "engine_mode": self.engine_mode,
                "status": self.status,
                "latency_ms": self.latency_ms,
                "avg_latency_ms": self.avg_latency_ms,
                "is_locked": self.is_locked,
                "total_cloud_calls": self.total_cloud_calls,
                "total_local_calls": self.total_local_calls,
                "total_timeouts": self.total_timeouts,
                "total_rate_limited": self.total_rate_limited,
                "total_errors": self.total_errors,
                "consecutive_errors": self.consecutive_errors,
                "last_checked_time": self.last_checked_time,
                "last_error_message": self.last_error_message
            }

api_monitor = APIMonitor()
