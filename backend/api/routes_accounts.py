"""Ganti kata sandi sendiri & kelola akun (T51). Kontrak di docs/RENCANA.md ("Rancangan T51").

Demo: semua akun `admin`, jadi kelola akun memakai `require_admin`.
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from .. import accounts, auth, messages
from .deps import client_address, require_admin, require_session
from .routes_auth import account_error

router = APIRouter()


class PasswordChange(BaseModel):
    current_password: str = ""
    new_password: str = ""


class NewAccount(BaseModel):
    username: str = ""
    password: str = ""


class PasswordReset(BaseModel):
    new_password: str = ""


def _account_json(account: accounts.Account) -> dict:
    return asdict(account)


@router.post("/api/account/password", status_code=204)
def change_own_password(body: PasswordChange, request: Request, user: auth.SessionUser = Depends(require_session)):
    if accounts.store.verify(user.username, body.current_password) is None:
        raise account_error(400, accounts.AccountError("wrong_password", messages.ACCOUNT_WRONG_PASSWORD))
    try:
        accounts.store.set_password(user.username, body.new_password)
    except accounts.AccountError as e:
        raise account_error(400, e)
    # Sesi lain akun ini berakhir; sesi yang sedang dipakai tetap
    auth.sessions.revoke_user(user.username, keep=request.cookies.get(auth.SESSION_COOKIE))
    accounts.record_event("change_password", username=user.username, actor=user.username,
                          client=client_address(request))
    return Response(status_code=204)


@router.get("/api/accounts", dependencies=[Depends(require_admin)])
def list_accounts():
    return [_account_json(a) for a in accounts.store.all()]


@router.post("/api/accounts", status_code=201)
def create_account(body: NewAccount, request: Request, user: auth.SessionUser = Depends(require_admin)):
    try:
        account = accounts.store.create(body.username, body.password)
    except accounts.AccountError as e:
        raise account_error(409 if e.code == "username_taken" else 400, e)
    accounts.record_event("create", username=account.username, actor=user.username, client=client_address(request))
    return _account_json(account)


@router.post("/api/accounts/{username}/password", status_code=204)
def reset_password(username: str, body: PasswordReset, request: Request,
                   user: auth.SessionUser = Depends(require_admin)):
    try:
        accounts.store.set_password(username, body.new_password)
    except accounts.AccountError as e:
        raise account_error(404 if e.code == "not_found" else 400, e)
    auth.sessions.revoke_user(username)
    accounts.record_event("reset_password", username=username, actor=user.username, client=client_address(request))
    return Response(status_code=204)


@router.delete("/api/accounts/{username}", status_code=204)
def delete_account(username: str, request: Request, user: auth.SessionUser = Depends(require_admin)):
    try:
        accounts.store.delete(username, actor=user.username)
    except accounts.AccountError as e:
        raise account_error(404 if e.code == "not_found" else 409, e)
    auth.sessions.revoke_user(username)
    accounts.record_event("delete", username=username, actor=user.username, client=client_address(request))
    return Response(status_code=204)
