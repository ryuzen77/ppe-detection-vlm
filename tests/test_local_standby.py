"""T72: rute A/B/C, siaga dingin, konkurensi, & telemetri; seluruh penyedia tiruan."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import ppe_rules, vlm_selection
from backend.api_monitor import APIMonitor, MODE_LOCAL, ROLE_EMERGENCY
from backend.config import cfg
from backend.internet_monitor import NORMAL, SLOW, DISCONNECTED, ProbeResult
from backend.local_model_guard import UNLOADED, LOADING, READY, FAILED
from backend.vlm_analyzer import VLMAnalyzer, VLMEngine
from backend.vlm_providers.base import VLMProvider
from backend.vlm_selection import Choice, Selection
from helpers import person_crop


def _complete():
    items = {}
    for item in ppe_rules.get_active_items():
        result = {"detected": not item.prohibited, "color": "orange"}
        if item.qualifier:
            result[item.qualifier.key] = True
        items[item.key] = result
    return json.dumps({"items": items, "orang_nyata": True})


class FakeProvider(VLMProvider):
    def __init__(self, name):
        super().__init__("model-uji")
        self.name = name
        self.error: Exception | None = None
        self.calls, self.warms, self.unloads = [], 0, 0
        self.warm_started, self.release = threading.Event(), threading.Event()
        self.release.set()
        self.warm_error = False

    def generate(self, image_jpeg, system_prompt, user_prompt):
        self.calls.append((image_jpeg, system_prompt))
        if self.error is not None:
            raise self.error
        return _complete()

    def ping(self):
        return "PONG"

    def warm_up(self):
        self.warms += 1
        self.warm_started.set()
        assert self.release.wait(3), "pemanasan tiruan tidak dilepas"
        if self.warm_error:
            raise RuntimeError("muat tiruan gagal")

    def gpu_residency(self):
        return 0.0

    def unload(self):
        self.unloads += 1


@pytest.fixture
def make_analyzer(monkeypatch, catalog_defaults):
    created = []
    monkeypatch.setattr(cfg, "VLM_LOCAL_PRELOAD", False)
    monkeypatch.setattr(cfg, "VLM_MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(cfg, "VLM_WARMUP_TIMEOUT_SECONDS", 1)

    def make(layout="A", warm=False):
        analyzer = VLMAnalyzer()
        choice = Selection(
            Choice("gemini", "model-uji"),
            Choice("ollama" if layout == "B" else "openai", "model-uji"),
            "env",
            Choice("ollama", "model-uji") if layout == "A" else None,
        )
        monkeypatch.setattr(vlm_selection, "effective_selection", lambda: choice)
        monkeypatch.setattr(analyzer, "_new_engine", _fake_engine)
        monkeypatch.setattr(analyzer, "_release_stale_local_model", lambda: None)
        analyzer.start()
        created.append(analyzer)
        if warm:
            analyzer.standby.preload()
            _clear_calls(analyzer)
        return analyzer

    yield make
    for analyzer in created:
        for engine in analyzer._engines():
            engine.provider.release.set()
        analyzer.local_guard.stop()
        for engine in analyzer._engines():
            engine.executor.shutdown(wait=True, cancel_futures=True)


def _fake_engine(role, choice):
    engine = VLMEngine(role, choice.provider, choice.model, api_key="kunci-uji")
    engine.provider = FakeProvider(choice.provider)
    engine.min_interval, engine.timeout = 0, 0.2
    return engine


def _clear_calls(analyzer):
    for engine in analyzer._engines():
        engine.provider.calls.clear()


def _internet(analyzer, state, median_ms=None):
    with analyzer.internet._condition:
        analyzer.internet._status.update(state=state, median_ms=median_ms)
    analyzer._internet_changed(analyzer.internet.status())


@pytest.mark.parametrize("layout", ["A", "B"])
def test_startup_keeps_local_cold_and_guard_does_not_reload(make_analyzer, layout):
    analyzer = make_analyzer(layout)
    analyzer.warm_up()
    local = analyzer.standby.engine
    assert analyzer.standby.status()["state"] == UNLOADED
    assert local.provider.warms == 0 and local.provider.calls == []
    assert analyzer._local_engine() is None
    assert analyzer.local_guard.check_and_repair(force=True) is None
    assert local.provider.warms == 0


@pytest.mark.parametrize("layout", ["A", "B"])
def test_preload_is_explicit(make_analyzer, monkeypatch, layout):
    analyzer = make_analyzer(layout)
    monkeypatch.setattr(cfg, "VLM_LOCAL_PRELOAD", True)
    analyzer.warm_up()
    assert analyzer.standby.state == READY
    assert analyzer.standby.engine.provider.warms == 1


@pytest.mark.parametrize(
    "layout,state,primary_error,backup_error,role",
    [
        ("A", NORMAL, False, False, "utama"),
        ("A", NORMAL, True, False, "cadangan"),
        ("A", NORMAL, True, True, ROLE_EMERGENCY),
        ("A", SLOW, False, False, "utama"),
        ("A", SLOW, True, False, ROLE_EMERGENCY),
        ("A", DISCONNECTED, False, False, ROLE_EMERGENCY),
        ("B", NORMAL, False, False, "utama"),
        ("B", NORMAL, True, False, "cadangan"),
        ("B", SLOW, False, False, "utama"),
        ("B", SLOW, True, False, "cadangan"),
        ("B", DISCONNECTED, False, False, "cadangan"),
    ],
)
def test_inspection_routing_table(make_analyzer, layout, state, primary_error, backup_error, role):
    analyzer = make_analyzer(layout, warm=True)
    analyzer.primary.provider.error = RuntimeError("429 tiruan") if primary_error else None
    if not analyzer.backup.is_local:
        analyzer.backup.provider.error = RuntimeError("503 tiruan") if backup_error else None
    _internet(analyzer, state)
    result = analyzer.analyze_person(person_crop())
    assert result.is_complete and result.decided_by == role
    if state == DISCONNECTED:
        assert analyzer.primary.provider.calls == []
    if layout == "A" and state != NORMAL:
        assert analyzer.backup.provider.calls == []
    if role == ROLE_EMERGENCY or (role == "cadangan" and layout == "B"):
        assert "GAMBAR BERPANEL" not in analyzer.standby.engine.provider.calls[-1][1]


@pytest.mark.parametrize("layout", ["A", "B"])
@pytest.mark.parametrize("median_ms", [200, 350, 500, 500.01, 600, None])
def test_slow_route_uses_cached_median_without_changing_telemetry_state(make_analyzer, monkeypatch, layout, median_ms):
    monkeypatch.setattr(cfg, "INTERNET_VERY_SLOW_MS", 500)
    analyzer = make_analyzer(layout, warm=True)
    _internet(analyzer, SLOW, median_ms)
    direct_local = median_ms is not None and median_ms > cfg.INTERNET_VERY_SLOW_MS
    route = vlm_selection.inspection_route(SLOW, analyzer.primary, analyzer.backup,
                                           analyzer.local_fallback, median_ms=median_ms)
    result = analyzer.analyze_person(person_crop())
    assert result.is_complete
    assert result.decided_by == (analyzer.standby.engine.role if direct_local else "utama")
    assert len(analyzer.primary.provider.calls) == (0 if direct_local else 1)
    if layout == "A":
        assert analyzer.backup.provider.calls == []
    assert route[0] is (analyzer.standby.engine if direct_local else analyzer.primary)
    assert analyzer.internet.status()["state"] == SLOW


@pytest.mark.parametrize("layout", ["A", "B"])
def test_slow_route_keeps_primary_circuit_breaker_and_retries_after_interval(make_analyzer, monkeypatch, layout):
    analyzer = make_analyzer(layout, warm=True)
    _internet(analyzer, SLOW, 350)
    analyzer.primary.provider.error = RuntimeError("429 tiruan")
    monkeypatch.setattr(cfg, "VLM_PRIMARY_FAILURES_BEFORE_DOWN", 2)
    for _ in range(cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN):
        assert analyzer.analyze_person(person_crop()).decided_by == analyzer.standby.engine.role
    assert len(analyzer.primary.provider.calls) == 2
    assert analyzer.primary_down_since is not None
    assert analyzer.analyze_person(person_crop()).decided_by == analyzer.standby.engine.role
    assert len(analyzer.primary.provider.calls) == 2
    if layout == "A":
        assert analyzer.backup.provider.calls == []
    analyzer.primary.provider.error = None
    analyzer.primary_last_attempt -= cfg.VLM_PRIMARY_RETRY_AFTER_SECONDS
    assert analyzer.analyze_person(person_crop()).decided_by == "utama"
    assert len(analyzer.primary.provider.calls) == 3 and analyzer.primary_down_since is None


@pytest.mark.parametrize("layout", ["A", "B"])
def test_very_slow_internet_waits_for_loading_local_without_calling_online(make_analyzer, layout):
    analyzer = make_analyzer(layout)
    provider = analyzer.standby.engine.provider
    provider.release.clear()
    try:
        _internet(analyzer, SLOW, cfg.INTERNET_VERY_SLOW_MS + 1)
        assert provider.warm_started.wait(1)
        result = analyzer.analyze_person(person_crop())
        assert result.is_system_unavailable and not result.is_complete
        assert analyzer.primary.provider.calls == [] and provider.calls == []
        if layout == "A":
            assert analyzer.backup.provider.calls == []
    finally:
        provider.release.set()
        analyzer.standby._loader.join(2)


def test_many_load_triggers_start_only_one_warmup_and_loading_is_not_failure(make_analyzer):
    analyzer = make_analyzer("B")
    provider = analyzer.backup.provider
    provider.release.clear()
    with ThreadPoolExecutor(max_workers=20) as pool:
        assert sum(pool.map(lambda _: analyzer.standby.request(), range(20))) == 1
    assert provider.warm_started.wait(1)
    _internet(analyzer, DISCONNECTED)
    start = perf_counter()
    result = analyzer.analyze_person(person_crop())
    assert perf_counter() - start < 0.2
    assert result.is_system_unavailable and not result.is_complete
    assert provider.warms == 1 and provider.calls == []
    assert analyzer.standby.state == LOADING and analyzer.backup.last_call_ok is None
    provider.release.set()
    analyzer.standby._loader.join(2)
    assert analyzer.standby.state == READY


def test_failed_load_retries_after_configured_interval(make_analyzer):
    analyzer = make_analyzer("B")
    now = [100.0]
    analyzer.standby._clock = lambda: now[0]
    provider = analyzer.backup.provider
    provider.warm_error = True
    analyzer.standby.request()
    analyzer.standby._loader.join(2)
    assert analyzer.standby.state == FAILED and provider.warms == 1
    analyzer.standby.tick()
    assert provider.warms == 1
    provider.warm_error = False
    now[0] += cfg.VLM_LOCAL_RETRY_SECONDS
    analyzer.standby.tick()
    analyzer.standby._loader.join(2)
    assert analyzer.standby.state == READY and provider.warms == 2


def test_unload_requires_continuous_normal_internet_and_healthy_primary(make_analyzer):
    analyzer = make_analyzer("A", warm=True)
    now = [100.0]
    analyzer.standby._clock = lambda: now[0]
    _internet(analyzer, NORMAL)
    analyzer.standby.primary_result(True)
    now[0] += cfg.VLM_LOCAL_IDLE_UNLOAD_SECONDS - 1
    analyzer.standby.tick()
    assert analyzer.standby.state == READY
    analyzer.standby.primary_result(False)
    now[0] += cfg.VLM_LOCAL_IDLE_UNLOAD_SECONDS * 2
    analyzer.standby.tick()
    assert analyzer.standby.state == READY and analyzer.standby.engine.provider.unloads == 0
    analyzer.standby.primary_result(True)
    now[0] += cfg.VLM_LOCAL_IDLE_UNLOAD_SECONDS
    analyzer.standby.tick()
    assert analyzer.standby.state == UNLOADED and analyzer.standby.engine.provider.unloads == 1


def test_internet_problem_resets_idle_unload_timer(make_analyzer):
    analyzer = make_analyzer("A", warm=True)
    now = [100.0]
    analyzer.standby._clock = lambda: now[0]
    _internet(analyzer, NORMAL)
    analyzer.standby.primary_result(True)
    now[0] += cfg.VLM_LOCAL_IDLE_UNLOAD_SECONDS - 1
    _internet(analyzer, SLOW)
    _internet(analyzer, NORMAL)
    now[0] += 2
    analyzer.standby.tick()
    assert analyzer.standby.state == READY


def test_internet_problem_during_unload_immediately_reloads(make_analyzer, monkeypatch):
    analyzer = make_analyzer("A", warm=True)
    now = [100.0]
    analyzer.standby._clock = lambda: now[0]
    _internet(analyzer, NORMAL)
    analyzer.standby.primary_result(True)
    now[0] += cfg.VLM_LOCAL_IDLE_UNLOAD_SECONDS
    provider = analyzer.standby.engine.provider
    entered, release = threading.Event(), threading.Event()
    original_unload = provider.unload

    def unload():
        original_unload()
        entered.set()
        assert release.wait(1)

    monkeypatch.setattr(provider, "unload", unload)
    worker = threading.Thread(target=analyzer.standby.tick)
    worker.start()
    try:
        assert entered.wait(1)
        _internet(analyzer, SLOW)
    finally:
        release.set()
        worker.join(2)
    analyzer.standby._loader.join(2)
    assert analyzer.standby.state == READY and provider.warms == 2 and provider.unloads == 1


def test_connection_error_rechecks_internet_and_skips_online_backup(make_analyzer):
    analyzer = make_analyzer("A", warm=True)
    analyzer.internet._probe = lambda: ProbeResult((None, None))
    analyzer.primary.provider.error = httpx.ConnectError("tiruan")
    analyzer.internet.start()
    result = analyzer.analyze_person(person_crop())
    assert result.decided_by == ROLE_EMERGENCY
    assert analyzer.internet.status()["state"] == DISCONNECTED
    assert analyzer.backup.provider.calls == []


@pytest.mark.parametrize(
    "error",
    [RuntimeError("429 tiruan"), RuntimeError("503 tiruan"), ValueError("JSON rusak"), httpx.ReadTimeout("tiruan")],
)
def test_api_failures_do_not_mark_internet_disconnected(make_analyzer, monkeypatch, error):
    analyzer = make_analyzer("A", warm=True)
    analyzer.primary.provider.error = error
    monkeypatch.setattr(analyzer.internet, "request_check", lambda: pytest.fail("bukan galat sambungan"))
    result = analyzer.analyze_person(person_crop())
    assert result.decided_by == "cadangan"
    assert analyzer.internet.status()["state"] == NORMAL


def test_configuration_c_keeps_internet_disabled_and_existing_fallback(make_analyzer):
    analyzer = make_analyzer("C")
    analyzer.primary.provider.error = RuntimeError("503 tiruan")
    result = analyzer.analyze_person(person_crop())
    assert result.decided_by == "cadangan"
    assert analyzer.internet.status()["state"] is None
    assert analyzer.standby.status()["role"] is None


def test_monitor_exposes_exact_internet_local_shapes_and_local_mode():
    monitor = APIMonitor()
    monitor.set_internet({"state": SLOW, "median_ms": 600, "checked_at": "08:01:30"})
    monitor.set_local({"role": ROLE_EMERGENCY, "state": LOADING, "since": "08:01:31"})
    monitor.record_decision(ROLE_EMERGENCY)
    status = monitor.get_status()
    assert status["mode"] == MODE_LOCAL
    assert status["internet"] == {"state": SLOW, "median_ms": 600, "checked_at": "08:01:30"}
    assert status["local"] == {"role": ROLE_EMERGENCY, "state": LOADING, "since": "08:01:31"}
    assert "primary" in status and "backup" in status


def test_route_has_no_io_and_benchmark_1_vs_20_inspections(make_analyzer, monkeypatch):
    analyzer = make_analyzer("A", warm=True)
    monkeypatch.setattr(analyzer.internet, "_probe", lambda: pytest.fail("rute tidak boleh melakukan I/O"))
    for state, median_ms in ((NORMAL, None), (SLOW, 350), (SLOW, 600)):
        _internet(analyzer, state, median_ms)
        for people in (1, 20):
            start = perf_counter()
            for _ in range(10_000):
                for _ in range(people):
                    internet = analyzer.internet.status()
                    vlm_selection.inspection_route(internet["state"], analyzer.primary, analyzer.backup,
                                                   analyzer.local_fallback, median_ms=internet["median_ms"])
            elapsed_us = (perf_counter() - start) / 10000 * 1e6
            print(f"ROUTE {state} median={median_ms} people={people}: {elapsed_us:.3f} us/batch")


def test_recovered_internet_returns_to_primary_before_breaker_retry(make_analyzer):
    analyzer = make_analyzer("A", warm=True)
    analyzer.primary.provider.error = RuntimeError("429 tiruan")
    for _ in range(cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN):
        analyzer.analyze_person(person_crop())
    assert analyzer.primary_down_since is not None
    _internet(analyzer, DISCONNECTED)
    assert analyzer.analyze_person(person_crop()).decided_by == ROLE_EMERGENCY
    analyzer.primary.provider.error = None
    _internet(analyzer, NORMAL)
    assert analyzer.analyze_person(person_crop()).decided_by == "utama"


def test_failed_selection_preparation_closes_new_engines_only(make_analyzer, monkeypatch):
    from backend.vlm_analyzer import EngineFailed

    analyzer = make_analyzer("C")
    fresh = _fake_engine("utama", Choice("gemini", "model-baru-uji"))
    closed = []
    monkeypatch.setattr(fresh, "close", lambda unload=False: closed.append(fresh))

    def prepare(role, choice):
        if role == "cadangan":
            raise EngineFailed("gagal tiruan")
        return fresh

    monkeypatch.setattr(analyzer, "_prepare", prepare)
    with pytest.raises(EngineFailed):
        analyzer.apply_selection(Selection(fresh.choice(), analyzer.backup.choice(), "dashboard"), lambda: True)
    assert closed == [fresh] and analyzer.primary is not fresh
    fresh.executor.shutdown()


def test_background_services_follow_existing_guard_lifecycle(make_analyzer):
    analyzer = make_analyzer("B")
    analyzer.internet._probe = lambda: ProbeResult((20, 30))
    analyzer.local_guard.start()
    assert analyzer.internet._thread.is_alive() and analyzer.standby._thread.is_alive()
    analyzer.local_guard.stop()
    assert not analyzer.internet._thread.is_alive() and not analyzer.standby._thread.is_alive()


def test_switch_provider_while_loading_finishes_without_deadlock(make_analyzer):
    analyzer = make_analyzer("A")
    provider = analyzer.standby.engine.provider
    provider.release.clear()
    analyzer.standby.request()
    assert provider.warm_started.wait(1)
    selection = Selection(Choice("gemini", "model-uji"), None, "dashboard")
    result = []
    worker = threading.Thread(target=lambda: result.append(analyzer.apply_selection(selection, lambda: True)))
    worker.start()
    provider.release.set()
    worker.join(2)
    assert not worker.is_alive() and result
    assert analyzer.local_fallback is None and analyzer.standby.engine is None


@pytest.mark.parametrize("layout", ["A", "B"])
def test_cold_load_leaves_inspection_lock_available_and_online_primary_responds(make_analyzer, layout):
    analyzer = make_analyzer(layout)
    provider = analyzer.standby.engine.provider
    provider.release.clear()
    try:
        _internet(analyzer, SLOW)
        assert provider.warm_started.wait(1)
        assert analyzer.api_lock.acquire(timeout=0.1)
        analyzer.api_lock.release()
        result = analyzer.analyze_person(person_crop())
        assert result.decided_by == "utama" and result.is_complete
        assert analyzer.standby.state == LOADING and provider.warms == 1
    finally:
        provider.release.set()
        analyzer.standby._loader.join(2)


def test_cold_ping_does_not_load_or_record_engine_failure(make_analyzer, monkeypatch):
    from backend import messages
    from backend.api_monitor import api_monitor

    analyzer = make_analyzer("B")
    local = analyzer.standby.engine
    failures = api_monitor.get_status()["backup"]["failures"]
    monkeypatch.setattr(analyzer.standby, "request", lambda: pytest.fail("ping tidak boleh memuat"))
    row = analyzer._ping_engine(local)
    assert not row["ok"] and row["error"] == messages.VLM_LOCAL_STANDBY_UNLOADED
    assert analyzer.standby.state == UNLOADED and local.provider.warms == 0
    assert api_monitor.get_status()["backup"]["failures"] == failures


def test_emergency_audit_label_and_telemetry_are_separate(make_analyzer):
    from backend.api_monitor import api_monitor

    analyzer = make_analyzer("A", warm=True)
    before = api_monitor.get_status()
    _internet(analyzer, DISCONNECTED)
    result = analyzer.analyze_person(person_crop())
    assert result.decided_by == ROLE_EMERGENCY
    assert result.inference_source == f"{vlm_selection.LOCAL_FALLBACK_SOURCE_PREFIX}ollama/model-uji"
    after = api_monitor.get_status()
    assert after["decisions_local"] == before["decisions_local"] + 1
    assert after["decisions_backup"] == before["decisions_backup"]


def test_current_local_fallback_includes_selection_source(make_analyzer):
    analyzer = make_analyzer("A")
    current = analyzer.current_selection()
    assert current["local_fallback"]["source"] == current["primary"]["source"] == "env"


@pytest.mark.parametrize("warm,error", [(False, False), (False, True), (True, False)])
def test_local_provider_test_restores_cold_state_but_keeps_ready_model(make_analyzer, monkeypatch, warm, error):
    from backend.api import routes_vlm
    from backend.app import app

    analyzer = make_analyzer("A", warm=warm)
    temporary = _fake_engine("cadangan", Choice("ollama", "qwen2.5vl:7b"))
    # Model sementara sama dengan standby; uji tidak boleh membongkar model yang sudah siap.
    analyzer.standby.engine.model_name = temporary.model_name
    provider = temporary.provider
    assert isinstance(provider, FakeProvider)
    if error:
        provider.error = RuntimeError("galat uji tiruan")
    monkeypatch.setattr(analyzer, "_new_engine", lambda role, choice: temporary)
    monkeypatch.setattr(routes_vlm, "vlm_analyzer", analyzer)
    response = TestClient(app).post("/api/config/vlm/test", json={
        "role": "backup", "provider": "ollama", "model": temporary.model_name})
    assert response.status_code == 200 and response.json()["json_ok"] is (not error)
    assert provider.unloads == (0 if warm else 1)
    assert analyzer.standby.state == (READY if warm else UNLOADED)


@pytest.mark.parametrize("layout", ["A", "B"])
def test_apply_local_standby_does_not_warm_it(make_analyzer, layout):
    analyzer = make_analyzer("C")
    local = Choice("ollama", "qwen2.5vl:7b")
    selection = Selection(analyzer.primary.choice(), local if layout == "B" else analyzer.backup.choice(),
                          "dashboard", local if layout == "A" else None)
    current = analyzer.apply_selection(selection, lambda: True)
    assert analyzer.standby.state == UNLOADED and analyzer.standby.engine.provider.warms == 0
    assert current["local_fallback"]["source"] == "dashboard" if layout == "A" else current["local_fallback"] is None


def test_local_as_primary_is_warmed_at_startup(make_analyzer):
    analyzer = make_analyzer("C")
    analyzer.primary.close()
    analyzer.primary = _fake_engine("utama", Choice("ollama", "model-uji"))
    analyzer._configure_standby()
    analyzer.warm_up()
    provider = analyzer.primary.provider
    assert isinstance(provider, FakeProvider) and provider.warms == 1
    assert analyzer._local_status()["state"] == READY
    assert analyzer.internet.status()["state"] is None


def test_selection_local_fallback_saved_loaded_and_validation_codes(monkeypatch, tmp_path):
    from backend import runtime_settings
    from backend.app import app
    from backend.api import routes_vlm

    monkeypatch.setattr(runtime_settings, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setenv("GEMINI_API_KEY", "kunci-uji")
    fallback = Choice("ollama", "qwen2.5vl:7b")
    selection = Selection(Choice("gemini", "gemini-3.5-flash-lite"), None, "dashboard", fallback)
    assert vlm_selection.save(selection)
    stored = vlm_selection.stored_selection()
    assert stored is not None and stored.local_fallback == fallback
    monkeypatch.setattr(routes_vlm, "_apply", lambda value, request: value.stored_form())
    client = TestClient(app)
    body = selection.stored_form()
    response = client.post("/api/config/vlm/apply", json=body)
    assert response.status_code == 200 and response.json()["local_fallback"] == body["local_fallback"]
    for backup, provider, code in [
        (None, "gemini", "local_fallback_not_local"),
        ({"provider": "ollama", "model": fallback.model}, "ollama", "local_fallback_with_local_backup"),
    ]:
        body.update(backup=backup, local_fallback={"provider": provider, "model": fallback.model})
        response = client.post("/api/config/vlm/apply", json=body)
        assert response.status_code == 400 and response.json()["detail"]["code"] == code
