"""Ketangguhan kamera (T45): tertutup, membeku, terputus — gerbang berhenti memeriksa, lampu kuning."""
import cv2
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


# Pemandangan bertekstur tetap (lantai, rak, dinding berpola): pemandangan nyata
# punya banyak tepi (uji C920 13-10: porsi tepi ~0,09), bidang rata tidak.
TEXTURE = cv2.resize(RNG.integers(40, 200, (27, 48), dtype=np.uint8), (864, 480),
                     interpolation=cv2.INTER_NEAREST)


def scene():
    """Pemandangan diam dengan derau sensor: tiap panggilan sedikit berbeda, seperti kamera hidup."""
    base = np.repeat(TEXTURE[:, :, None], 3, axis=2)
    noise = RNG.integers(-3, 4, base.shape, dtype=np.int16)
    return np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def blurred(frame, kernel=61):
    """Lensa berembun/diplastik: pemandangan masih terang & bervariasi, tetapi tanpa detail."""
    return cv2.GaussianBlur(frame, (kernel, kernel), 0)


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


def test_lensa_buram_dianggap_tertutup_walau_terang():
    """T57: buram terang lolos dari ambang gelap/seragam T45, ditangkap lewat ketajaman."""
    frame = blurred(scene())
    gray = ch.detail_gray(frame)
    assert not ch.is_dark_or_uniform(gray), "prasyarat: kasus ini memang lolos dari aturan T45"
    assert ch.is_blocked(frame)


def test_pemandangan_jelas_punya_detail_di_atas_ambang():
    sharpness, edges = ch.image_detail(ch.detail_gray(scene()))
    assert sharpness >= cfg.CAMERA_MIN_SHARPNESS and edges >= cfg.CAMERA_MIN_EDGE_RATIO


def test_setengah_lensa_tertutup_tidak_dianggap_tertutup():
    """Uji C920 13-10: setengah tertutup masih ketajaman ~224 — orang tetap terlihat, jangan alarm."""
    frame = scene()
    frame[:, : frame.shape[1] // 2] = blurred(frame)[:, : frame.shape[1] // 2]
    assert not ch.is_blocked(frame)


def test_dinding_polos_bertepi_tidak_dianggap_buram(monkeypatch):
    """Dua syarat sekaligus: ketajaman rendah saja tidak cukup bila tepi masih ada."""
    monkeypatch.setattr(ch, "image_detail", lambda gray: (cfg.CAMERA_MIN_SHARPNESS - 1, cfg.CAMERA_MIN_EDGE_RATIO))
    assert not ch.is_blurred(ch.detail_gray(scene()))


def test_buram_harus_bertahan_sebelum_gangguan():
    h = ch.CameraHealth()
    n = int(cfg.CAMERA_BLOCKED_SECONDS * 10)
    assert feed(h, [blurred(scene()) for _ in range(n)]) is None
    assert h.update(blurred(scene()), cfg.CAMERA_BLOCKED_SECONDS + 0.1) == ch.FAULT_BLOCKED


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
    monkeypatch.setattr(state_mgr, "camera_fault_sound_at", {})
    state_mgr.set_camera_fault(None)
    state_mgr.reset_all()
    yield played
    state_mgr.set_camera_fault(None)
    state_mgr.reset_all()


def _det():
    return DetectionResult(track_id=1, bbox=[470, 50, 810, 660], is_full_body=True, reason=messages.POSE_OK,
                           is_inside_corridor=True, crop_img=person_crop(), conf=0.9, keypoints=[[0, 0, 0.9]] * 17)


@pytest.mark.parametrize("fault", ["blocked", "system"])   # system = pengolah gambar galat (T77b)
def test_gangguan_membatalkan_hijau_dan_menyalakan_kuning(gate, fault):
    """Risiko utama: hijau tertahan untuk pekerja berikutnya saat kamera / pengolah gambar bermasalah."""
    notifier.set_complete()
    state_mgr.update_frame_detections([_det()])
    assert state_mgr.session is not None
    state_mgr.set_camera_fault(fault)
    assert state_mgr.session is None
    assert notifier.current_state == "YELLOW" and notifier.message == messages.LIGHT_CAMERA_FAULT[fault]


def test_suara_gangguan_hanya_sekali_saat_mulai(gate):
    for fault in ("lost", "lost", "frozen", "lost"):
        state_mgr.set_camera_fault(fault)
    assert gate == ["kamera_terputus"], "membeku & terputus = satu jenis suara"


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
    for sound in set(messages.CAMERA_FAULT_SOUND.values()):
        assert sound in messages.VOICE_TEXTS
        assert (cfg.AUDIO_DIR / f"{sound}.mp3").exists()


# --- Regresi uji fisik 06-10 (T45b) --------------------------------------------------------

def black():
    """Lensa kamera laptop tertutup rapat: hitam pekat, TANPA derau (frame identik)."""
    return np.zeros((480, 864, 3), np.uint8)


def test_lensa_tertutup_rapat_bukan_membeku(cam):
    """Dulu: hitam pekat identik -> 'membeku' -> kamera dibuka ulang tiap ±7 dtk."""
    fault = None
    for i in range(10 * 30):                       # ditutup 10 dtk, 30 FPS
        fault = cam._camera_fault(black(), i / 30)
    assert fault == ch.FAULT_BLOCKED
    assert not cam._device_missing, "tidak boleh membuka ulang kamera"


def test_reaksi_tertutup_cepat():
    h = ch.CameraHealth()
    assert cfg.CAMERA_BLOCKED_SECONDS <= 1.5
    assert feed(h, [black()] * int(cfg.CAMERA_BLOCKED_SECONDS * 10 + 2)) == ch.FAULT_BLOCKED


def test_membeku_tetap_berlaku_selama_dibuka_ulang(cam):
    frozen = scene()
    for i in range(int(cfg.CAMERA_FROZEN_SECONDS * 10) + 2):
        cam._camera_fault(frozen, i / 10)
    cam._device_missing = False                    # thread pembaca menangani penanda
    cam.camera_status = "OPENING"
    assert cam._camera_fault(scene(), 10.0) == ch.FAULT_FROZEN, "sedang dibuka ulang: belum selesai"
    cam.camera_status, cam.camera_error = "OK", ""
    assert cam._camera_fault(scene(), 10.1) == ch.FAULT_FROZEN, "frame sehat pertama belum cukup"
    assert cam._camera_fault(scene(), 10.1 + cfg.CAMERA_HEALTHY_SECONDS) is None


def test_reset_gerbang_tidak_menghapus_gangguan(gate):
    state_mgr.set_camera_fault("frozen")
    state_mgr.reset_all()                          # mis. setelah kamera dibuka ulang
    assert state_mgr.camera_fault == "frozen" and notifier.current_state == "YELLOW"


def test_suara_tidak_diulang_saat_gangguan_putus_sambung(gate):
    for _ in range(5):                             # pola log 06-10: mulai, selesai, mulai lagi...
        state_mgr.set_camera_fault("blocked")
        state_mgr.set_camera_fault(None)
    assert gate == ["kamera_terhalang"]


def test_terhalang_lalu_dicabut_tetap_diumumkan(gate):
    """Uji fisik 06-10: lensa ditutup lalu kamera dicabut <30 dtk -> dulu tanpa suara."""
    state_mgr.set_camera_fault("blocked")
    state_mgr.set_camera_fault("lost")
    assert gate == ["kamera_terhalang", "kamera_terputus"]


def test_terputus_dan_terhalang_beda_pesan_lampu(gate):
    state_mgr.set_camera_fault("lost")
    lost_msg = notifier.message
    state_mgr.set_camera_fault("blocked")
    assert notifier.message != lost_msg and notifier.current_state == "YELLOW"


def test_log_menunggu_kamera_berkala(cam, monkeypatch, caplog):
    import logging
    from backend import camera_manager
    monkeypatch.setattr(camera_manager, "list_device_names", lambda: ["Integrated Camera"])
    cam.camera_name = "HD Pro Webcam C920"
    with caplog.at_level(logging.WARNING):
        for second in range(25):
            cam._log_waiting(1000.0 + second)
    lines = [r.message for r in caplog.records if "Masih menunggu" in r.message]
    assert len(lines) == 3, "tiap CAMERA_WAITING_LOG_SECONDS, bukan tiap detik"
    assert "HD Pro Webcam C920" in lines[-1] and "Integrated Camera" in lines[-1] and "20 dtk" in lines[-1]
