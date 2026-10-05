"""Login admin & perlindungan data baca (T30)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import auth, messages
from backend.api.websocket import WS_CLOSE_LOGIN_REQUIRED
from backend.app import app
from backend.config import cfg
from backend.shutdown import SHUTTING_DOWN

PASSWORD = "sandi-uji-panjang"
PUBLIC = {"/api/login", "/api/logout", "/api/session"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(auth, "sessions", auth.SessionStore(clock=c))
    monkeypatch.setattr(auth, "login_limiter", auth.LoginLimiter(clock=c))
    return c


@pytest.fixture
def secured(monkeypatch, clock):
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", PASSWORD)
    return TestClient(app)


def login(client, password=PASSWORD):
    return client.post("/api/login", json={"password": password})


# --- Tanpa ADMIN_TOKEN (pengembangan di localhost): perilaku lama ---------------------

def test_tanpa_token_admin_semua_terbuka(clock):
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/session").json() == {"authenticated": True, "auth_required": False, "expires_in_s": None}


# --- Semua API terlindungi -----------------------------------------------------------------

@pytest.fixture
def finite_stream():
    """TestClient membaca seluruh isi respons; aliran MJPEG berhenti bila SHUTTING_DOWN
    diset. Dengan begitu, bila perlindungan /api/stream hilang, tes gagal cepat
    (200), bukan menggantung."""
    SHUTTING_DOWN.set()
    yield
    SHUTTING_DOWN.clear()


def _status(client, method, path):
    return client.request(method, path).status_code


def _api_routes():
    """Semua rute HTTP /api dari skema OpenAPI (router yang di-include tidak muncul
    sebagai APIRoute di app.routes pada FastAPI baru)."""
    routes = []
    for path, methods in app.openapi()["paths"].items():
        if path.startswith("/api") and path not in PUBLIC:
            routes += [(path.replace("{", "").replace("}", ""), m.upper()) for m in methods]
    assert len(routes) > 10, "daftar rute tidak terbaca; penjaga tidak boleh diam-diam kosong"
    return routes


@pytest.mark.parametrize("path,method", list(_api_routes()))
def test_setiap_rute_api_wajib_login(secured, finite_stream, path, method):
    """Penjaga: endpoint baru otomatis ikut terlindungi; bila ada yang lolos, tes ini gagal."""
    assert _status(secured, method, path) == 401, f"{method} {path} terbuka tanpa login"


def test_data_pribadi_terkunci_tanpa_login(secured, finite_stream):
    for path in ("/api/reports", "/api/reports/export", "/api/stream", "/api/health"):
        assert _status(secured, "GET", path) == 401, path


def test_websocket_ditutup_4401_tanpa_login(secured):
    with secured.websocket_connect("/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == WS_CLOSE_LOGIN_REQUIRED


# --- Login, sesi, logout ----------------------------------------------------------------

def test_login_benar_membuka_api_dan_websocket(secured):
    r = login(secured)
    assert r.status_code == 200 and r.json()["expires_in_s"] == round(cfg.SESSION_HOURS * 3600)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert secured.get("/api/health").status_code == 200
    assert secured.get("/api/session").json()["authenticated"] is True
    with secured.websocket_connect("/ws") as ws:
        assert "fps" in ws.receive_json()


def test_login_salah_ditolak(secured):
    r = login(secured, "salah")
    assert r.status_code == 401 and r.json()["detail"] == messages.API_LOGIN_FAILED
    assert secured.get("/api/health").status_code == 401


def test_header_token_admin_tetap_diterima_untuk_skrip(secured):
    assert secured.get("/api/health", headers={"X-Admin-Token": PASSWORD}).status_code == 200
    assert secured.get("/api/health", headers={"X-Admin-Token": "salah"}).status_code == 401


def test_logout_mencabut_sesi(secured):
    login(secured)
    token = secured.cookies.get(auth.SESSION_COOKIE)
    assert secured.post("/api/logout").status_code == 204
    secured.cookies.set(auth.SESSION_COOKIE, token)    # cookie lama dipakai lagi
    assert secured.get("/api/health").status_code == 401


def test_sesi_kedaluwarsa_setelah_satu_shift(secured, clock):
    login(secured)
    clock.now += cfg.SESSION_HOURS * 3600 - 1
    assert secured.get("/api/health").status_code == 200
    clock.now += 2
    assert secured.get("/api/health").status_code == 401


def test_cookie_karangan_ditolak(secured):
    secured.cookies.set(auth.SESSION_COOKIE, "token-karangan")
    assert secured.get("/api/health").status_code == 401


# --- Tebak kata sandi ----------------------------------------------------------------------

def test_terlalu_banyak_gagal_dikunci_sementara(secured, clock):
    for _ in range(cfg.LOGIN_MAX_FAILURES):
        assert login(secured, "salah").status_code == 401
    r = login(secured)                                  # sandi benar pun ditahan
    assert r.status_code == 429 and r.json()["retry_after_s"] == round(cfg.LOGIN_LOCKOUT_SECONDS)
    clock.now += cfg.LOGIN_LOCKOUT_SECONDS
    assert login(secured).status_code == 200


def test_login_berhasil_mengosongkan_hitungan_gagal(secured):
    for _ in range(cfg.LOGIN_MAX_FAILURES - 1):
        login(secured, "salah")
    assert login(secured).status_code == 200
    for _ in range(cfg.LOGIN_MAX_FAILURES - 1):
        assert login(secured, "salah").status_code == 401


def test_body_bukan_objek_ditolak(secured):
    assert secured.post("/api/login", json=["x"]).status_code == 401
