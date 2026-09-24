"""Katalog kamera, pemindaian, dan pergantian sumber video."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..config import cfg
from .. import messages
from .. import camera_manager
from ..camera_manager import camera_mgr
from ..video.capture import video_service
from .deps import require_admin

router = APIRouter()


# --- CAMERA SOURCE ENDPOINTS ---

@router.get("/api/cameras")
async def list_cameras():
    """Katalog kamera beserta mode terukurnya.

    Mengembalikan hasil pemindaian terakhir seketika; `scanning` menandakan
    pemindaian latar masih berjalan (probing satu perangkat butuh beberapa detik).
    """
    catalog = camera_mgr.get_catalog()
    active = video_service.get_camera_status()

    # Kalau belum pernah dipindai, daftar tetap dibentuk dari nama perangkat.
    # Perangkat yang belum diukur ditandai `scanned: False`, bukan "tidak tersedia":
    # kamera USB yang baru dicolok belum tentu bermasalah, hanya belum diperiksa.
    if not catalog["devices"]:
        catalog["devices"] = [
            {
                "index": i,
                "name": name,
                "available": True,
                "scanned": False,
                "in_use": False,
                "modes": [],
                "selected_mode": None,
            }
            for i, name in enumerate(camera_manager.list_device_names())
        ]

    # Perangkat yang sedang dipakai tidak bisa di-probe karena terkunci oleh
    # aliran video, jadi datanya diisi dari service yang berjalan. Dijalankan
    # setelah daftar terbentuk agar berlaku untuk kedua sumber daftar di atas.
    for dev in catalog["devices"]:
        if dev["index"] != active["index"]:
            continue
        dev["in_use"] = True
        dev["available"] = not active["is_synthetic"]
        dev["scanned"] = True
        if active["mode"] and not dev.get("selected_mode"):
            dev["selected_mode"] = active["mode"]
        # Kamera yang dibuka dengan permintaan bawaan belum punya angka hasil
        # pengukuran, jadi laju yang sedang berjalan dipakai supaya daftar
        # tidak menampilkan "@0 FPS".
        sel = dev.get("selected_mode")
        if sel and not sel.get("fps"):
            sel = dict(sel)
            sel["fps"] = active["fps"]
            dev["selected_mode"] = sel

    # Pilihan terakhir dipakai untuk menyorot bawaan di dialog pemilihan,
    # bukan untuk menyambung otomatis.
    catalog["saved"] = camera_manager.load_saved_selection()
    catalog["active"] = active
    catalog["quality_warning"] = (
        active["height"] > 0 and active["height"] < cfg.CAMERA_QUALITY_WARN_HEIGHT
    )
    return catalog


@router.post("/api/cameras/scan", dependencies=[Depends(require_admin)])
async def scan_cameras():
    """Memulai probing kemampuan seluruh kamera di latar belakang."""
    # Kamera aktif tidak bisa di-probe dari luar karena terkunci aliran video,
    # jadi pengukurannya dititipkan ke thread pembaca yang memilikinya.
    video_service.request_optimize()
    started = camera_mgr.start_scan(skip_index=video_service.camera_index)
    return {
        "status": "started" if started else "already_running",
        "scanning": True,
        "message": messages.API_SCAN_STARTED,
    }


@router.post("/api/config/camera", dependencies=[Depends(require_admin)])
async def set_camera_source(request: Request):
    """Memindahkan sumber video ke kamera lain tanpa menjalankan ulang server."""
    data = await request.json()

    # index null berarti lepaskan kamera dan kembali ke layar pemilihan
    if data.get("index") is None:
        video_service.request_idle()
        return {"status": "scheduled", "pending_index": None,
                "message": messages.API_CAMERA_RELEASED}

    try:
        index = int(data["index"])
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": messages.API_CAMERA_INDEX_INVALID},
        )

    mode = data.get("mode")
    video_service.request_camera(index, mode)
    # Pergantian dikerjakan thread pembaca, jadi belum selesai saat balasan ini
    # dikirim. Status sebenarnya dibaca klien dari telemetri WebSocket.
    return {
        "status": "scheduled",
        "pending_index": index,
        "message": messages.API_CAMERA_SWITCHING.format(index=index),
    }
