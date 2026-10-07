"""Login akun & perlindungan data (T30, akun sejak T51).

Semua tes di sini memakai pemeriksaan login sungguhan (penanda `real_auth`), bukan
admin tiruan dari conftest.
"""
import json
import threading

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import accounts, auth, messages
from backend.api.websocket import WS_CLOSE_LOGIN_REQUIRED
from backend.app import app
from backend.config import cfg
from backend.shutdown import SHUTTING_DOWN

pytestmark = pytest.mark.real_auth

ADMIN, PASSWORD = "admin-uji", "kata-sandi-uji-panjang"
PUBLIC = {"/api/login", "/api/logout", "/api/session", "/api/setup"}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch, tmp_path):
    """Sesi, penahan tebak, dan basis data akun yang bersih untuk setiap tes."""
    c = Clock()
    monkeypatch.setattr(auth, "sessions", auth.SessionStore(clock=c))
    monkeypatch.setattr(auth, "login_limiter", auth.LoginLimiter(clock=c))
    monkeypatch.setattr(accounts, "store", accounts.AccountStore(tmp_path / "accounts.db"))
    # Hash cepat untuk tes; parameter produksi diuji di test_accounts.py
    monkeypatch.setattr(cfg, "PASSWORD_SCRYPT_N", 2 ** 4)
    return c


def client_from(host: str) -> TestClient:
    return TestClient(app, client=(host, 50000))


@pytest.fixture
def local(clock):
    """Klien dari mesin gerbang (localhost)."""
    return client_from("127.0.0.1")


@pytest.fixture
def secured(clock):
    """Server yang sudah punya satu akun admin; klien dari jaringan, belum login."""
    accounts.store.create(ADMIN, PASSWORD)
    return client_from("192.168.1.20")


def login(client, username=ADMIN, password=PASSWORD):
    return client.post("/api/login", json={"username": username, "password": password})


# --- Setup admin pertama ---------------------------------------------------------------

def test_tanpa_akun_semua_tertutup_kecuali_setup(local, finite_stream):
    s = local.get("/api/session").json()
    assert s == {"authenticated": False, "setup_required": True, "setup_allowed": True, "user": None,
                 "expires_in_s": None}
    assert local.get("/api/health").status_code == 401, "tidak ada lagi mode terbuka tanpa login"


def test_setup_hanya_dari_mesin_gerbang(clock, security_events):
    remote = client_from("192.168.1.20")
    assert remote.get("/api/session").json()["setup_allowed"] is False
    r = remote.post("/api/setup", json={"username": ADMIN, "password": PASSWORD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "setup_local_only"
    assert accounts.store.count() == 0
    assert [(e["event"], e["client"], e["ok"]) for e in security_events] == [("setup_denied", "192.168.1.20", False)]


def test_setup_membuat_admin_dan_langsung_masuk(local, monkeypatch):
    from backend import startup_checks
    monkeypatch.setattr(startup_checks, "warnings", [startup_checks.check_accounts(0), "lain"])
    r = local.post("/api/setup", json={"username": "Admin-Uji", "password": PASSWORD})
    assert startup_checks.warnings == ["lain"], "peringatan 'belum ada akun' hilang setelah setup"
    assert r.status_code == 201
    assert r.json()["user"] == {"username": ADMIN, "role": accounts.ROLE_ADMIN}
    assert local.get("/api/health").status_code == 200
    again = local.post("/api/setup", json={"username": "lain", "password": PASSWORD})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "setup_done"


def test_setup_bersamaan_hanya_satu_admin_pertama(local):
    results = []

    def attempt(name):
        results.append(local.post("/api/setup", json={"username": name, "password": PASSWORD}).status_code)
    threads = [threading.Thread(target=attempt, args=(f"admin{i}",)) for i in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [201, 409, 409, 409, 409]
    assert accounts.store.count() == 1


@pytest.mark.parametrize("body, code", [
    ({"username": "ab", "password": PASSWORD}, "invalid_username"),
    ({"username": "admin uji", "password": PASSWORD}, "invalid_username"),
    ({"username": ADMIN, "password": "pendek"}, "weak_password"),
    ({"username": "kata-sandi-sama", "password": "kata-sandi-sama"}, "weak_password"),
])
def test_setup_menolak_nama_atau_sandi_lemah(local, body, code):
    r = local.post("/api/setup", json=body)
    assert r.status_code == 400 and r.json()["detail"]["code"] == code


# --- Semua API terlindungi -------------------------------------------------------------

@pytest.fixture
def finite_stream():
    """TestClient membaca seluruh isi respons; aliran MJPEG berhenti bila SHUTTING_DOWN
    diset. Bila perlindungan /api/stream hilang, tes gagal cepat (200), bukan menggantung."""
    SHUTTING_DOWN.set()
    yield
    SHUTTING_DOWN.clear()


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
    assert secured.request(method, path).status_code == 401, f"{method} {path} terbuka tanpa login"


def test_websocket_ditutup_4401_tanpa_login(secured):
    with secured.websocket_connect("/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == WS_CLOSE_LOGIN_REQUIRED


def test_header_token_admin_lama_tidak_berlaku(secured, monkeypatch):
    assert secured.get("/api/health", headers={"x-admin-token": PASSWORD}).status_code == 401


# --- Login, sesi, logout ---------------------------------------------------------------

def test_login_membuka_api_dan_websocket(secured):
    r = login(secured)
    assert r.status_code == 200
    assert r.json() == {"user": {"username": ADMIN, "role": "admin"}, "expires_in_s": round(cfg.SESSION_HOURS * 3600)}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert secured.get("/api/health").status_code == 200
    s = secured.get("/api/session").json()
    assert s["authenticated"] is True and s["user"]["username"] == ADMIN and s["setup_required"] is False
    with secured.websocket_connect("/ws") as ws:
        assert "camera" in ws.receive_json()


def test_login_salah_pesan_sama_untuk_nama_dan_sandi(secured):
    wrong_password, wrong_name = login(secured, password="salah-salah-salah"), login(secured, username="tidak-ada")
    assert wrong_password.status_code == wrong_name.status_code == 401
    assert wrong_password.json() == wrong_name.json()
    assert wrong_password.json()["detail"]["message"] == messages.API_LOGIN_FAILED


def test_respons_dan_jejak_tanpa_kata_sandi(secured, security_events):
    login(secured)
    login(secured, password="sandi-salah-sekali")
    assert all(PASSWORD not in json.dumps(e) and "sandi-salah" not in json.dumps(e) for e in security_events)
    assert [(e["event"], e["ok"]) for e in security_events] == [("login", True), ("login", False)]
    assert PASSWORD not in json.dumps(secured.get("/api/accounts").json())


def test_logout_mencabut_sesi(secured):
    login(secured)
    assert secured.post("/api/logout").status_code == 204
    assert secured.get("/api/health").status_code == 401


def test_sesi_kedaluwarsa_setelah_satu_shift(secured, clock):
    login(secured)
    clock.now += cfg.SESSION_HOURS * 3600 + 1
    assert secured.get("/api/health").status_code == 401


def test_cookie_karangan_ditolak(secured):
    secured.cookies.set(auth.SESSION_COOKIE, "karangan")
    assert secured.get("/api/health").status_code == 401


def test_tebakan_ditahan_per_alamat(secured, clock, security_events):
    for _ in range(cfg.LOGIN_MAX_FAILURES):
        login(secured, password="tebakan-salah-xx")
    r = login(secured)
    for _ in range(3):
        login(secured)   # tebakan selama terkunci tidak menambah catatan penguncian
    lockouts = [e for e in security_events if e["event"] == "lockout_started"]
    assert len(lockouts) == 1 and lockouts[0]["username"] == ADMIN and lockouts[0]["client"] == "192.168.1.20"
    assert r.status_code == 429 and r.json()["retry_after_s"] > 0
    clock.now += cfg.LOGIN_LOCKOUT_SECONDS + 1
    assert login(secured).status_code == 200


def test_tebakan_ditahan_per_nama_walau_alamat_berganti(secured):
    """Merotasi alamat tidak membuka tebakan tanpa batas untuk satu akun."""
    for i in range(cfg.LOGIN_MAX_FAILURES):
        login(client_from(f"10.0.0.{i + 1}"), password="tebakan-salah-xx")
    assert login(client_from("10.0.0.99")).status_code == 429


# --- Ganti kata sandi & kelola akun ----------------------------------------------------

def _admin(secured):
    login(secured)
    return secured


def test_ganti_sandi_sendiri_mencabut_sesi_lain(secured):
    other = client_from("192.168.1.30")
    login(other)
    me = _admin(secured)
    bad = me.post("/api/account/password", json={"current_password": "salah-salah-salah", "new_password": "x" * 12})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "wrong_password"
    ok = me.post("/api/account/password", json={"current_password": PASSWORD, "new_password": "sandi-baru-panjang"})
    assert ok.status_code == 204
    assert me.get("/api/health").status_code == 200, "sesi yang dipakai tetap"
    assert other.get("/api/health").status_code == 401, "sesi lain berakhir"
    assert login(client_from("192.168.1.40"), password="sandi-baru-panjang").status_code == 200


def test_kelola_akun(secured):
    me = _admin(secured)
    r = me.post("/api/accounts", json={"username": "petugas", "password": "sandi-petugas-01"})
    assert r.status_code == 201 and r.json()["username"] == "petugas" and "password" not in json.dumps(r.json())
    assert me.post("/api/accounts", json={"username": "petugas", "password": "sandi-petugas-01"}).json()[
        "detail"]["code"] == "username_taken"
    assert [a["username"] for a in me.get("/api/accounts").json()] == [ADMIN, "petugas"]
    petugas = client_from("192.168.1.50")
    login(petugas, "petugas", "sandi-petugas-01")
    assert me.post("/api/accounts/petugas/password", json={"new_password": "sandi-petugas-02"}).status_code == 204
    assert petugas.get("/api/health").status_code == 401, "reset kata sandi mencabut sesi akun itu"
    assert me.delete("/api/accounts/petugas").status_code == 204
    assert me.delete("/api/accounts/petugas").json()["detail"]["code"] == "not_found"


def test_akun_sendiri_dan_terakhir_tidak_bisa_dihapus(secured):
    me = _admin(secured)
    r = me.delete(f"/api/accounts/{ADMIN}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "self_delete"
    with pytest.raises(accounts.AccountError) as e:
        accounts.store.delete(ADMIN, actor="terminal")
    assert e.value.code == "last_account"


def test_hapus_akun_mencabut_sesinya(secured, security_events):
    me = _admin(secured)
    me.post("/api/accounts", json={"username": "petugas", "password": "sandi-petugas-01"})
    petugas = client_from("192.168.1.50")
    login(petugas, "petugas", "sandi-petugas-01")
    me.delete("/api/accounts/petugas")
    assert petugas.get("/api/health").status_code == 401
    assert security_events[-1]["event"] == "delete" and security_events[-1]["actor"] == ADMIN


def test_peran_lain_ditolak_di_perintah_admin(secured, security_events):
    """Siap peran operator kelak: akun non-admin bisa membaca tetapi tidak mengubah sistem."""
    accounts.store.create("pengamat", "sandi-pengamat-1", role="operator")
    viewer = client_from("192.168.1.60")
    login(viewer, "pengamat", "sandi-pengamat-1")
    assert viewer.get("/api/health").status_code == 200
    assert viewer.get("/api/accounts").status_code == 403
    assert viewer.post("/api/reset").status_code == 403
    denied = [(e["username"], e["path"]) for e in security_events if e["event"] == "forbidden"]
    assert denied == [("pengamat", "/api/accounts"), ("pengamat", "/api/reset")]
