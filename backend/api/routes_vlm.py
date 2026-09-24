"""API key VLM, pemantauan latensi, dan mode engine."""
from fastapi import APIRouter, Depends, Request

from .. import messages
from ..vlm_analyzer import vlm_analyzer
from ..api_monitor import api_monitor
from .deps import require_admin

router = APIRouter()


@router.get("/api/config/vlm")
async def get_vlm_config():
    """Penyedia & model VLM yang aktif, untuk tab Pengaturan. API key tidak pernah dikirim."""
    return vlm_analyzer.provider_info()


@router.post("/api/config/vlm-key", dependencies=[Depends(require_admin)])
async def update_vlm_key(request: Request):
    """Mengganti API key penyedia VLM yang sedang aktif."""
    data = await request.json()
    new_key = data.get("api_key", "").strip()
    if new_key:
        vlm_analyzer.update_api_key(new_key)
        return {"status": "success", "is_live": vlm_analyzer.is_live_api(), **vlm_analyzer.provider_info()}
    return {"status": "error", "message": messages.API_KEY_EMPTY}


# Nama lama, dipertahankan agar klien lama tidak rusak
router.add_api_route("/api/config/gemini-key", update_vlm_key, methods=["POST"],
                     dependencies=[Depends(require_admin)])

# --- API MONITORING & ENGINE MODE ENDPOINTS ---

@router.get("/api/monitoring/status")
async def get_monitoring_status():
    """Kesehatan penyedia VLM, latensi ping, dan mode engine."""
    return api_monitor.get_status()

@router.post("/api/monitoring/ping", dependencies=[Depends(require_admin)])
async def ping_vlm_api():
    """Uji latensi sesaat ke penyedia VLM yang aktif."""
    res = vlm_analyzer.ping_api()
    return res

@router.post("/api/config/engine-mode", dependencies=[Depends(require_admin)])
async def set_engine_mode(request: Request):
    """Beralih antara VLM (HYBRID_AUTO) dan heuristik lokal OpenCV (FORCE_LOCAL)."""
    data = await request.json()
    mode = data.get("engine_mode", "HYBRID_AUTO")
    new_mode = api_monitor.set_engine_mode(mode)
    return {
        "status": "success",
        "engine_mode": new_mode,
        "is_forced_local": new_mode == "FORCE_LOCAL"
    }
