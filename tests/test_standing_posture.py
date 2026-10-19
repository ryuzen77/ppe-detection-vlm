"""Syarat berdiri sebelum dikirim ke VLM (T73).

Uji nyata 19-10: orang duduk di depan kamera lolos syarat tubuh utuh (kepala & kaki
terlihat) dan ikut diperiksa VLM — kuota free tier terbuang, lampu merah & audit palsu.
"""
import numpy as np

from backend import messages
from backend import pose_keypoints as kp
from backend.audio_engine import POSITION_SOUNDS, AudioEngine
from backend.config import cfg
from backend.detector import FrameMargins, _not_standing, _pose_status

FRAME_H = 1080
BOX = [800, 100, 1100, 1000]
CONF = 0.9


def pose(left_leg=(600, 780, 960), right_leg=(600, 780, 960), hips_conf=CONF):
    """Orang menghadap kamera; kaki = (y pinggul, y lutut, y pergelangan kaki) per sisi."""
    k = np.zeros((17, 3))
    for i, y in ((kp.NOSE, 180), (kp.LEFT_EYE, 170), (kp.RIGHT_EYE, 170),
                 (kp.LEFT_SHOULDER, 300), (kp.RIGHT_SHOULDER, 300)):
        k[i] = (950, y, CONF)
    for (hip, knee, ankle), (hy, ky, ay) in (((kp.LEFT_HIP, kp.LEFT_KNEE, kp.LEFT_ANKLE), left_leg),
                                             ((kp.RIGHT_HIP, kp.RIGHT_KNEE, kp.RIGHT_ANKLE), right_leg)):
        k[hip], k[knee], k[ankle] = (900, hy, hips_conf), (900, ky, CONF), (900, ay, CONF)
    return k


def status(k):
    return _pose_status(k, BOX, FRAME_H, FrameMargins.for_height(FRAME_H))


def test_berdiri_lolos():
    assert status(pose()) == (True, messages.POSE_OK, "OPTIMAL")


def test_duduk_diminta_berdiri():
    # Paha mendatar: lutut hampir sejajar pinggul, tulang kering tegak
    duduk = pose(left_leg=(780, 800, 960), right_leg=(780, 805, 960))
    assert status(duduk) == (False, messages.POSE_NOT_STANDING, "NOT_STANDING")


def test_jongkok_pergelangan_tidak_di_bawah_lutut_belum_berdiri():
    assert _not_standing(pose(left_leg=(850, 900, 900), right_leg=(850, 900, 890)))


def test_melangkah_satu_kaki_terangkat_tetap_berdiri():
    assert not _not_standing(pose(left_leg=(600, 780, 960), right_leg=(600, 640, 760)))


def test_titik_pinggul_tak_terlihat_tidak_menghalangi():
    """Rompi menutupi pinggul: pekerja patuh tidak boleh tertahan karena titik hilang."""
    assert not _not_standing(pose(left_leg=(780, 800, 960), right_leg=(780, 800, 960), hips_conf=0.1))


def test_ambang_dari_config(monkeypatch):
    berdiri_pendek = pose(left_leg=(700, 780, 960), right_leg=(700, 780, 960))  # rasio 0,44
    assert _not_standing(berdiri_pendek)
    monkeypatch.setattr(cfg, "STANDING_MIN_THIGH_SHIN_RATIO", 0.4)
    assert not _not_standing(berdiri_pendek)


def test_kaki_terpotong_didahulukan_dari_postur():
    duduk_terpotong = pose(left_leg=(780, 800, FRAME_H - 2), right_leg=(780, 800, FRAME_H - 2))
    assert status(duduk_terpotong)[2] == "FEET_CLIPPED"


def test_postur_didahulukan_dari_kepala_terpotong():
    duduk = pose(left_leg=(780, 800, 960), right_leg=(780, 800, 960))
    duduk[kp.NOSE][kp.CONFIDENCE] = duduk[kp.LEFT_EYE][kp.CONFIDENCE] = duduk[kp.RIGHT_EYE][kp.CONFIDENCE] = 0
    assert status(duduk)[2] == "NOT_STANDING"


def test_suara_arahan_berdiri_tersedia():
    """Setiap suara arahan posisi punya teks (dibangkitkan generate_audio) dan berkas MP3 rilis."""
    for sound in POSITION_SOUNDS.values():
        assert messages.VOICE_TEXTS[sound]
        assert (cfg.AUDIO_DIR / f"{sound}.mp3").is_file(), f"jalankan python -m backend.generate_audio ({sound})"


def test_orang_duduk_mendengar_arahan_berdiri(monkeypatch):
    engine, played = AudioEngine(), []
    monkeypatch.setattr(engine, "play", lambda name, **kw: played.append(name))
    for clip in ("NOT_STANDING", "HEAD_CLIPPED", "FEET_CLIPPED", "TOO_CLOSE"):
        engine.play_step_back(clip)
    assert played == ["berdiri_tegak", "mundur_kepala", "mundur_kaki", "mundur"]
