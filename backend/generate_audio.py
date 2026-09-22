import os
from pathlib import Path
from gtts import gTTS

AUDIO_DIR = Path(__file__).resolve().parent / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

PROMPTS = {
    "mundur": "Silakan mundur sampai seluruh tubuh terlihat.",
    "mundur_kepala": "Silakan mundur sedikit, kepala terlalu dekat.",
    "mundur_kaki": "Silakan mundur satu langkah sampai kaki terlihat.",
    "posisi_pas": "Posisi tubuh sudah tepat. Mohon tunggu analisa APD.",
    "lengkap": "APD lengkap. Akses diizinkan. Silakan masuk.",
    "tidak_lengkap": "Peringatan! APD Anda tidak lengkap. Akses ditolak.",
    "kurang_helm": "Peringatan! Anda belum memakai helm keselamatan.",
    "kurang_rompi": "Peringatan! Anda belum memakai rompi keselamatan warna orange atau kuning.",
    "kurang_celana": "Peringatan! Anda belum memakai celana panjang.",
    "kurang_sepatu": "Peringatan! Anda belum memakai sepatu tertutup.",
    "sedang_analisa": "Mohon tunggu sebentar, sedang menganalisa kelengkapan APD."
}

def generate_all():
    print(f"Generating audio prompts to {AUDIO_DIR}...")
    for key, text in PROMPTS.items():
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
