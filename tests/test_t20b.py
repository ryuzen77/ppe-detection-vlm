"""Batas muatan POST (T20b). Pemeriksaan "jaringan terbuka tanpa ADMIN_TOKEN" dihapus di T51:
login akun selalu wajib, jadi tidak ada lagi mode terbuka yang perlu ditolak saat start."""

from fastapi.testclient import TestClient
from backend.app import app
from backend.config import cfg

client = TestClient(app)


def test_payload_too_large(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)

    payload = {"value": "this_is_a_very_long_string"}
    # /api/ppe-rules/active itu endpoint nyata; isi {'a':'b'} sengaja tidak valid sehingga tidak mengubah apa pun
    response = client.post("/api/ppe-rules/active", json=payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "Payload Too Large"

    response2 = client.post("/api/ppe-rules/active", json={"a": "b"})
    # It should pass the size limit and reach the router, which returns 404 Not Found
    assert response2.status_code != 413


def test_payload_chunked(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)

    def generate_large_payload():
        yield b'{"value": "'
        yield b"this_is_a_"
        yield b'very_long_string"}'

    response = client.post("/api/ppe-rules/active", content=generate_large_payload())
    assert response.status_code == 413
    assert response.json()["detail"] == "Payload Too Large"

    def generate_small_payload():
        yield b'{"a":"b"}'

    response2 = client.post("/api/ppe-rules/active", content=generate_small_payload())
    assert response2.status_code != 413
