"""Alur ujung ke ujung state machine gerbang: posisi, analisa, anti-spam, standby.

Pengganti `backend/test_lifecycle.py`. Mengimpor `state_manager` ikut memuat YOLO
(efek samping impor yang dijadwalkan dihapus di T16), jadi berkas ini paling lambat.
"""
import time

import pytest

from backend.config import cfg
from backend.detector import DetectionResult
from backend.state_manager import state_mgr, TrackState
from backend.audio_engine import audio_player
from backend.notifier import notifier
from backend import messages

from helpers import person_crop

TRACK_ID = 42


def _det(full_body: bool, **kwargs):
    base = dict(track_id=TRACK_ID, is_inside_corridor=True, crop_img=person_crop(), conf=0.95)
    if full_body:
        base.update(bbox=[470, 50, 810, 660], is_full_body=True, reason=messages.POSE_OK)
    else:
        base.update(bbox=[450, 20, 830, 715], is_full_body=False, reason=messages.POSE_FEET_CLIPPED_EDGE)
    base.update(kwargs)
    return DetectionResult(**base)


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def gerbang(monkeypatch, catalog_defaults):
    """State machine bersih, audio senyap, dan jeda standby dipersingkat."""
    monkeypatch.setattr(cfg, "STANDBY_RESET_DELAY_SECONDS", 0.2)
    was_muted = audio_player.is_muted
    audio_player.set_muted(True)
    state_mgr.reset_all()
    notifier.set_idle()
    yield state_mgr
    state_mgr.reset_all()
    notifier.set_idle()
    audio_player.set_muted(was_muted)


def _active():
    return state_mgr.get_telemetry()["active_track"]


def test_alur_gerbang_lengkap(gerbang):
    # Riwayat inspeksi sengaja bertahan melewati reset_all (log dashboard), jadi
    # yang diuji adalah pertambahannya.
    riwayat_awal = len(state_mgr.inspection_history)

    # 1. Tubuh terpotong: peringatan mundur, VLM belum dipanggil
    gerbang.update_frame_detections([_det(full_body=False)])
    active = _active()
    assert active["state"] == TrackState.STEP_BACK_WARNING
    assert active["is_full_body"] is False
    assert active["vlm_result"] is None
    assert notifier.current_state == "RED"

    # 2. Mundur hingga seluruh tubuh terlihat; analisa terpicu tepat saat stabil
    for i in range(1, cfg.STABLE_FRAMES_REQUIRED + 1):
        gerbang.update_frame_detections([_det(full_body=True)])
    telemetry = state_mgr.get_telemetry()
    assert telemetry["stable_frames_required"] == cfg.STABLE_FRAMES_REQUIRED

    # 3. Analisa selesai: APD lengkap, lampu hijau, tercatat di riwayat
    assert _wait_for(lambda: _active()["state"] == TrackState.ANALYZED), "Analisa tidak selesai dalam 5 detik"
    hasil = _active()["vlm_result"]
    assert hasil["is_complete"] is True
    assert hasil["inference_source"] == "OFFLINE_FALLBACK", "Tes tidak boleh memanggil Gemini"
    assert notifier.current_state == "GREEN"
    assert notifier.message == messages.LIGHT_GRANTED
    jumlah_analisa = len(state_mgr.inspection_history)
    assert jumlah_analisa == riwayat_awal + 1

    # 4. Anti-spam: orang yang sama tetap berdiri, tidak dianalisa ulang
    for _ in range(10):
        gerbang.update_frame_detections([_det(full_body=True)])
    time.sleep(0.2)
    assert len(state_mgr.inspection_history) == jumlah_analisa

    # 5. Orang meninggalkan kamera: gerbang kembali standby
    gerbang.update_frame_detections([])
    assert state_mgr.get_telemetry()["has_person"] is False
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([])
    assert notifier.current_state == "OFF"
    assert notifier.message == messages.LIGHT_IDLE


def test_apd_kurang_menutup_gerbang(gerbang):
    crop = person_crop(vest=False)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True, crop_img=crop)])

    assert _wait_for(lambda: _active()["state"] == TrackState.ANALYZED)
    hasil = _active()["vlm_result"]
    assert hasil["is_complete"] is False
    assert notifier.current_state == "RED"
    assert notifier.message.startswith(messages.LIGHT_DENIED_MISSING.split("{")[0])


def test_orang_di_luar_koridor_tidak_dianalisa(gerbang):
    riwayat_awal = len(state_mgr.inspection_history)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 3):
        gerbang.update_frame_detections([_det(full_body=True, is_inside_corridor=False)])
    time.sleep(0.2)
    assert len(state_mgr.inspection_history) == riwayat_awal
    assert _active() is None or _active()["vlm_result"] is None


def test_vlm_gagal_menolak_dengan_pesan_verifikasi(gerbang, monkeypatch):
    # VLM aktif tetapi selalu gagal: gerbang merah dengan pesan jujur, bukan
    # "APD tidak lengkap" dan bukan keputusan engine lokal.
    from backend.vlm_analyzer import vlm_analyzer
    from backend.vlm_providers import VLMProvider

    class SelaluGagal(VLMProvider):
        name = "gagal"

        def generate(self, *a):
            raise RuntimeError("503")

        def ping(self):
            return ""

    monkeypatch.setattr(cfg, "FREE_TIER_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(vlm_analyzer, "provider", SelaluGagal("model"))
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True)])

    assert _wait_for(lambda: _active()["state"] == TrackState.ANALYZED)
    hasil = _active()["vlm_result"]
    assert hasil["is_unverified"] is True and hasil["is_complete"] is False
    assert notifier.current_state == "RED"
    assert notifier.message == messages.LIGHT_UNVERIFIED
