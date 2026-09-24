import logging
import time
from .config import cfg
from . import messages

logger = logging.getLogger(__name__)

class LightState:
    OFF = "OFF"
    GREEN = "GREEN"
    RED = "RED"

class IoTNotifier:
    """Modular IoT Hardware Controller for Physical Tower Lights / Relays.
    
    Can be connected to Arduino/ESP32 via Serial, or a smart relay via HTTP/MQTT.
    Prepared for Stage 2 after system logic is fully validated.
    """
    def __init__(self):
        self.enabled = cfg.IOT_ENABLED
        self.iot_type = cfg.IOT_TYPE
        self.serial_conn = None

    def connect(self):
        """Membuka port serial bila IoT serial aktif. Idempoten."""
        if self.enabled and self.iot_type == "serial" and self.serial_conn is None:
            try:
                import serial
                if cfg.IOT_SERIAL_PORT.startswith("rfc2217://") or cfg.IOT_SERIAL_PORT.startswith("socket://"):
                    import serial.rfc2217
                    self.serial_conn = serial.serial_for_url(cfg.IOT_SERIAL_PORT, baudrate=cfg.IOT_SERIAL_BAUD, timeout=cfg.IOT_SERIAL_TIMEOUT_SECONDS)
                else:
                    self.serial_conn = serial.Serial(cfg.IOT_SERIAL_PORT, cfg.IOT_SERIAL_BAUD, timeout=cfg.IOT_SERIAL_TIMEOUT_SECONDS)
                logger.info(f"Connected to Serial port {cfg.IOT_SERIAL_PORT}")
            except Exception as e:
                logger.warning(f"Serial connection failed: {e}")

    def send_command(self, cmd: str):
        if not self.enabled:
            return
        try:
            if self.iot_type == "serial" and self.serial_conn:
                self.serial_conn.write(f"{cmd}\n".encode())
            elif self.iot_type == "http":
                import threading
                threading.Thread(target=self._send_http, args=(cmd,), daemon=True).start()
        except Exception as e:
            logger.warning(f"Failed to send command '{cmd}': {e}")

    def _send_http(self, cmd: str):
        import urllib.request
        state_map = {
            "LIGHT_GREEN": "green",
            "LIGHT_RED": "red",
            "LIGHT_OFF": "off"
        }
        state = state_map.get(cmd, "off")
        base_url = cfg.IOT_HTTP_URL.rstrip('/')
        url = f"{base_url}/api/light?state={state}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SafeguardAI/1.0"})
            # Isi balasan ESP32 tidak dipakai; cukup dipastikan permintaan diterima
            with urllib.request.urlopen(req, timeout=cfg.IOT_HTTP_TIMEOUT_SECONDS):
                pass
        except Exception as e:
            logger.warning(f"Wireless HTTP to ESP32 failed ({url}): {e}")

    def close(self):
        if self.serial_conn is not None:
            try:
                self.serial_conn.close()
            except Exception:
                pass
            self.serial_conn = None

    def set_green(self):
        self.send_command("LIGHT_GREEN")

    def set_red(self):
        self.send_command("LIGHT_RED")

    def set_off(self):
        self.send_command("LIGHT_OFF")


class NotifierManager:
    """Manages visual light status (UI state + optional IoT physical light)."""
    def __init__(self):
        self.current_state = LightState.OFF
        self.last_change_time = time.time()
        self.iot = IoTNotifier()
        self.message = messages.LIGHT_BOOT

    def start(self):
        """Menyambungkan lampu gerbang fisik (bila IoT aktif)."""
        self.iot.connect()

    def stop(self):
        self.iot.close()

    def set_complete(self, msg: str = messages.LIGHT_GRANTED_DEFAULT):
        self.current_state = LightState.GREEN
        self.message = msg
        self.last_change_time = time.time()
        self.iot.set_green()

    def set_incomplete(self, msg: str = messages.LIGHT_DENIED_DEFAULT):
        self.current_state = LightState.RED
        self.message = msg
        self.last_change_time = time.time()
        self.iot.set_red()

    def set_waiting(self, msg: str = messages.LIGHT_SYSTEM_WAIT):
        """Sistem gangguan: belum ada keputusan. Lampu padam — merah khusus APD kurang."""
        self.current_state = LightState.OFF
        self.message = msg
        self.last_change_time = time.time()
        self.iot.set_off()

    def set_idle(self):
        self.current_state = LightState.OFF
        self.message = messages.LIGHT_IDLE
        self.iot.set_off()

    def get_status(self) -> dict:
        return {
            "light_state": self.current_state,
            "message": self.message,
            "timestamp": self.last_change_time
        }

notifier = NotifierManager()
