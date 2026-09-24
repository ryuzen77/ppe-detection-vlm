from gtts import gTTS

from . import ppe_rules
from .config import cfg

# Sama dengan folder yang dibaca AudioEngine, supaya berkas yang dibangkitkan
# di sini pasti ditemukan saat diputar.
AUDIO_DIR = cfg.AUDIO_DIR
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Suara tingkat sistem, bukan milik satu item APD.
SYSTEM_PROMPTS = {
    "mundur": "Silakan mundur sampai seluruh tubuh terlihat.",
    "mundur_kepala": "Silakan mundur sedikit, kepala terlalu dekat.",
    "mundur_kaki": "Silakan mundur satu langkah sampai kaki terlihat.",
    "posisi_pas": "Posisi tubuh sudah tepat. Mohon tunggu analisa APD.",
    "lengkap": "APD lengkap. Akses diizinkan. Silakan masuk.",
    "tidak_lengkap": "Peringatan! APD Anda tidak lengkap. Akses ditolak.",
    "sedang_analisa": "Mohon tunggu sebentar, sedang menganalisa kelengkapan APD.",
    # Utama & cadangan VLM gagal (T27): belum ada keputusan, pemeriksaan diulang otomatis
    "sistem_gangguan": ("Mohon tunggu, sistem pemeriksaan sedang gangguan. "
                        "Bila sistem sudah aktif kembali, silakan berdiri di batas pemeriksaan."),
}


def build_prompts() -> dict:
    """Seluruh suara yang dibutuhkan: suara sistem + satu suara per item APD.

    Suara per item diambil dari katalog `ppe_rules`, jadi item baru otomatis
    mendapat berkas MP3-nya sendiri saat skrip ini dijalankan ulang.
    """
    prompts = dict(SYSTEM_PROMPTS)
    for item in ppe_rules.get_items():
        prompts[item.audio_missing] = item.audio_missing_text
    return prompts


def generate_all():
    print(f"Generating audio prompts to {AUDIO_DIR}...")
    for key, text in build_prompts().items():
        file_path = AUDIO_DIR / f"{key}.mp3"
        if not file_path.exists():
            print(f"Generating [{key}]: '{text}'")
            tts = gTTS(text=text, lang="id", slow=False)
            tts.save(str(file_path))
        else:
            print(f"Skipping [{key}], already exists.")
    print("All audio files ready!")

if __name__ == "__main__":
    generate_all()
