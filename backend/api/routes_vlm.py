"""Penyedia VLM (pilih dari dashboard, T28) dan kesehatan VLM utama & cadangan.

API key tidak pernah lewat sini: key hanya di backend/.env (keputusan T28 e).
Endpoint ganti key lama (`/api/config/vlm-key`, `/api/config/gemini-key`) dihapus.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import messages, vlm_selection
from ..api_monitor import api_monitor
from ..state_manager import state_mgr
from ..vlm_analyzer import ROLE_BACKUP, ROLE_PRIMARY, EngineFailed, LaneBusy, vlm_analyzer
from ..vlm_selection import Choice, Selection, SelectionError
from .deps import require_admin

router = APIRouter()

ROLES = {"primary": ROLE_PRIMARY, "backup": ROLE_BACKUP}


class ChoiceBody(BaseModel):
    provider: str
    model: str = ""


class TestBody(ChoiceBody):
    role: Literal["primary", "backup"] = "primary"


class ApplyBody(BaseModel):
    primary: ChoiceBody
    backup: Optional[ChoiceBody] = None
    confirm_unvalidated: bool = False


def _lane_empty() -> bool:
    return state_mgr.session is None


def _error(status: int, code: str, message: str) -> HTTPException:
    # `code` stabil untuk UI (mis. needs_confirmation -> tampilkan konfirmasi)
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _apply(selection: Selection, request: Request) -> dict:
    if not _lane_empty():
        raise _error(409, "lane_busy", messages.VLM_SELECT_LANE_BUSY)
    client = request.client.host if request.client else ""
    try:
        return vlm_analyzer.apply_selection(selection, _lane_empty, client=client)
    except LaneBusy as e:
        raise _error(409, "lane_busy", str(e))
    except EngineFailed as e:
        raise _error(502, "engine_failed", str(e))


@router.get("/api/config/vlm")
async def get_vlm_config():
    """Penyedia & model VLM yang aktif, untuk tab Pengaturan. API key tidak pernah dikirim."""
    return vlm_analyzer.provider_info()


@router.get("/api/config/vlm/providers", dependencies=[Depends(require_admin)])
async def list_vlm_providers():
    return {"current": vlm_analyzer.current_selection(), "prompt_version": messages.PROMPT_VERSION,
            "providers": vlm_selection.provider_catalog(vlm_analyzer.active_choices())}


@router.post("/api/config/vlm/test", dependencies=[Depends(require_admin)])
def test_vlm_provider(body: TestBody):
    """1 ping + 1 gambar sintetis ke penyedia itu (memakai kuota penyedia itu)."""
    choice = Choice.parse(body.model_dump())
    try:
        vlm_selection.check_choice(choice, confirm_unvalidated=True)
    except SelectionError as e:
        raise _error(400, e.code, e.message)
    return vlm_analyzer.test_choice(ROLES[body.role], choice)


@router.post("/api/config/vlm/apply", dependencies=[Depends(require_admin)])
def apply_vlm_selection(body: ApplyBody, request: Request):
    """Mengganti penyedia/model utama & cadangan tanpa restart; disimpan, menang atas .env."""
    primary, backup = Choice.parse(body.primary.model_dump()), Choice.parse(body.backup and body.backup.model_dump())
    if primary is None:
        raise _error(400, "unknown_provider", messages.VLM_SELECT_UNKNOWN_PROVIDER.format(provider=""))
    try:
        for choice in filter(None, (primary, backup)):
            vlm_selection.check_choice(choice, body.confirm_unvalidated)
    except SelectionError as e:
        raise _error(400, e.code, e.message)
    selection = Selection(primary, backup, vlm_selection.SOURCE_DASHBOARD)
    current = _apply(selection, request)
    vlm_selection.save(selection)
    return current


@router.delete("/api/config/vlm/selection", dependencies=[Depends(require_admin)])
def reset_vlm_selection(request: Request):
    """Kembali ke pilihan .env (aturan jalur kosong sama dengan apply)."""
    current = _apply(vlm_selection.env_selection(), request)
    vlm_selection.clear()
    return current


# --- PEMANTAUAN VLM ---
# Tidak ada lagi sakelar mode engine: operator tidak mengubah cara gerbang
# memutuskan saat berjalan; peralihan ke cadangan terjadi otomatis (T27).

@router.get("/api/monitoring/status")
async def get_monitoring_status():
    """Kesehatan VLM utama & cadangan dan siapa yang sedang memutuskan."""
    return api_monitor.get_status()


@router.post("/api/monitoring/ping", dependencies=[Depends(require_admin)])
async def ping_vlm_api():
    """Uji latensi sesaat ke VLM utama dan cadangan."""
    return vlm_analyzer.ping_api()
