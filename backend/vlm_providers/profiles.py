"""Katalog penyedia VLM & daftar model tervalidasi (T39b) — satu sumber, seperti katalog APD.

`.env` cukup memilih penyedia + model + key; sisanya (alamat bawaan, model
bawaan, lokal/cloud, cara mematikan mode berpikir) diambil dari profil.

Akurasi tiap model berbeda dan peka terhadap prompt, jadi pasangan penyedia +
model dicatat di VALIDATIONS setelah diuji dengan foto berlabel
(`tools/bench_vlm.py` / `tools/eval_vlm.py`). Model yang belum tervalidasi
tetap boleh dipakai (keputusan pengguna: peringatan saja), tetapi ditandai di
log dan Pengaturan. Modul ini sengaja tidak mengimpor apa pun dari backend,
karena `config.py` memakainya.
"""
from dataclasses import dataclass
from typing import Optional

OFFICIAL = "official"          # pernah diuji di gerbang ini
EXPERIMENTAL = "experimental"  # adaptor tersedia, belum pernah diuji di sini

API_GEMINI = "gemini"
API_OPENAI_COMPATIBLE = "openai_compatible"

# Tingkat "berpikir" umum (VLM_THINKING); profil menerjemahkannya ke parameter penyedia
THINKING_LEVELS = ("off", "low", "medium", "high")


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    api: str
    is_local: bool
    support: str
    base_url: str = ""
    default_model: str = ""
    # Tingkat umum -> nilai parameter penyedia; None = penyedia tidak bisa diatur
    thinking: Optional[dict] = None
    data_location: str = ""


PROFILES = {p.name: p for p in (
    # Gemini 3 tidak bisa mematikan berpikir sepenuhnya; "minimal" terukur ~1,4 dtk
    # vs ~5 dtk bawaan dengan jawaban APD yang sama (T23).
    ProviderProfile("gemini", API_GEMINI, is_local=False, support=OFFICIAL,
                    default_model="gemini-3.5-flash-lite",
                    thinking={"off": "minimal", "low": "low", "medium": "medium", "high": "high"},
                    data_location="Google Cloud (global)"),
    # T26: satu-satunya model lokal yang tidak meloloskan APD kurang
    ProviderProfile("ollama", API_OPENAI_COMPATIBLE, is_local=True, support=OFFICIAL,
                    base_url="http://localhost:11434/v1", default_model="qwen2.5vl:7b",
                    data_location="mesin ini"),
    # vLLM tidak punya port bawaan yang aman: 8000 dipakai server ini sendiri
    ProviderProfile("vllm", API_OPENAI_COMPATIBLE, is_local=True, support=EXPERIMENTAL,
                    data_location="mesin ini"),
    ProviderProfile("openai", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://api.openai.com/v1", data_location="OpenAI (AS)"),
    ProviderProfile("openrouter", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://openrouter.ai/api/v1", data_location="OpenRouter + penyedia model"),
    # Region internasional; akun Tiongkok daratan memakai dashscope.aliyuncs.com
    ProviderProfile("qwen", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    data_location="Alibaba Cloud"),
    # Hanya model yang menerima gambar (mis. deepseek-flash)
    ProviderProfile("deepseek", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://api.deepseek.com", data_location="DeepSeek (Tiongkok)"),
    ProviderProfile("openai-compatible", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL),
)}


@dataclass(frozen=True)
class ModelValidation:
    """Hasil uji foto berlabel. `missed` = pekerja APD kurang yang diloloskan (harus 0)."""
    provider: str
    model: str
    prompt_version: str
    date: str
    photos: int
    missed: int
    false_rejects: Optional[int]       # None = tidak tercatat
    median_seconds: Optional[float]    # None = tidak tercatat
    complete: bool          # False = uji sebagian (mis. 10 foto tersulit)
    note: str = ""


VALIDATIONS = (
    ModelValidation("ollama", "qwen2.5vl:7b", "T36a", "2026-09-27", photos=84, missed=0, false_rejects=2,
                    median_seconds=3.6, complete=True, note="T35 Uji 1, RTX 4060 Laptop, 100% GPU"),
    ModelValidation("gemini", "gemini-3.5-flash-lite", "T36a", "2026-09-27", photos=10, missed=0, false_rejects=0,
                    median_seconds=2.5, complete=False,
                    note="T39a, 10 foto tersulit; uji 84 foto menunggu izin kuota"),
    # T26 (prompt lama): lebih cepat, tetapi meloloskan pekerja ber-APD kurang
    ModelValidation("ollama", "qwen2.5vl:3b", "T26", "2026-09-24", photos=84, missed=11, false_rejects=None,
                    median_seconds=None, complete=True, note="T26: lolos 11/58 APD kurang, akurasi 83%"),
)

# Status validasi sepasang penyedia + model untuk prompt yang berlaku
VALIDATED = "validated"
PARTIAL = "partial"
OUTDATED = "outdated"          # tervalidasi untuk prompt lama
UNSAFE = "unsafe"              # pernah meloloskan APD kurang
UNVALIDATED = "unvalidated"


def get_profile(name: str) -> Optional[ProviderProfile]:
    return PROFILES.get((name or "").strip().lower())


def default_model(name: str) -> str:
    profile = get_profile(name)
    return profile.default_model if profile else ""


def is_local(name: str) -> bool:
    profile = get_profile(name)
    return bool(profile and profile.is_local)


def find_validation(provider: str, model: str) -> Optional[ModelValidation]:
    key = ((provider or "").strip().lower(), (model or "").strip())
    for v in VALIDATIONS:
        if (v.provider, v.model) == key:
            return v
    return None


def validation_status(provider: str, model: str, prompt_version: str) -> str:
    v = find_validation(provider, model)
    if v is None:
        return UNVALIDATED
    if v.missed > 0:
        return UNSAFE
    if v.prompt_version != prompt_version:
        return OUTDATED
    return VALIDATED if v.complete else PARTIAL


def thinking_value(name: str, level: str) -> Optional[str]:
    """Nilai parameter berpikir penyedia; None = tidak dikirim (penyedia tidak mendukungnya)."""
    profile = get_profile(name)
    if profile is None or profile.thinking is None:
        return None
    return profile.thinking.get(level)
