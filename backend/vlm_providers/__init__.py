"""Adaptor penyedia VLM. Menambah penyedia baru = satu kelas turunan `VLMProvider`."""
from .base import VLMProvider, parse_json_reply


def create_provider(name: str, api_key: str, model: str, **options) -> VLMProvider:
    """Membuat adaptor sesuai nama penyedia. Tidak ada panggilan jaringan.

    `options` diteruskan ke adaptor (mis. `thinking_level` untuk Gemini).
    """
    key = (name or "").strip().lower()
    if key == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model, **options)
    raise ValueError(f"Penyedia VLM tidak dikenal: {name!r}")


__all__ = ["VLMProvider", "create_provider", "parse_json_reply"]
