"""Data pekerja & templat wajah untuk admin (T34b1, foto pendaftaran T34b2). Kontrak: docs/RENCANA.md, Rancangan T34 -> T34b.

Semua endpoint khusus admin. Jawaban tidak pernah memuat embedding maupun foto;
setiap perubahan dicatat di security log (siapa, dari mana, pekerja mana).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import auth, face_engine, messages, security_log, worker_store
from ..config import cfg
from ..state_manager import state_mgr
from ..video.capture import video_service
from .deps import client_address, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

_STATUS = {
    "not_found": 404,
    "template_not_found": 404,
    "employee_no_taken": 409,
    "inactive": 409,
    "camera_busy": 409,
    "camera_unavailable": 409,
    "no_face": 422,
    "multiple_faces": 422,
    "face_too_small": 422,
    "face_not_ready": 503,
}


class NewWorker(BaseModel):
    employee_no: str = ""
    name: str = ""
    consent: bool = False


class NewTemplate(BaseModel):
    condition: str = ""


def _error(error: worker_store.WorkerError | face_engine.FaceEngineError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(error.code, 400), detail={"code": error.code, "message": error.message}
    )


def worker_json(worker: worker_store.Worker) -> dict:
    return {
        "id": worker.id,
        "employee_no": worker.employee_no,
        "name": worker.name,
        "active": worker.active,
        "consent": {"at": worker.consent_at, "by": worker.consent_by, "version": worker.consent_version},
        "created_at": worker.created_at,
        "deactivated_at": worker.deactivated_at,
        "delete_after": worker.delete_after,
        "face_deleted_at": worker.face_deleted_at,
        "templates": [template_json(t) for t in worker.templates],
    }


def template_json(template: worker_store.Template) -> dict:
    return {
        "id": template.id,
        "condition": template.condition,
        "model_version": template.model_version,
        "created_at": template.created_at,
    }


def _record(event: str, request: Request, user: auth.SessionUser, worker_id: int, **fields):
    security_log.record(
        event, worker_id=worker_id, actor=user.username, client=client_address(request), ok=True, **fields
    )


def _call(fn, *args):
    try:
        return fn(*args)
    except (worker_store.WorkerError, face_engine.FaceEngineError) as e:
        raise _error(e)


@router.get("/api/workers", dependencies=[Depends(require_admin)])
def list_workers():
    store = worker_store.store
    workers = store.all()
    return {
        "face_ready": store.face_ready(),
        "limit": worker_store.gallery_limit(sum(1 for w in workers if w.active)),
        "workers": [worker_json(w) for w in workers],
    }


@router.post("/api/workers", status_code=201)
def create_worker(body: NewWorker, request: Request, user: auth.SessionUser = Depends(require_admin)):
    worker = _call(worker_store.store.create, body.employee_no, body.name, body.consent, user.username)
    _record(
        security_log.WORKER_CREATED,
        request,
        user,
        worker.id,
        employee_no=worker.employee_no,
        consent_version=worker.consent_version,
    )
    limit = worker_store.gallery_limit(worker_store.store.active_count())
    if limit["over"]:
        logger.warning(messages.FACE_GALLERY_OVER_LIMIT.format(count=limit["count"], limit=limit["tested"]))
    return worker_json(worker)


@router.post("/api/workers/{worker_id}/deactivate")
def deactivate_worker(worker_id: int, request: Request, user: auth.SessionUser = Depends(require_admin)):
    worker = _call(worker_store.store.deactivate, worker_id)
    _record(security_log.WORKER_DEACTIVATED, request, user, worker_id, delete_after=worker.delete_after)
    return worker_json(worker)


@router.post("/api/workers/{worker_id}/activate")
def activate_worker(worker_id: int, request: Request, user: auth.SessionUser = Depends(require_admin)):
    worker = _call(worker_store.store.activate, worker_id)
    _record(security_log.WORKER_ACTIVATED, request, user, worker_id)
    return worker_json(worker)


@router.delete("/api/workers/{worker_id}/face", status_code=204)
def delete_worker_face(worker_id: int, request: Request, user: auth.SessionUser = Depends(require_admin)):
    deleted = _call(worker_store.store.delete_face, worker_id)
    _record(security_log.WORKER_FACE_DELETED, request, user, worker_id, reason="manual", templates=deleted)
    return Response(status_code=204)


@router.delete("/api/workers/{worker_id}/templates/{template_id}", status_code=204)
def delete_worker_template(
    worker_id: int, template_id: int, request: Request, user: auth.SessionUser = Depends(require_admin)
):
    _call(worker_store.store.delete_template, worker_id, template_id)
    _record(security_log.WORKER_TEMPLATE_DELETED, request, user, worker_id, template_id=template_id)
    return Response(status_code=204)


def _enrollment_frame():
    """Frame kamera untuk foto pendaftaran: tidak saat gerbang memeriksa orang (foto bisa milik
    orang lain & jalur inspeksi tidak boleh diganggu), dan hanya dari kamera sungguhan."""
    if state_mgr.session is not None:
        raise worker_store.WorkerError("camera_busy", messages.WORKER_CAMERA_BUSY)
    frame = video_service.camera_frame()
    if frame is None:
        raise worker_store.WorkerError("camera_unavailable", messages.WORKER_CAMERA_UNAVAILABLE)
    return frame


@router.post("/api/workers/{worker_id}/templates", status_code=201)
def add_worker_template(
    worker_id: int, body: NewTemplate, request: Request, user: auth.SessionUser = Depends(require_admin)
):
    """Foto pendaftaran dari kamera gerbang -> templat terenkripsi. Foto hanya di memori, tidak disimpan."""
    store = worker_store.store
    if not store.face_ready():
        raise _error(worker_store.WorkerError("face_not_ready", messages.WORKER_FACE_NOT_READY))
    _call(store.check_template_target, worker_id, body.condition)
    sample = _call(lambda: face_engine.engine.enrollment_sample(_enrollment_frame()))
    template = _call(
        store.add_template, worker_id, body.condition, cfg.FACE_MODEL_VERSION, sample.vector, user.username
    )
    quality = sample.detection.quality()
    _record(
        security_log.WORKER_TEMPLATE_ADDED,
        request,
        user,
        worker_id,
        template_id=template.id,
        condition=template.condition,
        **quality,
    )
    return {**template_json(template), "quality": quality}
