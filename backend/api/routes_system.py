"""Status server, reset pelacakan, koridor, audio, dan uji lampu IoT."""
from fastapi import APIRouter, Depends, Request

from ..config import cfg
from .. import messages
from ..state_manager import state_mgr
from ..vlm_analyzer import vlm_analyzer
from ..notifier import notifier
from ..audio_engine import audio_player
from ..video.capture import video_service
from .deps import require_admin

router = APIRouter()


@router.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "fps": round(video_service.fps, 1),
        "is_live_gemini": vlm_analyzer.is_live_api(),
        "camera_selected": video_service.camera_index is not None,
        "camera_index": video_service.camera_index,
        "camera_name": video_service.camera_name,
        "camera_status": video_service.camera_status,
        "resolution": f"{video_service.frame_width}x{video_service.frame_height}",
        # Saat LOST yang tampil juga frame sintetis, jadi ikut dihitung di sini
        "is_synthetic_camera": video_service.use_synthetic or video_service.camera_status == "LOST"
    }

@router.post("/api/reset", dependencies=[Depends(require_admin)])
async def reset_tracking():
    state_mgr.reset_all()
    return {"status": "success", "message": messages.API_STATE_RESET}


@router.post("/api/config/corridor", dependencies=[Depends(require_admin)])
async def set_corridor_filter(request: Request):
    """Menyalakan atau mematikan Virtual Inspection Corridor."""
    data = await request.json()
    cfg.ENABLE_CORRIDOR_FILTER = bool(data.get("enabled", True))
    return {"status": "success", "enabled": cfg.ENABLE_CORRIDOR_FILTER}


# --- IOT HARDWARE TEST ENDPOINT ---

@router.post("/api/iot/test", dependencies=[Depends(require_admin)])
async def test_iot_light(request: Request):
    """Allows manual operator testing of physical gate lights (green/red/off) from Settings tab."""
    data = await request.json()
    action = data.get("action", "off").lower()
    if action == "green":
        notifier.set_complete(messages.LIGHT_TEST_GREEN)
    elif action == "red":
        notifier.set_incomplete(messages.LIGHT_TEST_RED)
    else:
        notifier.set_idle()
    return {
        "status": "success",
        "action": action,
        "light_state": notifier.current_state
    }

# --- AUDIO MUTE CONFIG ENDPOINTS ---

@router.get("/api/config/audio")
async def get_audio_config():
    return {"muted": audio_player.is_muted}

@router.post("/api/config/audio", dependencies=[Depends(require_admin)])
async def set_audio_config(request: Request):
    data = await request.json()
    muted = data.get("muted", False)
    is_muted = audio_player.set_muted(muted)
    return {"status": "success", "muted": is_muted}
