"""Memilih penyedia VLM hanya lewat variabel lingkungan / .env, tanpa menyentuh kode (T23).

Tiap kombinasi dijalankan di proses terpisah supaya `config` dibaca ulang dari awal.
Seluruh variabel VLM ditulis eksplisit agar isi backend/.env tidak ikut terbaca.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import PROVIDER_KEY_ENVS

REPO_ROOT = Path(__file__).resolve().parent.parent

_PROBE = r"""
import json
from backend.config import cfg
from backend.vlm.analyzer import VLMAnalyzer
# Proses terpisah tanpa conftest: jangan menyentuh model Ollama sungguhan saat start (T71)
VLMAnalyzer._unload_if_loaded = staticmethod(lambda engine: engine.close())
a = VLMAnalyzer()
a.start()
p = a.provider
print(json.dumps({
    "provider": cfg.VLM_PROVIDER, "model": cfg.VLM_MODEL, "is_local": cfg.VLM_IS_LOCAL,
    "min_interval": a.primary.min_interval, "timeout": a.primary.timeout, "live": a.is_live_api(),
    "backup": a.backup.info() if a.backup else None,
    "kelas": type(p).__name__ if p else None, "base_url": getattr(p, "base_url", None),
    "label": a.source_label, "info": a.provider_info(),
}))
"""

_KOSONG = {
    k: ""
    for k in (
        "VLM_PROVIDER",
        "VLM_API_KEY",
        "VLM_MODEL",
        "VLM_BASE_URL",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "VLM_MIN_INTERVAL_SECONDS",
        "VLM_CLOUD_TIMEOUT_SECONDS",
        "VLM_LOCAL_TIMEOUT_SECONDS",
        "VLM_BACKUP_PROVIDER",
        "VLM_BACKUP_MODEL",
        "VLM_BACKUP_BASE_URL",
        "VLM_BACKUP_API_KEY",
        *PROVIDER_KEY_ENVS,
    )
}


def _probe(tmp_path, **env):
    full = {**os.environ, **_KOSONG, **env, "DATA_DIR": str(tmp_path / "data"), "LOG_TO_FILE": "false"}
    out = subprocess.run(
        [sys.executable, "-c", _PROBE], cwd=REPO_ROOT, env=full, capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_env_lama_gemini_tetap_berfungsi(tmp_path):
    r = _probe(tmp_path, GEMINI_API_KEY="kunci-lama", GEMINI_MODEL="gemini-3.8-flash")
    assert (r["provider"], r["model"], r["live"], r["kelas"]) == ("gemini", "gemini-3.8-flash", True, "GeminiProvider")
    assert r["label"] == "VLM_LIVE:gemini/gemini-3.8-flash"
    assert r["min_interval"] == 4.0, "Penyedia cloud menjaga kuota free tier"
    assert r["timeout"] == 4.0, "Cloud dipotong cepat supaya pekerja segera dialihkan ke cadangan"
    assert r["backup"] is None, "T71: bawaan tanpa cadangan (model lokal tidak dimuat ke GPU)"


def test_cadangan_lokal_diaktifkan_lewat_env(tmp_path):
    r = _probe(tmp_path, GEMINI_API_KEY="kunci-lama", VLM_BACKUP_PROVIDER="ollama")
    assert r["backup"]["provider"] == "ollama" and r["backup"]["model"] == "qwen2.5vl:7b", (
        "Model bawaan cadangan lokal = hasil evaluasi T26"
    )
    assert r["backup"]["timeout_s"] == 12.0


def test_nama_vlm_baru_menang_atas_nama_lama(tmp_path):
    r = _probe(
        tmp_path,
        VLM_PROVIDER="gemini",
        VLM_API_KEY="baru",
        VLM_MODEL="gemini-3.5-flash-lite",
        GEMINI_API_KEY="lama",
        GEMINI_MODEL="gemini-3.8-flash",
    )
    assert r["model"] == "gemini-3.5-flash-lite"
    assert r["info"]["has_key"] is True


def test_ganti_ke_ollama_hanya_lewat_env(tmp_path):
    r = _probe(tmp_path, VLM_PROVIDER="ollama")
    assert r["kelas"] == "OpenAICompatibleProvider"
    assert r["live"] is True, "Model lokal tidak butuh API key"
    assert r["model"] == "qwen2.5vl:7b"
    assert r["base_url"] == "http://localhost:11434/v1"
    assert r["is_local"] is True and r["min_interval"] == 0.0, "Tanpa kuota, antrean tidak ditahan"
    assert r["timeout"] == 12.0, "qwen2.5vl:7b lokal: p95 9,2 dtk (T26)"
    assert r["backup"] is None, "Utama sudah lokal: tanpa cadangan bawaan"
    assert r["info"]["needs_key"] is False
    assert r["label"] == "VLM_LIVE:ollama/qwen2.5vl:7b"


def test_penyedia_openai_compatible_dengan_base_url_sendiri(tmp_path):
    r = _probe(
        tmp_path,
        VLM_PROVIDER="qwen",
        VLM_API_KEY="k",
        VLM_MODEL="qwen-vl-max",
        VLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    assert r["kelas"] == "OpenAICompatibleProvider"
    assert r["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


@pytest.mark.parametrize(
    "env, alasan",
    [
        ({"VLM_PROVIDER": "openrouter", "VLM_MODEL": "qwen/qwen2.5-vl-72b-instruct"}, "penyedia cloud tanpa API key"),
        ({"VLM_PROVIDER": "openrouter", "VLM_API_KEY": "k"}, "penyedia tanpa model bawaan dan VLM_MODEL kosong"),
        ({"VLM_PROVIDER": "vllm", "VLM_MODEL": "m"}, "vLLM tanpa VLM_BASE_URL"),
    ],
)
def test_konfigurasi_tidak_lengkap_membuat_vlm_nonaktif_bukan_crash(tmp_path, env, alasan):
    r = _probe(tmp_path, **env)
    assert r["info"]["is_live"] is False and r["info"]["error"], alasan
    # Gerbang tetap bisa memutuskan lewat cadangan lokal bawaan (bila utama cloud)
    assert r["live"] is (r["backup"] is not None)


def test_info_penyedia_tidak_pernah_memuat_api_key(tmp_path):
    r = _probe(tmp_path, VLM_PROVIDER="gemini", VLM_API_KEY="rahasia-sekali")
    assert "rahasia-sekali" not in json.dumps(r["info"])


@pytest.mark.parametrize("penyedia", ["ollama", "openrouter", "deepseek"])
def test_kunci_gemini_lama_tidak_bocor_ke_penyedia_lain(tmp_path, penyedia):
    r = _probe(tmp_path, VLM_PROVIDER=penyedia, VLM_MODEL="m", GEMINI_API_KEY="kunci-gemini-rahasia")
    assert r["info"]["has_key"] is False


# --- Endpoint dashboard ----------------------------------------------------------------


@pytest.fixture
def klien(monkeypatch):
    """TestClient tanpa lifespan (tidak menyalakan kamera/model); status VLM dipulihkan."""
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.config import cfg
    from backend.vlm.analyzer import vlm_analyzer

    for attr in ("primary", "backup"):
        monkeypatch.setattr(vlm_analyzer, attr, getattr(vlm_analyzer, attr))
    for attr in ("failures", "down_since", "last_attempt"):
        monkeypatch.setattr(vlm_analyzer.breaker, attr, getattr(vlm_analyzer.breaker, attr))
    monkeypatch.setattr(cfg, "VLM_API_KEY", cfg.VLM_API_KEY)
    return TestClient(app), vlm_analyzer


@pytest.mark.parametrize("url", ["/api/config/vlm-key", "/api/config/gemini-key"])
def test_endpoint_ganti_api_key_sudah_dihapus(klien, url):
    """T28 (keputusan e): API key hanya di backend/.env, dashboard tidak bisa mengirimnya."""
    client, _ = klien
    assert client.post(url, json={"api_key": "kunci-dari-dashboard"}).status_code in (404, 405)


def test_key_per_penyedia_dari_env_sendiri(tmp_path):
    r = _probe(
        tmp_path, VLM_PROVIDER="openai", VLM_MODEL="m", OPENAI_API_KEY="kunci-openai", GEMINI_API_KEY="kunci-gemini"
    )
    assert r["live"] is True and r["info"]["has_key"] is True, "OPENAI_API_KEY dipakai untuk penyedia openai"
    assert "kunci" not in json.dumps(r["info"])


def test_key_cadangan_dari_env_penyedianya(tmp_path):
    r = _probe(
        tmp_path,
        VLM_PROVIDER="ollama",
        VLM_BACKUP_PROVIDER="deepseek",
        VLM_BACKUP_MODEL="m",
        DEEPSEEK_API_KEY="kunci-deepseek",
    )
    assert r["backup"]["has_key"] is True and r["backup"]["is_live"] is True
