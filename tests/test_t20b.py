import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.config import cfg
from backend.messages import STARTUP_INSECURE_LAN

client = TestClient(app)

def test_payload_too_large(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)
    
    payload = {"value": "this_is_a_very_long_string"}
    response = client.post("/api/config/vlm-key", json=payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "Payload Too Large"
    
    response2 = client.post("/api/config/vlm-key", json={"a":"b"})
    assert response2.status_code != 413

def test_payload_chunked(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)
    
    def generate_large_payload():
        yield b'{"value": "'
        yield b'this_is_a_'
        yield b'very_long_string"}'
        
    response = client.post("/api/config/vlm-key", content=generate_large_payload())
    # TestClient doesn't actually stream the generator in a way that chunks it to receive(),
    # or the exception gets swallowed somewhere. Let's just assert 413 or 500 if the connection drops.
    # Actually, we should check if the middleware works.
    if response.status_code != 413:
        print("Middleware chunked failed. Response code:", response.status_code)
        print("Response body:", response.text)
    assert response.status_code == 413
    
def test_startup_insecure_lan(monkeypatch):
    import sys
    from backend import runtime
    monkeypatch.setattr(runtime, "start", lambda: None)
    monkeypatch.setattr(runtime, "stop", lambda: None)
    
    exit_calls = []
    def mock_exit(msg=None):
        exit_calls.append(msg)
        raise RuntimeError("MockExit")
        
    monkeypatch.setattr(sys, "exit", mock_exit)
    
    monkeypatch.setattr(cfg, "HOST", "192.168.1.10")
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", "")
    monkeypatch.setattr(cfg, "ALLOW_INSECURE_DEMO", False)
    
    try:
        with TestClient(app):
            pass
    except RuntimeError as e:
        if str(e) != "MockExit":
            raise
    except BaseException:
        pass
        
    assert len(exit_calls) > 0
    assert STARTUP_INSECURE_LAN.format(host="192.168.1.10") in str(exit_calls[0])
    
    exit_calls.clear()
    monkeypatch.setattr(cfg, "ALLOW_INSECURE_DEMO", True)
    try:
        with TestClient(app):
            pass
    except RuntimeError as e:
        if str(e) == "MockExit":
            pytest.fail("Should not exit when ALLOW_INSECURE_DEMO is True")
    
    exit_calls.clear()
    monkeypatch.setattr(cfg, "HOST", "127.0.0.1")
    monkeypatch.setattr(cfg, "ALLOW_INSECURE_DEMO", False)
    try:
        with TestClient(app):
            pass
    except RuntimeError as e:
        if str(e) == "MockExit":
            pytest.fail("Should not exit when localhost")

    exit_calls.clear()
    monkeypatch.setattr(cfg, "HOST", "0.0.0.0")
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", "secret")
    try:
        with TestClient(app):
            pass
    except RuntimeError as e:
        if str(e) == "MockExit":
            pytest.fail("Should not exit when token set")