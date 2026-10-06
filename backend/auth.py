"""Login admin untuk dashboard (T30).

Foto bukti (wajah), video langsung, CSV audit, dan telemetri dulu terbuka bagi
siapa pun di jaringan; token admin hanya menjaga tombol yang mengubah sistem.
Sekarang semua `/api/*` dan `/ws` mewajibkan sesi bila `ADMIN_TOKEN` terisi.

Sesi berupa cookie acak `HttpOnly; SameSite=Strict`, bukan header, karena
`<img src>` video dan foto bukti tidak bisa mengirim header. Sesi disimpan di
memori: server dinyalakan ulang = login ulang (cukup untuk demo, tanpa berkas
rahasia tambahan di disk).
"""
import hmac
import secrets
import threading
import time
from typing import Callable, Optional

from .config import cfg

SESSION_COOKIE = "depro_session"
ADMIN_HEADER = "x-admin-token"   # alat & skrip lama tetap boleh memakai header


def auth_required() -> bool:
    """Tanpa ADMIN_TOKEN server hanya boleh berjalan di localhost (lihat app.py)."""
    return bool(cfg.ADMIN_TOKEN)


def password_matches(candidate: Optional[str]) -> bool:
    # compare_digest: waktu perbandingan tidak membocorkan berapa karakter yang benar
    return bool(candidate) and hmac.compare_digest(candidate.encode(), cfg.ADMIN_TOKEN.encode())


class SessionStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._sessions: dict[str, float] = {}   # token -> kedaluwarsa
        self._lock = threading.Lock()

    @staticmethod
    def lifetime_seconds() -> float:
        return cfg.SESSION_HOURS * 3600

    def create(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._purge()
            self._sessions[token] = self._clock() + self.lifetime_seconds()
        return token

    def remaining(self, token: Optional[str]) -> Optional[float]:
        """Sisa detik sesi, atau None bila tidak ada / kedaluwarsa."""
        if not token:
            return None
        with self._lock:
            expires = self._sessions.get(token)
            if expires is None:
                return None
            left = expires - self._clock()
            if left <= 0:
                del self._sessions[token]
                return None
            return left

    def revoke(self, token: Optional[str]):
        with self._lock:
            self._sessions.pop(token or "", None)

    def _purge(self):
        now = self._clock()
        for token in [t for t, exp in self._sessions.items() if exp <= now]:
            del self._sessions[token]


class LoginLimiter:
    """Menahan tebak kata sandi: LOGIN_MAX_FAILURES gagal → jeda LOGIN_LOCKOUT_SECONDS per alamat."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def retry_after(self, client: str) -> float:
        with self._lock:
            return max(0.0, self._locked_until.get(client, 0.0) - self._clock())

    def record_failure(self, client: str):
        with self._lock:
            count = self._failures.get(client, 0) + 1
            if count >= cfg.LOGIN_MAX_FAILURES:
                self._locked_until[client] = self._clock() + cfg.LOGIN_LOCKOUT_SECONDS
                count = 0
            self._failures[client] = count

    def record_success(self, client: str):
        with self._lock:
            self._failures.pop(client, None)
            self._locked_until.pop(client, None)


sessions = SessionStore()
login_limiter = LoginLimiter()


def is_authorized(cookie_token: Optional[str], header_token: Optional[str]) -> bool:
    """Sesi sah atau header token admin; selalu True bila login tidak diwajibkan."""
    if not auth_required():
        return True
    return sessions.remaining(cookie_token) is not None or password_matches(header_token)
