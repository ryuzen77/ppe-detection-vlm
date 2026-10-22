"""Pemilihan frame terbaik sebelum analisa VLM (T25a)."""

import time

import cv2
import numpy as np
import pytest

from backend import frame_quality, messages
from backend.config import cfg
from backend.detector import DetectionResult
from backend.frame_quality import FrameCandidate, choose_best
from backend.state_manager import state_mgr, TrackState

from helpers import person_crop

BBOX = [470, 50, 810, 660]


def buram(img, k=15):
    return cv2.GaussianBlur(img, (k, k), 0)


def kandidat(crop, bbox=BBOX, pose=0.9):
    kp = [[0, 0, pose]] * 17
    return FrameCandidate(crop=crop, bbox=list(bbox), keypoints=kp, track_id=1)


# --- Penilaian ----------------------------------------------------------------------


def test_foto_buram_lebih_rendah_ketajamannya():
    tajam = person_crop()
    assert frame_quality.sharpness(buram(tajam)) < frame_quality.sharpness(tajam) * 0.5


def test_ketajaman_tidak_bergantung_ukuran_crop():
    # Orang yang lebih dekat (crop lebih besar) tidak otomatis dianggap lebih tajam
    kecil = person_crop()
    besar = cv2.resize(kecil, (kecil.shape[1] * 2, kecil.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
    a, b = frame_quality.sharpness(kecil), frame_quality.sharpness(besar)
    assert abs(a - b) / max(a, b) < 0.35


def test_gerakan_relatif_terhadap_tinggi_tubuh():
    assert frame_quality.motion(BBOX, None) == 0.0
    assert frame_quality.motion(BBOX, BBOX) == 0.0
    geser = [BBOX[0] + 61, BBOX[1], BBOX[2] + 61, BBOX[3]]  # 61 px pada tinggi 610 px = 10%
    assert frame_quality.motion(geser, BBOX) == pytest.approx(0.1)


def test_kejelasan_pose_rata_rata_titik_penting():
    assert frame_quality.pose_clarity(None) == 0.0
    assert frame_quality.pose_clarity([[0, 0, 0.8]] * 17) == pytest.approx(0.8)


# --- Pemilihan ------------------------------------------------------------------------


def test_frame_tajam_dipilih_di_antara_yang_buram():
    tajam = person_crop()
    calon = [kandidat(buram(tajam)), kandidat(tajam), kandidat(buram(tajam, 9))]
    assert choose_best(calon) is calon[1]


def test_pada_ketajaman_sama_frame_yang_diam_dipilih():
    img = person_crop()
    bergeser = [BBOX[0] + 60, BBOX[1], BBOX[2] + 60, BBOX[3]]
    # Frame 1 diam di posisi sebelumnya; frame 2 bergeser ~10% tinggi tubuh.
    # Frame diam sengaja di depan: kalau lolos, itu karena gerakan dinilai,
    # bukan karena aturan seri yang memilih frame terakhir.
    calon = [kandidat(img, BBOX), kandidat(img, bergeser)]
    assert choose_best(calon, prev_bbox=BBOX) is calon[0]
    assert calon[0].motion == 0.0 and calon[1].motion > 0.05


def test_skor_seri_memilih_frame_terakhir():
    img = person_crop()
    calon = [kandidat(img), kandidat(img), kandidat(img)]
    assert choose_best(calon) is calon[2]


def test_tanpa_kandidat_ditolak():
    with pytest.raises(ValueError):
        choose_best([])


def test_penilaian_cepat():
    # Crop seukuran orang di kamera 848x480; bawaan 3 kandidat harus jauh di bawah 1 frame (33 ms)
    crop = cv2.resize(person_crop(), (180, 420))
    calon = [kandidat(crop) for _ in range(3)]
    mulai = time.perf_counter()
    for _ in range(20):
        choose_best(calon)
    per_pilihan_ms = (time.perf_counter() - mulai) / 20 * 1000
    assert per_pilihan_ms < 15, f"{per_pilihan_ms:.1f} ms"


# --- Integrasi state machine ------------------------------------------------------------


def _det(crop, full_body=True):
    return DetectionResult(
        track_id=42,
        bbox=list(BBOX),
        is_full_body=full_body,
        reason=messages.POSE_OK if full_body else messages.POSE_FEET_CLIPPED_EDGE,
        is_inside_corridor=True,
        crop_img=crop,
        conf=0.9,
        keypoints=[[0, 0, 0.9]] * 17,
    )


@pytest.fixture
def terkirim(monkeypatch, catalog_defaults):
    """Mencatat crop yang benar-benar diserahkan ke VLM."""
    from backend.audio_engine import audio_player
    from backend.notifier import notifier
    from backend.vlm_analyzer import vlm_analyzer

    asli = vlm_analyzer.analyze_person
    dikirim = []

    def catat(crop, keypoints=None):
        dikirim.append(crop.copy())
        return asli(crop)

    monkeypatch.setattr(vlm_analyzer, "analyze_person", catat)
    monkeypatch.setattr(cfg, "STABLE_FRAMES_REQUIRED", 3)
    monkeypatch.setattr(cfg, "READY_HOLD_SECONDS", 0.0)  # jendela diam diuji di test_readiness.py
    was_muted = audio_player.is_muted
    audio_player.set_muted(True)
    state_mgr.reset_all()
    yield dikirim
    state_mgr.reset_all()
    notifier.set_idle()
    audio_player.set_muted(was_muted)


def _tunggu(pred, batas=5.0):
    akhir = time.time() + batas
    while time.time() < akhir and not pred():
        time.sleep(0.02)
    return pred()


def test_frame_tertajam_yang_dikirim_ke_vlm(terkirim):
    tajam = person_crop()
    for crop in (buram(tajam), tajam, buram(tajam, 9)):
        state_mgr.update_frame_detections([_det(crop)])
    assert _tunggu(lambda: len(terkirim) == 1)
    time.sleep(0.2)
    assert len(terkirim) == 1, "Tetap satu panggilan VLM per sesi"
    assert np.array_equal(terkirim[0], tajam)


def test_belum_dikirim_sebelum_kandidat_lengkap(terkirim):
    tajam = person_crop()
    for _ in range(cfg.STABLE_FRAMES_REQUIRED - 1):
        state_mgr.update_frame_detections([_det(tajam)])
    time.sleep(0.2)
    assert terkirim == []
    assert state_mgr.get_telemetry()["active_track"]["state"] == TrackState.STABILIZING


def test_tubuh_terpotong_mengulang_kumpulan_kandidat(terkirim):
    tajam = person_crop()
    # Frame tajam di rangkaian pertama tidak boleh ikut: rangkaian terputus
    state_mgr.update_frame_detections([_det(tajam)])
    state_mgr.update_frame_detections([_det(tajam)])
    state_mgr.update_frame_detections([_det(tajam, full_body=False)])
    rangkaian_baru = [buram(tajam, 21), buram(tajam, 9), buram(tajam, 31)]
    for crop in rangkaian_baru:
        state_mgr.update_frame_detections([_det(crop)])
    assert _tunggu(lambda: len(terkirim) == 1)
    assert np.array_equal(terkirim[0], rangkaian_baru[1]), "Terbaik dari rangkaian baru, bukan frame lama"
