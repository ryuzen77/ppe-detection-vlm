"""Login, logout, dan status sesi admin (T30). Kontrak di docs/RENCANA.md."""
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .. import auth, messages

router = APIRouter()


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.get("/api/session")
async def session_status(request: Request):
    left = auth.sessions.remaining(request.cookies.get(auth.SESSION_COOKIE))
    return {"authenticated": not auth.auth_required() or left is not None,
            "auth_required": auth.auth_required(),
            "expires_in_s": None if left is None else round(left)}


@router.post("/api/login")
async def login(request: Request, response: Response):
    client = _client(request)
    wait = auth.login_limiter.retry_after(client)
    if wait > 0:
        return JSONResponse(status_code=429, content={"detail": messages.API_LOGIN_LOCKED,
                                                      "retry_after_s": round(wait)})
    body = await request.json()
    if not isinstance(body, dict) or not auth.password_matches(str(body.get("password", ""))):
        auth.login_limiter.record_failure(client)
        raise HTTPException(status_code=401, detail=messages.API_LOGIN_FAILED)
    auth.login_limiter.record_success(client)
    lifetime = auth.SessionStore.lifetime_seconds()
    response.set_cookie(auth.SESSION_COOKIE, auth.sessions.create(), max_age=int(lifetime),
                        httponly=True, samesite="strict", path="/")
    return {"expires_in_s": round(lifetime)}


@router.post("/api/logout", status_code=204)
async def logout(request: Request):
    auth.sessions.revoke(request.cookies.get(auth.SESSION_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response
