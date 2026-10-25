"""T97: ketersediaan dan bukti uji harus benar untuk peran/akun/model yang diterapkan."""

# ruff: noqa: F811
from types import SimpleNamespace

import pytest

from backend.vlm import selection as selection
from backend.api import routes_vlm
from backend.config import cfg
from backend.vlm_providers import model_list, profiles
from test_vlm_selection import SAFE, UNSAFE, analyzer, client, env, fakes  # noqa: F401 (fixtures)

MODEL = {"provider": "openai", "model": "model-baru"}


@pytest.fixture
def models(client, monkeypatch):
    responses = {"openai": {MODEL["model"]}, SAFE.provider: {SAFE.model}, "ollama": {"model-lokal-uji"}}

    def fetch(provider, key, base_url, timeout):
        value = responses[provider]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(model_list, "fetch_models", fetch)
    return responses


def apply(client, primary=None, **extra):
    return client.post(
        "/api/config/vlm/apply", json={"primary": primary or MODEL, "confirm_unvalidated": True, **extra}
    )


def run_test(client, choice=None, role="primary"):
    result = client.post("/api/config/vlm/test", json={**(choice or MODEL), "role": role})
    assert result.status_code == 200 and result.json()["ok"] and result.json()["json_ok"]
    return result


def test_successful_listing_rejects_missing_model_even_after_test(client, models):
    run_test(client)
    models["openai"] = {"model-lain"}
    result = apply(client)
    assert result.status_code == 400 and result.json()["detail"]["code"] == "model_not_found"


@pytest.mark.parametrize("state", [profiles.UNVALIDATED, profiles.OUTDATED])
def test_unvalidated_or_outdated_requires_successful_test(client, models, monkeypatch, state):
    original = selection.validation_of
    monkeypatch.setattr(
        selection, "validation_of", lambda choice: (state, None) if choice.model == MODEL["model"] else original(choice)
    )
    result = apply(client)
    assert result.status_code == 400 and result.json()["detail"]["code"] == "test_required"
    run_test(client)
    assert apply(client).status_code == 200


def test_successful_test_still_requires_confirmation(client, models):
    run_test(client)
    result = apply(client, confirm_unvalidated=False)
    assert result.status_code == 400 and result.json()["detail"]["code"] == "needs_confirmation"
    assert apply(client).status_code == 200


def test_validated_or_partial_needs_no_test(client, models):
    assert selection.validation_of(selection.Choice(SAFE.provider, SAFE.model))[0] in (
        profiles.VALIDATED,
        profiles.PARTIAL,
    )
    assert apply(client, {"provider": SAFE.provider, "model": SAFE.model}, confirm_unvalidated=False).status_code == 200


def test_unsafe_is_rejected_before_any_metadata_fetch(client, models):
    result = apply(client, {"provider": UNSAFE.provider, "model": UNSAFE.model})
    assert result.status_code == 400 and result.json()["detail"]["code"] == "unsafe_model"


@pytest.mark.parametrize(
    "error", [model_list.UNREACHABLE, model_list.TIMEOUT, model_list.AUTH_FAILED, model_list.UNSUPPORTED]
)
def test_listing_failure_allows_apply_only_with_fresh_successful_test(client, models, error):
    models["openai"] = model_list.ModelListError(error)
    assert apply(client).json()["detail"]["code"] == "test_required"
    run_test(client)
    assert apply(client).status_code == 200


def test_proof_expires_and_another_role_does_not_count(client, models, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(selection, "time", SimpleNamespace(monotonic=lambda: now[0]))
    run_test(client, role="backup")
    assert apply(client).json()["detail"]["code"] == "test_required"
    run_test(client)
    now[0] += cfg.VLM_TEST_FRESH_SECONDS
    assert apply(client).json()["detail"]["code"] == "test_required"
    run_test(client)
    assert apply(client).status_code == 200


def test_failed_or_invalid_json_test_revokes_prior_success(client, models, monkeypatch):
    run_test(client)
    monkeypatch.setattr(
        routes_vlm.vlm_analyzer,
        "test_choice",
        lambda role, choice: {"ok": True, "latency_ms": 1, "json_ok": False, "error": "JSON tiruan tidak sah"},
    )
    result = client.post("/api/config/vlm/test", json={**MODEL, "role": "primary"})
    assert result.status_code == 200 and result.json()["json_ok"] is False
    assert apply(client).json()["detail"]["code"] == "test_required"


def test_different_model_test_does_not_count(client, models):
    run_test(client, {"provider": MODEL["provider"], "model": "model-lain"})
    assert apply(client).json()["detail"]["code"] == "test_required"


def test_account_change_invalidates_test_proof(client, models, monkeypatch):
    run_test(client)
    monkeypatch.setenv("OPENAI_API_KEY", "kunci-akun-baru-uji")
    assert apply(client).json()["detail"]["code"] == "test_required"


def test_backup_apply_requires_backup_proof_independent_of_primary(client, models):
    primary = {"provider": SAFE.provider, "model": SAFE.model}
    run_test(client, role="primary")
    assert apply(client, primary, backup=MODEL).json()["detail"]["code"] == "test_required"
    run_test(client, role="backup")
    assert apply(client, primary, backup=MODEL).status_code == 200


def test_provider_change_does_not_share_test_proof(client, models, monkeypatch):
    alternate = {"provider": "deepseek", "model": MODEL["model"]}
    models["deepseek"] = {alternate["model"]}
    monkeypatch.setenv("DEEPSEEK_API_KEY", "kunci-deepseek-uji")
    run_test(client)
    assert apply(client, alternate).json()["detail"]["code"] == "test_required"


def test_local_test_role_is_distinct_from_backup(client, models):
    local = {"provider": "ollama", "model": "model-lokal-uji"}
    primary = {"provider": SAFE.provider, "model": SAFE.model}
    run_test(client, local, "backup")
    assert apply(client, primary, local_fallback=local).json()["detail"]["code"] == "test_required"
    run_test(client, local, "local")
    assert apply(client, primary, local_fallback=local).status_code == 200


def test_restart_does_not_invalidate_stored_selection_without_new_apply(client, models):
    run_test(client)
    assert apply(client).status_code == 200
    selection.recent_tests = selection.RecentModelTests()
    stored = selection.stored_selection()
    assert stored is not None and stored.primary.model == MODEL["model"]
    assert apply(client).json()["detail"]["code"] == "test_required"


@pytest.mark.parametrize("role,label", [("primary", "utama"), ("backup", "cadangan"), ("local", "lokal darurat")])
@pytest.mark.parametrize("code", ["model_not_found", "test_required"])
def test_apply_error_role_labels_are_indonesian(monkeypatch, role, label, code):
    choice = selection.Choice("ollama", "model-uji")
    primary = selection.Choice(SAFE.provider, SAFE.model)
    selected = selection.Selection(
        choice if role == "primary" else primary,
        choice if role == "backup" else None,
        "dashboard",
        choice if role == "local" else None,
    )
    listing = {"source": "provider" if code == "model_not_found" else "catalog", "models": []}

    def available(provider, selected_role):
        if selected_role == role:
            return listing
        return {"source": "provider", "models": [{"model": primary.model, "available": True}]}

    monkeypatch.setattr(selection, "available_models", available)
    with pytest.raises(selection.SelectionError) as error:
        selection.check_apply_models(selected)
    assert error.value.code == code
    assert label in error.value.message
    assert f"{role} " not in error.value.message
