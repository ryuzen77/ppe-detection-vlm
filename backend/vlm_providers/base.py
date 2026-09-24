"""Kontrak tunggal penyedia VLM.

Penyedia hanya bertugas mengirim satu gambar + prompt dan mengembalikan teks
jawaban model. Semua hal lain — timeout, rate-guard free tier, fallback ke
engine lokal, anti-spam, dan penilaian kelengkapan lewat `ppe_rules` — tetap
di `VLMAnalyzer`, sehingga tidak diulang untuk setiap penyedia.
"""
import json
from abc import ABC, abstractmethod


class VLMProvider(ABC):
    #: Nama penyedia untuk log, dashboard, dan label sumber laporan
    name: str = ""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def generate(self, image_jpeg: bytes, system_prompt: str, user_prompt: str) -> str:
        """Satu panggilan model dengan satu gambar JPEG. Mengembalikan teks jawaban mentah."""

    @abstractmethod
    def ping(self) -> str:
        """Panggilan teks termurah untuk mengukur latensi. Mengembalikan jawaban model."""

    def warm_up(self):
        """Membuat panggilan pertama pekerja secepat panggilan berikutnya.

        Bawaannya satu ping: membuka koneksi (TLS) dan, pada model lokal, memuat
        bobot model ke GPU. Adaptor boleh menimpanya.
        """
        self.ping()

    def analyze(self, image_jpeg: bytes, system_prompt: str, user_prompt: str) -> dict:
        """Memanggil model lalu mengurai jawabannya sebagai objek JSON."""
        return parse_json_reply(self.generate(image_jpeg, system_prompt, user_prompt))


def parse_json_reply(text: str) -> dict:
    """JSON dari jawaban model; pagar ```json yang kadang ditambahkan model dibuang."""
    raw = (text or "").strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    data = json.loads(raw.strip())
    if not isinstance(data, dict):
        raise ValueError(f"Jawaban model bukan objek JSON: {type(data).__name__}")
    return data
