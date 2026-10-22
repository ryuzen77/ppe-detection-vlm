"""Uji lampu gerbang fisik tanpa kamera (T47).

Jalankan dari akar repo, server DEPRO dalam keadaan mati (port serial hanya
bisa dibuka satu program):

    python iot/test_serial_lights.py COM3

Tiap lampu ditahan beberapa detik sambil heartbeat dikirim ulang seperti server.
Di akhir heartbeat dihentikan: papan harus beralih ke KUNING BERKEDIP sendiri.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import cfg  # noqa: E402
from backend.notifier import COMMANDS, LightState, open_serial  # noqa: E402

HOLD_SECONDS = 3.0
SEQUENCE = (LightState.GREEN, LightState.YELLOW, LightState.RED, LightState.OFF)
# Firmware menunggu 3 dtk tanpa perintah; beri jeda lebih untuk melihat kedipan
WATCHDOG_WAIT_SECONDS = 6.0


def list_ports():
    from serial.tools import list_ports as lp

    for p in lp.comports():
        print(f"  {p.device}: {p.description}")


def hold(conn, state: str):
    """Mengirim satu keadaan berulang (heartbeat) dan mencetak balasan papan."""
    end = time.monotonic() + HOLD_SECONDS
    while time.monotonic() < end:
        conn.write(f"{COMMANDS[state]}\n".encode())
        time.sleep(cfg.IOT_HEARTBEAT_SECONDS)
        reply = conn.read(conn.in_waiting or 1).decode(errors="replace").strip()
        if reply:
            print(f"  {state:<6} <- {reply}")


def main():
    if len(sys.argv) != 2:
        print("Pakai: python iot/test_serial_lights.py <PORT>\nPort terdeteksi:")
        list_ports()
        sys.exit(2)
    conn = open_serial(sys.argv[1], cfg.IOT_SERIAL_BAUD, cfg.IOT_SERIAL_TIMEOUT_SECONDS)
    try:
        for state in SEQUENCE:
            print(f"Lampu {state} selama {HOLD_SECONDS:.0f} dtk")
            hold(conn, state)
        print(f"Heartbeat dihentikan; dalam ~3 dtk papan harus KUNING BERKEDIP ({WATCHDOG_WAIT_SECONDS:.0f} dtk).")
        time.sleep(WATCHDOG_WAIT_SECONDS)
        print("  <-", conn.read(conn.in_waiting or 1).decode(errors="replace").strip() or "(tanpa balasan)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
