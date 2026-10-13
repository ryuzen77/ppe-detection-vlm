"""Dependensi bersama untuk endpoint: sesi login & hak per peran (T30, T51)."""
from fastapi import Depends, HTTPException, Request

from .. import accounts, auth, messages


def client_address(request: Request) -> str:
    return request.client.host if request.client else "?"


async def require_session(request: Request) -> auth.SessionUser:
    """Wajib sesi login yang sah. Dipasang di tingkat router (app.py), jadi endpoint baru
    otomatis terlindungi; hanya rute sesi/setup/login (`routes_auth`) dan UI statis yang bebas.
    Pengguna disimpan di `request.state.user` untuk jejak (siapa melakukan apa)."""
    user = auth.sessions.user(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail=messages.API_LOGIN_REQUIRED)
    request.state.user = user
    return user


def require_role(*roles: str):
    """Satu pintu hak per peran (T51). Demo: semua akun `admin`; peran operator kelak
    cukup menambah peran yang diizinkan di endpoint, bukan mengubah alur login."""
    async def check(user: auth.SessionUser = Depends(require_session)) -> auth.SessionUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=messages.API_FORBIDDEN)
        return user
    return check


# Perintah yang mengubah sistem
require_admin = require_role(accounts.ROLE_ADMIN)


def actor(request: Request) -> str:
    """Nama pengguna pelaku untuk jejak; kosong bila tidak lewat require_session."""
    user = getattr(request.state, "user", None)
    return user.username if user else ""
