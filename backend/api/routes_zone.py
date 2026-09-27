"""Zona titik berdiri (T36d): baca, ubah, dan kalibrasi. Kontrak di docs/RENCANA.md."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import messages
from .. import zone as zones
from ..state_manager import state_mgr
from ..zone import zone_store
from .deps import require_admin

router = APIRouter()


@router.get("/api/config/zone")
async def get_zone():
    return asdict(zone_store.get())


@router.post("/api/config/zone", dependencies=[Depends(require_admin)])
async def set_zone(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail=messages.ZONE_BODY_INVALID)
    try:
        zone = zone_store.update(enabled=data.get("enabled"), y_min=data.get("y_min"), y_max=data.get("y_max"))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e) or messages.ZONE_BODY_INVALID)
    return asdict(zone)


@router.post("/api/config/zone/calibrate", dependencies=[Depends(require_admin)])
async def calibrate_zone():
    """Titik berdiri = posisi kaki orang di lorong saat ini (yang paling dekat kamera)."""
    people = [d for d in state_mgr.latest_detections if getattr(d, "is_inside_corridor", True)]
    if not people:
        raise HTTPException(status_code=409, detail=messages.ZONE_CALIBRATE_NO_PERSON)
    subject = max(people, key=lambda d: d.bbox[3] - d.bbox[1])
    if subject.foot_y is None:
        raise HTTPException(status_code=409, detail=messages.ZONE_CALIBRATE_NO_FEET)
    return asdict(zone_store.set(zones.calibrated(subject.foot_y)))
