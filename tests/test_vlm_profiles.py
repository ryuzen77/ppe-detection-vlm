"""Katalog profil penyedia VLM & validasi model (T39b)."""
import hashlib
import logging

import pytest

from backend import config, messages, ppe_rules, vlm_selection
from backend.vlm_analyzer import (VLMEngine, build_system_prompt, confirmation_prompts, profile_warnings,
                                  thinking_option)
from backend.vlm_providers import OPENAI_COMPATIBLE, profiles
from backend.vlm_providers.openai_compatible import PRESETS

# Sidik jari prompt per versi. Bila tes ini gagal, isi prompt berubah: NAIKKAN
# messages.PROMPT_VERSION, tambahkan sidik jari baru di sini, lalu uji ulang model
# dengan foto berlabel dan perbarui profiles.VALIDATIONS. Tanpa itu, validasi lama
# diam-diam dianggap berlaku untuk prompt yang belum pernah diuji.
PROMPT_FINGERPRINTS = {"T36a": "3e5dec9fea79c1c2", "T48": "9fa299193654696e", "T58": "1b4f2a739acb7d79",
                       "T86": "1e31d0a1525c2f20"}


def _fingerprint(zoom: bool) -> str:
    # Pertanyaan konfirmasi larangan (T58) ikut menentukan keputusan, jadi ikut sidik jari
    confirm = "".join("".join(confirmation_prompts(i, zoom)) for i in ppe_rules.get_items() if i.prohibited)
    text = build_system_prompt(ppe_rules.get_items(), zoom) + confirm
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def test_prompt_berubah_wajib_menaikkan_versi(catalog_defaults):
    fingerprint = _fingerprint(zoom=True)
    assert PROMPT_FINGERPRINTS.get(messages.PROMPT_VERSION) == fingerprint, (
        f"Prompt berubah ({fingerprint}) tanpa menaikkan PROMPT_VERSION={messages.PROMPT_VERSION}")


def test_prompt_tanpa_panel_identik_versi_lama(catalog_defaults):
    """T86: VLM lokal memakai prompt & gambar tanpa panel; validasi lokal T58 (84 foto) hanya berlaku
    bila isinya PERSIS sama — bila tes ini gagal, PROMPT_VERSION_NO_ZOOM wajib dinaikkan & diuji ulang."""
    assert PROMPT_FINGERPRINTS.get(messages.PROMPT_VERSION_NO_ZOOM) == _fingerprint(zoom=False)


# --- Katalog ----------------------------------------------------------------------------

def test_resmi_hanya_gemini_dan_ollama():
    official = {n for n, p in profiles.PROFILES.items() if p.support == profiles.OFFICIAL}
    assert official == {"gemini", "ollama"}


def test_satu_sumber_untuk_adaptor_dan_config():
    # Setiap profil punya adaptor: OpenAI-compatible, Gemini, atau Anthropic (T28)
    anthropic = {n for n, p in profiles.PROFILES.items() if p.api == profiles.API_ANTHROPIC}
    assert anthropic == {"anthropic"}
    assert set(OPENAI_COMPATIBLE) | {"gemini"} | anthropic == set(profiles.PROFILES)
    assert PRESETS["ollama"] == profiles.PROFILES["ollama"].base_url
    assert set(config.LOCAL_VLM_PROVIDERS) == {"ollama", "vllm"}
    assert profiles.default_model("ollama") == "qwen2.5vl:7b"
    assert profiles.default_model("openrouter") == "", "penyedia cloud lain wajib menyebut modelnya"


# --- Status validasi ---------------------------------------------------------------------

def test_status_model_saat_ini():
    v = messages.PROMPT_VERSION
    # T86: VLM lokal menerima prompt & gambar TANPA panel (isi T58 persis) -> dinilai dengan versi itu
    local_version = vlm_selection.prompt_version_for("ollama")
    assert local_version == messages.PROMPT_VERSION_NO_ZOOM and vlm_selection.prompt_version_for("gemini") == v
    assert profiles.validation_status("ollama", "qwen2.5vl:7b", local_version) == profiles.VALIDATED
    # Gemini T58: 5 foto (izin pengguna 14-10) → sebagian
    assert profiles.validation_status("gemini", "gemini-3.5-flash-lite", v) == profiles.PARTIAL
    record = profiles.find_validation("gemini", "gemini-3.5-flash-lite", v)
    assert record is not None and record.prompt_version == v
    assert profiles.validation_status("openrouter", "model-baru", v) == profiles.UNVALIDATED
    assert profiles.validation_status("ollama", "qwen2.5vl:3b", v) == profiles.UNSAFE


def test_validasi_prompt_lama_kedaluwarsa():
    assert profiles.validation_status("ollama", "qwen2.5vl:7b", "T99") == profiles.OUTDATED
    # tanpa catatan untuk versi itu, yang dipakai catatan terbaru
    record = profiles.find_validation("gemini", "gemini-3.5-flash-lite", "T99")
    assert record is not None and record.prompt_version == "T86"


def test_model_yang_pernah_meloloskan_apd_kurang_ditandai_tidak_aman():
    """Tidak aman mengalahkan kedaluwarsa: prompt baru tidak menghapus catatan bahaya."""
    assert profiles.validation_status("ollama", "qwen2.5vl:3b", messages.PROMPT_VERSION) == profiles.UNSAFE
    warnings = profile_warnings("ollama", "qwen2.5vl:3b", "cadangan ollama/qwen2.5vl:3b")
    assert len(warnings) == 1 and "11 dari 84" in warnings[0]


def test_peringatan_penyedia_eksperimental_dan_model_belum_tervalidasi():
    warnings = profile_warnings("openrouter", "qwen/qwen2.5-vl-72b-instruct", "utama openrouter/x")
    assert warnings == [messages.VLM_PROVIDER_EXPERIMENTAL.format(who="utama openrouter/x"),
                        messages.VLM_MODEL_UNVALIDATED.format(who="utama openrouter/x")]
    # Tervalidasi penuh untuk prompt berlaku (T58, 84 foto): tanpa peringatan
    assert profile_warnings("ollama", "qwen2.5vl:7b", "cadangan") == []


def test_info_menyertakan_dukungan_dan_validasi():
    info = VLMEngine("cadangan", "ollama", "qwen2.5vl:7b").info()
    assert info["support"] == profiles.OFFICIAL and info["validated"] == profiles.VALIDATED
    assert VLMEngine("utama", "tidak-dikenal", "m").info()["support"] is None


# --- Mode berpikir -----------------------------------------------------------------------

@pytest.mark.parametrize("legacy,expected", [("minimal", "off"), ("low", "low"), ("HIGH", "high")])
def test_nama_lama_gemini_thinking_level_tetap_dibaca(legacy, expected):
    assert config._legacy_thinking(legacy) == expected


def test_berpikir_diterjemahkan_profil():
    assert thinking_option("gemini", "off") == "minimal"
    assert thinking_option("gemini", "high") == "high"


def test_berpikir_tidak_didukung_diabaikan_dengan_peringatan(caplog):
    with caplog.at_level(logging.WARNING):
        assert thinking_option("ollama", "high") is None
    assert "tidak bisa mengatur mode berpikir" in caplog.text
    with caplog.at_level(logging.WARNING):
        assert thinking_option("ollama", "off") is None
    assert caplog.text.count("tidak bisa mengatur") == 1, "off tidak perlu peringatan"


def test_nilai_berpikir_tak_dikenal_dianggap_off(caplog):
    with caplog.at_level(logging.WARNING):
        assert thinking_option("gemini", "maksimal") == "minimal"
    assert "tidak dikenal" in caplog.text
