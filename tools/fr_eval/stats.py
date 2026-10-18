"""Logika murni uji FR (T34m): ringkasan waktu, estimasi per sesi, cek hash.

Dipisah dari `bench_speed.py` supaya bisa dites di env utama tanpa onnxruntime,
OpenVINO, atau dlib (paket itu hanya ada di env `fr_eval`).
"""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HASH_CHUNK_BYTES = 1 << 20
CATALOG = Path(__file__).with_name("models.json")
# Bobot model di luar repo: besar dan berlisensi pihak ketiga, tidak di-commit
MODELS_DIR_ENV = "FR_EVAL_MODELS_DIR"
DEFAULT_MODELS_DIR = Path.home() / ".cache" / "depro_fr_eval" / "models"


def models_dir() -> Path:
    return Path(os.environ.get(MODELS_DIR_ENV) or DEFAULT_MODELS_DIR)


@dataclass(frozen=True)
class Timing:
    p50_ms: float
    p95_ms: float
    mean_ms: float


@dataclass(frozen=True)
class ModelFile:
    url: str
    sha256: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def summarize(samples_ms: list[float]) -> Timing:
    if not samples_ms:
        raise ValueError("tidak ada sampel waktu")
    data = np.asarray(samples_ms, dtype=float)
    return Timing(float(np.percentile(data, 50)), float(np.percentile(data, 95)), float(data.mean()))


def session_ms(detect_ms: float, embed_ms: float, search_ms: float, attempts: int) -> float:
    """Biaya FR satu sesi: setiap percobaan = deteksi wajah + embedding; pencarian sekali.

    Percobaan > 1 dipakai bila gerbang memilih wajah terbaik dari beberapa frame.
    """
    if attempts < 1:
        raise ValueError("attempts minimal 1")
    return attempts * (detect_ms + embed_ms) + search_ms


def meets_budget(total_ms: float, budget_ms: float) -> bool:
    return total_ms <= budget_ms


def load_catalog(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def model_files(entry: dict) -> list[ModelFile]:
    return [ModelFile(f["url"], f.get("sha256", "")) for f in entry["files"]]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> bool:
    """Hash kosong = belum dipatok (unduhan pertama); selain itu harus sama persis."""
    return path.is_file() and (not expected or sha256_of(path) == expected.lower())
