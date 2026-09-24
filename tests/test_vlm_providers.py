"""Adaptor penyedia VLM dan jalur VLMAnalyzer di atasnya, tanpa panggilan jaringan."""
import json
import time

import cv2
import numpy as np
import pytest

from backend import messages, ppe_rules
from backend.config import cfg
from backend.vlm_analyzer import USER_PROMPT, VLMAnalyzer, VLMEngine
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


def _engine(role, provider, local=False, timeout=None):
    """VLM utama/cadangan dengan penyedia tiruan, tanpa jeda kuota."""
    e = VLMEngine(role, "ollama" if local else "gemini", "model-palsu", api_key="kunci-palsu")
    e.provider, e.min_interval = provider, 0.0
    if timeout is not None:
        e.timeout = timeout
    return e


@pytest.fixture
def analyzer(catalog_defaults):
    a = VLMAnalyzer()

    def pasang(utama=None, cadangan=None, **opsi):
        a.primary = _engine("utama", utama, timeout=opsi.get("timeout_utama")) if utama else None
        a.backup = _engine("cadangan", cadangan, local=True, timeout=opsi.get("timeout_cadangan")) if cadangan else None
        return a

    a.pasang = pasang
    yield a
    for e in (a.primary, a.backup):
        if e is not None:
            e.executor.shutdown(wait=False)


def test_jawaban_utama_menjadi_keputusan(analyzer):
    utama = FakeProvider(reply=_lengkap())
    hasil = analyzer.pasang(utama=utama, cadangan=FakeProvider(reply=_lengkap())).analyze_person(person_crop())

    assert hasil.inference_source == "VLM_LIVE:gemini/model-palsu" == analyzer.source_label
    assert hasil.decided_by == "utama"
    assert hasil.is_complete is True and hasil.is_system_unavailable is False
    assert analyzer.backup.provider.calls == [], "Cadangan tidak disentuh selama utama menjawab"

    (jpeg, system_prompt, user_prompt), = utama.calls
    assert user_prompt == USER_PROMPT
    assert cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR) is not None, "Gambar harus JPEG utuh"
    # Prompt menyebut item lewat kuncinya di bentuk JSON yang diminta
    for item in ppe_rules.get_active_items():
        assert f'"{item.key}":' in system_prompt


def test_prompt_mengikuti_item_aktif_tanpa_membuat_klien_ulang(analyzer, catalog_defaults):
    utama = FakeProvider(reply=_lengkap())
    analyzer.pasang(utama=utama)
    catalog_defaults.set_active({"kacamata": True})
    analyzer.analyze_person(person_crop())
    _, system_prompt, _ = utama.calls[0]
    assert '"kacamata":' in system_prompt


def _assert_diputuskan_cadangan(hasil, analyzer):
    assert hasil.decided_by == "cadangan"
    assert hasil.inference_source == "VLM_CADANGAN:ollama/model-palsu"
    assert hasil.is_complete is True and hasil.is_system_unavailable is False
    assert len(analyzer.backup.provider.calls) == 1


def test_utama_galat_cadangan_memutuskan_di_inspeksi_yang_sama(analyzer):
    analyzer.pasang(utama=FakeProvider(error=RuntimeError("503 UNAVAILABLE")), cadangan=FakeProvider(reply=_lengkap()))
    hasil = analyzer.analyze_person(person_crop())
    _assert_diputuskan_cadangan(hasil, analyzer)
    assert len(analyzer.primary.provider.calls) == 1, "Utama tidak diulang: pekerja langsung ke cadangan"


def test_utama_lambat_dibatasi_waktu_lalu_cadangan_memutuskan(analyzer):
    analyzer.pasang(utama=FakeProvider(reply=_lengkap(), delay=1.0), cadangan=FakeProvider(reply=_lengkap()),
                    timeout_utama=0.2)
    start = time.time()
    hasil = analyzer.analyze_person(person_crop())
    assert time.time() - start < 0.8, "Gerbang tidak menunggu utama melewati batas waktunya"
    _assert_diputuskan_cadangan(hasil, analyzer)


def test_jawaban_utama_rusak_dialihkan_ke_cadangan(analyzer):
    analyzer.pasang(utama=FakeProvider(reply="maaf, saya tidak bisa"), cadangan=FakeProvider(reply=_lengkap()))
    _assert_diputuskan_cadangan(analyzer.analyze_person(person_crop()), analyzer)


def _assert_tanpa_keputusan(hasil):
    # Tidak ada VLM yang menjawab: pekerja tidak diloloskan, tidak juga ditolak
    assert hasil.is_system_unavailable is True
    assert hasil.is_complete is False
    assert hasil.items == {} and hasil.missing_items == [], "Tidak ada item yang benar-benar diperiksa"
    assert hasil.inference_source == "VLM_GANGGUAN"


def test_utama_dan_cadangan_gagal_tanpa_keputusan(analyzer):
    analyzer.pasang(utama=FakeProvider(error=RuntimeError("503 UNAVAILABLE")),
                    cadangan=FakeProvider(error=RuntimeError("connection refused")))
    hasil = analyzer.analyze_person(person_crop())
    _assert_tanpa_keputusan(hasil)
    assert "503" in hasil.notes and "connection refused" in hasil.notes


def test_tanpa_cadangan_utama_gagal_tanpa_keputusan(analyzer):
    analyzer.pasang(utama=FakeProvider(error=RuntimeError("503 UNAVAILABLE")))
    hasil = analyzer.analyze_person(person_crop())
    _assert_tanpa_keputusan(hasil)
    assert "cadangan: tidak tersedia" in hasil.notes


def test_tanpa_vlm_sama_sekali_tanpa_keputusan(analyzer):
    hasil = analyzer.pasang().analyze_person(person_crop())
    _assert_tanpa_keputusan(hasil)
    assert messages.VLM_NOT_CONFIGURED in hasil.notes


def test_utama_dianggap_terputus_setelah_n_gagal_lalu_dicoba_lagi(analyzer, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_PRIMARY_FAILURES_BEFORE_DOWN", 2)
    monkeypatch.setattr(cfg, "VLM_PRIMARY_RETRY_AFTER_SECONDS", 0.3)
    utama = FakeProvider(error=RuntimeError("503 UNAVAILABLE"))
    analyzer.pasang(utama=utama, cadangan=FakeProvider(reply=_lengkap()))

    for _ in range(2):
        assert analyzer.analyze_person(person_crop()).decided_by == "cadangan"
    assert len(utama.calls) == 2 and analyzer.provider_info()["primary_down"] is True

    # Terputus: pekerja berikutnya langsung ke cadangan tanpa membuang waktu di utama
    assert analyzer.analyze_person(person_crop()).decided_by == "cadangan"
    assert len(utama.calls) == 2

    # Setelah jeda, utama dicoba lagi pada pekerja nyata; pulih = kembali memutuskan
    time.sleep(0.35)
    utama.error, utama.reply = None, _lengkap()
    hasil = analyzer.analyze_person(person_crop())
    assert hasil.decided_by == "utama" and len(utama.calls) == 3
    assert analyzer.provider_info()["primary_down"] is False


def test_jeda_kuota_hanya_untuk_vlm_cloud(analyzer):
    analyzer.pasang(utama=FakeProvider(reply=_lengkap()))
    analyzer.primary.min_interval = 0.4
    analyzer.primary.last_call_time = time.time()  # panggilan lain baru saja terjadi
    start = time.time()
    assert analyzer.analyze_person(person_crop()).decided_by == "utama"
    assert time.time() - start >= 0.35, "Kuota free tier dijaga dengan menunggu, bukan dilewati"

    lokal = VLMEngine("cadangan", "ollama", "m")
    cloud = VLMEngine("utama", "gemini", "m", api_key="k")
    assert lokal.min_interval == 0.0 and cloud.min_interval == cfg.VLM_MIN_INTERVAL_SECONDS
    assert lokal.timeout == cfg.VLM_LOCAL_TIMEOUT_SECONDS and cloud.timeout == cfg.VLM_CLOUD_TIMEOUT_SECONDS
    for e in (lokal, cloud):
        e.executor.shutdown(wait=False)


def test_antrean_vlm_yang_tidak_kunjung_kosong_tanpa_keputusan(analyzer):
    utama = FakeProvider(reply=_lengkap())
    analyzer.pasang(utama=utama, timeout_utama=0.1)
    analyzer.api_lock.acquire()  # inspeksi lain memegang giliran terlalu lama
    try:
        _assert_tanpa_keputusan(analyzer.analyze_person(person_crop()))
        assert utama.calls == []
    finally:
        analyzer.api_lock.release()


def test_ping_menguji_utama_dan_cadangan(analyzer):
    analyzer.pasang(utama=FakeProvider(), cadangan=FakeProvider(error=None))
    res = analyzer.ping_api()
    assert [r["role"] for r in res["engines"]] == ["utama", "cadangan"]
    assert all(r["ok"] for r in res["engines"])


def test_status_dashboard_mengikuti_siapa_yang_memutuskan(analyzer):
    from backend.api_monitor import api_monitor
    analyzer.pasang(utama=FakeProvider(error=RuntimeError("503")), cadangan=FakeProvider(reply=_lengkap()))
    analyzer.analyze_person(person_crop())
    assert api_monitor.get_status()["mode"] == "CADANGAN"
    analyzer.primary.provider.error = None
    analyzer.primary.provider.reply = _lengkap()
    analyzer.analyze_person(person_crop())
    assert api_monitor.get_status()["mode"] == "UTAMA"
    analyzer.primary.provider.error = RuntimeError("503")
    analyzer.backup.provider.error = RuntimeError("mati")
    analyzer.analyze_person(person_crop())
    assert api_monitor.get_status()["mode"] == "GANGGUAN"


def test_klien_gemini_membatalkan_panggilan_lewat_batas_waktu(monkeypatch):
    # Tanpa batas waktu HTTP, panggilan saat Google kelebihan beban menggantung
    # ~60 dtk dan menyandera thread walau aplikasi berhenti menunggu (T27).
    from google import genai
    dibuat = {}

    class ClientPalsu:
        def __init__(self, **kwargs):
            dibuat.update(kwargs)

    monkeypatch.setattr(genai, "Client", ClientPalsu)
    GeminiProvider(api_key="k", model="m", http_timeout=12.0)
    assert dibuat["http_options"].timeout == 12000, "SDK google-genai memakai milidetik"
    # Gemini menolak tenggat < 10 dtk (400 INVALID_ARGUMENT, terukur 24-09)
    GeminiProvider(api_key="k", model="m", http_timeout=5.0)
    assert dibuat["http_options"].timeout == 10000


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
