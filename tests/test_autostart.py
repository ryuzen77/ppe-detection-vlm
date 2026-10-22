"""Gerbang berjalan sendiri (T29): penjaga proses, kamera otomatis lewat nama, pemeriksaan saat start."""

import pytest
from fastapi.testclient import TestClient

from backend import camera_manager, messages, startup_checks, supervisor
from backend.app import app
from backend.config import cfg
from backend.video.capture import VideoCaptureService


# --- Penjaga proses -------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _runner(codes, clock, durations):
    calls = []

    def run(cmd):
        calls.append(cmd)
        clock.now += durations.pop(0)
        return codes.pop(0)

    return run, calls


def test_berhenti_rapi_tidak_dinyalakan_ulang():
    clock = Clock()
    run, calls = _runner([0], clock, [100])
    assert supervisor.supervise(["srv"], run=run, sleep=lambda s: None, clock=clock) == 0
    assert len(calls) == 1


def test_crash_dinyalakan_ulang_sampai_berhenti_rapi():
    clock, sleeps = Clock(), []
    run, calls = _runner([1, -9, 0], clock, [300, 300, 300])
    assert supervisor.supervise(["srv"], run=run, sleep=sleeps.append, clock=clock) == 0
    assert len(calls) == 3
    assert sleeps == [cfg.SUPERVISOR_RESTART_DELAY_SECONDS] * 2, "server yang sempat stabil: jeda awal"


def test_crash_beruntun_jedanya_berlipat_sampai_batas():
    clock, sleeps = Clock(), []
    run, _ = _runner([1] * 8, clock, [1] * 8)
    supervisor.supervise(["srv"], run=run, sleep=sleeps.append, clock=clock, max_runs=8)
    assert sleeps[0] == cfg.SUPERVISOR_RESTART_DELAY_SECONDS, "crash pertama: jeda dasar"
    assert sleeps[1] == 2 * sleeps[0] and sleeps == sorted(sleeps) and sleeps[-1] == cfg.SUPERVISOR_MAX_DELAY_SECONDS


def test_ctrl_c_menghentikan_penjaga():
    def run(cmd):
        raise KeyboardInterrupt

    assert supervisor.supervise(["srv"], run=run, sleep=lambda s: None) == 0


# --- Kamera otomatis lewat nama --------------------------------------------------------------


@pytest.fixture
def cam(monkeypatch):
    svc = VideoCaptureService()
    opened = []

    def fake_init(index, mode=None):
        opened.append(index)
        svc.camera_status, svc.camera_index = "OK", index
        return True

    monkeypatch.setattr(svc, "_init_camera", fake_init)
    monkeypatch.setattr(
        camera_manager,
        "load_saved_selection",
        lambda: {"index": 1, "name": "HD Pro Webcam C920", "mode": {"width": 864}},
    )
    return svc, opened


def test_kamera_eksternal_dibuka_lewat_nama_walau_indeks_berpindah(cam, monkeypatch):
    svc, opened = cam
    monkeypatch.setattr(camera_manager, "list_device_names", lambda: ["Integrated Camera", "OBS", "HD Pro Webcam C920"])
    svc._autostart_camera()
    assert opened == [2]


def test_kamera_belum_terlihat_menunggu_bukan_membuka_kamera_lain(cam, monkeypatch):
    """Dulu: jatuh ke indeks 0 = kamera bawaan laptop, diam-diam."""
    svc, opened = cam
    monkeypatch.setattr(camera_manager, "list_device_names", lambda: ["Integrated Camera", "OBS"])
    mode = svc._autostart_camera()
    assert opened == [] and svc.camera_status == "LOST"
    assert svc.camera_name == "HD Pro Webcam C920" and mode == {"width": 864}, "sambung ulang memakai nama & mode"
    assert svc._camera_fault(None, 0.0) == "lost", "lampu kuning selama menunggu"


def test_camera_name_menang_atas_pilihan_terakhir(cam, monkeypatch):
    svc, opened = cam
    monkeypatch.setattr(cfg, "CAMERA_NAME", "USB Cam X")
    monkeypatch.setattr(camera_manager, "list_device_names", lambda: ["HD Pro Webcam C920", "USB Cam X"])
    svc._autostart_camera()
    assert opened == [1]
    assert camera_manager.autostart_target()[1] is None, "mode kamera lain tidak dipakai"


def test_tanpa_nama_menunggu_operator(cam, monkeypatch):
    svc, opened = cam
    monkeypatch.setattr(camera_manager, "load_saved_selection", lambda: None)
    svc._autostart_camera()
    assert opened == [] and svc.camera_status == "IDLE"


# --- Pemeriksaan saat start ------------------------------------------------------------------


@pytest.fixture
def ada_akun(monkeypatch):
    from backend.accounts import store

    monkeypatch.setattr(store, "count", lambda: 1)


def test_pemeriksaan_start(monkeypatch, ada_akun):
    monkeypatch.setattr(startup_checks, "ollama_version", lambda url: "0.35.1")
    out = startup_checks.run(False, "http://localhost:11434/v1", "HD Pro Webcam C920", lambda: ["Integrated Camera"])
    assert out == [
        messages.STARTUP_NO_CUDA,
        messages.STARTUP_OLLAMA_VERSION.format(found="0.35.1", expected=cfg.OLLAMA_VALIDATED_VERSION),
        messages.STARTUP_CAMERA_MISSING.format(name="HD Pro Webcam C920", seen="Integrated Camera"),
    ]


def test_pemeriksaan_start_semua_baik(monkeypatch, ada_akun):
    monkeypatch.setattr(startup_checks, "ollama_version", lambda url: cfg.OLLAMA_VALIDATED_VERSION)
    assert startup_checks.run(True, "http://localhost:11434/v1", "Cam", lambda: ["Cam"]) == []
    assert startup_checks.check_ollama_version(None) == messages.STARTUP_OLLAMA_UNREACHABLE


def test_peringatan_tanpa_cadangan(monkeypatch, ada_akun):
    """T71: tanpa cadangan (bawaan) admin diberi tahu konsekuensinya saat start."""
    assert startup_checks.check_backup(True) is None
    out = startup_checks.run(True, None, "Cam", lambda: ["Cam"], has_backup=False)
    assert out == [messages.STARTUP_NO_BACKUP]


def test_health_menyertakan_peringatan_start(monkeypatch):
    monkeypatch.setattr(startup_checks, "warnings", ["contoh peringatan"])
    assert TestClient(app).get("/api/health").json()["startup_warnings"] == ["contoh peringatan"]


def test_peringatan_akun_dan_token_lama(monkeypatch):
    """T51: belum ada akun → arahkan ke setup di mesin gerbang; ADMIN_TOKEN lama → hapus dari .env."""
    assert startup_checks.check_accounts(0) == messages.STARTUP_NO_ACCOUNT.format(port=cfg.PORT)
    assert startup_checks.check_accounts(2) is None
    assert startup_checks.check_legacy_admin_token(True) == messages.STARTUP_ADMIN_TOKEN_UNUSED
    assert startup_checks.check_legacy_admin_token(False) is None
