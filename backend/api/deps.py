"""Dependensi bersama untuk endpoint."""
from fastapi import Header, HTTPException

from ..config import cfg
from .. import messages


async def require_admin(x_admin_token: str | None = Header(default=None)):
    """Guard opsional untuk endpoint yang mengubah state server.

    Server ini bind ke 0.0.0.0, jadi tanpa guard siapa pun di jaringan yang sama
    bisa mengganti API key, me-reset tracking, atau menyalakan lampu gerbang.
    Non-aktif ketika ADMIN_TOKEN kosong agar demo lokal tidak terhambat.
    """
    if not cfg.ADMIN_TOKEN:
        return
    if x_admin_token != cfg.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail=messages.API_INVALID_ADMIN_TOKEN)
