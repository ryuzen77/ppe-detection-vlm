"""T97: daftar metadata penyedia lewat HTTP tiruan; tanpa panggilan model/cloud sungguhan."""

import json
import threading
from time import perf_counter
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend import vlm_selection as selection
from backend.api.deps import require_session
from backend.app import app
from backend.auth import SessionUser
from backend.config import cfg
from backend.vlm_providers import model_list, profiles

REAL_FETCH = model_list.fetch_models
PRIMARY_KEY, BACKUP_KEY = "kunci-uji-model-utama", "kunci-uji-model-cadangan"


@pytest.fixture
def http(monkeypatch):
    calls, controls = [], {"handle": lambda request: httpx.Response(200, json={"data": []})}

    def handle(request):
        calls.append(request)
        return controls["handle"](request)

    def make_client(base_url, headers, timeout):
        return httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=httpx.MockTransport(handle),
            follow_redirects=False,
        )

    monkeypatch.setattr(model_list, "_make_client", make_client)
    monkeypatch.setattr(model_list, "fetch_models", REAL_FETCH)
    for attr, value in {
        "VLM_PROVIDER": "gemini",
        "VLM_BACKUP_PROVIDER": "gemini",
        "VLM_API_KEY": PRIMARY_KEY,
        "VLM_BACKUP_API_KEY": BACKUP_KEY,
        "VLM_BASE_URL": "",
        "VLM_BACKUP_BASE_URL": "",
    }.items():
        monkeypatch.setattr(cfg, attr, value)
    return SimpleNamespace(calls=calls, controls=controls, client=TestClient(app))


def get(http, provider="gemini", role="primary", **params):
    response = http.client.get("/api/config/vlm/models", params={"provider": provider, "role": role, **params})
    assert response.status_code == 200
    return response.json()


def model_rows(response):
    return {entry["model"]: entry for entry in response["models"]}


def gemini_page(names, cursor=None):
    return {
        "models": [{"name": "models/" + name, "supportedGenerationMethods": ["generateContent"]} for name in names],
        **({"nextPageToken": cursor} if cursor else {}),
    }


def test_gemini_pagination_filters_generate_content_and_preserves_schema(http):
    def handle(request):
        if request.url.params.get("pageToken"):
            return httpx.Response(200, json=gemini_page(["zeta"]))
        page = gemini_page(["alpha"], "next")
        page["models"].append({"name": "models/embedding-only", "supportedGenerationMethods": ["embedContent"]})
        return httpx.Response(200, json=page)

    http.controls["handle"] = handle
    response = get(http)
    assert response["source"] == "provider" and response["error"] is None
    assert "embedding-only" not in model_rows(response)
    assert model_rows(response)["alpha"]["available"] is True
    assert len(http.calls) == 2 and http.calls[1].url.params["pageToken"] == "next"
    assert set(response) == {"provider", "role", "source", "fetched_at", "error", "models"}
    assert set(response["models"][0]) == {
        "model",
        "validated",
        "photos",
        "missed",
        "false_rejects",
        "median_seconds",
        "available",
    }
    assert all(call.method == "GET" and "key=" not in str(call.url) for call in http.calls)


@pytest.mark.parametrize("provider", ["openai", "openrouter", "qwen", "deepseek", "kimi", "vllm", "openai-compatible"])
def test_compatible_provider_model_ids_and_address(http, monkeypatch, provider):
    monkeypatch.setattr(cfg, "VLM_PROVIDER", provider)
    monkeypatch.setattr(cfg, "VLM_BASE_URL", "https://provider.example.test/custom/v1")
    http.controls["handle"] = lambda request: httpx.Response(200, json={"data": [{"id": "model-uji"}]})
    response = get(http, provider)
    assert model_rows(response)["model-uji"]["available"] is True
    assert http.calls[0].url.path == "/custom/v1/models"
    assert http.calls[0].headers["Authorization"] == "Bearer " + PRIMARY_KEY


def test_anthropic_lists_all_pages_with_native_auth(http, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PROVIDER", "anthropic")

    def handle(request):
        cursor = request.url.params.get("after_id")
        return httpx.Response(
            200,
            json={
                "data": [{"id": "second" if cursor else "first"}],
                "has_more": not cursor,
                "last_id": "first" if not cursor else "second",
            },
        )

    http.controls["handle"] = handle
    response = get(http, "anthropic")
    assert {name for name, entry in model_rows(response).items() if entry["available"]} == {"first", "second"}
    assert http.calls[0].url.path == "/v1/models" and http.calls[1].url.params["after_id"] == "first"
    assert http.calls[0].headers["x-api-key"] == PRIMARY_KEY


def test_ollama_tags_do_not_load_model_and_local_role_has_no_key(http, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PROVIDER", "ollama")
    monkeypatch.setattr(cfg, "VLM_BACKUP_PROVIDER", "ollama")
    http.controls["handle"] = lambda request: httpx.Response(200, json={"models": [{"name": "model-uji:latest"}]})
    response = get(http, "ollama", "local")
    assert response["source"] == "provider" and model_rows(response)["model-uji:latest"]["available"]
    assert http.calls[0].url.path == "/api/tags" and http.calls[0].method == "GET"
    assert "Authorization" not in http.calls[0].headers


def test_cache_is_per_role_and_refresh_bypasses_it(http):
    http.controls["handle"] = lambda request: httpx.Response(200, json=gemini_page(["model-uji"]))
    get(http)
    get(http)
    get(http, role="backup")
    assert [call.headers["x-goog-api-key"] for call in http.calls] == [PRIMARY_KEY, BACKUP_KEY]
    get(http, refresh=True)
    assert len(http.calls) == 3


def test_cache_expires_and_changes_account_without_leaking(http, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(model_list, "time", SimpleNamespace(monotonic=lambda: now[0]))
    http.controls["handle"] = lambda request: httpx.Response(200, json=gemini_page(["model-uji"]))
    get(http)
    now[0] += cfg.VLM_MODEL_LIST_CACHE_SECONDS + 1
    get(http)
    monkeypatch.setattr(cfg, "VLM_API_KEY", BACKUP_KEY)
    response = get(http)
    assert len(http.calls) == 3 and http.calls[-1].headers["x-goog-api-key"] == BACKUP_KEY
    assert PRIMARY_KEY not in json.dumps(response) and BACKUP_KEY not in json.dumps(response)


@pytest.mark.parametrize(
    "status,code", [(401, "auth_failed"), (403, "auth_failed"), (404, "unsupported"), (500, "unreachable")]
)
def test_failure_returns_catalog_without_provider_error_or_key(http, caplog, status, code):
    http.controls["handle"] = lambda request: httpx.Response(status, text="galat memuat " + PRIMARY_KEY)
    response = get(http)
    assert response["source"] == "catalog" and response["error"] == code
    assert all(entry["available"] is None for entry in response["models"])
    assert PRIMARY_KEY not in json.dumps(response) and PRIMARY_KEY not in caplog.text


def test_no_key_does_not_contact_provider(http, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert get(http)["error"] == "no_key" and not http.calls


@pytest.mark.parametrize(
    "kind,code",
    [("read", "timeout"), ("connect", "unreachable"), ("malformed", "unsupported"), ("redirect", "unsupported")],
)
def test_transport_schema_and_redirect_errors_are_safe(http, kind, code):
    def handle(request):
        if kind == "read":
            raise httpx.ReadTimeout("timeout tiruan " + PRIMARY_KEY)
        if kind == "connect":
            raise httpx.ConnectError("putus tiruan " + PRIMARY_KEY)
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "https://other.example.test/models"})
        return httpx.Response(200, json={"models": "bukan daftar"})

    http.controls["handle"] = handle
    assert get(http)["error"] == code and len(http.calls) == 1


def test_hard_timeout_does_not_wait_for_slow_http(http, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(cfg, "VLM_MODEL_LIST_TIMEOUT_SECONDS", 0.05)

    def handle(request):
        release.wait(2)
        return httpx.Response(200, json=gemini_page(["late-model"]))

    http.controls["handle"] = handle
    try:
        started = perf_counter()
        assert get(http)["error"] == "timeout"
        assert perf_counter() - started < 1
    finally:
        release.set()


def test_validated_models_first_catalog_absent_false_and_unknown_a_to_z(http):
    known = profiles.default_model("gemini")
    http.controls["handle"] = lambda request: httpx.Response(200, json=gemini_page(["zeta", "alpha"]))
    response = get(http)
    assert response["models"][0]["model"] == known
    assert model_rows(response)[known]["available"] is False
    assert [entry["model"] for entry in response["models"] if entry["available"]] == ["alpha", "zeta"]


def test_admin_only_and_invalid_role_rejected(http):
    async def operator(request: Request):
        return SessionUser("operator-uji", "operator")

    assert (
        http.client.get("/api/config/vlm/models", params={"provider": "gemini", "role": "invalid"}).status_code == 422
    )
    app.dependency_overrides[require_session] = operator
    assert (
        http.client.get("/api/config/vlm/models", params={"provider": "gemini", "role": "primary"}).status_code == 403
    )


def test_successful_body_echoing_key_falls_back_without_exposing_it(http, caplog):
    http.controls["handle"] = lambda request: httpx.Response(200, json=gemini_page([PRIMARY_KEY]))
    response = get(http)
    assert response["source"] == "catalog" and response["error"] == "unsupported"
    assert PRIMARY_KEY not in json.dumps(response) and PRIMARY_KEY not in caplog.text


def test_repeated_pagination_cursor_falls_back_instead_of_hanging(http):
    http.controls["handle"] = lambda request: httpx.Response(200, json=gemini_page(["alpha"], "same-cursor"))
    assert get(http)["error"] == "unsupported" and len(http.calls) == 2


def test_concurrent_same_role_requests_share_inflight_fetch(http):
    from concurrent.futures import ThreadPoolExecutor

    entered, release = threading.Event(), threading.Event()

    def handle(request):
        entered.set()
        release.wait(2)
        return httpx.Response(200, json=gemini_page(["model-uji"]))

    http.controls["handle"] = handle
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(selection.available_models, "gemini", "primary")
        assert entered.wait(1)
        second = executor.submit(selection.available_models, "gemini", "primary")
        release.set()
        assert first.result(timeout=2)["source"] == second.result(timeout=2)["source"] == "provider"
    assert len(http.calls) == 1


def test_refresh_after_timed_out_fetch_starts_new_request(http, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(cfg, "VLM_MODEL_LIST_TIMEOUT_SECONDS", 0.05)

    def handle(request):
        release.wait(2)
        return httpx.Response(200, json=gemini_page(["model-uji"]))

    http.controls["handle"] = handle
    try:
        assert get(http)["error"] == "timeout"
        release.set()
        pending = selection.model_lists._pending[("gemini", selection.ROLE_PRIMARY)]
        pending[1].result(timeout=1)
        assert get(http, refresh=True)["source"] == "provider"
        assert len(http.calls) == 2
    finally:
        release.set()


def test_compatible_pagination_does_not_mistake_next_page_model_as_missing(http, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PROVIDER", "openai")

    def handle(request):
        cursor = request.url.params.get("after")
        return httpx.Response(200, json={"data": [{"id": "zeta" if cursor else "alpha"}], "has_more": not cursor})

    http.controls["handle"] = handle
    response = get(http, "openai")
    assert model_rows(response)["zeta"]["available"] is True
    assert http.calls[1].url.params["after"] == "alpha"
