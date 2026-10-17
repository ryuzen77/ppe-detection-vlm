"""Alur ujung ke ujung state machine gerbang: posisi, analisa, anti-spam, standby.

Alur yang diharapkan pengguna (T24): tubuh belum utuh = API terkunci; satu analisa
per sesi; keputusan terkunci sampai jalur inspeksi kosong; LED merah hanya untuk
APD tidak lengkap.
"""
import json
import time
from typing import Any

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
    base: dict[str, Any] = dict(track_id=TRACK_ID, is_inside_corridor=True, crop_img=person_crop(), conf=0.95)
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
    # Jendela diam T46 diuji di test_readiness.py; di sini alur gerbangnya
    monkeypatch.setattr(cfg, "READY_HOLD_SECONDS", 0.0)
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
    # Utama gagal dan tidak ada cadangan (T27): TIDAK ada keputusan. Lampu kuning
    # (T47; merah khusus APD kurang), tidak ada baris audit, pekerja menunggu.
    monkeypatch.setattr(cfg, "VLM_SYSTEM_RETRY_SECONDS", 0.3)
    vlm.error = RuntimeError("503 UNAVAILABLE")
    riwayat = len(state_mgr.inspection_history)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True)])

    assert _wait_for(lambda: _active()["state"] == TrackState.WAITING_SYSTEM)
    assert _active()["vlm_result"] is None, "Belum ada item yang dinilai"
    assert notifier.current_state == "YELLOW"
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

    # Pekerja berikutnya = orang lain, jadi ID pelacak lain. ID yang sama dalam
    # DECIDED_TRACK_MEMORY_SECONDS dianggap orang yang sama (T36c).
    vlm.reply = _balasan(helm=True)
    _analisa_selesai(gerbang, track_id=TRACK_ID + 1)
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


# --- Ingatan keputusan per ID pelacak (T36c) -------------------------------------------

def _jalur_kosong(gerbang):
    gerbang.update_frame_detections([])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([])
    assert _active() is None, "Sesi berakhir setelah jalur kosong"


def test_id_yang_baru_lolos_tidak_diperiksa_ulang_di_sesi_berikutnya(gerbang, vlm):
    # Orang yang lolos keluar jalur > jeda (mis. saat berjalan ke gerbang), lalu
    # terlihat lagi dengan ID sama: keputusan lolos dipakai, tanpa VLM/audit ganda.
    _analisa_selesai(gerbang)
    panggilan, riwayat, sesi = vlm.calls, len(state_mgr.inspection_history), _active()["session_id"]
    _jalur_kosong(gerbang)
    assert notifier.current_state == "OFF"

    vlm.reply = _balasan(rompi=True)  # seandainya dianalisa ulang, hasilnya akan berbeda
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 3):
        gerbang.update_frame_detections([_det(full_body=True)])
    time.sleep(0.2)

    assert _active()["session_id"] != sesi, "Sesi baru dimulai"
    assert _active()["state"] == TrackState.ANALYZED
    assert _active()["vlm_result"]["is_complete"] is True, "Keputusan lolos dipakai"
    assert vlm.calls == panggilan, "Tanpa panggilan VLM kedua"
    assert len(state_mgr.inspection_history) == riwayat, "Tanpa baris audit ganda"
    assert notifier.current_state == "GREEN", "Lampu kembali ke keputusan sebelumnya"


def test_pekerja_ditolak_yang_memperbaiki_apd_diperiksa_ulang_walau_id_sama(gerbang, vlm):
    # Temuan tinjauan (T36c): ditolak -> mundur selangkah, pakai helm, maju lagi
    # dengan ID sama. Ia harus dianalisa ulang, bukan ditolak lagi dari ingatan.
    vlm.reply = _balasan(helm=True)
    _analisa_selesai(gerbang)
    assert notifier.current_state == "RED"
    _jalur_kosong(gerbang)

    vlm.reply = _balasan()  # kini memakai helm
    riwayat = len(state_mgr.inspection_history)
    _analisa_selesai(gerbang)
    assert _active()["vlm_result"]["is_complete"] is True
    assert len(state_mgr.inspection_history) == riwayat + 1
    assert notifier.current_state == "GREEN"


def test_id_diperiksa_ulang_setelah_ingatan_kedaluwarsa(gerbang, vlm, monkeypatch):
    monkeypatch.setattr(cfg, "DECIDED_TRACK_MEMORY_SECONDS", 0.1)
    _analisa_selesai(gerbang)  # lolos -> diingat
    _jalur_kosong(gerbang)
    time.sleep(0.15)  # ingatan dihitung sejak sesi berakhir; tunggu melewatinya
    vlm.reply = _balasan(rompi=True)
    riwayat = len(state_mgr.inspection_history)

    _analisa_selesai(gerbang)
    assert _active()["vlm_result"]["is_complete"] is False
    assert len(state_mgr.inspection_history) == riwayat + 1


def test_orang_lain_setelah_sesi_tetap_diperiksa(gerbang, vlm):
    _analisa_selesai(gerbang)
    _jalur_kosong(gerbang)
    riwayat = len(state_mgr.inspection_history)
    _analisa_selesai(gerbang, track_id=TRACK_ID + 7)
    assert len(state_mgr.inspection_history) == riwayat + 1


def test_reset_operator_menghapus_ingatan_keputusan(gerbang, vlm):
    _analisa_selesai(gerbang)
    _jalur_kosong(gerbang)
    gerbang.reset_all()
    riwayat = len(state_mgr.inspection_history)
    _analisa_selesai(gerbang)
    assert len(state_mgr.inspection_history) == riwayat + 1


# --- Zona titik berdiri (T36d) ----------------------------------------------------------

@pytest.fixture
def zona(monkeypatch):
    from backend import zone as zones
    import backend.state_manager as sm
    store = zones.ZoneStore()
    store.update(enabled=True, y_min=0.70, y_max=0.85)
    monkeypatch.setattr(sm, "zone_store", store)
    return store


def test_antrean_di_belakang_zona_tidak_memulai_sesi(gerbang, zona):
    riwayat = len(state_mgr.inspection_history)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 3):
        gerbang.update_frame_detections([_det(full_body=True, foot_y=0.5)])
    time.sleep(0.2)
    assert _active() is None
    assert len(state_mgr.inspection_history) == riwayat


def test_subjek_keluar_zona_mengakhiri_sesi_walau_antrean_terlihat(gerbang, zona, vlm):
    subjek: dict[str, Any] = dict(full_body=True, track_id=TRACK_ID, foot_y=0.78)
    antrean = _det(full_body=True, track_id=TRACK_ID + 1, foot_y=0.5)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(**subjek), antrean])
    assert _wait_for(lambda: _active() is not None and _active()["state"] == TrackState.ANALYZED)
    assert _active()["track_id"] == TRACK_ID, "antrean tidak menjadi subjek"

    # Subjek berjalan ke gerbang (kaki melewati zona); antrean masih terlihat
    gerbang.update_frame_detections([_det(full_body=True, track_id=TRACK_ID, foot_y=0.97), antrean])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([_det(full_body=True, track_id=TRACK_ID, foot_y=0.97), antrean])
    assert _active() is None, "antrean di belakang zona tidak menahan sesi"

    # Orang berikutnya maju ke zona dan diperiksa
    riwayat = len(state_mgr.inspection_history)
    _analisa_selesai_zona(gerbang, TRACK_ID + 1)
    assert len(state_mgr.inspection_history) == riwayat + 1


def _analisa_selesai_zona(gerbang, track_id):
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        gerbang.update_frame_detections([_det(full_body=True, track_id=track_id, foot_y=0.78)])
    assert _wait_for(lambda: _active() is not None and _active()["state"] == TrackState.ANALYZED)


def test_kaki_subjek_tertutup_sesaat_sesi_tetap_berjalan(gerbang, zona, monkeypatch, vlm):
    # Temuan tinjauan T36d: orang lewat di depan subjek, pergelangan kaki tak
    # terlihat dan kotak tubuh berhenti di pinggang (0,5). Tanpa ingatan kaki,
    # subjek dianggap keluar zona dan sesi berakhir di tengah pemeriksaan.
    monkeypatch.setattr(cfg, "FOOT_MEMORY_SECONDS", 2.0)
    _analisa_selesai_zona(gerbang, TRACK_ID)
    sesi, panggilan = _active()["session_id"], vlm.calls

    tertutup = _det(full_body=True, track_id=TRACK_ID, foot_y=None, foot_y_box=0.5)
    gerbang.update_frame_detections([tertutup])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.1)
    gerbang.update_frame_detections([tertutup])
    assert _active() is not None and _active()["session_id"] == sesi, "sesi tidak terputus"
    assert vlm.calls == panggilan


# --- T59: poster/orang lain di koridor tidak boleh mewarisi keputusan ---------------------

POSTER_ID, NEXT_ID = 7, 99


def _poster():
    """Poster K3 bergambar orang (uji 14-10): terdeteksi stabil, tidak pernah tubuh utuh."""
    return DetectionResult(track_id=POSTER_ID, bbox=[600, 300, 700, 480], is_inside_corridor=True,
                           is_full_body=False, reason=messages.POSE_FEET_CLIPPED_EDGE,
                           crop_img=person_crop(), conf=0.88)


def _decide(gerbang, track_id):
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 1):
        gerbang.update_frame_detections([_det(full_body=True, track_id=track_id), _poster()])
    assert _wait_for(lambda: _active() and _active()["state"] == TrackState.ANALYZED)


def test_keputusan_tidak_pindah_ke_pekerja_berikutnya_lewat_poster(gerbang, vlm):
    _decide(gerbang, TRACK_ID)
    assert notifier.current_state == "GREEN" and vlm.calls == 1

    # Pekerja A pergi; poster tetap di koridor lebih lama dari jeda reset
    end = time.time() + cfg.STANDBY_RESET_DELAY_SECONDS + 0.3
    while time.time() < end:
        gerbang.update_frame_detections([_poster()])
        time.sleep(0.05)

    # Pekerja B tanpa helm datang: harus diperiksa ulang, bukan mewarisi hijau A
    vlm.reply = _balasan(helm=True)
    _decide(gerbang, NEXT_ID)
    assert vlm.calls == 2, "pekerja berikutnya tidak diperiksa: keputusan A terbawa lewat poster"
    assert notifier.current_state == "RED"


def test_poster_sejak_awal_tidak_menahan_sesi(gerbang, vlm):
    """Gerbang menyala dengan poster di koridor: sesi poster tidak boleh menghalangi pekerja."""
    for _ in range(5):
        gerbang.update_frame_detections([_poster()])
    assert _active()["track_id"] == POSTER_ID and vlm.calls == 0, "poster tidak pernah dianalisa"
    _decide(gerbang, TRACK_ID)
    assert vlm.calls == 1 and _active()["track_id"] == TRACK_ID


def test_orang_antre_di_koridor_tidak_mewarisi_keputusan(gerbang, vlm):
    """Pekerja B sudah terlihat (antre) saat A diputuskan, lalu maju setelah A pergi."""
    antre = lambda: _det(full_body=False, track_id=NEXT_ID, bbox=[480, 200, 560, 470])  # noqa: E731
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 1):
        gerbang.update_frame_detections([_det(full_body=True), antre()])
    assert _wait_for(lambda: _active()["state"] == TrackState.ANALYZED) and notifier.current_state == "GREEN"
    end = time.time() + cfg.STANDBY_RESET_DELAY_SECONDS + 0.3
    while time.time() < end:                         # A pergi, B masih di koridor
        gerbang.update_frame_detections([antre()])
        time.sleep(0.05)
    vlm.reply = _balasan(helm=True)
    for _ in range(cfg.STABLE_FRAMES_REQUIRED + 1):
        gerbang.update_frame_detections([_det(full_body=True, track_id=NEXT_ID)])
    assert _wait_for(lambda: vlm.calls == 2), "B harus diperiksa sendiri"
    assert _wait_for(lambda: notifier.current_state == "RED")


def test_id_baru_yang_sudah_terlihat_bersama_subjek_bukan_orang_yang_sama(gerbang, vlm):
    """Kotak sama persis tidak cukup: track yang pernah terlihat bersamaan subjek tidak mewarisi."""
    _decide(gerbang, TRACK_ID)
    gerbang.update_frame_detections([_det(full_body=True), _det(full_body=True, track_id=NEXT_ID)])
    gerbang.update_frame_detections([_det(full_body=True, track_id=NEXT_ID)])
    assert _active()["track_id"] == TRACK_ID, "keputusan tidak pindah ke track lain"


def test_bbox_iou():
    from backend.state_manager import bbox_iou
    assert bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert bbox_iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert abs(bbox_iou([0, 0, 10, 10], [5, 0, 15, 10]) - 1 / 3) < 1e-9
