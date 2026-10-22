"""Ganti penyedia VLM dari dashboard (T28).

Rambu rancangan yang disetujui 06-10:
(a) key hanya dari .env, tidak pernah dikirim ke penyedia lain / ke browser;
(b) engine ditukar hanya saat jalur kosong, inspeksi yang berjalan tidak dipotong;
(c) setiap pergantian tercatat di security log (T53);
(d) model `unsafe` selalu ditolak, model belum tervalidasi hanya dengan konfirmasi;
(e) pilihan dashboard disimpan & menang atas .env, bisa dikembalikan ke .env.
"""

import json
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend import messages, runtime_settings, vlm_selection
from backend.config import cfg
from backend.vlm_analyzer import ROLE_BACKUP, ROLE_PRIMARY, EngineFailed, LaneBusy, VLMAnalyzer
from backend.vlm_providers import profiles
from backend.vlm_providers.base import VLMProvider
from backend.vlm_selection import Choice, Selection, SelectionError

from helpers import PROVIDER_KEY_ENVS, person_crop

UNSAFE = next(v for v in profiles.VALIDATIONS if v.missed > 0)
SAFE = next(
    v
    for v in profiles.VALIDATIONS
    if v.missed == 0
    and v.prompt_version == messages.PROMPT_VERSION
    and not any(o.missed for o in profiles.VALIDATIONS if (o.provider, o.model) == (v.provider, v.model))
)
REPLY = json.dumps({"items": {}, "orang_nyata": True})


class FakeProvider(VLMProvider):
    """Penyedia tiruan: mencatat panggilan; bisa dibuat lambat atau gagal."""

    made: list = []

    def __init__(self, name, model, api_key, fail_warm_up=False, delay=0.0):
        super().__init__(model)
        self.name, self.api_key, self.fail_warm_up, self.delay = name, api_key, fail_warm_up, delay
        self.calls = 0

    def generate(self, image_jpeg, system_prompt, user_prompt):
        self.calls += 1
        time.sleep(self.delay)
        return REPLY

    def ping(self):
        return "PONG"

    warm_up_error = "model tidak ditemukan"

    def warm_up(self):
        if self.fail_warm_up:
            raise RuntimeError(self.warm_up_error)

    unloads = 0
    # Porsi model di GPU menurut /api/ps tiruan: 1.0 = dimuat, 0.0 = tidak, Exception = Ollama mati
    residency: "float | Exception" = 0.0  # T72: cadangan mulai dingin; tes model sisa mengisi 1.0 eksplisit.

    def unload(self):
        self.unloads += 1

    def gpu_residency(self):
        if isinstance(self.residency, Exception):
            raise self.residency
        return self.residency


@pytest.fixture
def env(monkeypatch, tmp_path):
    """.env tiruan: utama gemini (key), cadangan ollama; penyedia lain sesuai tes."""
    for name in PROVIDER_KEY_ENVS:
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("GEMINI_API_KEY", "kunci-gemini")
    monkeypatch.setenv("OPENAI_API_KEY", "kunci-openai")
    for attr, value in (
        ("VLM_PROVIDER", "gemini"),
        ("VLM_MODEL", "gemini-3.5-flash-lite"),
        ("VLM_API_KEY", "kunci-gemini"),
        ("VLM_BASE_URL", ""),
        ("VLM_BACKUP_PROVIDER", "ollama"),
        ("VLM_BACKUP_MODEL", "qwen2.5vl:7b"),
        ("VLM_BACKUP_API_KEY", ""),
        ("VLM_BACKUP_BASE_URL", ""),
        ("VLM_CLOUD_TIMEOUT_SECONDS", 2.0),
        ("VLM_LOCAL_TIMEOUT_SECONDS", 2.0),
        ("VLM_MIN_INTERVAL_SECONDS", 0.0),
    ):
        monkeypatch.setattr(cfg, attr, value)
    monkeypatch.setattr(runtime_settings, "SETTINGS_PATH", tmp_path / "runtime_settings.json")
    return tmp_path


@pytest.fixture
def fakes(monkeypatch):
    """Adaptor penyedia diganti tiruan; `options` mengatur perilaku per penyedia."""
    made, options = [], {}

    def create(name, api_key, model, base_url="", **_):
        provider = FakeProvider(name, model, api_key, **options.get(name, {}))
        made.append(provider)
        return provider

    monkeypatch.setattr("backend.vlm_analyzer.create_provider", create)
    return made, options


@pytest.fixture
def analyzer(env, fakes):
    a = VLMAnalyzer()
    a.start()
    yield a
    for e in (a.primary, a.backup):
        if e is not None:
            e.close()


# --- (a) key hanya dari .env ---------------------------------------------------------


def test_key_env_tercatat_untuk_semua_penyedia_cloud_bernama():
    named = {p.key_env for p in profiles.PROFILES.values() if p.key_env}
    assert named == set(PROVIDER_KEY_ENVS), "helpers.PROVIDER_KEY_ENVS harus sama dengan katalog profil"
    assert all(p.key_env or p.is_local or p.name == "openai-compatible" for p in profiles.PROFILES.values())


def test_key_satu_penyedia_tidak_dipakai_penyedia_lain(env):
    assert vlm_selection.api_key_for("gemini") == "kunci-gemini"
    assert vlm_selection.api_key_for("openai") == "kunci-openai"
    assert vlm_selection.api_key_for("deepseek") == "", "VLM_API_KEY milik gemini tidak boleh bocor"
    assert vlm_selection.api_key_for("ollama") == ""


def test_katalog_tanpa_key_dan_menandai_penyedia_siap(env):
    catalog = vlm_selection.provider_catalog([Choice("gemini", "gemini-3.5-flash-lite")])
    text = json.dumps(catalog)
    assert "kunci-" not in text
    ready = {p["name"]: p["has_key"] for p in catalog}
    assert ready["gemini"] and ready["openai"] and ready["ollama"]
    assert not ready["deepseek"] and not ready["anthropic"], "key belum ada di .env"
    assert not ready["vllm"], "vLLM tanpa alamat tidak bisa dipakai"
    # UI menulis "isi key" vs "isi alamat" dari sini; vLLM lokal tidak pernah butuh key
    missing = {p["name"]: p["missing"] for p in catalog}
    assert missing["gemini"] is None and missing["ollama"] is None
    assert missing["deepseek"] == "key" and missing["vllm"] == "base_url"
    assert missing["openai-compatible"] == "key", "key dicek lebih dulu daripada alamat"
    unsafe = next(p for p in catalog if p["name"] == UNSAFE.provider)
    entry = next(m for m in unsafe["models"] if m["model"] == UNSAFE.model)
    assert entry["validated"] == profiles.UNSAFE and entry["missed"] == UNSAFE.missed


@pytest.mark.parametrize(
    "text",
    [
        "openai HTTP 401: Incorrect API key provided: kunci-op***enai. You can find your API key",
        "openai HTTP 401: key kunci-openai ditolak",
    ],
)
def test_pesan_galat_penyedia_tanpa_key(text):
    clean = vlm_selection.redact(text, "kunci-openai")
    assert "kunci-op" not in clean and "kunci-openai" not in clean and "HTTP 401" in clean


def test_galat_pemanasan_ke_browser_tanpa_potongan_key(analyzer, fakes, monkeypatch):
    _, options = fakes
    options["openai"] = {"fail_warm_up": True}
    monkeypatch.setattr(FakeProvider, "warm_up_error", "Incorrect API key provided: kunci-op***enai")
    with pytest.raises(EngineFailed) as e:
        analyzer.apply_selection(Selection(Choice("openai", "m"), None, "dashboard"), lambda: True)
    assert "kunci-op" not in str(e.value) and vlm_selection.REDACTED in str(e.value)


# --- (d) aturan pilihan --------------------------------------------------------------


@pytest.mark.parametrize(
    "choice, code",
    [
        (Choice("tidak-ada", "m"), "unknown_provider"),
        (Choice("openai", ""), "missing_model"),
        (Choice("deepseek", "deepseek-flash"), "missing_key"),
        (Choice("vllm", "m"), "missing_base_url"),
    ],
)
def test_pilihan_tidak_lengkap_ditolak(env, choice, code):
    with pytest.raises(SelectionError) as e:
        vlm_selection.check_choice(choice, confirm_unvalidated=True)
    assert e.value.code == code


def test_model_tidak_aman_selalu_ditolak_walau_dikonfirmasi(env):
    with pytest.raises(SelectionError) as e:
        vlm_selection.check_choice(Choice(UNSAFE.provider, UNSAFE.model), confirm_unvalidated=True)
    assert e.value.code == "unsafe_model"


def test_model_belum_tervalidasi_perlu_konfirmasi(env):
    choice = Choice("openai", "model-baru")
    with pytest.raises(SelectionError) as e:
        vlm_selection.check_choice(choice, confirm_unvalidated=False)
    assert e.value.code == "needs_confirmation"
    vlm_selection.check_choice(choice, confirm_unvalidated=True)


def test_model_tervalidasi_tanpa_konfirmasi(env):
    vlm_selection.check_choice(Choice(SAFE.provider, SAFE.model), confirm_unvalidated=False)


# --- (e) pilihan tersimpan -----------------------------------------------------------


def test_tanpa_pilihan_tersimpan_memakai_env(env):
    s = vlm_selection.effective_selection()
    assert (s.primary, s.backup, s.source) == (
        Choice("gemini", "gemini-3.5-flash-lite"),
        Choice("ollama", "qwen2.5vl:7b"),
        vlm_selection.SOURCE_ENV,
    )


def test_pilihan_tersimpan_menang_atas_env(env):
    vlm_selection.save(Selection(Choice("openai", "model-baru"), None, vlm_selection.SOURCE_DASHBOARD))
    s = vlm_selection.effective_selection()
    assert (s.primary, s.backup, s.source) == (Choice("openai", "model-baru"), None, vlm_selection.SOURCE_DASHBOARD)
    vlm_selection.clear()
    assert vlm_selection.effective_selection().source == vlm_selection.SOURCE_ENV


@pytest.mark.parametrize(
    "stored",
    [
        {"primary": {"provider": UNSAFE.provider, "model": UNSAFE.model}, "backup": None},
        {"primary": {"provider": "deepseek", "model": "m"}, "backup": None},
        {"primary": None, "backup": None},
        "rusak",
    ],
)
def test_pilihan_tersimpan_yang_tidak_boleh_lagi_diabaikan(env, stored):
    """Katalog validasi atau .env bisa berubah sejak pilihan disimpan."""
    runtime_settings.update(vlm_selection.SETTINGS_KEY, stored)
    assert vlm_selection.effective_selection().source == vlm_selection.SOURCE_ENV


# --- (b) pertukaran engine -----------------------------------------------------------


def test_apply_menukar_engine_dan_memakai_ulang_yang_sama(analyzer, fakes):
    made, _ = fakes
    backup_before = analyzer.backup
    current = analyzer.apply_selection(
        Selection(Choice("openai", "model-baru"), Choice("ollama", "qwen2.5vl:7b"), vlm_selection.SOURCE_DASHBOARD),
        lambda: True,
        client="uji",
    )
    assert current["primary"] == {"provider": "openai", "model": "model-baru", "source": "dashboard"}
    assert analyzer.backup is backup_before, "cadangan tidak berubah: tidak dirakit/dipanaskan ulang"
    assert analyzer.primary.provider.api_key == "kunci-openai"
    result = analyzer.analyze_person(person_crop())
    assert result.inference_source == "VLM_LIVE:openai/model-baru"


def test_gagal_panaskan_engine_lama_tetap_dipakai(analyzer, fakes):
    _, options = fakes
    options["openai"] = {"fail_warm_up": True}
    before = analyzer.primary
    with pytest.raises(EngineFailed) as e:
        analyzer.apply_selection(Selection(Choice("openai", "m"), None, "dashboard"), lambda: True)
    assert "model tidak ditemukan" in str(e.value)
    assert analyzer.primary is before and analyzer.backup is not None


def test_jalur_berisi_tidak_ditukar(analyzer):
    before = (analyzer.primary, analyzer.backup)
    with pytest.raises(LaneBusy):
        analyzer.apply_selection(Selection(Choice("openai", "m"), None, "dashboard"), lambda: False)
    assert (analyzer.primary, analyzer.backup) == before


def test_inspeksi_berjalan_selesai_dengan_engine_lama(analyzer, fakes):
    """Pertukaran menunggu gembok inspeksi: keputusan tidak dicampur dua penyedia."""
    _, options = fakes
    analyzer.primary.provider.delay = 0.5
    results = []
    worker = threading.Thread(target=lambda: results.append(analyzer.analyze_person(person_crop())))
    worker.start()
    time.sleep(0.1)  # inspeksi sudah memegang gembok
    analyzer.apply_selection(Selection(Choice("openai", "m"), None, "dashboard"), lambda: True)
    assert results, "pertukaran harus menunggu inspeksi yang sedang berjalan selesai"
    worker.join()
    assert results[0].inference_source == "VLM_LIVE:gemini/gemini-3.5-flash-lite"
    assert analyzer.primary.provider_name == "openai" and analyzer.backup is None


# --- (c) jejak -----------------------------------------------------------------------


def test_setiap_pergantian_tercatat(analyzer, security_events):
    analyzer.apply_selection(
        Selection(Choice("openai", "model-baru"), None, "dashboard"), lambda: True, client="10.0.0.5", user="admin-uji"
    )
    lines = [e for e in security_events if e["event"] == "vlm_change"]
    assert [(x["role"], x["to"]) for x in lines] == [
        (ROLE_PRIMARY, {"provider": "openai", "model": "model-baru"}),
        (ROLE_BACKUP, None),
    ]
    assert lines[0]["from"] == {"provider": "gemini", "model": "gemini-3.5-flash-lite"}
    assert lines[0]["validated"] == profiles.UNVALIDATED and lines[0]["client"] == "10.0.0.5"
    assert lines[0]["user"] == "admin-uji", "T51: jejak mencatat siapa yang mengganti"


# --- Uji penyedia ---------------------------------------------------------------------


def test_uji_penyedia_tidak_menyentuh_engine_gerbang(analyzer):
    before = analyzer.primary
    r = analyzer.test_choice(ROLE_PRIMARY, Choice("openai", "m"))
    assert r["ok"] is True and r["json_ok"] is True and r["latency_ms"] is not None
    assert analyzer.primary is before


# --- Endpoint -------------------------------------------------------------------------


@pytest.fixture
def client(analyzer, monkeypatch):
    from backend.api import routes_vlm
    from backend.app import app

    monkeypatch.setattr(routes_vlm, "vlm_analyzer", analyzer)
    monkeypatch.setattr(routes_vlm.state_mgr, "session", None)
    return TestClient(app)


def test_endpoint_daftar_penyedia(client):
    r = client.get("/api/config/vlm/providers").json()
    assert r["prompt_version"] == messages.PROMPT_VERSION
    assert r["current"]["primary"] == {"provider": "gemini", "model": "gemini-3.5-flash-lite", "source": "env"}
    assert "kunci-" not in json.dumps(r)


def test_endpoint_apply_kode_galat(client):
    def post(body):
        return client.post("/api/config/vlm/apply", json=body)

    r = post({"primary": {"provider": UNSAFE.provider, "model": UNSAFE.model}, "confirm_unvalidated": True})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unsafe_model"
    r = post({"primary": {"provider": "openai", "model": "model-baru"}})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "needs_confirmation"
    r = post({"primary": {"provider": "openai", "model": "model-baru"}, "backup": None, "confirm_unvalidated": True})
    assert r.status_code == 200 and r.json()["primary"]["source"] == "dashboard"
    assert runtime_settings.load()[vlm_selection.SETTINGS_KEY]["primary"]["provider"] == "openai"


def test_endpoint_apply_409_saat_ada_pekerja(client, monkeypatch):
    from backend.api import routes_vlm

    monkeypatch.setattr(routes_vlm.state_mgr, "session", object())
    r = client.post("/api/config/vlm/apply", json={"primary": {"provider": SAFE.provider, "model": SAFE.model}})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "lane_busy"


def test_endpoint_kembali_ke_env(client):
    client.post(
        "/api/config/vlm/apply", json={"primary": {"provider": "openai", "model": "m"}, "confirm_unvalidated": True}
    )
    r = client.delete("/api/config/vlm/selection")
    assert r.status_code == 200 and r.json()["primary"]["provider"] == "gemini"
    assert r.json()["primary"]["source"] == "env"
    assert runtime_settings.load().get(vlm_selection.SETTINGS_KEY) is None


@pytest.mark.parametrize("fallback_provider", ["ollama", "gemini"])
def test_invalid_env_fallback_warns_and_keeps_startup_running(env, fakes, monkeypatch, caplog, fallback_provider):
    monkeypatch.setattr(cfg, "VLM_LOCAL_FALLBACK_PROVIDER", fallback_provider)
    with caplog.at_level(logging.WARNING):
        analyzer = VLMAnalyzer()
        analyzer.start()
    try:
        assert analyzer.primary is not None and analyzer.backup is not None
        assert analyzer.current_selection()["local_fallback"] is None
        assert any(messages.VLM_LOCAL_FALLBACK_ENV_IGNORED.split(":")[0] in r.message for r in caplog.records)
    finally:
        for engine in analyzer._engines():
            engine.close()


def test_reset_with_conflicting_local_env_fallback_returns_200(client, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_LOCAL_FALLBACK_PROVIDER", "ollama")
    response = client.delete("/api/config/vlm/selection")
    assert response.status_code == 200
    assert response.json()["backup"]["provider"] == "ollama"
    assert response.json()["local_fallback"] is None


def test_endpoint_uji(client):
    r = client.post("/api/config/vlm/test", json={"role": "backup", "provider": "openai", "model": "m"})
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.post("/api/config/vlm/test", json={"provider": "deepseek", "model": "m"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "missing_key"


@pytest.mark.parametrize("provider", ["", "none", "  NONE "])
def test_endpoint_uji_tanpa_penyedia_ditolak_400(client, provider):
    # T65: dulu Choice.parse -> None lalu check_choice(None) -> AttributeError -> HTTP 500
    r = client.post("/api/config/vlm/test", json={"role": "backup", "provider": provider, "model": "m"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unknown_provider"


# --- T70: cadangan dimatikan = model keluar dari GPU -----------------------------------


def _wait_unloaded(provider, expected=1, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end and provider.unloads < expected:
        time.sleep(0.01)
    return provider.unloads


def test_mematikan_cadangan_mengeluarkan_model_dari_gpu(analyzer):
    old_backup = analyzer.backup.provider
    analyzer.apply_selection(
        Selection(Choice("gemini", "gemini-3.5-flash-lite"), None, vlm_selection.SOURCE_DASHBOARD), lambda: True
    )
    assert analyzer.backup is None
    assert _wait_unloaded(old_backup) == 1


def test_cadangan_yang_tetap_dipakai_tidak_dikeluarkan(analyzer):
    backup = analyzer.backup.provider
    analyzer.apply_selection(
        Selection(Choice("openai", "model-baru"), Choice("ollama", "qwen2.5vl:7b"), vlm_selection.SOURCE_DASHBOARD),
        lambda: True,
    )
    time.sleep(0.2)
    assert analyzer.backup.provider is backup and backup.unloads == 0


def test_ganti_model_lokal_yang_lama_dikeluarkan(analyzer):
    old = analyzer.backup.provider
    analyzer.apply_selection(
        Selection(
            Choice("gemini", "gemini-3.5-flash-lite"), Choice("ollama", "qwen2.5vl:3b"), vlm_selection.SOURCE_DASHBOARD
        ),
        lambda: True,
    )
    assert _wait_unloaded(old) == 1 and analyzer.backup.provider.unloads == 0


def _start_without_backup(monkeypatch, made, residency: "float | Exception" = 1.0, env_backup=None):
    """Server menyala tanpa VLM lokal; model Ollama sisa sesi lalu = `residency` di /api/ps tiruan."""
    if env_backup is not None:
        monkeypatch.setattr(cfg, "VLM_BACKUP_PROVIDER", env_backup)
    monkeypatch.setattr(FakeProvider, "residency", residency)
    monkeypatch.setattr(
        vlm_selection,
        "effective_selection",
        lambda: Selection(Choice("gemini", "gemini-3.5-flash-lite"), None, vlm_selection.SOURCE_DASHBOARD),
    )
    a = VLMAnalyzer()
    a.start()
    stale = [p for p in made if p.name == "ollama"]
    assert a.backup is None and len(stale) == 1 and a.primary is not None
    return a, stale[0]


@pytest.mark.stale_model
def test_saat_menyala_tanpa_cadangan_model_sisa_sesi_lalu_dikeluarkan(env, fakes, monkeypatch):
    a, stale = _start_without_backup(monkeypatch, fakes[0])
    assert _wait_unloaded(stale) == 1 and stale.model == "qwen2.5vl:7b"
    a.primary.close()  # pyright: ignore[reportOptionalMemberAccess] (dicek di _start_without_backup)


@pytest.mark.stale_model
def test_saat_menyala_env_tanpa_cadangan_model_bawaan_ollama_dikeluarkan(env, fakes, monkeypatch):
    """Uji nyata 19-10: .env tanpa cadangan (bawaan T71) dulu melewati pembersihan → model tertinggal."""
    a, stale = _start_without_backup(monkeypatch, fakes[0], env_backup="none")
    assert _wait_unloaded(stale) == 1 and stale.model == profiles.default_model(cfg.VLM_LOCAL_BACKUP_PROVIDER)
    a.primary.close()  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.stale_model
def test_saat_menyala_model_tidak_dimuat_tidak_dibongkar(env, fakes, monkeypatch):
    a, stale = _start_without_backup(monkeypatch, fakes[0], residency=0.0, env_backup="none")
    time.sleep(0.2)
    assert stale.unloads == 0
    a.primary.close()  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.stale_model
def test_saat_menyala_ollama_mati_diam_tanpa_peringatan(env, fakes, monkeypatch, caplog):
    """Gerbang tanpa cadangan di mesin tanpa Ollama: bukan masalah, tidak boleh mengotori log."""
    with caplog.at_level(logging.WARNING):
        a, stale = _start_without_backup(
            monkeypatch, fakes[0], residency=ConnectionError("ollama mati"), env_backup="none"
        )
        time.sleep(0.2)
    stale_logs = [r for r in caplog.records if "Ollama" in r.getMessage() or "GPU" in r.getMessage()]
    assert stale.unloads == 0 and not stale_logs
    a.primary.close()  # pyright: ignore[reportOptionalMemberAccess]
