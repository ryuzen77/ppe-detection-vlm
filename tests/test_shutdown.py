"""Server berhenti bersih saat stream MJPEG dan WebSocket masih terhubung.

Tanpa penanda SHUTTING_DOWN (shutdown.py) kedua endpoint itu berputar selamanya
dan uvicorn menggantung di "Waiting for connections to close". Tes ini menjalankan
server sungguhan (`python -m backend`) di proses dan port terpisah, lalu mengirim
sinyal berhenti: CTRL_BREAK_EVENT di Windows (jalur yang sama dengan Ctrl+C),
SIGTERM di Linux/macOS (yang dikirim systemd dan Docker saat menghentikan layanan).
"""

import io
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.client import HTTPResponse
from pathlib import Path
from types import SimpleNamespace
from typing import IO, Any, cast

import httpx
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


def _read_headers(request: str | urllib.request.Request, timeout: float):
    """T94: habiskan body sebelum menutup koneksi, walau pemanggil hanya membutuhkan header.

    Setup/probe yang membuang body bisa me-reset koneksi server: Proactor Windows lalu gagal
    di socket.shutdown() (WinError 10054), sebelum sinyal shutdown tes dikirim.
    """
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
        return response.headers


def _setup_cookie(base: str) -> str:
    """T51: semua API wajib login. Server uji punya DATA_DIR kosong, jadi admin pertama
    dibuat lewat setup (diizinkan dari localhost) dan cookie sesinya dipakai klien."""
    import json

    body = json.dumps({"username": "admin-uji", "password": "kata-sandi-uji-panjang"}).encode()
    request = urllib.request.Request(
        base + "/api/setup", data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    return _read_headers(request, timeout=10)["Set-Cookie"].split(";", 1)[0]


@pytest.mark.parametrize("setup", [False, True], ids=["session-probe", "admin-setup"])
def test_http_client_consumes_response_before_closing(monkeypatch, setup):
    """Parser HTTP sungguhan atas soket tiruan: penutupan tidak boleh menyisakan body."""
    unread_on_close = []

    class ResponseBuffer(io.BytesIO):
        def close(self):
            if not self.closed:
                unread_on_close.append(len(self.getvalue()) - self.tell())
            super().close()

    wire = ResponseBuffer(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nSet-Cookie: session=uji; HttpOnly\r\n\r\n{}")
    socket_stub = cast("socket.socket", SimpleNamespace(makefile=lambda *_args: wire))
    response = HTTPResponse(socket_stub)
    response.begin()
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: response)
    if setup:
        assert _setup_cookie("http://server-uji") == "session=uji"
    else:
        assert _read_headers("http://server-uji/api/session", timeout=2)["Content-Length"] == "2"
    assert unread_on_close == [0], "body HTTP tidak boleh dibuang saat koneksi ditutup"
    assert response.isclosed()


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _api_key_vars() -> set[str]:
    """Semua variabel API key VLM: milik tiap penyedia (katalog profil) + key utama/cadangan."""
    return {p.key_env for p in vlm_profiles.PROFILES.values() if p.key_env} | {"VLM_API_KEY", "VLM_BACKUP_API_KEY"}


_PROXY_VARS = {"http_proxy", "https_proxy", "all_proxy"}


def _server_env(tmp_path, port: int, **extra: str) -> dict[str, str]:
    """Lingkungan server uji yang tidak menyentuh dunia luar (T91).

    `load_dotenv` tidak menimpa variabel yang sudah ada dan `_env` membaca string kosong sebagai
    "tidak diisi", jadi key yang dikosongkan di sini menutup key asli `backend/.env`: tanpa
    panggilan VLM cloud (kuota gerbang), relay, kamera, atau kartu suara sungguhan. Ollama tidak
    bisa dialihkan lewat lingkungan (pemeriksaan model sisa memakai alamat profil) → `_ISOLATION`.
    """
    # Proxy warisan dibuang & NO_PROXY=* (tinjauan Codex T91 v2): httpx mengikuti HTTP(S)_PROXY/ALL_PROXY,
    # sehingga sambungan menuju port proxy — bukan port Ollama — lolos dari pengaman `_ISOLATION`
    inherited = {k: v for k, v in os.environ.items() if k.lower() not in _PROXY_VARS}
    return {
        **inherited,
        "NO_PROXY": "*",
        "no_proxy": "*",
        "PORT": str(port),
        "HOST": "127.0.0.1",
        "DATA_DIR": str(tmp_path / "data"),
        "LOG_TO_FILE": "false",
        "PYTHONIOENCODING": "utf-8",
        "PYGAME_HIDE_SUPPORT_PROMPT": "1",
        "SDL_AUDIODRIVER": "dummy",
        **dict.fromkeys(_api_key_vars(), ""),
        "VLM_BACKUP_PROVIDER": "none",
        "VLM_LOCAL_FALLBACK_PROVIDER": "none",
        "IOT_ENABLED": "false",
        "CAMERA_AUTOSTART": "false",
        **extra,
    }


# Dijalankan lebih dulu di proses server uji (tinjauan Codex T91): startup tetap memeriksa model
# Ollama sisa sesi lalu & bisa membongkarnya (keep_alive=0) — model milik server lain bisa keluar
# dari GPU. Sambungan ke port Ollama (dari katalog profil) ditolak; jalur produksinya tetap jalan.
GUARD_READY = "T91_ISOLATION_READY"
_ISOLATION = rf"""
import socket
from urllib.parse import urlparse
from backend.vlm_providers import profiles

_ollama_port = urlparse(profiles.PROFILES["ollama"].base_url).port
_connect = socket.socket.connect

def _guarded_connect(sock, address):
    if isinstance(address, tuple) and len(address) >= 2 and address[1] == _ollama_port:
        raise ConnectionRefusedError("T91: Ollama diblokir di server uji")
    return _connect(sock, address)

socket.socket.connect = _guarded_connect
print("{GUARD_READY}", flush=True)
"""
_RUN_SERVER = _ISOLATION + "from backend.app import run\nrun()\n"


def test_server_uji_tanpa_api_key_dan_perangkat(tmp_path):
    env = _server_env(tmp_path, 1234)
    assert "GEMINI_API_KEY" in _api_key_vars()
    assert all(env[name] == "" for name in _api_key_vars())
    assert env["VLM_BACKUP_PROVIDER"] == env["VLM_LOCAL_FALLBACK_PROVIDER"] == "none"
    assert env["IOT_ENABLED"] == env["CAMERA_AUTOSTART"] == "false"
    assert env["SDL_AUDIODRIVER"] == "dummy"
    assert env["NO_PROXY"] == env["no_proxy"] == "*"


@pytest.fixture
def isolation_guard():
    """Pengaman yang sama dengan server uji, dipasang di proses tes lalu dilepas lagi."""
    scope: dict = {}
    exec(_ISOLATION.replace(f'print("{GUARD_READY}", flush=True)', ""), scope)
    yield scope["_ollama_port"]
    socket.socket.connect = scope["_connect"]


def test_pengaman_menolak_sambungan_ke_port_ollama(isolation_guard):
    """Port Ollama ditolak sebelum paket keluar."""
    with socket.socket() as sock, pytest.raises(ConnectionRefusedError, match="T91"):
        sock.connect(("127.0.0.1", isolation_guard))


def test_proxy_warisan_tidak_melewati_pengaman(isolation_guard, monkeypatch, tmp_path):
    """Proxy di lingkungan pengembang tidak boleh meneruskan /api/ps ke Ollama (tinjauan Codex T91 v2)."""
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:18080")  # proxy palsu, port tertutup
    env = _server_env(tmp_path, 1234)
    assert not {k.lower() for k in env} & _PROXY_VARS
    for name in list(os.environ):
        monkeypatch.delenv(name)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    # Klien seperti adaptor Ollama (httpx, trust_env bawaan): harus langsung ke port Ollama & ditolak pengaman
    with httpx.Client() as client, pytest.raises(httpx.ConnectError, match="T91"):
        client.get(f"http://127.0.0.1:{isolation_guard}/api/ps", timeout=2)


def test_server_berhenti_bersih_dengan_klien_aktif(tmp_path):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = _server_env(tmp_path, port)
    proc = subprocess.Popen(
        [sys.executable, "-c", _RUN_SERVER],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **POPEN_FLAGS,
    )
    output = []
    # Tanpa text=True keluaran berupa bytes; **POPEN_FLAGS membuat pyright memilih overload teks
    stdout = cast("IO[bytes] | None", proc.stdout)
    assert stdout is not None
    threading.Thread(target=lambda: [output.append(l.decode("utf-8", "replace")) for l in stdout], daemon=True).start()
    try:
        for _ in range(240):
            try:
                _read_headers(base + "/api/session", timeout=2)
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
                    async with websockets.connect(
                        f"ws://127.0.0.1:{port}/ws", additional_headers={"Cookie": cookie}
                    ) as ws:
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
    assert GUARD_READY in log, "pengaman Ollama T91 tidak aktif di server uji"
    # Endpoint kita wajib berhenti sendiri (penanda SHUTTING_DOWN): tidak ada koneksi/tugas yang ditunggu
    assert "Waiting for connections to close" not in log, "stream/WebSocket masih terbuka saat shutdown"
    assert not re.search(r"Cancel [1-9]\d* running task", log), "tugas aplikasi dibatalkan paksa"
    assert elapsed < _stop_limit(log), f"Berhenti terlalu lama: {elapsed:.1f} detik"
    assert "Traceback" not in log and "CancelledError" not in log, log
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
    proc = subprocess.Popen(
        [sys.executable, "-c", _ISOLATION + _WAIT_CLOSED_MACET],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **POPEN_FLAGS,
    )
    output = []
    # Tanpa text=True keluaran berupa bytes; **POPEN_FLAGS membuat pyright memilih overload teks
    stdout = cast("IO[bytes] | None", proc.stdout)
    assert stdout is not None
    threading.Thread(target=lambda: [output.append(l.decode("utf-8", "replace")) for l in stdout], daemon=True).start()
    try:
        for _ in range(240):
            try:
                _read_headers(f"http://127.0.0.1:{port}/api/session", timeout=2)
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
