"""Mode pendaftaran wajah (T75): gerbang jeda selama admin memotret, tidak pernah meloloskan orang."""

import time

import pytest

from backend import messages
from backend.audio_engine import audio_player
from backend.detector import DetectionResult
from backend.notifier import notifier
from backend.state_manager import state_mgr

from helpers import person_crop


@pytest.fixture
def gate(monkeypatch, catalog_defaults):
    played = []
    monkeypatch.setattr(audio_player, "play", lambda name, *a, **k: played.append(name))
    monkeypatch.setattr(state_mgr, "camera_fault_sound_at", {})
    state_mgr.release_enrollment()
    state_mgr.set_camera_fault(None)
    state_mgr.reset_all()
    yield played
    state_mgr.release_enrollment()
    state_mgr.set_camera_fault(None)
    state_mgr.reset_all()


def _det():
    return DetectionResult(
        track_id=1,
        bbox=[470, 50, 810, 660],
        is_full_body=True,
        reason=messages.POSE_OK,
        is_inside_corridor=True,
        crop_img=person_crop(),
        conf=0.9,
        keypoints=[[0, 0, 0.9]] * 17,
    )


def _expire_hold():
    state_mgr.enrollment_until = time.time() - 1


def _enrollment_light():
    return notifier.current_state == "YELLOW" and notifier.message == messages.LIGHT_ENROLLMENT


def test_jeda_membatalkan_sesi_dan_hijau_lalu_kuning(gate):
    """Risiko utama: hijau yang sedang menyala tidak boleh tertahan selama jeda."""
    notifier.set_complete()
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is not None
    assert state_mgr.hold_for_enrollment() is True
    assert state_mgr.session is None and _enrollment_light()


def test_selama_jeda_orang_di_jalur_tidak_diperiksa(gate):
    state_mgr.hold_for_enrollment()
    for _ in range(10):
        state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is None and gate == [], "tanpa sesi, arahan posisi, maupun suara"
    telemetry = state_mgr.get_telemetry()
    assert telemetry["active_track"] is None and telemetry["enrollment"]["active"] is True
    assert telemetry["enrollment"]["remaining_s"] > 0


def test_denyut_memperpanjang_tanpa_memulai_ulang(gate):
    assert state_mgr.hold_for_enrollment() is True
    first = state_mgr.enrollment_until
    time.sleep(0.01)
    assert state_mgr.hold_for_enrollment() is False, "denyut bukan jeda baru (security log sekali)"
    assert state_mgr.enrollment_until > first


def test_modal_ditutup_gerbang_memeriksa_lagi(gate):
    state_mgr.hold_for_enrollment()
    assert state_mgr.release_enrollment() is True
    assert notifier.current_state == "OFF" and state_mgr.get_telemetry()["enrollment"] == {
        "active": False,
        "remaining_s": None,
    }
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is not None
    assert state_mgr.release_enrollment() is False, "menutup dua kali tidak tercatat dua kali"


def test_tanpa_denyut_jeda_selesai_sendiri(gate):
    """Browser ditutup / jaringan putus: gerbang tidak boleh jeda selamanya."""
    state_mgr.hold_for_enrollment()
    _expire_hold()
    assert state_mgr.get_telemetry()["enrollment"]["active"] is False
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is not None and state_mgr.enrollment_until == 0.0
    assert not _enrollment_light()


def test_wajah_dekat_terbaca_terhalang_tanpa_suara_gangguan(gate):
    state_mgr.hold_for_enrollment()
    state_mgr.set_camera_fault("blocked")
    assert gate == [] and _enrollment_light()
    state_mgr.set_camera_fault(None)
    assert _enrollment_light(), "gangguan pulih: jeda tetap berlaku"


def test_gangguan_yang_berlanjut_tampil_setelah_jeda(gate):
    state_mgr.hold_for_enrollment()
    state_mgr.set_camera_fault("blocked")
    state_mgr.release_enrollment()
    assert notifier.current_state == "YELLOW" and notifier.message == messages.LIGHT_CAMERA_FAULT["blocked"]
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is None, "gambar tetap tidak dipercaya"


def test_reset_gerbang_tidak_menghapus_jeda(gate):
    state_mgr.hold_for_enrollment()
    state_mgr.reset_all()  # mis. kamera dibuka ulang saat modal terbuka
    assert _enrollment_light()
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is None
