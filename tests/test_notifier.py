"""Lampu gerbang fisik lewat USB serial (T47): heartbeat, balasan, sambung ulang, uji lampu."""
import pytest
from fastapi.testclient import TestClient

from backend import messages, notifier as notifier_mod
from backend.app import app
from backend.config import cfg
from backend.notifier import GateLightLink, LightState, NotifierManager, notifier
from backend.state_manager import state_mgr


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakePort:
    """Port serial tiruan: mencatat tulisan dan membalas seperti firmware."""

    def __init__(self, reply=True):
        self.written = []
        self.reply = reply
        self.rx = b""
        self.closed = False
        self.fail_write = False

    def write(self, data):
        if self.fail_write:
            raise OSError("perangkat dicabut")
        self.written.append(data.decode().strip())
        if self.reply:
            self.rx += f"OK:{data.decode().strip().removeprefix('LIGHT_')}\n".encode()

    @property
    def in_waiting(self):
        return len(self.rx)

    def read(self, n):
        out, self.rx = self.rx[:n], self.rx[n:]
        return out

    def close(self):
        self.closed = True


@pytest.fixture
def link():
    clock = Clock()
    ports = []

    def opener(port, baud, timeout):
        p = FakePort()
        ports.append(p)
        return p

    return GateLightLink(opener=opener, clock=clock), clock, ports


# --- Heartbeat & balasan -------------------------------------------------------------

def test_keadaan_dikirim_ulang_tiap_putaran_sebagai_heartbeat(link):
    lnk, clock, ports = link
    lnk.set_state(LightState.GREEN)
    for _ in range(3):
        lnk.tick()
        clock.now += cfg.IOT_HEARTBEAT_SECONDS
    assert ports[0].written == ["LIGHT_GREEN"] * 3


def test_balasan_ok_menandai_tersambung(link):
    lnk, clock, _ = link
    assert lnk.status()["connected"] is False
    lnk.tick()
    st = lnk.status()
    assert st["connected"] is True and st["error"] is None and st["last_ack_age_s"] == 0.0


def test_balasan_terbaca_walau_in_waiting_bukan_jumlah_byte():
    """Backend socket:// pyserial mengisi in_waiting 0/1 (temuan smoke test T47)."""
    class SocketLikePort(FakePort):
        @property
        def in_waiting(self):
            return 1 if self.rx else 0

    clock = Clock()
    lnk = GateLightLink(opener=lambda *a: SocketLikePort(), clock=clock)
    lnk.tick()                 # tulis + balasan masuk
    lnk.tick()
    assert lnk.status()["connected"] is True


def test_tanpa_balasan_dianggap_terputus(link):
    lnk, clock, ports = link
    lnk.tick()
    ports[0].reply = False
    clock.now += cfg.IOT_ACK_TIMEOUT_SECONDS + 0.5
    lnk.tick()
    st = lnk.status()
    assert st["connected"] is False and st["error"] == messages.IOT_NO_ACK


def test_kabel_dicabut_lalu_disambung_ulang(link):
    lnk, clock, ports = link
    lnk.tick()
    ports[0].fail_write = True
    lnk.tick()
    assert ports[0].closed and lnk.status()["connected"] is False
    lnk.tick()                                  # belum waktunya membuka ulang
    assert len(ports) == 1
    clock.now += cfg.IOT_RECONNECT_SECONDS
    lnk.set_state(LightState.RED)
    lnk.tick()
    assert len(ports) == 2 and ports[1].written == ["LIGHT_RED"]
    assert lnk.status()["connected"] is True


def test_port_tidak_ada_tidak_menghentikan_thread():
    clock = Clock()

    def opener(port, baud, timeout):
        raise OSError("could not open port")

    lnk = GateLightLink(opener=opener, clock=clock)
    lnk.tick()
    assert "could not open port" in lnk.status()["error"]


def test_data_sampah_tanpa_baris_baru_dibatasi(link):
    lnk, clock, ports = link
    lnk.tick()
    ports[0].reply = False
    ports[0].rx = b"x" * (cfg.IOT_RX_MAX_BYTES * 4)
    lnk.tick()
    assert len(lnk._rx) <= cfg.IOT_RX_MAX_BYTES


def test_port_dibuka_tanpa_mereset_papan(monkeypatch):
    """DTR/RTS harus sudah False SEBELUM open(); sesudahnya papan sudah ter-reset."""
    import serial
    urutan = []

    class SpySerial:
        def __init__(self):
            self.__dict__["port"] = None

        def __setattr__(self, name, value):
            urutan.append((name, value))
            self.__dict__[name] = value

        def open(self):
            urutan.append(("open", None))

    monkeypatch.setattr(serial, "Serial", SpySerial)
    notifier_mod.open_serial("COM9", 9600, 1.0)
    names = [n for n, _ in urutan]
    assert names.index("dtr") < names.index("open") and names.index("rts") < names.index("open")
    assert ("dtr", False) in urutan and ("rts", False) in urutan


# --- NotifierManager ----------------------------------------------------------------------

def test_gangguan_sistem_kuning_bukan_merah():
    m = NotifierManager()
    m.set_waiting()
    assert m.current_state == LightState.YELLOW


def test_status_iot_saat_nonaktif():
    m = NotifierManager()
    m.link = None
    assert m.iot_status() == {"enabled": False, "connected": False, "last_ack_age_s": None, "error": None,
                              "lamps_on": None, "lamps_available": None}


@pytest.mark.parametrize("reply,expected", [
    (b"OK:GREEN\n", ["green"]), (b"OK:RED\n", ["red"]),
    (b"OK:YELLOW\n", ["yellow"]), (b"OK:OFF\n", []),
    (b"OK:UNKNOWN\n", None), (b"OK:GREEN\nOK:OFF\n", []),
    (b"OK:GREEN\nOK:UNKNOWN\n", None),
])
def test_serial_lamps_follow_last_ack_instead_of_command(link, reply, expected):
    lnk, _, ports = link
    lnk.set_state(LightState.RED)
    lnk.tick()
    ports[0].reply = False
    ports[0].rx = reply
    lnk.tick()
    manager = NotifierManager()
    manager.link = lnk
    assert manager.iot_status()["lamps_on"] == expected
    assert manager.iot_status()["lamps_available"] == ["green", "red", "yellow"]


@pytest.mark.parametrize("elapsed,expected", [(0, ["green"]), (0.01, None), (0.5, None)])
def test_serial_lamps_expire_at_unrounded_timeout(link, elapsed, expected):
    lnk, clock, _ = link
    lnk.set_state(LightState.GREEN)
    lnk.tick()
    clock.now += cfg.IOT_ACK_TIMEOUT_SECONDS + elapsed
    assert lnk.status()["lamps_on"] == expected


@pytest.mark.parametrize("condition", ["unopened", "closed", "error"])
def test_serial_lamps_unknown_without_connection(link, condition):
    lnk, _, ports = link
    if condition != "unopened":
        lnk.tick()
        if condition == "closed":
            lnk.stop()
        else:
            ports[0].fail_write = True
            lnk.tick()
    assert lnk.status()["lamps_on"] is None
    assert lnk.status()["lamps_available"] == ["green", "red", "yellow"]


def test_iot_type_selain_serial_ditolak(monkeypatch, link):
    lnk, _, _ = link
    m = NotifierManager()
    m.link = lnk
    monkeypatch.setattr(cfg, "IOT_TYPE", "http")
    m.start()
    assert m.link is None


# --- Uji lampu dari Pengaturan ---------------------------------------------------------------

@pytest.fixture
def client():
    state_mgr.reset_all()
    notifier.set_idle()
    yield TestClient(app)
    state_mgr.reset_all()
    notifier.set_idle()


@pytest.mark.parametrize("action,state", [("green", "GREEN"), ("red", "RED"), ("yellow", "YELLOW"), ("off", "OFF")])
def test_uji_lampu(client, action, state):
    r = client.post("/api/iot/test", json={"action": action})
    assert r.status_code == 200 and r.json()["light_state"] == state


def test_uji_lampu_aksi_tidak_dikenal_ditolak(client):
    r = client.post("/api/iot/test", json={"action": "blink"})
    assert r.status_code == 400
    assert notifier.current_state == LightState.OFF


def test_uji_lampu_ditolak_saat_ada_pekerja(client, monkeypatch):
    monkeypatch.setattr(state_mgr, "session", object())
    r = client.post("/api/iot/test", json={"action": "green"})
    assert r.status_code == 409 and r.json()["detail"] == messages.API_LIGHT_TEST_BUSY
    assert notifier.current_state == LightState.OFF
