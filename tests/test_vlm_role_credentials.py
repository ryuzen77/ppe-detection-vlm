"""T98: key/alamat per peran, isolasi penyedia, dan keluaran tanpa rahasia (semua tiruan)."""

# ruff: noqa: F811
import json
from statistics import median
from time import perf_counter

import pytest

from backend import ppe_rules
from backend.vlm import selection as selection
from backend.api import routes_vlm
from backend.api_monitor import ROLE_EMERGENCY, api_monitor
from backend.config import cfg
from backend.vlm.analyzer import ROLE_BACKUP, ROLE_PRIMARY, VLMAnalyzer
from backend.vlm.selection import Choice, Selection, SelectionError
from helpers import person_crop
from test_vlm_selection import FakeProvider, analyzer, client, env, fakes  # noqa: F401 (fixtures)

PRIMARY_KEY = "kunci-uji-utama"
BACKUP_KEY = "kunci-uji-cadangan"
PROVIDER_KEY = "kunci-uji-penyedia"
PRIMARY_URL = "https://primary.example.test/v1"
BACKUP_URL = "https://backup.example.test/v1"
CHOICE = Choice("gemini", "model-uji")


@pytest.fixture
def role_env(env, monkeypatch):
    for name, value in {
        "VLM_PROVIDER": "gemini",
        "VLM_BACKUP_PROVIDER": "gemini",
        "VLM_API_KEY": PRIMARY_KEY,
        "VLM_BACKUP_API_KEY": BACKUP_KEY,
        "VLM_MODEL": CHOICE.model,
        "VLM_BACKUP_MODEL": CHOICE.model,
        "VLM_BASE_URL": PRIMARY_URL,
        "VLM_BACKUP_BASE_URL": BACKUP_URL,
    }.items():
        monkeypatch.setattr(cfg, name, value)
    monkeypatch.setenv("GEMINI_API_KEY", PROVIDER_KEY)


@pytest.fixture
def role_analyzer(role_env, fakes):
    instance = VLMAnalyzer()
    instance.start()
    yield instance
    instance._stop_services()
    for engine in instance._engines():
        engine.close()


def test_same_provider_uses_distinct_role_keys_and_urls(role_analyzer):
    assert role_analyzer.primary.api_key == role_analyzer.primary.provider.api_key == PRIMARY_KEY
    assert role_analyzer.backup.api_key == role_analyzer.backup.provider.api_key == BACKUP_KEY
    assert role_analyzer.primary.base_url == PRIMARY_URL
    assert role_analyzer.backup.base_url == BACKUP_URL


@pytest.mark.parametrize("role", [ROLE_PRIMARY, ROLE_BACKUP])
def test_changed_provider_uses_its_own_key_and_default_url(role_env, monkeypatch, role):
    monkeypatch.setenv("OPENAI_API_KEY", PROVIDER_KEY)
    assert selection.api_key_for("openai", role) == PROVIDER_KEY
    assert selection.base_url_for("openai", role) == ""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert selection.api_key_for("openai", role) == ""


@pytest.mark.parametrize("role", [ROLE_PRIMARY, ROLE_BACKUP])
def test_empty_role_key_falls_back_only_to_provider_key(role_env, monkeypatch, role):
    field = "VLM_API_KEY" if role == ROLE_PRIMARY else "VLM_BACKUP_API_KEY"
    monkeypatch.setattr(cfg, field, "")
    assert selection.api_key_for("gemini", role) == PROVIDER_KEY
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert selection.api_key_for("gemini", role) == ""


def test_backup_override_never_used_by_primary_even_for_backup_provider(role_env, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PROVIDER", "openai")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert selection.api_key_for("gemini", ROLE_PRIMARY) == ""
    assert selection.base_url_for("gemini", ROLE_PRIMARY) == ""
    assert selection.api_key_for("gemini", ROLE_BACKUP) == BACKUP_KEY


@pytest.mark.parametrize("role", [ROLE_PRIMARY, ROLE_BACKUP])
def test_validation_requires_key_for_the_selected_role(role_env, monkeypatch, role):
    field = "VLM_API_KEY" if role == ROLE_PRIMARY else "VLM_BACKUP_API_KEY"
    monkeypatch.setattr(cfg, field, "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(SelectionError, match=".") as error:
        selection.check_choice(CHOICE, True, role)
    assert error.value.code == "missing_key"
    with pytest.raises(SelectionError):
        selection.check_selection(Selection(CHOICE, CHOICE, "dashboard"), True)


def test_backup_only_key_is_visible_in_catalog_but_not_accepted_for_primary(role_env, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    catalog = selection.provider_catalog([CHOICE])
    entry = next(item for item in catalog if item["name"] == "gemini")
    assert entry["has_key"] is True and entry["missing"] is None
    selection.check_choice(CHOICE, True, ROLE_BACKUP)
    with pytest.raises(SelectionError):
        selection.check_choice(CHOICE, True, ROLE_PRIMARY)


@pytest.mark.parametrize(
    "role,field",
    [
        (ROLE_PRIMARY, "VLM_API_KEY"),
        (ROLE_BACKUP, "VLM_BACKUP_API_KEY"),
        (ROLE_PRIMARY, "VLM_BASE_URL"),
        (ROLE_BACKUP, "VLM_BACKUP_BASE_URL"),
    ],
)
def test_matches_detects_only_its_own_role_changes(role_analyzer, monkeypatch, role, field):
    engine = role_analyzer.primary if role == ROLE_PRIMARY else role_analyzer.backup
    other = role_analyzer.backup if role == ROLE_PRIMARY else role_analyzer.primary
    assert engine.matches(CHOICE) and other.matches(CHOICE)
    monkeypatch.setattr(cfg, field, "nilai-uji-baru")
    assert not engine.matches(CHOICE) and other.matches(CHOICE)


def test_dashboard_switch_keeps_role_credentials_isolated(role_analyzer, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", PROVIDER_KEY)
    fresh = Selection(Choice("openai", "model-uji"), CHOICE, "dashboard")
    selection.check_selection(fresh, True)
    role_analyzer.apply_selection(fresh, lambda: True)
    assert role_analyzer.primary.provider.api_key == PROVIDER_KEY
    assert role_analyzer.primary.base_url == ""
    assert role_analyzer.backup.provider.api_key == BACKUP_KEY


def test_backup_test_endpoint_uses_backup_key(role_analyzer, monkeypatch, client, fakes):
    monkeypatch.setattr(routes_vlm, "vlm_analyzer", role_analyzer)
    monkeypatch.setattr(cfg, "VLM_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    response = client.post(
        "/api/config/vlm/test", json={"provider": CHOICE.provider, "model": CHOICE.model, "role": "backup"}
    )
    assert response.status_code == 200 and response.json()["ok"] is True
    assert fakes[0][-1].api_key == BACKUP_KEY
    response = client.post(
        "/api/config/vlm/test", json={"provider": CHOICE.provider, "model": CHOICE.model, "role": "primary"}
    )
    assert response.status_code == 400 and response.json()["detail"]["code"] == "missing_key"


def test_ping_uses_each_engine_account_without_keys_in_payload(role_analyzer, monkeypatch):
    used = []
    original = FakeProvider.generate

    def generate(self, *args):
        used.append(self.api_key)
        return original(self, *args)

    monkeypatch.setattr(FakeProvider, "generate", generate)
    response = role_analyzer.ping_api()
    assert used == [PRIMARY_KEY, BACKUP_KEY]
    assert response["engines"][0]["ok"] and response["engines"][1]["ok"]
    for key in (PRIMARY_KEY, BACKUP_KEY):
        assert key not in json.dumps(response)


def test_emergency_local_never_inherits_role_credentials(role_env, fakes, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PROVIDER", "ollama")
    monkeypatch.setattr(cfg, "VLM_BACKUP_PROVIDER", "ollama")
    engine = VLMAnalyzer._new_engine(ROLE_EMERGENCY, Choice("ollama", "model-uji"))
    try:
        assert isinstance(engine.provider, FakeProvider)
        assert engine.api_key == engine.provider.api_key == ""
        assert engine.base_url == "" and engine.matches(engine.choice())
    finally:
        engine.close()


def test_primary_failure_reaches_other_account_without_secret_in_logs_or_telemetry(role_analyzer, monkeypatch, caplog):
    def fail(*args):
        raise RuntimeError("kuota tiruan habis untuk " + PRIMARY_KEY)

    monkeypatch.setattr(role_analyzer.primary.provider, "generate", fail)
    result = role_analyzer.analyze_person(person_crop())
    assert result.decided_by == ROLE_BACKUP and not result.is_system_unavailable
    exported = json.dumps(
        {
            "result": result.model_dump(),
            "monitor": api_monitor.get_status(),
            "selection": role_analyzer.current_selection(),
            "info": role_analyzer.provider_info(),
        }
    )
    for key in (PRIMARY_KEY, BACKUP_KEY):
        assert key not in caplog.text and key not in exported


def test_http_adapter_receives_url_and_key_for_its_role(role_env, fakes, monkeypatch):
    from backend.vlm import engine as module

    monkeypatch.setattr(cfg, "VLM_PROVIDER", "openai")
    monkeypatch.setattr(cfg, "VLM_BACKUP_PROVIDER", "openai")
    received, factory = [], module.create_provider

    def create(name, api_key, model, base_url="", **options):
        received.append((api_key, base_url))
        return factory(name, api_key, model, base_url=base_url, **options)

    monkeypatch.setattr(module, "create_provider", create)
    for role in (ROLE_PRIMARY, ROLE_BACKUP):
        engine = VLMAnalyzer._new_engine(role, Choice("openai", "model-uji"))
        engine.close()
    assert received == [(PRIMARY_KEY, PRIMARY_URL), (BACKUP_KEY, BACKUP_URL)]


def test_custom_url_validation_is_role_specific(role_env, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PROVIDER", "openai-compatible")
    monkeypatch.setattr(cfg, "VLM_BACKUP_PROVIDER", "openai-compatible")
    monkeypatch.setattr(cfg, "VLM_BASE_URL", "")
    choice = Choice("openai-compatible", "model-uji")
    selection.check_choice(choice, True, ROLE_BACKUP)
    with pytest.raises(SelectionError) as error:
        selection.check_choice(choice, True, ROLE_PRIMARY)
    assert error.value.code == "missing_base_url"


def test_reapplying_after_backup_key_rotation_rebuilds_only_backup(role_analyzer, monkeypatch):
    old_primary, old_backup = role_analyzer.primary, role_analyzer.backup
    monkeypatch.setattr(cfg, "VLM_BACKUP_API_KEY", PROVIDER_KEY)
    role_analyzer.apply_selection(Selection(CHOICE, CHOICE, "dashboard"), lambda: True)
    assert role_analyzer.primary is old_primary and role_analyzer.backup is not old_backup
    assert role_analyzer.backup.provider.api_key == PROVIDER_KEY


@pytest.mark.parametrize("operation", ["build", "warm_up", "confirmation"])
def test_provider_errors_never_export_key_in_log_or_engine_info(role_env, fakes, monkeypatch, caplog, operation):
    engine = VLMAnalyzer._new_engine(ROLE_BACKUP, CHOICE)

    def fail(*args, **kwargs):
        raise RuntimeError("key tiruan ditolak: " + BACKUP_KEY)

    try:
        if operation == "build":
            monkeypatch.setattr("backend.vlm.engine.create_provider", fail)
            assert engine.build() is False
        elif operation == "warm_up":
            monkeypatch.setattr(engine.provider, "warm_up", fail)
            engine.warm_up()
        else:
            monkeypatch.setattr(engine.provider, "generate", fail)
            item = next(item for item in ppe_rules.get_items() if item.prohibited)
            with pytest.raises(RuntimeError):
                VLMAnalyzer._ask_confirmation(engine, b"gambar-tiruan", item)
        assert BACKUP_KEY not in caplog.text
        assert BACKUP_KEY not in json.dumps(engine.info()) and BACKUP_KEY not in engine.warm_error
        assert selection.REDACTED in caplog.text
    finally:
        engine.close()


@pytest.mark.parametrize("size", [100, 100_000])
def test_role_resolution_and_failure_redaction_timing(role_analyzer, size):
    engine = role_analyzer.backup
    error = RuntimeError("galat tiruan untuk " + BACKUP_KEY)
    elapsed = []
    described = ""
    for _ in range(5):
        started = perf_counter()
        for _ in range(size):
            assert selection.api_key_for(CHOICE.provider, ROLE_BACKUP) == BACKUP_KEY
            described = role_analyzer._describe(error, engine)
        elapsed.append((perf_counter() - started) * 1_000_000 / size)
    assert BACKUP_KEY not in described and selection.REDACTED in described
    print(f"T98 {size}: resolver + failure redaction median={median(elapsed):.3f} us/call (semua tiruan)")
