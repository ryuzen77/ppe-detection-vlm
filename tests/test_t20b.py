from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app import app, insecure_network_reason
from backend.config import cfg
from backend import messages
from backend.messages import STARTUP_INSECURE_LAN

client = TestClient(app)

STARTUP_TEST_PORT = "8099"
STARTUP_TEST_TIMEOUT_S = 60

def test_payload_too_large(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)
    
    payload = {"value": "this_is_a_very_long_string"}
    # /api/ppe-rules/active itu endpoint nyata; isi {'a':'b'} sengaja tidak valid sehingga tidak mengubah apa pun
    response = client.post("/api/ppe-rules/active", json=payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "Payload Too Large"
    
    response2 = client.post("/api/ppe-rules/active", json={"a":"b"})
    # It should pass the size limit and reach the router, which returns 404 Not Found
    assert response2.status_code != 413

def test_payload_chunked(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)
    
    def generate_large_payload():
        yield b'{"value": "'
        yield b'this_is_a_'
        yield b'very_long_string"}'
        
    response = client.post("/api/ppe-rules/active", content=generate_large_payload())
    assert response.status_code == 413
    assert response.json()["detail"] == "Payload Too Large"
    
    def generate_small_payload():
        yield b'{"a":"b"}'
        
    response2 = client.post("/api/ppe-rules/active", content=generate_small_payload())
    assert response2.status_code != 413

def test_insecure_network_reason_direct():
    # Test murni tanpa mock
    # 1. LAN tanpa token dan demo dimatikan -> kembalikan pesan peringatan
    reason = insecure_network_reason("192.168.1.10", "", False)
    assert reason is not None
    assert STARTUP_INSECURE_LAN.format(host="192.168.1.10") in reason
    
    # 2. LAN tanpa token tapi demo diizinkan -> kembalikan None (hanya warning di log)
    assert insecure_network_reason("192.168.1.10", "", True) is None
    
    # 3. Localhost tanpa token -> kembalikan None
    assert insecure_network_reason("127.0.0.1", "", False) is None
    
    # 4. LAN dengan token -> kembalikan None
    assert insecure_network_reason("192.168.1.10", "kalimat-sandi-panjang-uji", False) is None

def test_startup_insecure_lan_lifespan(monkeypatch):
    from backend import runtime
    monkeypatch.setattr(runtime, "start", lambda: None)
    monkeypatch.setattr(runtime, "stop", lambda: None)
    
    monkeypatch.setattr(cfg, "HOST", "192.168.1.10")
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", "")
    monkeypatch.setattr(cfg, "ALLOW_INSECURE_DEMO", False)
    
    # Lifespan akan melempar RuntimeError
    try:
        with TestClient(app):
            pass
        pytest.fail("TestClient harusnya gagal karena RuntimeError di lifespan")
    except BaseException as e:
        # Pengecekan ada di ExceptionGroup / Exception
        assert "Server berjalan di jaringan terbuka" in str(e.args) or "Server berjalan di jaringan terbuka" in str(getattr(e, 'exceptions', e))

def test_startup_subprocess():
    import subprocess
    import sys
    import os
    env = os.environ.copy()
    env["HOST"] = "0.0.0.0"
    env["ADMIN_TOKEN"] = ""
    env["ALLOW_INSECURE_DEMO"] = "false"
    # Port terpisah & batas waktu: bila pemeriksaan ini rusak, server sungguhan
    # akan menyala; tes harus gagal cepat, bukan menggantung atau bentrok
    # dengan server pengembangan di port 8000.
    env["PORT"] = STARTUP_TEST_PORT

    result = subprocess.run(
        [sys.executable, "-m", "backend"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
        timeout=STARTUP_TEST_TIMEOUT_S,
    )
    
    assert result.returncode == 1
    assert "Server berjalan di jaringan terbuka" in result.stderr
    assert "Traceback" not in result.stderr



# --- Panjang minimal kata sandi admin (T30, keputusan 06-10) -------------------------------

def test_kata_sandi_pendek_ditolak_di_jaringan():
    reason = insecure_network_reason("192.168.1.10", "pendek123", False)
    assert reason == messages.ADMIN_TOKEN_TOO_SHORT.format(length=9, minimum=cfg.ADMIN_TOKEN_MIN_LENGTH)
    assert "pendek123" not in reason, "nilai kata sandi tidak boleh dicetak"


def test_kata_sandi_pendek_di_localhost_hanya_peringatan(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        assert insecure_network_reason("127.0.0.1", "pendek123", False) is None
    assert "minimal" in caplog.text and "pendek123" not in caplog.text


def test_kata_sandi_cukup_panjang_diterima():
    assert insecure_network_reason("192.168.1.10", "x" * cfg.ADMIN_TOKEN_MIN_LENGTH, False) is None
