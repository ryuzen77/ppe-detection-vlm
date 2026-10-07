"""Status sesi, setup admin pertama, login, dan logout (T30, akun sejak T51).

Satu-satunya router tanpa `require_session`. Kontrak di docs/RENCANA.md ("Rancangan T51").
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import accounts, auth, messages, security_log, startup_checks
from ..config import cfg
from .deps import client_address

router = APIRouter()


class Credentials(BaseModel):
    username: str = ""
    password: str = ""


def account_error(status: int, error: accounts.AccountError) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": error.code, "message": error.message})


def _user_json(user: Optional[auth.SessionUser]) -> Optional[dict]:
    return None if user is None else {"username": user.username, "role": user.role}


def _start_session(response: Response, account: accounts.Account) -> dict:
    user = auth.SessionUser(account.username, account.role)
    lifetime = auth.SessionStore.lifetime_seconds()
    response.set_cookie(auth.SESSION_COOKIE, auth.sessions.create(user), max_age=int(lifetime),
                        httponly=True, samesite="strict", path="/")
    return {"user": _user_json(user), "expires_in_s": round(lifetime)}


def _is_local(request: Request) -> bool:
    return client_address(request) in cfg.LOCALHOST_IPS


@router.get("/api/session")
def session_status(request: Request):
    found = auth.sessions.lookup(request.cookies.get(auth.SESSION_COOKIE))
    return {"authenticated": found is not None, "setup_required": accounts.store.count() == 0,
            "setup_allowed": _is_local(request), "user": _user_json(found[0] if found else None),
            "expires_in_s": round(found[1]) if found else None}


@router.post("/api/setup", status_code=201)
def setup(body: Credentials, request: Request, response: Response):
    """Akun admin pertama: hanya dari mesin gerbang dan hanya selama belum ada akun."""
    if not _is_local(request):
        security_log.record(security_log.SETUP_DENIED, client=client_address(request), ok=False)
        raise account_error(403, accounts.AccountError(
            "setup_local_only", messages.ACCOUNT_SETUP_LOCAL_ONLY.format(port=cfg.PORT)))
    try:
        account = accounts.store.create(body.username, body.password, only_if_empty=True)
    except accounts.AccountError as e:
        raise account_error(409 if e.code == "setup_done" else 400, e)
    accounts.record_event("setup", username=account.username, actor=account.username, client=client_address(request))
    startup_checks.account_created()
    return _start_session(response, account)


@router.post("/api/login")
def login(body: Credentials, request: Request, response: Response):
    client, username = client_address(request), body.username.strip().lower()
    keys = auth.limiter_keys(client, username)
    wait = auth.login_limiter.retry_after(*keys)
    if wait > 0:
        return JSONResponse(status_code=429, content={"detail": messages.API_LOGIN_LOCKED,
                                                      "retry_after_s": round(wait)})
    account = accounts.store.authenticate(username, body.password)
    accounts.record_event("login", username=username, client=client, ok=account is not None)
    if account is None:
        auth.login_limiter.record_failure(*keys)
        locked_for = auth.login_limiter.retry_after(*keys)
        if locked_for > 0:
            # Sekali per penguncian (bukan per percobaan selama terkunci): tebakan
            # beruntun tidak membanjiri security log
            security_log.record(security_log.LOCKOUT_STARTED, username=username, client=client,
                                seconds=round(locked_for), ok=False)
        raise account_error(401, accounts.AccountError("login_failed", messages.API_LOGIN_FAILED))
    auth.login_limiter.record_success(*keys)
    return _start_session(response, account)


@router.post("/api/logout", status_code=204)
def logout(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    user = auth.sessions.user(token)
    auth.sessions.revoke(token)
    if user is not None:
        accounts.record_event("logout", username=user.username, actor=user.username, client=client_address(request))
    response = Response(status_code=204)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response
