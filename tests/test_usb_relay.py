"""Lampu gerbang lewat relay USB HID 2 kanal (T54), dengan papan tiruan.

Paling penting: hijau HANYA saat APD lengkap, merah HANYA saat APD kurang, dan
relay yang mengunci tidak boleh tertinggal hijau saat server berhenti/crash.
"""
import sys
import types

import pytest

from backend import messages, notifier as notifier_module, supervisor, usb_relay
from backend.config import cfg
from backend.notifier import LightState, NotifierManager

GREEN_BIT, RED_BIT = 0b01, 0b10


class FakeDevice:
    """Meniru papan dcttech: feature report = [report id, serial 5 byte, 0, 0, bitmask]."""

    def __init__(self, serial=b"HURTM", ignore_commands=False):
        self.mask = 0
        self.serial = serial
        self.ignore_commands = ignore_commands
        self.unplugged = False
        self.sent = []
        self.closed = False

    def get_feature_report(self, report_id, length):
        if self.unplugged:
            raise OSError("perangkat dicabut")
        assert (report_id, length) == (usb_relay.REPORT_ID, usb_relay.REPORT_LENGTH)
        return [0, *self.serial, 0, 0, self.mask]

    def send_feature_report(self, data):
        if self.unplugged:
            raise OSError("perangkat dicabut")
        assert len(data) == usb_relay.REPORT_LENGTH and data[0] == usb_relay.REPORT_ID
        self.sent.append(tuple(data[:3]))
        if not self.ignore_commands:
            bit = usb_relay.channel_mask(data[2])
            self.mask = self.mask | bit if data[1] == usb_relay.CMD_ON else self.mask & ~bit
        return len(data)

    def write(self, data):
        raise AssertionError("papan ini mengabaikan write(); perintah wajib lewat feature report (uji 13-10)")

    def open_path(self, path):
        pass

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def board():
    return FakeDevice()


@pytest.fixture
def relay_link(monkeypatch, board):
    """Link seperti yang dibuat notifier untuk IOT_TYPE=usb_relay (relay 1 hijau, 2 merah)."""
    monkeypatch.setattr(cfg, "IOT_RELAY_GREEN_CHANNEL", 1)
    monkeypatch.setattr(cfg, "IOT_RELAY_RED_CHANNEL", 2)
    clock = Clock()
    boards = {"current": board}

    def opener(serial):
        dev = boards["current"]
        return None if dev is None else usb_relay.RelayBoard(dev, "USBRelay2", dev.serial.decode())
    link = notifier_module._usb_relay_link()
    link._opener, link._clock = opener, clock
    return link, clock, boards


# --- Pemetaan keadaan -> lampu -------------------------------------------------------------

@pytest.mark.parametrize("state,expected", [
    (LightState.GREEN, GREEN_BIT),
    (LightState.RED, RED_BIT),
    (LightState.YELLOW, 0),      # kuning tidak ada: peringatan = semua mati, BUKAN merah
    (LightState.OFF, 0),
])
def test_hanya_lengkap_hijau_hanya_kurang_merah(relay_link, board, state, expected):
    link, _, _ = relay_link
    link.set_state(state)
    link.tick()
    assert board.mask == expected
    assert link.status()["connected"] is True


def test_berganti_hijau_ke_merah_tidak_pernah_keduanya(relay_link, board):
    link, _, _ = relay_link
    link.set_state(LightState.GREEN)
    link.tick()
    link.set_state(LightState.RED)
    link.tick()
    assert board.mask == RED_BIT


def test_keadaan_dikoreksi_bila_relay_berubah_sendiri(relay_link, board):
    link, _, _ = relay_link
    link.set_state(LightState.OFF)
    link.tick()
    board.mask = GREEN_BIT           # mis. disentuh alat lain / gangguan
    link.tick()                      # heartbeat berikutnya
    assert board.mask == 0


def test_perintah_tidak_dijalankan_papan_terdeteksi(relay_link, board):
    link, _, _ = relay_link
    board.ignore_commands = True
    link.set_state(LightState.GREEN)
    link.tick()
    status = link.status()
    assert status["connected"] is False
    assert status["error"] == messages.IOT_RELAY_MISMATCH.format(wanted=GREEN_BIT, actual=0)


# --- Sambungan --------------------------------------------------------------------------------

def test_dicabut_lalu_dicolok_lagi(relay_link, board):
    link, clock, boards = relay_link
    link.set_state(LightState.RED)
    link.tick()
    board.unplugged = True
    link.tick()
    assert link.status()["connected"] is False
    replacement = FakeDevice()
    boards["current"] = replacement
    link.tick()                                  # masih dalam jeda sambung ulang
    assert replacement.mask == 0
    clock.now += cfg.IOT_RECONNECT_SECONDS
    link.tick()
    assert replacement.mask == RED_BIT and link.status()["connected"] is True


def test_papan_tidak_ada(relay_link):
    link, _, boards = relay_link
    boards["current"] = None
    link.tick()
    assert link.status()["error"] == messages.IOT_RELAY_NOT_FOUND.format(target=messages.IOT_RELAY_ANY_BOARD)


@pytest.mark.parametrize("green,red", [(1, 1), (1, 3), (0, 2)])
def test_kanal_tidak_sah_tidak_pernah_menyalakan(monkeypatch, board, green, red):
    monkeypatch.setattr(cfg, "IOT_RELAY_GREEN_CHANNEL", green)
    monkeypatch.setattr(cfg, "IOT_RELAY_RED_CHANNEL", red)
    link = notifier_module._usb_relay_link()
    link._opener = lambda serial: usb_relay.RelayBoard(board, "USBRelay2", "HURTM")
    link.set_state(LightState.GREEN)
    link.tick()
    assert board.sent == [] and link.status()["connected"] is False


# --- Pengaman relay yang mengunci ---------------------------------------------------------------

def test_berhenti_rapi_mematikan_semua_lampu(relay_link, board):
    link, _, _ = relay_link
    link.set_state(LightState.GREEN)
    link.tick()
    link.stop()
    assert board.mask == 0 and board.closed


def test_all_off_mematikan_semua_kanal(board):
    board.mask = GREEN_BIT | RED_BIT
    opened = usb_relay.RelayBoard(board, "USBRelay2", "HURTM")
    assert usb_relay.all_off("uji", opener=lambda serial: opened) is True
    assert board.mask == 0 and board.closed


def test_all_off_tanpa_papan_atau_galat_tidak_melempar(board):
    assert usb_relay.all_off("uji", opener=lambda serial: None) is False
    board.unplugged = True
    assert usb_relay.all_off("uji", opener=lambda serial: usb_relay.RelayBoard(board, "USBRelay2", "x")) is False


def test_penjaga_mematikan_lampu_setiap_server_keluar():
    codes, events = iter([1, 0]), []
    supervisor.supervise(["server"], run=lambda cmd: next(codes), sleep=lambda s: events.append("jeda"),
                         clock=lambda: 0.0, on_exit=lambda code: events.append(f"lampu mati {code}"))
    assert events == ["lampu mati 1", "jeda", "lampu mati 0"], "lampu mati SEBELUM jeda nyala ulang"


@pytest.mark.parametrize("enabled,iot_type,called", [(True, "usb_relay", True), (True, "serial", False),
                                                     (False, "usb_relay", False)])
def test_penjaga_hanya_menyentuh_relay_bila_dipakai(monkeypatch, enabled, iot_type, called):
    calls = []
    monkeypatch.setattr(cfg, "IOT_ENABLED", enabled)
    monkeypatch.setattr(cfg, "IOT_TYPE", iot_type)
    monkeypatch.setattr(usb_relay, "all_off", lambda reason: calls.append(reason))
    supervisor.lights_off_after_exit(3)
    assert calls == ([messages.IOT_RELAY_REASON_EXIT.format(code=3)] if called else [])


# --- Menemukan papan (hidapi tiruan) --------------------------------------------------------------

def fake_hid(devices):
    module = types.ModuleType("hid")
    module.enumerate = lambda vid, pid: [
        {"product_string": product, "path": i} for i, (product, _) in enumerate(devices)
        if (vid, pid) == (usb_relay.VENDOR_ID, usb_relay.PRODUCT_ID)]
    queue = [dev for _, dev in devices]
    module.device = lambda: queue.pop(0)
    return module


def test_menemukan_papan_menurut_serial(monkeypatch):
    first, second = FakeDevice(serial=b"AAAAA"), FakeDevice(serial=b"HURTM")
    monkeypatch.setitem(sys.modules, "hid", fake_hid([("USBRelay2", first), ("USBRelay2", second)]))
    found = usb_relay.find_board("HURTM")
    assert found.serial == "HURTM" and found.channel_count == 2 and first.closed


def test_perangkat_lain_dengan_vid_sama_diabaikan(monkeypatch):
    monkeypatch.setitem(sys.modules, "hid", fake_hid([("V-USB Lain", FakeDevice())]))
    assert usb_relay.find_board() is None


def test_perintah_lewat_feature_report(board):
    """Regresi uji perangkat 13-10: write() diterima Windows tetapi diabaikan papan."""
    usb_relay.RelayBoard(board, "USBRelay2", "HURTM").switch(1, True)
    assert board.sent == [(0, usb_relay.CMD_ON, 1)] and board.mask == GREEN_BIT


# --- NotifierManager ------------------------------------------------------------------------------

def test_notifier_memakai_relay_bila_dipilih(monkeypatch):
    monkeypatch.setattr(cfg, "IOT_ENABLED", True)
    monkeypatch.setattr(cfg, "IOT_TYPE", "usb_relay")
    assert isinstance(NotifierManager().link, usb_relay.UsbRelayLink)


def test_keputusan_gerbang_sampai_ke_relay(relay_link, board):
    link, _, _ = relay_link
    manager = NotifierManager()
    manager.link = link
    manager.set_complete()
    link.tick()
    assert board.mask == GREEN_BIT
    manager.set_incomplete()
    link.tick()
    assert board.mask == RED_BIT
    manager.set_waiting()
    link.tick()
    assert board.mask == 0
