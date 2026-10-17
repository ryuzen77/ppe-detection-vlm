"""Pekerja dipotret hanya setelah siap: utuh, menghadap kamera, dan diam (T46).

Regresi uji nyata 28-09: 12 dari 20 sesi dipotret 0,08 dtk setelah sesi mulai,
saat pekerja masih melangkah masuk.
"""
import time

import pytest

from backend import messages, readiness
from backend.config import cfg
from backend.detector import DetectionResult
from backend.readiness import ReadinessTracker
from backend.state_manager import state_mgr, TrackState

from helpers import person_crop

BBOX = [470, 50, 810, 660]          # tinggi tubuh 610 px
FACING = [[0, 0, 0.9]] * 17
SIDEWAYS = [[0, 0, 0.9]] * 5 + [[0, 0, 0.1], [0, 0, 0.1]] + [[0, 0, 0.9]] * 10


def geser(bbox, dy=0, grow=0):
    """Kotak bergeser ke bawah `dy` px dan membesar `grow` px (mendekat ke kamera)."""
    x1, y1, x2, y2 = bbox
    return [x1 - grow, y1 + dy - grow, x2 + grow, y2 + dy + grow]


@pytest.fixture
def tahan(monkeypatch):
    monkeypatch.setattr(cfg, "READY_HOLD_SECONDS", 1.0)
    monkeypatch.setattr(cfg, "READY_MAX_DRIFT", 0.05)
    monkeypatch.setattr(cfg, "READY_REQUIRE_SHOULDERS", True)


# --- Logika murni ---------------------------------------------------------------------

def test_berdiri_diam_siap_setelah_waktu_tahan(tahan):
    t = ReadinessTracker()
    for i in range(31):                       # 30 FPS selama 1 dtk, goyangan kotak ~1%
        t.update(geser(BBOX, dy=(i % 3) * 3), FACING, now=i / 30)
    assert t.ready(now=30 / 30)
    assert not t.ready(now=0.5)


def test_berjalan_pelan_tidak_pernah_siap(tahan):
    """Tiap frame hanya bergeser 0,5% (tampak diam antar-frame), tetapi terus bergeser."""
    t = ReadinessTracker()
    bbox = BBOX
    for i in range(90):                       # 3 dtk berjalan
        bbox = geser(bbox, dy=3)
        t.update(bbox, FACING, now=i / 30)
        assert not t.ready(now=i / 30), f"dipotret saat berjalan, frame {i}"
    assert t.restarts >= 2


def test_mendekat_lurus_ke_kamera_tidak_dianggap_diam(tahan):
    """Titik tengah nyaris tetap, tetapi tubuh membesar."""
    t = ReadinessTracker()
    bbox = BBOX
    for i in range(60):
        bbox = geser(bbox, grow=4)
        t.update(bbox, FACING, now=i / 30)
        assert not t.ready(now=i / 30)


def test_menyamping_menahan_jendela(tahan):
    t = ReadinessTracker()
    for i in range(60):
        t.update(BBOX, SIDEWAYS, now=i / 30)
    assert not t.holding and not t.ready(now=2.0)
    t.update(BBOX, FACING, now=2.0)
    assert t.holding and not t.ready(now=2.5)
    t.update(BBOX, FACING, now=3.0)
    assert t.ready(now=3.0)


def test_tanpa_data_pose_tidak_menahan(tahan):
    assert readiness.shoulders_visible(None)
    t = ReadinessTracker()
    t.update(BBOX, None, now=0.0)
    t.update(BBOX, None, now=1.0)
    assert t.ready(now=1.0)


def test_syarat_bahu_bisa_dimatikan(tahan, monkeypatch):
    monkeypatch.setattr(cfg, "READY_REQUIRE_SHOULDERS", False)
    t = ReadinessTracker()
    t.update(BBOX, SIDEWAYS, now=0.0)
    t.update(BBOX, SIDEWAYS, now=1.0)
    assert t.ready(now=1.0)


# --- Integrasi state machine ------------------------------------------------------------

def _det(bbox=BBOX, keypoints=FACING):
    return DetectionResult(
        track_id=7, bbox=list(bbox), is_full_body=True, reason=messages.POSE_OK,
        is_inside_corridor=True, crop_img=person_crop(), conf=0.9, keypoints=keypoints)


@pytest.fixture
def terkirim(monkeypatch, catalog_defaults):
    """Mencatat panggilan VLM; jendela tahan dipendekkan supaya tes cepat."""
    from backend.audio_engine import audio_player
    from backend.notifier import notifier
    from backend.vlm_analyzer import vlm_analyzer
    asli = vlm_analyzer.analyze_person
    dikirim = []

    def catat(crop):
        dikirim.append(time.time())
        return asli(crop)

    monkeypatch.setattr(vlm_analyzer, "analyze_person", catat)
    monkeypatch.setattr(cfg, "STABLE_FRAMES_REQUIRED", 3)
    monkeypatch.setattr(cfg, "READY_HOLD_SECONDS", 0.4)
    monkeypatch.setattr(cfg, "READY_MAX_DRIFT", 0.05)
    monkeypatch.setattr(cfg, "READY_REQUIRE_SHOULDERS", True)
    was_muted = audio_player.is_muted
    audio_player.set_muted(True)
    state_mgr.reset_all()
    yield dikirim
    state_mgr.reset_all()
    notifier.set_idle()
    audio_player.set_muted(was_muted)


def _kirim_selama(detik, buat_det):
    akhir = time.time() + detik
    i = 0
    while time.time() < akhir:
        state_mgr.update_frame_detections([buat_det(i)])
        i += 1
        time.sleep(1 / 30)


def _tunggu(pred, batas=3.0):
    akhir = time.time() + batas
    while time.time() < akhir and not pred():
        time.sleep(0.02)
    return pred()


def test_tiga_frame_pertama_tidak_langsung_dipotret(terkirim):
    """Regresi 28-09: dulu VLM dipanggil 0,08 dtk setelah sesi dimulai."""
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 2):
        state_mgr.update_frame_detections([_det()])
    time.sleep(0.1)
    assert terkirim == []
    assert state_mgr.get_telemetry()["active_track"]["state"] == TrackState.STABILIZING


def test_dipotret_sekali_setelah_diam(terkirim):
    mulai = time.time()
    _kirim_selama(0.8, lambda i: _det())
    assert _tunggu(lambda: len(terkirim) == 1)
    assert terkirim[0] - mulai >= cfg.READY_HOLD_SECONDS
    time.sleep(0.2)
    assert len(terkirim) == 1, "Tetap satu panggilan VLM per sesi"


def test_berjalan_melewati_jalur_tidak_dipotret(terkirim):
    _kirim_selama(1.0, lambda i: _det(bbox=geser(BBOX, dy=4 * i)))
    time.sleep(0.1)
    assert terkirim == []


def test_kandidat_dibatasi(terkirim, monkeypatch):
    monkeypatch.setattr(cfg, "READY_HOLD_SECONDS", 5.0)
    for _ in range(cfg.READY_MAX_CANDIDATES * 3):
        state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is not None
    assert len(state_mgr.session.candidates) == cfg.READY_MAX_CANDIDATES
