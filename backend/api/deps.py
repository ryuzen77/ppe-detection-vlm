"""Dependensi bersama untuk endpoint."""
from fastapi import HTTPException, Request

from .. import auth, messages


async def require_session(request: Request):
    """Wajib sesi login (cookie) atau header token admin, bila ADMIN_TOKEN terisi (T30).

    Dipasang di tingkat router (app.py), jadi endpoint baru otomatis terlindungi;
    hanya rute login (`routes_auth`) dan berkas UI statis yang bebas.
    """
    if not auth.is_authorized(request.cookies.get(auth.SESSION_COOKIE), request.headers.get(auth.ADMIN_HEADER)):
        raise HTTPException(status_code=401, detail=messages.API_LOGIN_REQUIRED)


# Demo hanya punya satu peran (admin): perintah yang mengubah sistem memakai
# syarat yang sama. Nama lama dipertahankan supaya pemakaiannya tetap terbaca.
require_admin = require_session
