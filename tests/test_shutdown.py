"""Server berhenti bersih saat stream MJPEG dan WebSocket masih terhubung.

Tanpa penanda SHUTTING_DOWN (shutdown.py) kedua endpoint itu berputar selamanya
dan uvicorn menggantung di "Waiting for connections to close". Tes ini menjalankan
server sungguhan (`python -m backend`) di proses dan port terpisah, lalu mengirim
sinyal berhenti: CTRL_BREAK_EVENT di Windows (jalur yang sama dengan Ctrl+C),
SIGTERM di Linux/macOS (yang dikirim systemd dan Docker saat menghentikan layanan).
"""
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import IO, Any, cast

import pytest

from backend.config import cfg
from backend.vlm_providers import profiles as vlm_profiles

REPO_ROOT = Path(__file__).resolve().parent.parent

POPEN_FLAGS: dict[str, Any]
if sys.platform == "win32":
    STOP_SIGNAL = signal.CTRL_BREAK_EVENT
    POPEN_FLAGS = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
else:
    STOP_SIGNAL = signal.SIGTERM
    POPEN_FLAGS = {}


def _setup_cookie(base: str) -> str:
    """T51: semua API wajib login. Server uji punya DATA_DIR kosong, jadi admin pertama
    dibuat lewat setup (diizinkan dari localhost) dan cookie sesinya dipakai klien."""
    import json
    body = json.dumps({"username": "admin-uji", "password": "kata-sandi-uji-panjang"}).encode()
    request = urllib.request.Request(base + "/api/setup", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as r:
        return r.headers["Set-Cookie"].split(";", 1)[0]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _api_key_vars() -> set[str]:
    """Semua variabel API key VLM: milik tiap penyedia (katalog profil) + key utama/cadangan."""
    return {p.key_env for p in vlm_profiles.PROFILES.values() if p.key_env} | {"VLM_API_KEY", "VLM_BACKUP_API_KEY"}


def _server_env(tmp_path, port: int, **extra: str) -> dict[str, str]:
    """Lingkungan server uji yang tidak menyentuh dunia luar (T91).

    `load_dotenv` tidak menimpa variabel yang sudah ada dan `_env` membaca string kosong sebagai
    "tidak diisi", jadi key yang dikosongkan di sini menutup key asli `backend/.env`: tanpa
    panggilan VLM cloud (kuota gerbang), tanpa memuat model lokal, tanpa relay & kamera sungguhan.
    """
    return {**os.environ, "PORT": str(port), "HOST": "127.0.0.1",
            "DATA_DIR": str(tmp_path / "data"), "LOG_TO_FILE": "false",
            "PYTHONIOENCODING": "utf-8", "PYGAME_HIDE_SUPPORT_PROMPT": "1",
            **dict.fromkeys(_api_key_vars(), ""),
            "VLM_BACKUP_PROVIDER": "none", "VLM_LOCAL_FALLBACK_PROVIDER": "none",
            "IOT_ENABLED": "false", "CAMERA_AUTOSTART": "false", **extra}


def test_server_uji_tanpa_api_key_dan_perangkat(tmp_path):
    env = _server_env(tmp_path, 1234)
    assert "GEMINI_API_KEY" in _api_key_vars()
    assert all(env[name] == "" for name in _api_key_vars())
    assert env["VLM_BACKUP_PROVIDER"] == env["VLM_LOCAL_FALLBACK_PROVIDER"] == "none"
    assert env["IOT_ENABLED"] == env["CAMERA_AUTOSTART"] == "false"


def test_server_berhenti_bersih_dengan_klien_aktif(tmp_path):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = _server_env(tmp_path, port)
    proc = subprocess.Popen([sys.executable, "-m", "backend"], cwd=REPO_ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            **POPEN_FLAGS)
    output = []
    # Tanpa text=True keluaran berupa bytes; **POPEN_FLAGS membuat pyright memilih overload teks
    stdout = cast("IO[bytes] | None", proc.stdout)
    assert stdout is not None
    threading.Thread(target=lambda: [output.append(l.decode("utf-8", "replace")) for l in stdout],
                     daemon=True).start()
    try:
        for _ in range(240):
            try:
                urllib.request.urlopen(base + "/api/session", timeout=2)
                break
            except Exception:
                if proc.poll() is not None:
                    pytest.fail("Server berhenti saat startup:\n" + "".join(output)[-3000:])
                time.sleep(0.5)
        else:
            pytest.fail("Server tidak siap dalam 120 detik")

        cookie = _setup_cookie(base)
        # Klien stream yang terus membaca (layar tunggu tetap dialirkan tanpa kamera)
        received = [0]

        def read_stream():
            try:
                stream = urllib.request.Request(base + "/api/stream", headers={"Cookie": cookie})
                with urllib.request.urlopen(stream, timeout=30) as r:
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
                    async with websockets.connect(f"ws://127.0.0.1:{port}/ws",
                                                  additional_headers={"Cookie": cookie}) as ws:
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
    # Endpoint kita wajib berhenti sendiri (penanda SHUTTING_DOWN): tidak ada koneksi/tugas yang ditunggu
    assert "Waiting for connections to close" not in log, "stream/WebSocket masih terbuka saat shutdown"
    assert not re.search(r"Cancel [1-9]\d* running task", log), "tugas aplikasi dibatalkan paksa"
    assert elapsed < _stop_limit(log), f"Berhenti terlalu lama: {elapsed:.1f} detik"
    assert "Traceback" not in log and "CancelledError" not in log
    assert "Shutdown selesai" in log


def _stop_limit(log: str) -> float:
    """Batas waktu berhenti yang diterima.

    T85: di Windows, sesekali (±1 dari 6, diukur 20-10) `Server.wait_closed()` asyncio tertahan
    walau koneksi & tugas aplikasi sudah nol (bug proactor Python 3.12, lihat tes berikutnya) —
    terlihat dari "Cancel 0 running task(s)". Batas `SHUTDOWN_TIMEOUT_SECONDS` yang menghentikannya,
    jadi jalur itu boleh sampai batas tersebut + kelonggaran; di luar itu tetap < 5 dtk.
    """
    if "Cancel 0 running task(s), timeout graceful shutdown exceeded" in log:
        return cfg.SHUTDOWN_TIMEOUT_SECONDS + 3
    return 5


# Python 3.12 di Windows: bila klien me-reset koneksi, asyncio (proactor) bisa
# melewatkan server._detach() sehingga Server.wait_closed() menunggu selamanya.
# uvicorn memanggilnya saat shutdown, jadi server menggantung dan Ctrl+C kedua
# pun tidak menolong (terjadi nyata 24-09 dari terminal VS Code). Tes ini
# memaksa wait_closed() menggantung di semua OS dan menuntut server tetap
# berhenti bersih berkat batas waktu shutdown.
_WAIT_CLOSED_MACET = r"""
import asyncio.base_events as be
import asyncio

async def _tak_pernah_selesai(self):
    await asyncio.Event().wait()

be.Server.wait_closed = _tak_pernah_selesai
from backend.app import run
run()
"""


def test_server_tetap_berhenti_walau_koneksi_macet_saat_shutdown(tmp_path):
    port = _free_port()
    env = _server_env(tmp_path, port, SHUTDOWN_TIMEOUT_SECONDS="1")
    proc = subprocess.Popen([sys.executable, "-c", _WAIT_CLOSED_MACET], cwd=REPO_ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **POPEN_FLAGS)
    output = []
    # Tanpa text=True keluaran berupa bytes; **POPEN_FLAGS membuat pyright memilih overload teks
    stdout = cast("IO[bytes] | None", proc.stdout)
    assert stdout is not None
    threading.Thread(target=lambda: [output.append(l.decode("utf-8", "replace")) for l in stdout],
                     daemon=True).start()
    try:
        for _ in range(240):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/session", timeout=2)
                break
            except Exception:
                if proc.poll() is not None:
                    pytest.fail("Server berhenti saat startup:\n" + "".join(output)[-3000:])
                time.sleep(0.5)
        else:
            pytest.fail("Server tidak siap dalam 120 detik")

        start = time.time()
        os.kill(proc.pid, STOP_SIGNAL)
        try:
            code = proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            pytest.fail("Server menggantung di wait_closed():\n" + "".join(output)[-2000:])
        elapsed = time.time() - start
    finally:
        if proc.poll() is None:
            proc.kill()

    log = "".join(output)
    assert code == 0
    assert elapsed < 8, f"Berhenti terlalu lama: {elapsed:.1f} detik"
    assert "Shutdown selesai" in log
