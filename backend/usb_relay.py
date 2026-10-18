"""Lampu gerbang lewat relay USB HID dcttech "USBRelayN" (T54).

Papan V-USB (VID 16C0, PID 05DF, nama produk `USBRelay<jumlah kanal>`) tanpa port
COM: perintah dikirim sebagai HID *feature report* (`HidD_SetFeature` di Windows,
sama seperti pustaka vendor `usb_relay_device.dll`). `write()` biasa diterima
Windows tetapi diabaikan papan — terbukti saat uji perangkat 13-10.

Relay MENGUNCI keadaannya: tanpa heartbeat seperti firmware ESP32 (T47), lampu
hijau tetap menyala bila server mati mendadak. Karena itu:
- keadaan dibaca balik tiap IOT_HEARTBEAT_SECONDS dan dikoreksi bila berbeda;
- semua relay dimatikan saat link berhenti (server berhenti rapi);
- `all_off()` dipanggil penjaga proses (`supervisor`) setiap kali server keluar,
  termasuk crash, sebelum server dinyalakan ulang;
- kabel dicabut / laptop mati = papan tanpa daya = relay lepas (lampu di kontak NO).
Sisa risiko: server macet tanpa crash; tertulis di IOT_HARDWARE_SPEC.md.
"""
import logging
import threading
import time
from typing import Callable, Optional

from . import messages
from .config import cfg

logger = logging.getLogger(__name__)

VENDOR_ID = 0x16C0
PRODUCT_ID = 0x05DF
PRODUCT_PREFIX = "USBRelay"
REPORT_ID = 0
REPORT_LENGTH = 9               # report id + 8 byte data
CMD_ON = 0xFF
CMD_OFF = 0xFD
SERIAL_BYTES = slice(1, 6)      # 5 byte serial setelah report id
STATE_INDEX = 8                 # bitmask relay menyala; bit 0 = relay 1


def channel_mask(channel: int) -> int:
    """Kanal < 1 (salah isi .env) = 0, bukan galat: link tetap dibuat saat impor dan
    validasi saat membuka papan yang menolaknya (lampu fisik tidak dinyalakan)."""
    return 1 << (channel - 1) if channel >= 1 else 0


class RelayBoard:
    """Satu papan relay yang sudah dibuka (perangkat hidapi)."""

    def __init__(self, device, product: str, serial: str):
        self._device = device
        self.product = product
        self.serial = serial
        suffix = product[len(PRODUCT_PREFIX):]
        self.channel_count = int(suffix) if suffix.isdigit() else 0

    def read_mask(self) -> int:
        data = self._device.get_feature_report(REPORT_ID, REPORT_LENGTH)
        if len(data) <= STATE_INDEX:
            raise OSError(f"laporan relay terlalu pendek ({len(data)} byte)")
        return data[STATE_INDEX]

    def switch(self, channel: int, on: bool):
        report = [REPORT_ID, CMD_ON if on else CMD_OFF, channel] + [0] * (REPORT_LENGTH - 3)
        if self._device.send_feature_report(report) < 0:
            raise OSError(f"perintah relay {channel} ditolak perangkat")

    def close(self):
        try:
            self._device.close()
        except Exception:
            pass


def find_board(serial: str = "") -> Optional[RelayBoard]:
    """Papan USBRelay pertama (atau yang serialnya cocok); None bila tidak ada."""
    import hid
    for info in hid.enumerate(VENDOR_ID, PRODUCT_ID):
        product = info.get("product_string") or ""
        if not product.startswith(PRODUCT_PREFIX):
            continue
        device = hid.device()
        device.open_path(info["path"])
        report = device.get_feature_report(REPORT_ID, REPORT_LENGTH)
        board_serial = bytes(report[SERIAL_BYTES]).decode("ascii", "replace")
        if serial and board_serial != serial:
            device.close()
            continue
        return RelayBoard(device, product, board_serial)
    return None


def all_off(reason: str, opener: Callable[[str], Optional[RelayBoard]] = find_board) -> bool:
    """Matikan semua relay papan. Dipakai penjaga proses saat server keluar/crash."""
    try:
        board = opener(cfg.IOT_RELAY_SERIAL)
        if board is None:
            return False
        try:
            for channel in range(1, board.channel_count + 1):
                board.switch(channel, False)
        finally:
            board.close()
    except Exception as e:
        logger.error(messages.IOT_RELAY_ALL_OFF_FAILED.format(reason=reason, error=str(e)[:120]))
        return False
    logger.warning(messages.IOT_RELAY_ALL_OFF.format(reason=reason))
    return True


class RelayMismatch(Exception):
    pass


class UsbRelayLink:
    """Thread tunggal pemegang papan relay; antarmuka sama dengan GateLightLink (ESP32)."""

    def __init__(self, masks: dict[str, int], channels: tuple[int, ...],
                 opener: Callable[[str], Optional[RelayBoard]] = find_board, clock=time.monotonic):
        self._masks = masks              # keadaan lampu -> bitmask relay yang menyala
        self._channels = channels
        self._all = sum(channel_mask(c) for c in channels)
        self._opener = opener
        self._clock = clock
        self._board: Optional[RelayBoard] = None
        self._desired = ""
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_ok: Optional[float] = None
        self.error: Optional[str] = None
        self._next_open_at = 0.0

    # --- API untuk NotifierManager ------------------------------------------------

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GateRelayLink", daemon=True)
        self._thread.start()

    def stop(self):
        """Berhenti rapi: semua lampu dimatikan sebelum papan dilepas."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=cfg.THREAD_STOP_TIMEOUT_SECONDS)
        with self._lock:
            self._desired = ""
        if self._board is not None or self._try_open():
            try:
                self._apply()
            except Exception as e:
                logger.error(messages.IOT_RELAY_ALL_OFF_FAILED.format(reason=messages.IOT_RELAY_REASON_STOP,
                                                                      error=str(e)[:120]))
        self._close()

    def set_state(self, state: str):
        with self._lock:
            self._desired = state
        self._wake.set()

    def status(self) -> dict:
        age = None if self.last_ok is None else round(self._clock() - self.last_ok, 1)
        connected = age is not None and age <= cfg.IOT_ACK_TIMEOUT_SECONDS
        return {"enabled": True, "connected": connected, "last_ack_age_s": age,
                "error": None if connected else (self.error or messages.IOT_NO_ACK)}

    # --- Satu putaran thread (dipanggil langsung oleh tes) ----------------------------

    def tick(self):
        if self._board is None and not self._try_open():
            return
        try:
            self._apply()
        except RelayMismatch as e:
            self._fail(str(e))
        except Exception as e:
            self._fail(messages.IOT_LINK_LOST.format(error=str(e)[:120]))

    def _run(self):
        while not self._stop.is_set():
            self.tick()
            self._wake.wait(cfg.IOT_HEARTBEAT_SECONDS)
            self._wake.clear()

    # --- Rincian ----------------------------------------------------------------------

    def _apply(self):
        """Samakan relay dengan keadaan yang diminta, lalu buktikan dengan membaca balik."""
        with self._lock:
            wanted = self._masks.get(self._desired, 0)
        board = self._board
        assert board is not None, "tick() membuka papan sebelum _apply()"
        actual = board.read_mask() & self._all
        for channel in self._channels:
            bit = channel_mask(channel)
            if (wanted ^ actual) & bit:
                board.switch(channel, bool(wanted & bit))
        if actual != wanted:
            actual = board.read_mask() & self._all
        if actual != wanted:
            raise RelayMismatch(messages.IOT_RELAY_MISMATCH.format(wanted=wanted, actual=actual))
        self.last_ok = self._clock()
        self.error = None

    def _try_open(self) -> bool:
        if self._clock() < self._next_open_at:
            return False
        try:
            board = self._opener(cfg.IOT_RELAY_SERIAL)
        except Exception as e:
            self._fail(messages.IOT_LINK_LOST.format(error=str(e)[:120]))
            return False
        if board is None:
            self._fail(messages.IOT_RELAY_NOT_FOUND.format(target=cfg.IOT_RELAY_SERIAL or messages.IOT_RELAY_ANY_BOARD))
            return False
        if not self._channels_valid(board.channel_count):
            board.close()
            self._fail(messages.IOT_RELAY_CHANNEL_INVALID.format(
                green=self._channels[0], red=self._channels[-1], count=board.channel_count))
            return False
        self._board = board
        logger.info(messages.IOT_RELAY_CONNECTED.format(product=board.product, serial=board.serial))
        return True

    def _channels_valid(self, count: int) -> bool:
        return len(set(self._channels)) == len(self._channels) and all(1 <= c <= count for c in self._channels)

    def _fail(self, message: str):
        if message != self.error:
            logger.warning(message)
        self.error = message
        self.last_ok = None
        self._close()
        self._next_open_at = self._clock() + cfg.IOT_RECONNECT_SECONDS

    def _close(self):
        if self._board is not None:
            self._board.close()
            self._board = None
