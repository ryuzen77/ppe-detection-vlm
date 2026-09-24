"""API key VLM, pemantauan latensi, dan mode engine."""
from fastapi import APIRouter, Depends, Request

from .. import messages
from ..vlm_analyzer import vlm_analyzer
from ..api_monitor import api_monitor
from .deps import require_admin

router = APIRouter()


@router.post("/api/config/gemini-key", dependencies=[Depends(require_admin)])
async def update_gemini_key(request: Request):
    data = await request.json()
    new_key = data.get("api_key", "").strip()
    if new_key:
        vlm_analyzer.update_api_key(new_key)
        return {"status": "success", "is_live": vlm_analyzer.is_live_api()}
    return {"status": "error", "message": messages.API_KEY_EMPTY}

# --- API MONITORING & ENGINE MODE ENDPOINTS ---

@router.get("/api/monitoring/status")
async def get_monitoring_status():
    """Returns real-time Gemini Cloud API health, ping latency, and engine mode."""
    return api_monitor.get_status()

@router.post("/api/monitoring/ping", dependencies=[Depends(require_admin)])
async def ping_gemini_api():
    """Initiates an on-demand latency test to Google Gemini API."""
    res = vlm_analyzer.ping_api()
    return res

@router.post("/api/config/engine-mode", dependencies=[Depends(require_admin)])
async def set_engine_mode(request: Request):
    """Allows operator to toggle between Online (Cloud Gemini) and Offline (heuristik lokal OpenCV)."""
    data = await request.json()
    mode = data.get("engine_mode", "HYBRID_AUTO")
    new_mode = api_monitor.set_engine_mode(mode)
    return {
        "status": "success",
        "engine_mode": new_mode,
        "is_forced_local": new_mode == "FORCE_LOCAL"
    }
