"""Katalog item APD dan pengaturan item yang diwajibkan."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from .. import messages
from .. import ppe_rules
from .deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


# --- KATALOG APD ---


def _ppe_catalog_payload() -> dict:
    """Katalog lengkap beserta status aktif. Semua item dinilai VLM (utama atau cadangan)."""
    return {"items": [item.to_public_dict() for item in ppe_rules.get_items()]}


@router.get("/api/ppe-rules")
async def get_ppe_rules():
    """Katalog item APD untuk dashboard; checklist dan lencana dirender dari sini."""
    return _ppe_catalog_payload()


@router.post("/api/ppe-rules/active", dependencies=[Depends(require_admin)])
async def set_ppe_rules_active(request: Request):
    """Menghidupkan/mematikan item APD. Body: {"active": {"kacamata": true, ...}}.

    Berlaku untuk inspeksi berikutnya dan tersimpan di `runtime_settings.json`.
    """
    data = await request.json()
    changes = data.get("active") if isinstance(data, dict) else None
    if not isinstance(changes, dict) or not all(isinstance(v, bool) for v in changes.values()):
        raise HTTPException(status_code=400, detail=messages.API_PPE_ACTIVE_FORMAT)
    try:
        ppe_rules.set_active(changes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    aktif = [item.label for item in ppe_rules.get_active_items()]
    logger.info(f"Item APD aktif: {', '.join(aktif)}")
    return _ppe_catalog_payload()
