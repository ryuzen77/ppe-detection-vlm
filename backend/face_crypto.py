"""Enkripsi templat wajah (T34b): AES-256-GCM, satu nonce acak per templat.

Templat wajah = data pribadi spesifik (UU PDP), jadi tidak pernah disimpan polos.
Data tambahan terautentikasi (AAD) mengikat templat ke pekerja & versi modelnya:
ciphertext yang disalin ke baris pekerja lain gagal dibuka, bukan diam-diam
dikenali sebagai orang lain.

Kunci hanya dari `FACE_DATA_KEY` di backend/.env. Membuat kunci (dijalankan
admin di mesin gerbang, lalu disalin sendiri ke .env):
    python -m backend.face_crypto generate-key
"""

import argparse
import base64
import binascii
import secrets
import struct
from typing import Optional

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import messages

KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12  # ukuran nonce yang dianjurkan untuk GCM
VECTOR_DTYPE = np.dtype("<f4")  # float32 little-endian: sama di semua mesin


class FaceKeyError(Exception):
    """Kunci tidak valid, atau templat tidak bisa dibuka dengan kunci ini."""


def parse_key(text: str) -> Optional[bytes]:
    """None bila kosong (fitur FR mati); FaceKeyError bila isinya bukan kunci 32 byte."""
    if not text.strip():
        return None
    try:
        key = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise FaceKeyError(messages.FACE_KEY_INVALID.format(size=KEY_BYTES)) from None
    if len(key) != KEY_BYTES:
        raise FaceKeyError(messages.FACE_KEY_INVALID.format(size=KEY_BYTES))
    return key


def generate_key() -> str:
    return base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")


def template_aad(worker_id: int, model_version: str) -> bytes:
    return struct.pack(">q", worker_id) + model_version.encode("utf-8")


class FaceCipher:
    def __init__(self, key: bytes):
        self._aead = AESGCM(key)

    def encrypt(self, vector: np.ndarray, aad: bytes) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(NONCE_BYTES)
        plain = np.ascontiguousarray(vector, dtype=VECTOR_DTYPE).tobytes()
        return nonce, self._aead.encrypt(nonce, plain, aad)

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes, dim: int) -> np.ndarray:
        try:
            plain = self._aead.decrypt(nonce, ciphertext, aad)
        except InvalidTag:
            raise FaceKeyError("templat tidak bisa dibuka dengan kunci ini") from None
        vector = np.frombuffer(plain, dtype=VECTOR_DTYPE)
        if vector.size != dim:
            raise FaceKeyError(f"dimensi templat {vector.size}, seharusnya {dim}")
        return vector.astype(np.float32)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.face_crypto")
    parser.add_argument("command", choices=("generate-key",))
    parser.parse_args(argv)
    print(messages.FACE_KEY_GENERATED)
    print(f"FACE_DATA_KEY={generate_key()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
