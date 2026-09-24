"""Adaptor penyedia VLM dan jalur VLMAnalyzer di atasnya, tanpa panggilan jaringan."""
import json
import time

import cv2
import numpy as np
import pytest

from backend import messages, ppe_rules
from backend.config import cfg
from backend.vlm_analyzer import USER_PROMPT, VLMAnalyzer
from backend.vlm_providers import VLMProvider, create_provider, parse_json_reply
from backend.vlm_providers.gemini import GeminiProvider

from helpers import person_crop


# --- Penguraian jawaban ---------------------------------------------------------

@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    '```\n{"a": 1}\n```',
    '  {"a": 1}  \n',
])
def test_jawaban_json_diurai_dengan_atau_tanpa_pagar(text):
    assert parse_json_reply(text) == {"a": 1}


def test_jawaban_bukan_objek_ditolak():
    with pytest.raises(ValueError):
        parse_json_reply("[1, 2]")


def test_penyedia_tidak_dikenal_ditolak():
    with pytest.raises(ValueError):
        create_provider("tidak-ada", api_key="x", model="m")


# --- Adaptor Gemini ------------------------------------------------------------------

class _Recorder:
    """Pengganti `client.models` yang mencatat permintaan alih-alih mengirimnya."""

    def __init__(self, reply):
        self.calls = []
        self.reply = reply

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return type("Resp", (), {"text": self.reply})()


def test_klien_gemini_dibuat_tanpa_jaringan():
    # Kunci palsu tidak boleh gagal di sini; kesalahan kunci baru muncul saat dipanggil
    provider = create_provider("gemini", api_key="kunci-palsu", model="gemini-3.5-flash-lite")
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


def test_permintaan_gemini_sama_dengan_perilaku_lama(monkeypatch):
    provider = GeminiProvider(api_key="kunci-palsu", model="gemini-3.5-flash-lite")
    recorder = _Recorder('{"ok": true}')
    # `models` pada klien SDK hanya-baca, jadi klien diganti utuh
    monkeypatch.setattr(provider, "_client", type("Client", (), {"models": recorder})())

    jpeg = b"\xff\xd8contoh-jpeg\xff\xd9"
    assert provider.analyze(jpeg, system_prompt="SISTEM", user_prompt="PENGGUNA") == {"ok": True}

    (call,) = recorder.calls
    assert call["model"] == "gemini-3.5-flash-lite"
    teks, gambar = call["contents"]
    assert teks == "PENGGUNA"
    assert gambar.inline_data.mime_type == "image/jpeg"
    assert gambar.inline_data.data == jpeg
    conf = call["config"]
    assert conf.system_instruction == "SISTEM"
    assert conf.response_mime_type == "application/json"
    assert conf.temperature == 0.1


def test_ping_gemini_mengembalikan_teks(monkeypatch):
    provider = GeminiProvider(api_key="kunci-palsu", model="gemini-3.5-flash-lite")
    monkeypatch.setattr(provider, "_client", type("Client", (), {"models": _Recorder(" PONG \n")})())
    assert provider.ping() == "PONG"


# --- VLMAnalyzer dengan penyedia tiruan ------------------------------------------------

class FakeProvider(VLMProvider):
    name = "palsu"

    def __init__(self, reply=None, error=None, delay=0.0):
        super().__init__("model-palsu")
        self.reply, self.error, self.delay = reply, error, delay
        self.calls = []

    def generate(self, image_jpeg, system_prompt, user_prompt):
        self.calls.append((image_jpeg, system_prompt, user_prompt))
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.reply

    def ping(self):
        return "PONG"


def _lengkap():
    return json.dumps({"items": {
        "helm": {"detected": True},
        "rompi": {"detected": True, "is_valid_color": True, "color": "orange"},
        "celana": {"detected": True},
        "sepatu": {"detected": True, "is_closed_shoes": True},
    }, "missing_items": [], "notes": "lengkap"})


@pytest.fixture
def analyzer(catalog_defaults, monkeypatch):
    # Jeda free tier dimatikan supaya percobaan ulang tidak membuat tes lambat
    monkeypatch.setattr(cfg, "FREE_TIER_MIN_INTERVAL_SECONDS", 0.0)
    a = VLMAnalyzer()
    a.api_key = "kunci-palsu"
    yield a
    a.executor.shutdown(wait=False)


def test_jawaban_penyedia_menjadi_keputusan_vlm(analyzer):
    analyzer.provider = FakeProvider(reply=_lengkap())
    hasil = analyzer.analyze_person(person_crop(vest=False))

    # Keputusan dari VLM, bukan dari engine lokal yang melihat rompi hilang
    assert hasil.inference_source == "GEMINI_LIVE"
    assert hasil.is_complete is True
    assert hasil.is_low_confidence is False

    (jpeg, system_prompt, user_prompt), = analyzer.provider.calls
    assert user_prompt == USER_PROMPT
    assert cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR) is not None, "Gambar harus JPEG utuh"
    # Prompt menyebut item lewat kuncinya di bentuk JSON yang diminta
    for item in ppe_rules.get_active_items():
        assert f'"{item.key}":' in system_prompt


def test_prompt_mengikuti_item_aktif_tanpa_membuat_klien_ulang(analyzer, catalog_defaults):
    analyzer.provider = FakeProvider(reply=_lengkap())
    catalog_defaults.set_active({"kacamata": True})
    analyzer.analyze_person(person_crop())
    _, system_prompt, _ = analyzer.provider.calls[0]
    assert '"kacamata":' in system_prompt


def _assert_ditolak_tidak_terverifikasi(hasil):
    # Selama VLM aktif, kegagalan tidak boleh berubah jadi keputusan heuristik lokal
    assert hasil.is_unverified is True
    assert hasil.is_complete is False
    assert hasil.items == {}, "Tidak ada item yang benar-benar diperiksa"
    assert hasil.missing_items == [messages.VLM_UNVERIFIED_LABEL]
    assert hasil.inference_source.startswith("VLM_GAGAL")


def test_galat_penyedia_dicoba_ulang_lalu_ditolak(analyzer):
    analyzer.provider = FakeProvider(error=RuntimeError("503 overloaded"))
    # Orang ber-APD lengkap sekalipun tidak diloloskan tanpa verifikasi VLM
    hasil = analyzer.analyze_person(person_crop())
    _assert_ditolak_tidak_terverifikasi(hasil)
    assert len(analyzer.provider.calls) == cfg.VLM_MAX_ATTEMPTS == 2
    assert "503" in hasil.notes


def test_penyedia_lambat_dicoba_ulang_lalu_ditolak(analyzer, monkeypatch):
    monkeypatch.setattr(cfg, "GEMINI_TIMEOUT_SECONDS", 0.2)
    analyzer.provider = FakeProvider(reply=_lengkap(), delay=1.0)
    start = time.time()
    hasil = analyzer.analyze_person(person_crop())
    assert time.time() - start < 0.9, "Tiap percobaan dibatasi timeout, gerbang tidak menunggu penyedia"
    _assert_ditolak_tidak_terverifikasi(hasil)
    assert hasil.inference_source == "VLM_GAGAL (API Timeout)"
    assert len(analyzer.provider.calls) == 2


def test_jawaban_rusak_dicoba_ulang_lalu_ditolak(analyzer):
    analyzer.provider = FakeProvider(reply="maaf, saya tidak bisa")
    _assert_ditolak_tidak_terverifikasi(analyzer.analyze_person(person_crop()))


class FlakyProvider(FakeProvider):
    """Gagal pada panggilan pertama, berhasil pada berikutnya."""

    def generate(self, image_jpeg, system_prompt, user_prompt):
        self.calls.append((image_jpeg, system_prompt, user_prompt))
        if len(self.calls) == 1:
            raise RuntimeError("500 sementara")
        return self.reply


def test_percobaan_ulang_yang_berhasil_menjadi_keputusan_vlm(analyzer):
    analyzer.provider = FlakyProvider(reply=_lengkap())
    hasil = analyzer.analyze_person(person_crop())
    assert hasil.inference_source == "GEMINI_LIVE"
    assert hasil.is_complete is True
    assert len(analyzer.provider.calls) == 2


def test_jeda_free_tier_ditunggu_bukan_dialihkan_ke_lokal(analyzer, monkeypatch):
    monkeypatch.setattr(cfg, "FREE_TIER_MIN_INTERVAL_SECONDS", 0.4)
    analyzer.provider = FakeProvider(reply=_lengkap())
    analyzer.last_api_call_time = time.time()  # panggilan lain baru saja terjadi
    start = time.time()
    hasil = analyzer.analyze_person(person_crop(vest=False))
    assert time.time() - start >= 0.35
    assert hasil.inference_source == "GEMINI_LIVE"


def test_antrean_vlm_yang_tidak_kunjung_kosong_ditolak(analyzer, monkeypatch):
    monkeypatch.setattr(cfg, "GEMINI_TIMEOUT_SECONDS", 0.1)
    analyzer.provider = FakeProvider(reply=_lengkap())
    analyzer.api_lock.acquire()  # inspeksi lain memegang giliran terlalu lama
    try:
        _assert_ditolak_tidak_terverifikasi(analyzer.analyze_person(person_crop()))
        assert analyzer.provider.calls == []
    finally:
        analyzer.api_lock.release()


def test_mode_offline_pilihan_operator_tetap_memakai_engine_lokal(analyzer, monkeypatch):
    from backend.api_monitor import api_monitor
    monkeypatch.setattr(api_monitor, "engine_mode", "FORCE_LOCAL")
    analyzer.provider = FakeProvider(reply=_lengkap())
    hasil = analyzer.analyze_person(person_crop())
    assert hasil.inference_source == "LOCAL_GPU"
    assert hasil.is_low_confidence is True
    assert analyzer.provider.calls == []


def test_ping_lewat_penyedia(analyzer):
    analyzer.provider = FakeProvider()
    res = analyzer.ping_api()
    assert res["reply"] == "PONG"


def test_thinking_level_dikirim_bila_disetel(monkeypatch):
    provider = GeminiProvider(api_key="kunci-palsu", model="gemini-3.5-flash-lite", thinking_level="minimal")
    recorder = _Recorder('{"ok": true}')
    monkeypatch.setattr(provider, "_client", type("Client", (), {"models": recorder})())
    provider.analyze(b"\xff\xd8x\xff\xd9", system_prompt="S", user_prompt="U")
    provider.ping()
    for call in recorder.calls:
        assert call["config"].thinking_config.thinking_level.value == "MINIMAL"


def test_thinking_level_kosong_tidak_dikirim(monkeypatch):
    provider = GeminiProvider(api_key="kunci-palsu", model="gemini-3.5-flash-lite", thinking_level="")
    recorder = _Recorder('{"ok": true}')
    monkeypatch.setattr(provider, "_client", type("Client", (), {"models": recorder})())
    provider.analyze(b"\xff\xd8x\xff\xd9", system_prompt="S", user_prompt="U")
    assert recorder.calls[0]["config"].thinking_config is None
