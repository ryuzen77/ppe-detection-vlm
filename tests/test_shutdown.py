"""Server berhenti bersih saat stream MJPEG dan WebSocket masih terhubung.

Tanpa penanda SHUTTING_DOWN (shutdown.py) kedua endpoint itu berputar selamanya
dan uvicorn menggantung di "Waiting for connections to close". Tes ini menjalankan
server sungguhan (`python -m backend`) di proses dan port terpisah, lalu mengirim
sinyal berhenti: CTRL_BREAK_EVENT di Windows (jalur yang sama dengan Ctrl+C),
SIGTERM di Linux/macOS (yang dikirim systemd dan Docker saat menghentikan layanan).
"""
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

if sys.platform == "win32":
    STOP_SIGNAL = signal.CTRL_BREAK_EVENT
    POPEN_FLAGS = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
else:
    STOP_SIGNAL = signal.SIGTERM
    POPEN_FLAGS = {}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_server_berhenti_bersih_dengan_klien_aktif(tmp_path):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1",
           "DATA_DIR": str(tmp_path / "data"), "LOG_TO_FILE": "false",
           "PYTHONIOENCODING": "utf-8", "PYGAME_HIDE_SUPPORT_PROMPT": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "backend"], cwd=REPO_ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            **POPEN_FLAGS)
    output = []
    threading.Thread(target=lambda: [output.append(l.decode("utf-8", "replace")) for l in proc.stdout],
                     daemon=True).start()
    try:
        for _ in range(240):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=2)
                break
            except Exception:
                if proc.poll() is not None:
                    pytest.fail("Server berhenti saat startup:\n" + "".join(output)[-3000:])
                time.sleep(0.5)
        else:
            pytest.fail("Server tidak siap dalam 120 detik")

        # Klien stream yang terus membaca (layar tunggu tetap dialirkan tanpa kamera)
        received = [0]

        def read_stream():
            try:
                with urllib.request.urlopen(base + "/api/stream", timeout=30) as r:
                    while chunk := r.read(65536):
                        received[0] += len(chunk)
            except Exception:
                pass
        threading.Thread(target=read_stream, daemon=True).start()

        # Klien WebSocket yang terus menerima telemetri
        def read_ws():
            import asyncio
            import websockets

            async def run():
                try:
                    async with websockets.connect(f"ws://127.0.0.1:{port}/ws") as ws:
                        while True:
                            await ws.recv()
                except Exception:
                    pass
            asyncio.run(run())
        threading.Thread(target=read_ws, daemon=True).start()

        deadline = time.time() + 15
        while received[0] == 0 and time.time() < deadline:
            time.sleep(0.2)
        assert received[0] > 0, "Stream tidak mengalir sebelum sinyal dikirim"

        start = time.time()
        os.kill(proc.pid, STOP_SIGNAL)
        try:
            code = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pytest.fail("Server menggantung setelah sinyal berhenti:\n" + "".join(output)[-2000:])
        elapsed = time.time() - start
    finally:
        if proc.poll() is None:
            proc.kill()

    log = "".join(output)
    assert code == 0
    assert elapsed < 5, f"Berhenti terlalu lama: {elapsed:.1f} detik"
    assert "Traceback" not in log and "CancelledError" not in log
    assert "Shutdown selesai" in log
