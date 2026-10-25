"""Penjaga model lokal (T38): model yang sebagian jatuh ke CPU dimuat ulang."""

import json
import logging
import threading

import httpx
import pytest

from backend import local_model_guard as guard_mod
from backend.config import cfg
from backend.local_model_guard import LocalModelGuard
from backend.vlm_providers.openai_compatible import OpenAICompatibleProvider


class FakeProvider:
    def __init__(self, residencies):
        self.residencies = list(residencies)
        self.reloads = 0

    def gpu_residency(self):
        return self.residencies.pop(0) if len(self.residencies) > 1 else self.residencies[0]

    def reload(self):
        self.reloads += 1


class FakeEngine:
    who = "cadangan ollama/qwen2.5vl:7b"

    def __init__(self, provider):
        self.provider = provider


def _guard(provider, lock=None):
    return LocalModelGuard(lock or threading.Lock(), lambda: FakeEngine(provider) if provider else None)


def test_model_sebagian_di_cpu_dimuat_ulang(caplog):
    p = FakeProvider([0.26, 1.0])
    with caplog.at_level(logging.WARNING, logger=guard_mod.__name__):
        assert _guard(p).check_and_repair() is True
    assert p.reloads == 1
    assert any("26%" in r.getMessage() for r in caplog.records)


def test_model_penuh_di_gpu_tidak_disentuh():
    p = FakeProvider([1.0])
    assert _guard(p).check_and_repair() is True
    assert p.reloads == 0


def test_model_cloud_tidak_diperiksa():
    p = FakeProvider([None])
    assert _guard(p).check_and_repair() is None
    assert p.reloads == 0
    assert _guard(None).check_and_repair() is None


def test_gagal_pulih_dicatat_sebagai_galat(caplog):
    p = FakeProvider([0.3, 0.3])
    with caplog.at_level(logging.ERROR, logger=guard_mod.__name__):
        assert _guard(p).check_and_repair() is False
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_tidak_memuat_ulang_di_tengah_inspeksi(monkeypatch):
    # Gembok inspeksi dipegang (pekerja sedang diperiksa): jangan putus pekerja
    monkeypatch.setattr(cfg, "LOCAL_GPU_REPAIR_WAIT_SECONDS", 0.05)
    lock = threading.Lock()
    lock.acquire()
    p = FakeProvider([0.26])
    try:
        assert _guard(p, lock).check_and_repair() is None
    finally:
        lock.release()
    assert p.reloads == 0


def test_hanya_satu_pemeriksaan_sekaligus():
    p = FakeProvider([0.26, 1.0])
    g = _guard(p)
    g._busy.acquire()
    try:
        assert g.check_and_repair() is None
    finally:
        g._busy.release()
    assert p.reloads == 0


# --- Adaptor Ollama: /api/ps & muat ulang -----------------------------------------------


def _ollama(handler):
    p = OpenAICompatibleProvider(api_key="", model="qwen2.5vl:7b", base_url="http://ollama.test/v1", name="ollama")
    p._client = httpx.Client(base_url=p.base_url, transport=httpx.MockTransport(handler))
    return p


def test_porsi_gpu_dari_api_ps():
    def handler(req):
        assert req.url.path == "/api/ps"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5vl:7b", "size": 6_000, "size_vram": 1_560}]})

    assert _ollama(handler).gpu_residency() == pytest.approx(0.26)


def test_model_tidak_dimuat_berarti_nol():
    assert _ollama(lambda req: httpx.Response(200, json={"models": []})).gpu_residency() == 0.0


def test_muat_ulang_bongkar_lalu_muat():
    calls = []

    def handler(req):
        calls.append((req.url.path, json.loads(req.content)["keep_alive"]))
        return httpx.Response(200, json={})

    _ollama(handler).reload()
    assert calls == [("/api/generate", 0), ("/api/generate", -1)]


def test_penyedia_cloud_tidak_punya_porsi_gpu():
    p = OpenAICompatibleProvider(api_key="k", model="m", base_url="http://x.test/v1", name="openrouter")
    assert p.gpu_residency() is None


# --- Sambungan ke analyzer -------------------------------------------------------------


def test_cadangan_lokal_gagal_memicu_pemeriksaan(monkeypatch):
    from backend.vlm.analyzer import VLMAnalyzer, VLMEngine
    from helpers import person_crop

    a = VLMAnalyzer()
    a.primary = None
    backup = VLMEngine("cadangan", "ollama", "qwen2.5vl:7b")

    class Crash:
        def analyze(self, *args, **kwargs):
            raise RuntimeError("ollama HTTP 500")

    backup.provider = Crash()  # pyright: ignore[reportAttributeAccessIssue]
    a.backup = backup
    triggered = []
    monkeypatch.setattr(a.local_guard, "trigger", lambda: triggered.append(True))
    result = a.analyze_person(person_crop())
    assert result.is_system_unavailable
    assert triggered == [True]


def test_keluarkan_model_dari_gpu_saat_cadangan_dimatikan():
    # T70: keep_alive=-1 menahan model selamanya; mematikan cadangan harus mengirim keep_alive=0
    calls = []

    def handler(req):
        calls.append((req.url.path, json.loads(req.content)["keep_alive"]))
        return httpx.Response(200, json={})

    _ollama(handler).unload()
    assert calls == [("/api/generate", 0)]
    OpenAICompatibleProvider(api_key="k", model="m", base_url="http://x.test/v1", name="openrouter").unload()
