"""Data pekerja & templat wajah untuk admin (T34b1, foto pendaftaran T34b2). Kontrak: docs/RENCANA.md, Rancangan T34 -> T34b.

Semua endpoint khusus admin. Jawaban tidak pernah memuat embedding maupun foto;
setiap perubahan dicatat di security log (siapa, dari mana, pekerja mana).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from typing import Optional

from pydantic import BaseModel

from .. import auth, face_engine, face_identity, messages, security_log, worker_store, worker_voice
from ..audio_engine import audio_player
from ..config import cfg
from ..audit.report_manager import report_mgr
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
    "camera_low_resolution": 409,
    "no_face": 422,
    "multiple_faces": 422,
    "face_too_small": 422,
    "face_too_close": 422,
    "face_matches_other": 409,
    "enrollment_inactive": 409,
    "invalid_prompt": 400,
    "face_not_ready": 503,
    "invalid_department": 400,
    "invalid_company": 400,
    "employee_no_locked": 409,
}


class NewWorker(BaseModel):
    employee_no: Optional[str] = ""
    name: str = ""
    consent: bool = False
    nickname: str = ""  # T34d: wajib (nama yang diucapkan)
    gender: str = ""  # T34d: "male" | "female", wajib (sapaan Pak/Bu)
    department_id: Optional[int] = None
    company_id: Optional[int] = None


class WorkerUpdate(BaseModel):
    """PATCH: hanya kolom yang dikirim yang diubah (T34d, T79)."""

    nickname: Optional[str] = None
    gender: Optional[str] = None
    department_id: Optional[int] = None
    company_id: Optional[int] = None
    employee_no: Optional[str] = None


class NewTemplate(BaseModel):
    condition: str = ""


class EnrollmentPrompt(BaseModel):
    prompt: str = ""


def _error(error: worker_store.WorkerError | face_engine.FaceEngineError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(error.code, 400), detail={"code": error.code, "message": error.message}
    )


def worker_json(worker: worker_store.Worker, last_seen: object = ...) -> dict:
    if last_seen is ...:
        last_seen = report_mgr.get_last_seen(worker.id)
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
        "nickname": worker.nickname,
        "gender": worker.gender,
        "salutation": worker.salutation,
        "voice_ready": worker_voice.voice_ready(worker.id),
        "department": {"id": worker.department.id, "name": worker.department.name} if worker.department else None,
        "company": {"id": worker.company.id, "name": worker.company.name}
        if worker.company
        else {"id": 0, "name": cfg.WORKER_DEFAULT_COMPANY},
        "last_seen": last_seen,
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
def list_workers(q: Optional[str] = None, active: Optional[str] = None):
    store = worker_store.store
    active_filter: Optional[bool] = None
    if active is not None and active.strip() != "":
        val = active.strip().lower()
        if val in ("true", "1"):
            active_filter = True
        elif val in ("false", "0"):
            active_filter = False
    workers = store.all(q=q, active=active_filter)
    last_seens = report_mgr.get_last_seen_batch([w.id for w in workers])
    return {
        "face_ready": store.face_ready(),
        "limit": worker_store.gallery_limit(store.active_count()),
        "workers": [worker_json(w, last_seen=last_seens.get(w.id)) for w in workers],
    }


@router.get("/api/workers/next-employee-no", dependencies=[Depends(require_admin)])
def next_employee_no():
    return {"employee_no": worker_store.store.next_employee_no()}


@router.post("/api/workers", status_code=201)
def create_worker(body: NewWorker, request: Request, user: auth.SessionUser = Depends(require_admin)):
    worker = _call(
        lambda: worker_store.store.create(
            body.employee_no or "",
            body.name,
            body.consent,
            user.username,
            nickname=body.nickname,
            gender=body.gender,
            department_id=body.department_id,
            company_id=body.company_id,
        )
    )
    worker_voice.request(worker)
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
    worker_voice.delete([worker_id])  # MP3 nama ikut terhapus bersama data wajah (T34d)
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


def _restore_voice(worker_id: int) -> None:
    """Hapus data wajah ikut menghapus MP3 nama (T34d); wajah yang didaftarkan ulang harus dipanggil
    namanya lagi (uji nyata 19-10: dikenali skor 0,85 tetapi suara umum karena MP3 sudah terhapus)."""
    if not worker_voice.voice_ready(worker_id):
        worker_voice.request(worker_store.store.get(worker_id))


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
    _call(_reject_other_workers_face, worker_id, sample.vector)
    template = _call(
        store.add_template, worker_id, body.condition, cfg.FACE_MODEL_VERSION, sample.vector, user.username
    )
    _restore_voice(worker_id)
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


@router.post("/api/workers/enrollment")
def hold_enrollment(request: Request, user: auth.SessionUser = Depends(require_admin)):
    """Mode pendaftaran wajah (T75): gerbang jeda selama modal foto terbuka. Dipanggil saat modal
    dibuka lalu berulang sebagai denyut; tanpa denyut jeda selesai sendiri (ENROLLMENT_HOLD_SECONDS)."""
    if state_mgr.hold_for_enrollment():
        security_log.record(
            security_log.ENROLLMENT_STARTED, actor=user.username, client=client_address(request), ok=True
        )
    return {"active": True, "hold_s": cfg.ENROLLMENT_HOLD_SECONDS}


def _reject_other_workers_face(worker_id: int, vector) -> None:
    similar = face_identity.identifier.similar_worker(vector, worker_id)
    if similar is not None:
        employee_no, score = similar
        raise worker_store.WorkerError(
            "face_matches_other", messages.WORKER_FACE_MATCHES_OTHER.format(employee_no=employee_no, score=score)
        )


def _require_enrollment() -> None:
    """Pratinjau & suara pendaftaran hanya selama gerbang jeda (kamera gerbang bukan alat pantau)."""
    if not state_mgr.enrollment_active():
        raise worker_store.WorkerError("enrollment_inactive", messages.WORKER_ENROLLMENT_INACTIVE)


@router.get("/api/workers/enrollment/plan", dependencies=[Depends(require_admin)])
def enrollment_plan():
    """Rencana pendaftaran terpandu (T76): urutan kondisi & arah kepala dari config, bukan salinan di UI."""
    return {
        "shots_per_condition": cfg.ENROLLMENT_SHOTS_PER_CONDITION,
        "poses": list(cfg.ENROLLMENT_POSES),
        "condition_sets": {k: list(v) for k, v in cfg.ENROLLMENT_CONDITION_SETS.items()},
        "interocular": {"min_px": cfg.FACE_MIN_INTEROCULAR_PX, "max_ratio": cfg.ENROLLMENT_MAX_INTEROCULAR_RATIO},
        "min_frame_height": cfg.ENROLLMENT_MIN_FRAME_HEIGHT,
        "prompts": messages.ENROLLMENT_PROMPT_KEYS,
    }


@router.get("/api/workers/enrollment/preview", dependencies=[Depends(require_admin)])
def enrollment_preview():
    """Indikator jarak sebelum memotret: hanya deteksi wajah, tanpa embedding & tanpa disimpan."""
    _call(_require_enrollment)
    frame = video_service.camera_frame()
    if frame is None:
        raise _error(worker_store.WorkerError("camera_unavailable", messages.WORKER_CAMERA_UNAVAILABLE))
    detections = face_engine.engine.detect(frame)
    return face_engine.enrollment_fit(detections, frame.shape[0])


@router.post("/api/workers/enrollment/prompt", status_code=204, dependencies=[Depends(require_admin)])
def enrollment_prompt(body: EnrollmentPrompt):
    """Petunjuk suara lewat speaker gerbang untuk pekerja yang berdiri jauh dari layar."""
    _call(_require_enrollment)
    if body.prompt not in messages.ENROLLMENT_VOICE_TEXTS:
        raise _error(
            worker_store.WorkerError("invalid_prompt", messages.WORKER_INVALID_PROMPT.format(prompt=body.prompt))
        )
    # Tidak `urgent`: petunjuk berurutan (pakai helm, lalu arah kepala) diantrekan, bukan saling memotong
    audio_player.play(body.prompt)
    return Response(status_code=204)


@router.delete("/api/workers/enrollment", status_code=204)
def release_enrollment(request: Request, user: auth.SessionUser = Depends(require_admin)):
    if state_mgr.release_enrollment():
        security_log.record(security_log.ENROLLMENT_ENDED, actor=user.username, client=client_address(request), ok=True)
    return Response(status_code=204)


def _log_worker_update(
    request: Request,
    user: auth.SessionUser,
    worker_id: int,
    fields: set[str],
) -> None:
    _record(security_log.WORKER_UPDATED, request, user, worker_id, fields=list(fields))


@router.patch("/api/workers/{worker_id}")
def update_worker(
    worker_id: int,
    body: WorkerUpdate,
    request: Request,
    user: auth.SessionUser = Depends(require_admin),
):
    """Ubah profil, divisi, kontraktor (T34d, T79, T84)."""
    fs = body.model_fields_set
    dep_arg = body.department_id if "department_id" in fs else ...
    worker = _call(
        lambda: worker_store.store.update_worker(
            worker_id,
            nickname=body.nickname if "nickname" in fs else None,
            gender=body.gender if "gender" in fs else None,
            department_id=dep_arg,
            company_id=body.company_id if "company_id" in fs else None,
            employee_no=body.employee_no if "employee_no" in fs else None,
        )
    )
    worker_voice.request(worker)
    _log_worker_update(request, user, worker_id, fs)
    return worker_json(worker)


@router.get("/api/workers/{worker_id}/inspections", dependencies=[Depends(require_admin)])
def worker_inspections(
    worker_id: int,
    limit: int = 50,
    before: Optional[int] = None,
):
    """Riwayat pemeriksaan pekerja berhalaman urut terbaru (T79)."""
    _call(lambda: worker_store.store.get(worker_id))
    return report_mgr.get_worker_inspections(worker_id, limit=limit, before=before)
