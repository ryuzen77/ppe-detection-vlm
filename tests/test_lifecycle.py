"""Alur ujung ke ujung state machine gerbang: posisi, analisa, anti-spam, standby.

Alur yang diharapkan pengguna (T24): tubuh belum utuh = API terkunci; satu analisa
per sesi; keputusan terkunci sampai jalur inspeksi kosong; LED merah hanya untuk
APD tidak lengkap.
"""
import json
import time

import pytest

from backend.config import cfg
from backend.detector import DetectionResult
from backend.state_manager import state_mgr, TrackState
from backend.audio_engine import audio_player
from backend.notifier import notifier
from backend import messages
from backend.vlm_providers import VLMProvider

from helpers import person_crop

TRACK_ID = 42


def _balasan(**kurang):
    """Jawaban VLM tiruan; kurang=dict item yang tidak terdeteksi, mis. rompi=True."""
    items = {
        "helm": {"detected": not kurang.get("helm")},
        "rompi": {"detected": not kurang.get("rompi"), "is_valid_color": not kurang.get("rompi"), "color": "orange"},
        "celana": {"detected": True},
        "sepatu": {"detected": True, "is_closed_shoes": True},
    }
    return json.dumps({"items": items, "missing_items": [], "notes": "tiruan"})


class VLMTiruan(VLMProvider):
    """VLM utama tiruan: jawabannya diatur tes, tanpa jaringan dan tanpa kuota."""
    name = "tiruan"

    def __init__(self):
        super().__init__("model-tiruan")
        self.reply = _balasan()
        self.error = None
        self.calls = 0

    def generate(self, image_jpeg, system_prompt, user_prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply

    def ping(self):
        return "PONG"


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
def vlm(monkeypatch):
    """VLM utama tiruan tanpa cadangan, dipasang pada analyzer global gerbang."""
    from backend.vlm_analyzer import vlm_analyzer, VLMEngine
    tiruan = VLMTiruan()
    engine = VLMEngine("utama", "gemini", "model-tiruan", api_key="kunci-uji")
    engine.provider, engine.min_interval = tiruan, 0.0
    monkeypatch.setattr(vlm_analyzer, "primary", engine)
    monkeypatch.setattr(vlm_analyzer, "backup", None)
    monkeypatch.setattr(vlm_analyzer, "primary_failures", 0)
    monkeypatch.setattr(vlm_analyzer, "primary_down_since", None)
    yield tiruan
    engine.executor.shutdown(wait=False)


@pytest.fixture
def gerbang(monkeypatch, catalog_defaults, vlm):
    """State machine bersih, VLM tiruan, audio senyap, dan jeda standby dipersingkat."""
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
    # LED merah khusus APD tidak lengkap; arahan posisi tidak menyalakannya
    assert notifier.current_state == "OFF"

    # 2. Mundur hingga seluruh tubuh terlihat; analisa terpicu tepat saat stabil
    for i in range(1, cfg.STABLE_FRAMES_REQUIRED + 1):
        gerbang.update_frame_detections([_det(full_body=True)])
    telemetry = state_mgr.get_telemetry()
    assert telemetry["stable_frames_required"] == cfg.STABLE_FRAMES_REQUIRED

    # 3. Analisa selesai: APD lengkap, lampu hijau, tercatat di riwayat
    assert _wait_for(lambda: _active()["state"] == TrackState.ANALYZED), "Analisa tidak selesai dalam 5 detik"
    hasil = _active()["vlm_result"]
    assert hasil["is_complete"] is True
    assert hasil["inference_source"] == "VLM_LIVE:gemini/model-tiruan", "Tes tidak boleh memanggil Gemini"
    assert hasil["decided_by"] == "utama"
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
    assert _active() is None, "Sesi berakhir setelah jalur kosong"


def test_apd_kurang_menutup_gerbang(gerbang, vlm):
    vlm.reply = _balasan(rompi=True)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True)])

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
    assert _active() is None, "Orang di luar jalur tidak memulai sesi"


def test_vlm_tidak_menjawab_pekerja_diminta_menunggu_lalu_diperiksa_ulang(gerbang, vlm, monkeypatch):
    # Utama gagal dan tidak ada cadangan (T27): TIDAK ada keputusan. Lampu tidak
    # merah (merah khusus APD kurang), tidak ada baris audit, pekerja menunggu.
    monkeypatch.setattr(cfg, "VLM_SYSTEM_RETRY_SECONDS", 0.3)
    vlm.error = RuntimeError("503 UNAVAILABLE")
    riwayat = len(state_mgr.inspection_history)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True)])

    assert _wait_for(lambda: _active()["state"] == TrackState.WAITING_SYSTEM)
    assert _active()["vlm_result"] is None, "Belum ada item yang dinilai"
    assert notifier.current_state == "OFF"
    assert notifier.message == messages.LIGHT_SYSTEM_WAIT
    assert len(state_mgr.inspection_history) == riwayat, "Gangguan tidak dicatat sebagai inspeksi"

    # Sebelum jeda habis tidak ada panggilan baru walau pekerja tetap berdiri
    panggilan = vlm.calls
    gerbang.update_frame_detections([_det(full_body=True)])
    assert vlm.calls == panggilan and _active()["state"] == TrackState.WAITING_SYSTEM

    # VLM pulih; setelah jeda, orang yang sama diperiksa ulang otomatis
    vlm.error = None
    time.sleep(0.35)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 1):
        gerbang.update_frame_detections([_det(full_body=True)])
    assert _wait_for(lambda: _active()["state"] == TrackState.ANALYZED)
    assert _active()["vlm_result"]["is_complete"] is True
    assert notifier.current_state == "GREEN"
    assert len(state_mgr.inspection_history) == riwayat + 1


def test_pekerja_pergi_saat_menunggu_sistem_gerbang_kembali_standby(gerbang, vlm):
    vlm.error = RuntimeError("503 UNAVAILABLE")
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True)])
    assert _wait_for(lambda: _active()["state"] == TrackState.WAITING_SYSTEM)

    gerbang.update_frame_detections([])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([])
    assert _active() is None
    assert notifier.current_state == "OFF" and notifier.message == messages.LIGHT_IDLE


# --- Sesi gerbang (T24) ------------------------------------------------------------

def _analisa_selesai(gerbang, crop=None, track_id=TRACK_ID):
    extra = {"crop_img": crop} if crop is not None else {}
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True, track_id=track_id, **extra)])
    assert _wait_for(lambda: _active() is not None and _active()["state"] == TrackState.ANALYZED)


def test_pergantian_id_pelacak_di_tengah_sesi_tidak_menganalisa_ulang(gerbang, vlm):
    # Pekerja ditolak (tanpa rompi), lalu pelacak memberinya ID baru tanpa ia
    # meninggalkan jalur. Ia tidak boleh diperiksa ulang lalu tiba-tiba lolos.
    vlm.reply = _balasan(rompi=True)
    _analisa_selesai(gerbang)
    vlm.reply = _balasan()  # seandainya dianalisa ulang, hasilnya akan berbeda
    riwayat = len(state_mgr.inspection_history)
    sesi = _active()["session_id"]
    assert notifier.current_state == "RED"

    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 5):
        gerbang.update_frame_detections([_det(full_body=True, track_id=TRACK_ID + 1)])
    time.sleep(0.2)

    assert len(state_mgr.inspection_history) == riwayat, "Tidak boleh ada analisa kedua"
    assert _active()["session_id"] == sesi
    assert _active()["track_id"] == TRACK_ID + 1
    assert notifier.current_state == "RED", "Keputusan tetap terkunci"


def test_hilang_sesaat_kurang_dari_jeda_tetap_satu_sesi(gerbang):
    _analisa_selesai(gerbang)
    riwayat = len(state_mgr.inspection_history)
    sesi = _active()["session_id"]

    gerbang.update_frame_detections([])            # tertutup sesaat
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS / 3)
    gerbang.update_frame_detections([])
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 2):
        gerbang.update_frame_detections([_det(full_body=True)])
    time.sleep(0.1)

    assert _active()["session_id"] == sesi
    assert len(state_mgr.inspection_history) == riwayat
    assert notifier.current_state == "GREEN"


def test_setelah_jalur_kosong_pekerja_berikutnya_diperiksa_dari_awal(gerbang, vlm):
    _analisa_selesai(gerbang)
    sesi_pertama = _active()["session_id"]
    riwayat = len(state_mgr.inspection_history)

    gerbang.update_frame_detections([])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([])
    assert _active() is None and notifier.current_state == "OFF"

    vlm.reply = _balasan(helm=True)
    _analisa_selesai(gerbang)
    assert _active()["session_id"] != sesi_pertama
    assert len(state_mgr.inspection_history) == riwayat + 1
    assert notifier.current_state == "RED"


def test_orang_lewat_di_luar_jalur_tidak_menahan_reset(gerbang):
    _analisa_selesai(gerbang)
    orang_lewat = _det(full_body=True, track_id=77, is_inside_corridor=False)
    gerbang.update_frame_detections([orang_lewat])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([orang_lewat])
    assert _active() is None
    assert notifier.current_state == "OFF"


def test_hasil_yang_tiba_setelah_pekerja_pergi_tidak_menyalakan_lampu(gerbang, monkeypatch):
    from backend.vlm_analyzer import vlm_analyzer
    asli = vlm_analyzer.analyze_person

    def lambat(crop):
        time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.4)
        return asli(crop)

    monkeypatch.setattr(vlm_analyzer, "analyze_person", lambat)
    riwayat = len(state_mgr.inspection_history)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True)])

    # Pekerja pergi sebelum hasil tiba; sesi berakhir
    gerbang.update_frame_detections([])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([])
    assert _active() is None

    # Hasil tetap tercatat di audit, tetapi lampu tidak ditujukan ke siapa pun
    assert _wait_for(lambda: len(state_mgr.inspection_history) == riwayat + 1)
    time.sleep(0.1)
    assert notifier.current_state == "OFF"
