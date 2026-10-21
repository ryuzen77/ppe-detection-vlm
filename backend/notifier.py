"""Lampu gerbang: status untuk dashboard + lampu fisik ESP32 lewat USB serial (T47).

Lampu fisik dikendalikan satu thread `GateLightLink` yang memegang port serial:
- port dibuka TANPA menyentuh DTR/RTS, karena keduanya me-reset ESP32/Arduino
  (papan reboot tiap server start dan perintah pertama hilang);
- keadaan lampu dikirim ulang tiap IOT_HEARTBEAT_SECONDS. Firmware menyalakan
  kuning berkedip bila heartbeat hilang, jadi hijau tidak tertinggal menyala
  saat server crash;
- balasan `OK:` dari papan menandai sambungan sehat; port yang galat ditutup
  dan dibuka ulang otomatis (kabel dicabut lalu dicolok lagi).

Alternatifnya (T54) relay USB HID 2 kanal (`usb_relay.py`): hijau & merah saja.
Perintah lewat HTTP/Wi-Fi tanpa tanda tangan bisa dipalsukan siapa pun di jaringan
yang sama (analisa T47), jadi dibuang.
"""
import logging
import threading
import time
from typing import Optional

from . import messages
from .config import cfg

logger = logging.getLogger(__name__)


class LightState:
    OFF = "OFF"
    GREEN = "GREEN"
    RED = "RED"
    # Gangguan sistem / pekerja diminta menunggu. Merah khusus APD kurang.
    YELLOW = "YELLOW"


# Perintah firmware iot/esp32_gate_controller untuk tiap keadaan lampu
COMMANDS = {
    LightState.OFF: "LIGHT_OFF",
    LightState.GREEN: "LIGHT_GREEN",
    LightState.RED: "LIGHT_RED",
    LightState.YELLOW: "LIGHT_YELLOW",
}
ACK_PREFIX = b"OK:"
ACK_LAMPS = {
    LightState.GREEN.encode(): (cfg.IOT_LAMP_GREEN,),
    LightState.RED.encode(): (cfg.IOT_LAMP_RED,),
    LightState.YELLOW.encode(): (cfg.IOT_LAMP_YELLOW,),
    LightState.OFF.encode(): (),
}
SERIAL_LAMPS = (cfg.IOT_LAMP_GREEN, cfg.IOT_LAMP_RED, cfg.IOT_LAMP_YELLOW)
SERIAL_URL_SCHEMES = ("rfc2217://", "socket://")   # simulator Wokwi


def open_serial(port: str, baud: int, timeout: float):
    """Membuka port tanpa memicu auto-reset papan (DTR/RTS diset sebelum open)."""
    import serial
    if port.startswith(SERIAL_URL_SCHEMES):
        conn = serial.serial_for_url(port, do_not_open=True)
    else:
        conn = serial.Serial()
        conn.port = port
    conn.baudrate = baud
    conn.timeout = 0
    conn.write_timeout = timeout
    conn.dtr = False
    conn.rts = False
    conn.open()
    return conn


class GateLightLink:
    """Thread tunggal pemegang port serial lampu gerbang."""

    def __init__(self, opener=open_serial, clock=time.monotonic):
        self._opener = opener
        self._clock = clock
        self._conn = None
        self._desired = LightState.OFF
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._rx = b""
        self.last_ack: Optional[float] = None
        self._ack_state: Optional[bytes] = None
        self.error: Optional[str] = None
        self._next_open_at = 0.0

    # --- API untuk NotifierManager ------------------------------------------------

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GateLightLink", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=cfg.THREAD_STOP_TIMEOUT_SECONDS)
        self._close()

    def set_state(self, state: str):
        with self._lock:
            self._desired = state
        self._wake.set()   # kirim segera, tidak menunggu heartbeat berikutnya

    def status(self) -> dict:
        now = self._clock()
        age = None if self.last_ack is None else round(now - self.last_ack, 1)
        connected = age is not None and age <= cfg.IOT_ACK_TIMEOUT_SECONDS
        lamps = ACK_LAMPS.get(self._ack_state) if self._ack_state is not None else None
        fresh = self.last_ack is not None and now - self.last_ack <= cfg.IOT_ACK_TIMEOUT_SECONDS
        known = fresh and self._conn is not None and self.error is None and lamps is not None
        return {"enabled": True, "connected": connected, "last_ack_age_s": age,
                "error": None if connected else (self.error or messages.IOT_NO_ACK),
                "lamps_on": list(lamps) if known and lamps is not None else None,
                "lamps_available": list(SERIAL_LAMPS)}

    # --- Satu putaran thread (dipanggil langsung oleh tes) ----------------------------

    def tick(self):
        if self._conn is None and not self._try_open():
            return
        try:
            with self._lock:
                command = COMMANDS[self._desired]
            conn = self._conn
            assert conn is not None, "_try_open() baru saja membuka port"
            conn.write(f"{command}\n".encode())
            self._read_acks()
        except Exception as e:
            self._fail(messages.IOT_LINK_LOST.format(error=str(e)[:120]))

    def _run(self):
        while not self._stop.is_set():
            self.tick()
            self._wake.wait(cfg.IOT_HEARTBEAT_SECONDS)
            self._wake.clear()

    # --- Rincian ----------------------------------------------------------------------

    def _try_open(self) -> bool:
        if self._clock() < self._next_open_at:
            return False
        try:
            self._conn = self._opener(cfg.IOT_SERIAL_PORT, cfg.IOT_SERIAL_BAUD, cfg.IOT_SERIAL_TIMEOUT_SECONDS)
            self._rx = b""
            logger.info(messages.IOT_CONNECTED.format(port=cfg.IOT_SERIAL_PORT))
            return True
        except Exception as e:
            self._fail(messages.IOT_OPEN_FAILED.format(port=cfg.IOT_SERIAL_PORT, error=str(e)[:120]))
            return False

    def _read_acks(self):
        # Port dibuka non-blocking (timeout 0): read() langsung mengembalikan yang
        # tersedia. `in_waiting` tidak dipakai karena di sebagian backend pyserial
        # (mis. socket:// Wokwi) isinya 0/1, bukan jumlah byte (temuan smoke test).
        conn = self._conn
        assert conn is not None, "dipanggil hanya dari tick() setelah port terbuka"
        data = conn.read(cfg.IOT_RX_MAX_BYTES)
        if not data:
            return
        self._rx += data
        *lines, self._rx = self._rx.split(b"\n")
        for line in lines:
            if line.strip().startswith(ACK_PREFIX):
                self._ack_state = line.strip()[len(ACK_PREFIX):]
                self.last_ack = self._clock()
                self.error = None
        # Sisa tanpa baris baru dibatasi supaya data sampah tidak menumpuk
        self._rx = self._rx[-cfg.IOT_RX_MAX_BYTES:]

    def _fail(self, message: str):
        if message != self.error:
            logger.warning(message)
        self.error = message
        self.last_ack = None
        self._close()
        self._next_open_at = self._clock() + cfg.IOT_RECONNECT_SECONDS

    def _close(self):
        self._ack_state = None
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


def _usb_relay_link():
    """Relay USB 2 kanal (T54): hanya hijau & merah; kuning/siaga = semua mati."""
    from .usb_relay import UsbRelayLink, channel_mask
    green, red = cfg.IOT_RELAY_GREEN_CHANNEL, cfg.IOT_RELAY_RED_CHANNEL
    return UsbRelayLink({LightState.GREEN: channel_mask(green), LightState.RED: channel_mask(red)}, (green, red))


# IOT_TYPE -> pembuat link lampu fisik. Membuat link tidak menyentuh perangkat;
# port/papan baru dibuka oleh thread link setelah start().
LINK_FACTORIES = {"serial": GateLightLink, "usb_relay": _usb_relay_link}


class NotifierManager:
    """Keadaan lampu untuk dashboard, diteruskan ke lampu fisik bila IoT aktif."""

    def __init__(self):
        self.current_state = LightState.OFF
        self.last_change_time = time.time()
        self.message = messages.LIGHT_BOOT
        factory = LINK_FACTORIES.get(cfg.IOT_TYPE) if cfg.IOT_ENABLED else None
        self.link = factory() if factory is not None else None

    def start(self):
        if cfg.IOT_TYPE not in LINK_FACTORIES:
            if cfg.IOT_ENABLED or self.link is not None:
                logger.error(messages.IOT_TYPE_UNSUPPORTED.format(iot_type=cfg.IOT_TYPE))
            self.link = None
            return
        if self.link is not None:
            self.link.start()

    def stop(self):
        if self.link is not None:
            self.link.stop()

    def _set(self, state: str, msg: str):
        self.current_state = state
        self.message = msg
        self.last_change_time = time.time()
        if self.link is not None:
            self.link.set_state(state)

    def set_complete(self, msg: str = messages.LIGHT_GRANTED_DEFAULT):
        self._set(LightState.GREEN, msg)

    def set_incomplete(self, msg: str = messages.LIGHT_DENIED_DEFAULT):
        self._set(LightState.RED, msg)

    def set_waiting(self, msg: str = messages.LIGHT_SYSTEM_WAIT):
        """Sistem gangguan: belum ada keputusan, pekerja diminta menunggu (kuning)."""
        self._set(LightState.YELLOW, msg)

    def set_idle(self):
        self._set(LightState.OFF, messages.LIGHT_IDLE)

    def get_status(self) -> dict:
        return {
            "light_state": self.current_state,
            "message": self.message,
            "timestamp": self.last_change_time
        }

    def iot_status(self) -> dict:
        """Status lampu fisik untuk telemetri (kontrak T47)."""
        if self.link is None:
            return {"enabled": False, "connected": False, "last_ack_age_s": None, "error": None,
                    "lamps_on": None, "lamps_available": None}
        return self.link.status()


notifier = NotifierManager()
