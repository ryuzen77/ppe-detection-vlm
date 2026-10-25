"""Kebijakan akses T83: hak admin dan konfirmasi mutu pengenalan wajah."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, StrictBool

from .. import face_identity, messages, registration_policy, security_log
from ..config import cfg
from ..audit.report_manager import report_mgr
from .deps import actor, require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


class PolicyBody(BaseModel):
    require_registered: StrictBool
    confirm_low_recognition: StrictBool = False


def policy_status() -> dict:
    return {
        "require_registered": registration_policy.policy.enabled,
        "fr_ready": registration_policy.fr_ready(),
        "recognition": report_mgr.recognition_rate(cfg.FR_RATE_WINDOW_DAYS),
    }


@router.get("/api/config/registration-policy")
def get_registration_policy():
    face_identity.identifier.check_ready()
    return policy_status()


@router.post("/api/config/registration-policy")
def set_registration_policy(body: PolicyBody, request: Request):
    ready = face_identity.identifier.check_ready() if body.require_registered else registration_policy.fr_ready()
    if body.require_registered and not ready:
        raise HTTPException(400, detail={"code": "fr_not_ready", "message": messages.REGISTRATION_FR_NOT_READY})
    rate = report_mgr.recognition_rate(cfg.FR_RATE_WINDOW_DAYS)["rate"]
    if body.require_registered and (rate is None or rate < cfg.FR_REQUIRED_RATE) and not body.confirm_low_recognition:
        raise HTTPException(
            400, detail={"code": "low_recognition_needs_confirmation", "message": messages.REGISTRATION_LOW_RECOGNITION}
        )
    if not registration_policy.policy.save(body.require_registered):
        raise HTTPException(500, detail=messages.REGISTRATION_SAVE_FAILED)
    security_log.record(
        registration_policy.POLICY_CHANGED,
        actor=actor(request),
        require_registered=body.require_registered,
        confirm_low_recognition=body.confirm_low_recognition,
        ok=True,
    )
    return policy_status()
