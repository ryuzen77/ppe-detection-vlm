"""Manajemen divisi (departments) dan perusahaan kontraktor (companies) (T79).

Semua endpoint khusus admin. Perubahan dicatat di security log.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import auth, security_log, worker_store
from .deps import client_address, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

_STATUS = {
    "invalid_kind": 404,
    "not_found": 404,
    "invalid_name": 400,
    "name_taken": 409,
    "in_use": 409,
    "builtin": 409,
}


class OrgBody(BaseModel):
    name: str = ""


def _error(error: worker_store.WorkerError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(error.code, 400),
        detail={"code": error.code, "message": error.message},
    )


def _call(fn, *args):
    try:
        return fn(*args)
    except worker_store.WorkerError as e:
        raise _error(e)


@router.get("/api/org/{kind}", dependencies=[Depends(require_admin)])
def list_org(kind: str):
    return _call(worker_store.store.list_org, kind)


@router.post("/api/org/{kind}", status_code=201)
def create_org(kind: str, body: OrgBody, request: Request, user: auth.SessionUser = Depends(require_admin)):
    result = _call(worker_store.store.create_org, kind, body.name)
    security_log.record(
        f"org_{kind}_created",
        actor=user.username,
        client=client_address(request),
        ok=True,
        kind=kind,
        id=result["id"],
        name=result["name"],
    )
    return result


@router.patch("/api/org/{kind}/{org_id}")
def update_org(kind: str, org_id: int, body: OrgBody, request: Request, user: auth.SessionUser = Depends(require_admin)):
    result = _call(worker_store.store.update_org, kind, org_id, body.name)
    security_log.record(
        f"org_{kind}_updated",
        actor=user.username,
        client=client_address(request),
        ok=True,
        kind=kind,
        id=org_id,
        name=result["name"],
    )
    return result


@router.delete("/api/org/{kind}/{org_id}", status_code=204)
def delete_org(kind: str, org_id: int, request: Request, user: auth.SessionUser = Depends(require_admin)):
    _call(worker_store.store.delete_org, kind, org_id)
    security_log.record(
        f"org_{kind}_deleted",
        actor=user.username,
        client=client_address(request),
        ok=True,
        kind=kind,
        id=org_id,
    )
    return Response(status_code=204)
