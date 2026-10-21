"""Kesehatan VLM utama & cadangan untuk dashboard (T27).

Status gerbang yang ditampilkan operator:
- UTAMA     : keputusan terakhir oleh VLM utama (hijau)
- CADANGAN  : utama gagal/terputus, keputusan oleh VLM cadangan (kuning)
- GANGGUAN  : tidak ada VLM yang menjawab; pekerja diminta menunggu (merah)
"""
import time
import threading
from typing import Any, Optional
from collections import deque

from .config import cfg

MODE_PRIMARY = "UTAMA"
MODE_BACKUP = "CADANGAN"
MODE_DOWN = "GANGGUAN"
MODE_LOCAL = "LOKAL"
ROLE_EMERGENCY = "darurat"


class EngineStats:
    """Catatan panggilan satu VLM (utama atau cadangan)."""

    def __init__(self):
        self.info: Optional[dict] = None
        self.status = "BELUM_DIPAKAI"      # BELUM_DIPAKAI / OK / GAGAL
        self.latency_ms = 0.0
        self.latency_history: deque = deque(maxlen=cfg.API_LATENCY_HISTORY)
        self.calls = 0
        self.failures = 0
        self.timeouts = 0
        self.rate_limited = 0
        self.consecutive_failures = 0
        self.last_error = ""
        self.last_checked = "-"

    def as_dict(self) -> dict:
        avg = round(sum(self.latency_history) / len(self.latency_history), 1) if self.latency_history else 0.0
        return {
            "configured": bool(self.info and self.info.get("is_live")),
            "provider": (self.info or {}).get("provider", ""),
            "model": (self.info or {}).get("model", ""),
            "is_local": (self.info or {}).get("is_local", False),
            "status": self.status,
            "latency_ms": self.latency_ms,
            "avg_latency_ms": avg,
            "calls": self.calls,
            "failures": self.failures,
            "timeouts": self.timeouts,
            "rate_limited": self.rate_limited,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "last_checked": self.last_checked,
        }


class APIMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.engines = {role: EngineStats() for role in ("utama", "cadangan", ROLE_EMERGENCY)}
        self.primary_down = False
        self.mode = MODE_DOWN
        self.decisions = {role: 0 for role in self.engines}
        self.no_decisions = 0
        self.last_no_decision_reason = ""
        self.is_locked = False
        self.internet = {"state": None, "median_ms": None, "checked_at": None}
        self.local = {"role": None, "state": "unloaded", "since": time.strftime(cfg.TELEMETRY_TIME_FORMAT)}

    def set_internet(self, status: dict):
        with self.lock:
            self.internet = dict(status)

    def set_local(self, status: dict):
        with self.lock:
            self.local = dict(status)

    def set_emergency(self, info: Optional[dict]):
        with self.lock:
            self.engines[ROLE_EMERGENCY].info = info

    def set_engines(self, primary: Optional[dict], backup: Optional[dict], primary_down: bool):
        with self.lock:
            self.engines["utama"].info = primary
            self.engines["cadangan"].info = backup
            self.primary_down = primary_down
            # Sebelum inspeksi pertama, mode mengikuti VLM mana yang siap
            if sum(self.decisions.values()) == 0 and self.no_decisions == 0:
                if primary and primary.get("is_live"):
                    self.mode = MODE_PRIMARY
                elif backup and backup.get("is_live"):
                    self.mode = MODE_BACKUP
                else:
                    self.mode = MODE_DOWN
            elif primary_down and self.mode == MODE_PRIMARY:
                self.mode = MODE_BACKUP

    def record_success(self, role: str, duration_ms: float):
        with self.lock:
            s = self.engines[role]
            s.calls += 1
            s.consecutive_failures = 0
            s.status = "OK"
            s.latency_ms = round(duration_ms, 1)
            s.latency_history.append(s.latency_ms)
            s.last_checked = time.strftime("%H:%M:%S")
            s.last_error = ""

    def record_failure(self, role: str, err_msg: str, is_timeout: bool = False):
        with self.lock:
            s = self.engines[role]
            s.calls += 1
            s.failures += 1
            s.consecutive_failures += 1
            s.status = "GAGAL"
            if is_timeout:
                s.timeouts += 1
            if "429" in err_msg or "quota" in err_msg.lower():
                s.rate_limited += 1
            s.last_checked = time.strftime("%H:%M:%S")
            s.last_error = str(err_msg)[:cfg.ERROR_MESSAGE_MAX_CHARS]

    def record_decision(self, role: Optional[str], reason: str = ""):
        """Siapa yang memutuskan inspeksi terakhir; None = tidak ada keputusan."""
        with self.lock:
            if role is None:
                self.no_decisions += 1
                self.last_no_decision_reason = reason[:cfg.ERROR_MESSAGE_MAX_CHARS]
                self.mode = MODE_DOWN
            else:
                self.decisions[role] += 1
                self.mode = MODE_LOCAL if role == ROLE_EMERGENCY else MODE_PRIMARY if role == "utama" else MODE_BACKUP

    def set_locked(self, locked: bool):
        with self.lock:
            self.is_locked = locked

    def get_status(self) -> dict[str, Any]:
        with self.lock:
            primary = self.engines["utama"].as_dict()
            backup = self.engines["cadangan"].as_dict()
            active = (self.engines[ROLE_EMERGENCY].as_dict() if self.mode == MODE_LOCAL
                      else backup if self.mode == MODE_BACKUP else primary)
            return {
                "mode": self.mode,
                "internet": dict(self.internet),
                "local": dict(self.local),
                "primary_down": self.primary_down,
                "primary": primary,
                "backup": backup,
                "decisions_primary": self.decisions["utama"],
                "decisions_backup": self.decisions["cadangan"],
                "no_decisions": self.no_decisions,
                "last_no_decision_reason": self.last_no_decision_reason,
                "is_locked": self.is_locked,
                # Latensi VLM yang sedang dipakai, untuk laci teknis
                "latency_ms": active["latency_ms"],
                "avg_latency_ms": active["avg_latency_ms"],
            }


api_monitor = APIMonitor()
