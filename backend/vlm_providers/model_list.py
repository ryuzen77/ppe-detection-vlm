"""Daftar model: HTTP metadata saja, tenggat total, cache per akun/peran tanpa key di keluaran."""

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus

import httpx

from ..config import cfg
from . import profiles

NO_KEY, UNREACHABLE, TIMEOUT, UNSUPPORTED, AUTH_FAILED = (
    "no_key",
    "unreachable",
    "timeout",
    "unsupported",
    "auth_failed",
)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class ModelListError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def credential_signature(api_key: str, base_url: str) -> str:
    return hashlib.sha256(repr((api_key, base_url)).encode()).hexdigest()


def get_json(client: httpx.Client, path: str, remaining, params=None) -> dict:
    response = client.get(path, params=params, timeout=remaining())
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ModelListError(UNSUPPORTED)
    return data


def pages(client, path, remaining, parse_page, cursor_param: str) -> set[str]:
    names, visited, params = set(), set(), {}
    while True:
        found, cursor = parse_page(get_json(client, path, remaining, params))
        names.update(found)
        if not cursor:
            return names
        if cursor in visited:
            raise ModelListError(UNSUPPORTED)
        visited.add(cursor)
        params = {cursor_param: cursor}


def data_ids(data: dict) -> list[str]:
    rows = data.get("data")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in rows
    ):
        raise ModelListError(UNSUPPORTED)
    return [row["id"] for row in rows]


def _make_client(base_url: str, headers: dict, timeout: float):
    # Tidak mengikuti redirect: header key tidak boleh diteruskan ke host lain.
    return httpx.Client(base_url=base_url, headers=headers, timeout=timeout, follow_redirects=False)


def fetch_models(provider: str, api_key: str, base_url: str, timeout: float) -> set[str]:
    from . import anthropic, gemini, openai_compatible

    profile = profiles.get_profile(provider)
    if profile is None:
        raise ModelListError(UNSUPPORTED)
    if not profile.is_local and not api_key:
        raise ModelListError(NO_KEY)
    headers = {}
    if profile.api == profiles.API_GEMINI:
        base_url, loader = base_url or GEMINI_BASE_URL, gemini.list_models
        headers = {"x-goog-api-key": api_key}
    elif profile.api == profiles.API_ANTHROPIC:
        base_url, loader = base_url or profile.base_url, anthropic.list_models
        headers = {"x-api-key": api_key, "anthropic-version": anthropic.API_VERSION}
    else:
        base_url, loader = base_url or profile.base_url, openai_compatible.list_models
        headers = {"Authorization": "Bearer " + api_key} if api_key else {}
    if not base_url:
        raise ModelListError(UNSUPPORTED)
    deadline = time.monotonic() + timeout
    with _make_client(base_url, headers, timeout) as client:
        names = loader(client, lambda: _remaining(deadline), provider)
    if api_key and any(api_key in name for name in names):
        raise ModelListError(UNSUPPORTED)
    return names


def _remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise ModelListError(TIMEOUT)
    return value


def _error_code(error: Exception) -> str:
    if isinstance(error, ModelListError):
        return error.code
    if isinstance(error, (httpx.TimeoutException, FutureTimeout)):
        return TIMEOUT
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            return AUTH_FAILED
        return (
            UNSUPPORTED
            if HTTPStatus.MULTIPLE_CHOICES <= status < HTTPStatus.BAD_REQUEST
            or status in (HTTPStatus.NOT_FOUND, HTTPStatus.METHOD_NOT_ALLOWED, HTTPStatus.NOT_IMPLEMENTED)
            else UNREACHABLE
        )
    return UNREACHABLE if isinstance(error, (httpx.TransportError, OSError)) else UNSUPPORTED


@dataclass(frozen=True)
class ModelListResult:
    names: frozenset[str]
    error: str | None
    fetched_at: str
    expires: float
    signature: str


class ModelListCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[tuple, ModelListResult] = {}
        self._pending: dict[tuple, tuple] = {}
        self._executor = ThreadPoolExecutor(max_workers=len(profiles.PROFILES), thread_name_prefix="VLM_Models")

    def get(self, provider: str, role: str, api_key: str, base_url: str, refresh: bool = False) -> ModelListResult:
        key, signature = (provider, role), credential_signature(api_key, base_url)
        with self._lock:
            cached = self._entries.get(key)
            if not refresh and cached and cached.signature == signature and cached.expires > time.monotonic():
                return cached
            pending = self._pending.get(key)
            if pending is None or pending[0] != signature or (refresh and pending[1].done()):
                pending = (
                    signature,
                    self._executor.submit(
                        fetch_models, provider, api_key, base_url, cfg.VLM_MODEL_LIST_TIMEOUT_SECONDS
                    ),
                )
                self._pending[key] = pending
        try:
            names = frozenset(pending[1].result(timeout=cfg.VLM_MODEL_LIST_TIMEOUT_SECONDS))
            error = None
        except Exception as failure:
            names, error = frozenset(), _error_code(failure)
        ttl = cfg.VLM_MODEL_LIST_ERROR_CACHE_SECONDS if error else cfg.VLM_MODEL_LIST_CACHE_SECONDS
        result = ModelListResult(
            names, error, datetime.now().isoformat(timespec="seconds"), time.monotonic() + ttl, signature
        )
        with self._lock:
            if self._pending.get(key) is pending:
                self._entries[key] = result
                if pending[1].done():
                    del self._pending[key]
        return result

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=True)
