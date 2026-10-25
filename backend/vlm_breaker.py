"""State pemutus utama; waktu dan ketersediaan cadangan diberikan oleh fasad."""

from dataclasses import dataclass
from typing import Optional

from .config import cfg


@dataclass
class PrimaryBreaker:
    failures: int = 0
    down_since: Optional[float] = None
    last_attempt: float = 0.0

    def reset(self):
        self.failures = 0
        self.down_since = None
        self.last_attempt = 0.0

    def allowed(self, now: float, has_backup: bool) -> bool:
        # T87: tanpa cadangan aktif, setiap pekerja tetap mencoba utama.
        if not has_backup:
            return True
        if self.failures < cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN:
            return True
        return now - self.last_attempt >= cfg.VLM_PRIMARY_RETRY_AFTER_SECONDS

    def result(self, ok: bool, now: float) -> bool:
        """True hanya pada kegagalan pertama yang menandai utama terputus; tanpa log atau probe."""
        if ok:
            self.failures = 0
            self.down_since = None
            return False
        self.failures += 1
        if self.failures >= cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN and self.down_since is None:
            self.down_since = now
            return True
        return False
