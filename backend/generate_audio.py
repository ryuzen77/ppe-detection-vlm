"""Membangkitkan MP3 suara gerbang (gTTS) dari teks di messages.py & katalog APD.

Berkas MP3 adalah aset rilis (dilacak git). Teks yang dipakai tiap berkas
dicatat di `_texts.json`; berkas dibangkitkan ulang hanya bila belum ada atau
teksnya berubah, jadi mengubah kalimat cukup dengan menjalankan skrip ini lagi.
Yang dikirim ke gTTS hanya kalimat tetap ini, tanpa data pekerja.

    python -m backend.generate_audio
"""

import json

from gtts import gTTS

from . import messages, ppe_rules
from .config import cfg

# Sama dengan folder yang dibaca AudioEngine, supaya berkas yang dibangkitkan
# di sini pasti ditemukan saat diputar.
AUDIO_DIR = cfg.AUDIO_DIR
TEXTS_MANIFEST = AUDIO_DIR / "_texts.json"
TTS_LANG = "id"


def build_prompts() -> dict:
    """Seluruh suara yang dibutuhkan: suara sistem + satu suara per item APD.

    Suara per item diambil dari katalog `ppe_rules`, jadi item baru otomatis
    mendapat berkas MP3-nya sendiri saat skrip ini dijalankan ulang.
    """
    prompts = dict(messages.VOICE_TEXTS)
    for item in ppe_rules.get_items():
        prompts[item.audio_missing] = item.audio_missing_text
    return prompts


def stale_keys(prompts: dict, recorded: dict, existing: set) -> list:
    """Kunci yang perlu dibangkitkan: berkas belum ada atau teksnya berubah."""
    return [k for k, text in prompts.items() if k not in existing or recorded.get(k) != text]


def generate_all():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    prompts = build_prompts()
    try:
        recorded = json.loads(TEXTS_MANIFEST.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        recorded = {}
    existing = {p.stem for p in AUDIO_DIR.glob("*.mp3")}
    todo = stale_keys(prompts, recorded, existing)
    print(f"{len(todo)} dari {len(prompts)} suara perlu dibangkitkan ke {AUDIO_DIR}")
    for key in todo:
        print(f"  [{key}] {prompts[key]}")
        gTTS(text=prompts[key], lang=TTS_LANG, slow=False).save(str(AUDIO_DIR / f"{key}.mp3"))
        recorded[key] = prompts[key]
    TEXTS_MANIFEST.write_text(
        json.dumps(dict(sorted(recorded.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Selesai.")


if __name__ == "__main__":
    generate_all()
