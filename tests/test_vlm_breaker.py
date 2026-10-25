"""Pemutus utama menerima waktu eksplisit; tidak memiliki lock, probe atau mesin VLM."""

import pytest

from backend import vlm_analyzer, vlm_breaker
from backend.config import cfg
from backend.vlm_breaker import PrimaryBreaker


@pytest.fixture(autouse=True)
def breaker_config(monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PRIMARY_FAILURES_BEFORE_DOWN", 2)
    monkeypatch.setattr(cfg, "VLM_PRIMARY_RETRY_AFTER_SECONDS", 60.0)


@pytest.mark.parametrize(
    "failures,last_attempt,now,backup,expected",
    [
        (0, 100.0, 100.0, True, True),
        (1, 100.0, 100.0, True, True),
        (2, 100.0, 159.999, True, False),
        (2, 100.0, 160.0, True, True),
        (3, 100.0, 161.0, True, True),
        (2, 100.0, 99.0, True, False),
        (2, 100.0, 100.0, False, True),
        (20, 100.0, 100.0, False, True),
    ],
)
def test_allowed_preserves_retry_boundary_and_no_backup_exception(failures, last_attempt, now, backup, expected):
    breaker = PrimaryBreaker(failures=failures, last_attempt=last_attempt)
    assert breaker.allowed(now, backup) is expected


def test_failure_marks_down_once_and_keeps_first_down_time():
    breaker = PrimaryBreaker()
    assert breaker.result(False, 10.0) is False
    assert breaker.failures == 1 and breaker.down_since is None
    assert breaker.result(False, 11.0) is True
    assert breaker.failures == 2 and breaker.down_since == 11.0
    assert breaker.result(False, 12.0) is False
    assert breaker.failures == 3 and breaker.down_since == 11.0


def test_recovery_resets_failures_without_changing_last_attempt():
    breaker = PrimaryBreaker(failures=4, down_since=100.0, last_attempt=150.0)
    assert breaker.result(True, 151.0) is False
    assert breaker.failures == 0 and breaker.down_since is None
    assert breaker.last_attempt == 150.0
    assert breaker.allowed(151.0, True)


def test_reset_clears_all_state():
    breaker = PrimaryBreaker(failures=4, down_since=100.0, last_attempt=150.0)
    breaker.reset()
    assert breaker == PrimaryBreaker()


def test_configuration_is_read_when_used_like_before(monkeypatch):
    breaker = PrimaryBreaker(failures=1, last_attempt=100.0)
    monkeypatch.setattr(cfg, "VLM_PRIMARY_FAILURES_BEFORE_DOWN", 1)
    monkeypatch.setattr(cfg, "VLM_PRIMARY_RETRY_AFTER_SECONDS", 10)
    assert not breaker.allowed(109.999, True)
    assert breaker.allowed(110.0, True)
    assert breaker.result(False, 111.0) is True


def test_zero_time_is_a_valid_down_timestamp():
    breaker = PrimaryBreaker(failures=1)
    assert breaker.result(False, 0.0) is True
    assert breaker.down_since == 0.0
    assert breaker.result(False, 1.0) is False


@pytest.mark.parametrize("name", ["primary_failures", "primary_down_since", "primary_last_attempt"])
def test_old_breaker_patch_attributes_are_absent(name):
    assert not hasattr(vlm_analyzer.VLMAnalyzer(), name)


def test_provider_factory_has_one_patch_owner_and_breaker_has_no_io():
    assert not hasattr(vlm_analyzer, "create_provider")
    for name in ("time", "threading", "create_provider", "VLMEngine"):
        assert not hasattr(vlm_breaker, name)
