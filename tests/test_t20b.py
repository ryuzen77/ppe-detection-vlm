import pytest
from fastapi.testclient import TestClient
from backend.app import app, insecure_network_reason
from backend.config import cfg
from backend.messages import STARTUP_INSECURE_LAN

client = TestClient(app)

def test_payload_too_large(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)
    
    payload = {"value": "this_is_a_very_long_string"}
    # Use a non-existent endpoint to safely test payload limit without side effects
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
    assert insecure_network_reason("192.168.1.10", "secret", False) is None

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
