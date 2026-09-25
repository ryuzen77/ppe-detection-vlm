import pytest
from fastapi.testclient import TestClient
from backend.app import app, run
from backend.config import cfg
from backend.messages import STARTUP_INSECURE_LAN
import uvicorn

client = TestClient(app)

def test_payload_too_large(monkeypatch):
    monkeypatch.setattr(cfg, "MAX_PAYLOAD_BYTES", 15)
    
    # Large payload
    payload = {"value": "this_is_a_very_long_string"}
    response = client.post("/api/config/vlm-key", json=payload)
    assert response.status_code == 413
    assert response.json()["detail"] == "Payload Too Large"
    
    # Small payload (under 15 bytes JSON). '{"a":"b"}' is 9 bytes
    response2 = client.post("/api/config/vlm-key", json={"a":"b"})
    assert response2.status_code != 413

def test_startup_insecure_lan(monkeypatch):
    monkeypatch.setattr(cfg, "HOST", "192.168.1.10")
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", "")
    monkeypatch.setattr(cfg, "ALLOW_UNSECURE_DEMO", False)
    
    with pytest.raises(SystemExit) as excinfo:
        run()
    
    assert STARTUP_INSECURE_LAN.format(host="192.168.1.10") in str(excinfo.value)
    
    monkeypatch.setattr(cfg, "ALLOW_UNSECURE_DEMO", True)
    
    # Mock uvicorn Server run to prevent actual server from starting
    monkeypatch.setattr(uvicorn.Server, "run", lambda self: None)
    
    # Should not raise SystemExit
    try:
        run()
    except SystemExit:
        pytest.fail("Should not raise SystemExit if ALLOW_UNSECURE_DEMO is True")
    
    # Should not raise if host is localhost
    monkeypatch.setattr(cfg, "HOST", "127.0.0.1")
    monkeypatch.setattr(cfg, "ALLOW_UNSECURE_DEMO", False)
    try:
        run()
    except SystemExit:
        pytest.fail("Should not raise SystemExit if host is localhost")

    # Should not raise if token is set
    monkeypatch.setattr(cfg, "HOST", "0.0.0.0")
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", "secret")
    try:
        run()
    except SystemExit:
        pytest.fail("Should not raise SystemExit if ADMIN_TOKEN is set")
