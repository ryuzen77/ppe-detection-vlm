"""Adaptor penyedia VLM. Menambah penyedia baru = satu kelas turunan `VLMProvider`."""
from . import profiles
from .base import VLMProvider, parse_json_reply

# Nama penyedia yang dilayani adaptor OpenAI-compatible (dari katalog profil)
OPENAI_COMPATIBLE = tuple(name for name, p in profiles.PROFILES.items() if p.api == profiles.API_OPENAI_COMPATIBLE)


def create_provider(name: str, api_key: str, model: str, base_url: str = "", **options) -> VLMProvider:
    """Membuat adaptor sesuai nama penyedia. Tidak ada panggilan jaringan.

    `base_url` hanya dipakai penyedia OpenAI-compatible; kosong = alamat bawaan
    penyedia itu. `options` diteruskan ke adaptor (mis. `thinking_level` untuk
    Gemini, `json_mode` untuk OpenAI-compatible).
    """
    key = (name or "").strip().lower()
    if key == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model, **options)
    if key in OPENAI_COMPATIBLE:
        from .openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            api_key=api_key, model=model, name=key,
            base_url=base_url or profiles.PROFILES[key].base_url, **options,
        )
    raise ValueError(f"Penyedia VLM tidak dikenal: {name!r}")


__all__ = ["VLMProvider", "create_provider", "parse_json_reply", "OPENAI_COMPATIBLE"]
