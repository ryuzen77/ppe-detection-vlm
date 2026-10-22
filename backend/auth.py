"""Sesi login dashboard (T30, akun sejak T51).

Foto bukti (wajah), video langsung, CSV audit, dan telemetri hanya untuk pengguna
yang login. Sejak T51 login selalu wajib (tidak ada lagi mode terbuka tanpa
`ADMIN_TOKEN`) dan sesi milik satu akun (`accounts.py`).

Sesi berupa cookie acak `HttpOnly; SameSite=Strict`, bukan header, karena
`<img src>` video dan foto bukti tidak bisa mengirim header. Sesi disimpan di
memori: server dinyalakan ulang = login ulang (cukup untuk demo, tanpa berkas
rahasia tambahan di disk).
"""

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .config import cfg

SESSION_COOKIE = "depro_session"


@dataclass(frozen=True)
class SessionUser:
    username: str
    role: str


@dataclass
class _Session:
    user: SessionUser
    expires: float


class SessionStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    @staticmethod
    def lifetime_seconds() -> float:
        return cfg.SESSION_HOURS * 3600

    def create(self, user: SessionUser) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge()
            self._sessions[token] = _Session(user, self._clock() + self.lifetime_seconds())
        return token

    def lookup(self, token: Optional[str]) -> Optional[tuple[SessionUser, float]]:
        """(pengguna, sisa detik), atau None bila tidak ada / kedaluwarsa."""
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            left = session.expires - self._clock()
            if left <= 0:
                del self._sessions[token]
                return None
            return session.user, left

    def user(self, token: Optional[str]) -> Optional[SessionUser]:
        found = self.lookup(token)
        return found[0] if found else None

    def revoke(self, token: Optional[str]):
        with self._lock:
            self._sessions.pop(token or "", None)

    def revoke_user(self, username: str, keep: Optional[str] = None):
        """Akun dihapus / kata sandi diganti: semua sesinya berakhir (kecuali `keep`)."""
        with self._lock:
            for token in [t for t, s in self._sessions.items() if s.user.username == username and t != keep]:
                del self._sessions[token]

    def _purge(self):
        now = self._clock()
        for token in [t for t, s in self._sessions.items() if s.expires <= now]:
            del self._sessions[token]


class LoginLimiter:
    """Menahan tebak kata sandi: LOGIN_MAX_FAILURES gagal → jeda LOGIN_LOCKOUT_SECONDS per kunci.

    Kuncinya alamat klien DAN nama pengguna (T51): merotasi alamat tidak membuka
    tebakan tanpa batas untuk satu akun.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, *keys: str) -> float:
        with self._lock:
            now = self._clock()
            return max([0.0] + [self._locked_until.get(k, 0.0) - now for k in keys])

    def record_failure(self, *keys: str):
        with self._lock:
            for key in keys:
                count = self._failures.get(key, 0) + 1
                if count >= cfg.LOGIN_MAX_FAILURES:
                    self._locked_until[key] = self._clock() + cfg.LOGIN_LOCKOUT_SECONDS
                    count = 0
                self._failures[key] = count

    def record_success(self, *keys: str):
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)
                self._locked_until.pop(key, None)


def limiter_keys(client: str, username: str) -> tuple[str, str]:
    return f"ip:{client}", f"user:{username}"


sessions = SessionStore()
login_limiter = LoginLimiter()
