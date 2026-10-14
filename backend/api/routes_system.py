"""Status server, reset pelacakan, koridor, audio, dan uji lampu IoT."""
from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import cfg
from .. import messages
from ..state_manager import state_mgr
from ..vlm_analyzer import vlm_analyzer
from ..notifier import notifier
from .. import startup_checks
from ..disk_guard import disk_guard
from ..audio_engine import audio_player
from ..video.capture import video_service
from .deps import require_admin

router = APIRouter()


@router.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "fps": round(video_service.fps, 1),
        "is_live_vlm": vlm_analyzer.is_live_api(),
        "is_live_gemini": vlm_analyzer.is_live_api(),   # nama lama, untuk klien lama
        "vlm": vlm_analyzer.provider_info(),
        "camera_selected": video_service.camera_index is not None,
        "camera_index": video_service.camera_index,
        "camera_name": video_service.camera_name,
        "camera_status": video_service.camera_status,
        "resolution": f"{video_service.frame_width}x{video_service.frame_height}",
        # Saat LOST yang tampil juga frame sintetis, jadi ikut dihitung di sini
        "is_synthetic_camera": video_service.use_synthetic or video_service.camera_status == "LOST",
        # Peringatan pemeriksaan saat server menyala (T29)
        "startup_warnings": list(startup_checks.warnings),
        # Sisa disk data (T53): ok / low / critical
        "disk": disk_guard.status(),
        # Kesehatan VLM lokal (T56): ok / slow / partial_gpu / unknown + aplikasi lain di GPU
        "local_vlm": vlm_analyzer.local_guard.status(),
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
    """Uji lampu gerbang dari tab Pengaturan. Ditolak (409) bila ada pekerja di jalur,
    supaya lampu uji tidak terbaca sebagai keputusan oleh pekerja sungguhan."""
    data = await request.json()
    action = str(data.get("action", "")).lower()
    tests = {
        "green": lambda: notifier.set_complete(messages.LIGHT_TEST_GREEN),
        "red": lambda: notifier.set_incomplete(messages.LIGHT_TEST_RED),
        "yellow": lambda: notifier.set_waiting(messages.LIGHT_TEST_YELLOW),
        "off": notifier.set_idle,
    }
    if action not in tests:
        raise HTTPException(status_code=400, detail=messages.API_LIGHT_TEST_INVALID.format(actions=", ".join(tests)))
    if state_mgr.session is not None:
        raise HTTPException(status_code=409, detail=messages.API_LIGHT_TEST_BUSY)
    tests[action]()
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
