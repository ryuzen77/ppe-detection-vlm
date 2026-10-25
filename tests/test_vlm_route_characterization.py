"""Urutan panggilan gerbang sebelum pemindahan mesin/pemutus T99c, tanpa jaringan."""

import json
import time
from types import SimpleNamespace

import pytest

from backend import ppe_rules, vlm_analyzer as analyzer_module
from backend.config import cfg
from backend.internet_monitor import NORMAL, SLOW, DISCONNECTED
from backend.local_model_guard import READY, LOADING
from backend.vlm_analyzer import VLMAnalyzer, VLMEngine, LaneBusy
from backend.vlm_providers.base import VLMProvider
from backend.vlm_selection import Choice, Selection
from helpers import person_crop


def complete_payload():
    items = {}
    for item in ppe_rules.get_active_items():
        value = {"detected": not item.prohibited}
        if item.qualifier:
            value[item.qualifier.key] = True
        items[item.key] = value
    return {"items": items, "orang_nyata": True}


class ScriptedProvider(VLMProvider):
    name = "tiruan"

    def __init__(self, label, trace):
        super().__init__("model-uji")
        self.label, self.trace, self.replies = label, trace, []

    def generate(self, image_jpeg, system_prompt, user_prompt):
        self.trace.append(self.label)
        reply = self.replies.pop(0) if self.replies else complete_payload()
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply)

    def ping(self):
        raise AssertionError("Pemeriksaan pekerja tidak boleh memanggil probe VLM")


@pytest.fixture
def route_setup(monkeypatch, catalog_defaults):
    created, clock = [], [100.0]
    monkeypatch.setattr(analyzer_module, "time", SimpleNamespace(time=lambda: clock[0], strftime=time.strftime))
    monkeypatch.setattr(cfg, "VLM_PRIMARY_FAILURES_BEFORE_DOWN", 2)
    monkeypatch.setattr(cfg, "VLM_PRIMARY_RETRY_AFTER_SECONDS", 60.0)
    monkeypatch.setattr(cfg, "INTERNET_VERY_SLOW_MS", 500)

    def engine(role, provider, label, trace):
        result = VLMEngine(role, provider, "model-uji", api_key="kunci-uji")
        result.provider = ScriptedProvider(label, trace)
        result.min_interval = 0
        return result

    def make(layout="A", state=NORMAL, median_ms=50):
        analyzer, trace = VLMAnalyzer(), []
        analyzer.primary = engine("utama", "gemini", "P", trace)
        analyzer.backup = engine("cadangan", "ollama" if layout == "B" else "openai", "B", trace)
        analyzer.local_fallback = engine("darurat", "ollama", "L", trace) if layout == "A" else None
        analyzer.standby.configure(analyzer.local_fallback if layout == "A" else analyzer.backup)
        analyzer.standby.state = READY
        monkeypatch.setattr(analyzer.internet, "status", lambda: {"state": state, "median_ms": median_ms})
        monkeypatch.setattr(analyzer.local_guard, "trigger", lambda: None)
        created.append(analyzer)
        return SimpleNamespace(analyzer=analyzer, clock=clock, trace=trace)

    yield make
    for analyzer in created:
        for item in analyzer._engines():
            item.executor.shutdown(wait=True, cancel_futures=True)


def assert_waiting(result):
    assert result.is_system_unavailable and not result.is_complete
    assert result.items == {} and result.missing_items == []
    assert result.inference_source == "VLM_GANGGUAN"


def test_two_failures_skip_primary_until_real_worker_at_retry_boundary(route_setup):
    env = route_setup()
    env.analyzer.primary.provider.replies = [RuntimeError("503 tiruan"), RuntimeError("429 tiruan")]
    for now in (100.0, 101.0, 160.999):
        env.clock[0] = now
        assert env.analyzer.analyze_person(person_crop()).decided_by == "cadangan"
    assert env.trace == ["P", "B", "P", "B", "B"]
    env.clock[0] = 161.0
    assert env.trace == ["P", "B", "P", "B", "B"]  # waktu lewat bukan probe otomatis
    assert env.analyzer.analyze_person(person_crop()).decided_by == "utama"
    assert env.trace == ["P", "B", "P", "B", "B", "P"]
    assert env.analyzer.provider_info()["primary_down"] is False


def test_all_engines_fail_without_rejection_or_second_primary_call(route_setup):
    env = route_setup()
    for item in env.analyzer._engines():
        item.provider.replies = [RuntimeError("engine gagal tiruan")]
    assert_waiting(env.analyzer.analyze_person(person_crop()))
    assert env.trace == ["P", "B", "L"]


@pytest.mark.parametrize(
    "layout,state,median,primary_fails,expected",
    [
        ("A", SLOW, 350, False, ["P"]),
        ("A", SLOW, 500, True, ["P", "L"]),
        ("A", SLOW, 500.01, False, ["L"]),
        ("A", DISCONNECTED, None, False, ["L"]),
        ("B", SLOW, 350, True, ["P", "B"]),
        ("B", DISCONNECTED, None, False, ["B"]),
    ],
)
def test_local_route_preserves_exact_call_order(route_setup, layout, state, median, primary_fails, expected):
    env = route_setup(layout, state, median)
    if primary_fails:
        env.analyzer.primary.provider.replies = [RuntimeError("utama gagal tiruan")]
    result = env.analyzer.analyze_person(person_crop())
    assert result.is_complete and not result.is_system_unavailable
    assert env.trace == expected


@pytest.mark.parametrize("layout", ["A", "B"])
def test_disconnected_loading_local_waits_without_online_calls(route_setup, layout):
    env = route_setup(layout, DISCONNECTED, None)
    env.analyzer.standby.state = LOADING
    assert_waiting(env.analyzer.analyze_person(person_crop()))
    assert env.trace == []


@pytest.mark.parametrize("confirmation,complete", [({"detected": True}, False), ({}, True)])
def test_prohibition_requires_exactly_one_confirmation(route_setup, catalog_defaults, confirmation, complete):
    catalog_defaults.set_active({"rokok": True})
    env = route_setup()
    payload = complete_payload()
    payload["items"]["rokok"]["detected"] = True
    env.analyzer.primary.provider.replies = [payload, confirmation]
    result = env.analyzer.analyze_person(person_crop())
    assert result.is_complete is complete and not result.is_system_unavailable
    assert env.trace == ["P", "P"]


@pytest.mark.parametrize("all_fail", [False, True])
def test_confirmation_timeout_falls_back_or_waits(route_setup, catalog_defaults, all_fail):
    catalog_defaults.set_active({"rokok": True})
    env = route_setup()
    payload = complete_payload()
    payload["items"]["rokok"]["detected"] = True
    env.analyzer.primary.provider.replies = [payload, TimeoutError("konfirmasi tiruan")]
    if all_fail:
        for item in (env.analyzer.backup, env.analyzer.local_fallback):
            item.provider.replies = [RuntimeError("cadangan gagal tiruan")]
        assert_waiting(env.analyzer.analyze_person(person_crop()))
        assert env.trace == ["P", "P", "B", "L"]
    else:
        assert env.analyzer.analyze_person(person_crop()).decided_by == "cadangan"
        assert env.trace == ["P", "P", "B"]


def test_lane_busy_keeps_engines_and_releases_facade_locks(route_setup, monkeypatch):
    env = route_setup()
    analyzer = env.analyzer
    original = tuple(analyzer._engines())

    def prepare(selection):
        assert analyzer.apply_lock.locked() and not analyzer.api_lock.locked()
        return original

    def lane_empty():
        assert analyzer.apply_lock.locked() and analyzer.api_lock.locked()
        return False

    monkeypatch.setattr(analyzer, "_prepare_selection", prepare)
    selection = Selection(Choice("gemini", "model-uji"), Choice("openai", "model-uji"), "dashboard")
    with pytest.raises(LaneBusy):
        analyzer.apply_selection(selection, lane_empty)
    assert tuple(analyzer._engines()) == original and env.trace == []
    assert not analyzer.apply_lock.locked() and not analyzer.api_lock.locked()
