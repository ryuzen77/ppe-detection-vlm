"""Ketangguhan kamera (T45): tertutup, membeku, terputus — gerbang berhenti memeriksa, lampu kuning."""
import numpy as np
import pytest

from backend import camera_health as ch
from backend import messages
from backend.audio_engine import audio_player
from backend.config import cfg
from backend.detector import DetectionResult
from backend.notifier import notifier
from backend.state_manager import state_mgr
from backend.video.capture import VideoCaptureService

from helpers import person_crop

RNG = np.random.default_rng(45)


def scene():
    """Pemandangan diam dengan derau sensor: tiap panggilan sedikit berbeda, seperti kamera hidup."""
    base = np.full((480, 864, 3), 120, np.uint8)
    base[100:400, 300:560] = 60                      # ada objek -> tidak seragam
    noise = RNG.integers(-3, 4, base.shape, dtype=np.int16)
    return np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def dark():
    return np.full((480, 864, 3), 8, np.uint8) + RNG.integers(0, 3, (480, 864, 3), dtype=np.uint8)


def feed(health, frames, start=0.0, fps=10):
    fault = None
    for i, f in enumerate(frames):
        fault = health.update(f, start + i / fps)
    return fault


# --- Deteksi murni ----------------------------------------------------------------------

def test_pemandangan_normal_tidak_dianggap_tertutup():
    assert not ch.is_blocked(scene())


@pytest.mark.parametrize("value", [8, 250])
def test_terlalu_gelap_atau_terang_dianggap_tertutup(value):
    assert ch.is_blocked(np.full((480, 864, 3), value, np.uint8))


def test_gambar_seragam_dianggap_tertutup():
    assert ch.is_blocked(np.full((480, 864, 3), 128, np.uint8))     # tangan menempel di lensa


def test_tertutup_harus_bertahan_sebelum_gangguan():
    h = ch.CameraHealth()
    n = int(cfg.CAMERA_BLOCKED_SECONDS * 10)
    assert feed(h, [dark() for _ in range(n)]) is None, "kurang dari batas waktu: belum gangguan"
    assert h.update(dark(), cfg.CAMERA_BLOCKED_SECONDS + 0.1) == ch.FAULT_BLOCKED


def test_kamera_hidup_yang_diam_tidak_dianggap_membeku():
    h = ch.CameraHealth()
    assert feed(h, [scene() for _ in range(int(cfg.CAMERA_FROZEN_SECONDS * 10) + 20)]) is None


def test_frame_identik_dianggap_membeku():
    h = ch.CameraHealth()
    frozen = scene()
    assert feed(h, [frozen] * (int(cfg.CAMERA_FROZEN_SECONDS * 10) + 2)) == ch.FAULT_FROZEN


def test_pulih_harus_stabil_sebentar():
    h = ch.CameraHealth()
    feed(h, [dark() for _ in range(int(cfg.CAMERA_BLOCKED_SECONDS * 10) + 2)])
    t = cfg.CAMERA_BLOCKED_SECONDS + 1
    assert h.update(scene(), t) == ch.FAULT_BLOCKED, "satu frame sehat belum cukup"
    assert h.update(scene(), t + cfg.CAMERA_HEALTHY_SECONDS) is None


# --- Gerbang -------------------------------------------------------------------------------

@pytest.fixture
def gate(monkeypatch, catalog_defaults):
    played = []
    monkeypatch.setattr(audio_player, "play", lambda name, *a, **k: played.append(name))
    state_mgr.reset_all()
    yield played
    state_mgr.reset_all()


def _det():
    return DetectionResult(track_id=1, bbox=[470, 50, 810, 660], is_full_body=True, reason=messages.POSE_OK,
                           is_inside_corridor=True, crop_img=person_crop(), conf=0.9, keypoints=[[0, 0, 0.9]] * 17)


def test_gangguan_membatalkan_hijau_dan_menyalakan_kuning(gate):
    """Risiko utama: hijau tertahan untuk pekerja berikutnya saat kamera bermasalah."""
    notifier.set_complete()
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is not None
    state_mgr.set_camera_fault("blocked")
    assert state_mgr.session is None
    assert notifier.current_state == "YELLOW" and notifier.message == messages.LIGHT_CAMERA_FAULT["blocked"]


def test_suara_gangguan_hanya_sekali_saat_mulai(gate):
    for fault in ("lost", "lost", "frozen", "lost"):
        state_mgr.set_camera_fault(fault)
    assert gate == ["gangguan_kamera"]


def test_selama_gangguan_tidak_ada_sesi_baru(gate):
    state_mgr.set_camera_fault("blocked")
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is None and state_mgr.get_telemetry()["camera_fault"] == "blocked"


def test_pulih_kembali_siaga(gate):
    state_mgr.set_camera_fault("lost")
    state_mgr.set_camera_fault(None)
    assert notifier.current_state == "OFF" and state_mgr.get_telemetry()["camera_fault"] is None
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is not None, "pemeriksaan berjalan lagi"


# --- Sambungan di thread kamera -------------------------------------------------------------

@pytest.fixture
def cam():
    svc = VideoCaptureService()
    svc.camera_index, svc.camera_status = 0, "OK"
    return svc


def test_kamera_terputus_jadi_gangguan(cam):
    cam.camera_status = "LOST"
    assert cam._camera_fault(scene(), 0.0) == "lost"


def test_kamera_dibuka_atau_belum_dipilih_bukan_gangguan(cam):
    cam.camera_status = "OPENING"
    assert cam._camera_fault(dark(), 0.0) is None


def test_membeku_memicu_sambung_ulang_dengan_alasan_jelas(cam):
    frozen = scene()
    fault = None
    for i in range(int(cfg.CAMERA_FROZEN_SECONDS * 10) + 2):
        fault = cam._camera_fault(frozen, i / 10)
    assert fault == ch.FAULT_FROZEN and cam._device_missing and cam._missing_reason == messages.CAMERA_FROZEN
    # Thread pembaca lalu menandai LOST dengan alasan "membeku"; gangguan tetap "frozen"
    cam.camera_status, cam.camera_error = "LOST", messages.CAMERA_FROZEN
    assert cam._camera_fault(frozen, 99.0) == ch.FAULT_FROZEN


def test_status_kamera_tertutup_di_telemetri(cam):
    for i in range(int(cfg.CAMERA_BLOCKED_SECONDS * 10) + 2):
        cam._camera_fault(dark(), i / 10)
    assert cam.get_camera_status()["status"] == "BLOCKED"


def test_suara_gangguan_kamera_tersedia():
    assert "gangguan_kamera" in messages.VOICE_TEXTS
    assert (cfg.AUDIO_DIR / "gangguan_kamera.mp3").exists()
