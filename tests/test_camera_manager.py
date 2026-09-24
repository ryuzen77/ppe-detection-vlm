"""Pemilihan mode kamera dan pelacakan kamera tersimpan lewat namanya."""
import pytest

from backend import camera_manager
from backend.camera_manager import CameraMode, pick_best_mode, resolve_saved_index
from backend.config import cfg


def mode(w, h, fps):
    return CameraMode(width=w, height=h, fps=fps, fourcc="MJPG")


# --- pick_best_mode ---------------------------------------------------------

def test_tidak_ada_mode_menghasilkan_none():
    assert pick_best_mode([]) is None


def test_kelancaran_mengalahkan_rasio_16_9():
    # Kasus nyata kamera USB penguji: 16:9 hanya 7 FPS, 4:3 mencapai 25 FPS.
    # Rasio adalah preferensi, bukan syarat; video 7 FPS tersendat parah.
    lambat_16_9 = mode(1280, 720, 7.0)
    lancar_4_3 = mode(640, 480, 25.0)
    assert pick_best_mode([lambat_16_9, lancar_4_3]) == lancar_4_3


def test_di_antara_mode_lancar_rasio_16_9_diutamakan():
    lancar_4_3_tinggi = mode(1280, 960, 30.0)
    lancar_16_9 = mode(1280, 720, 30.0)
    assert pick_best_mode([lancar_4_3_tinggi, lancar_16_9]) == lancar_16_9


def test_di_antara_mode_lancar_16_9_resolusi_tertinggi_dipilih():
    kecil = mode(848, 480, 30.0)
    besar = mode(1280, 720, 30.0)
    assert pick_best_mode([kecil, besar]) == besar


def test_tanpa_mode_lancar_yang_tercepat_dipilih():
    target = cfg.CAMERA_TARGET_FPS
    a = mode(1280, 720, target - 10)
    b = mode(640, 480, target - 2)
    assert pick_best_mode([a, b]) == b


def test_semua_di_bawah_resolusi_minimum_tetap_memilih_yang_tercepat():
    rendah = cfg.CAMERA_MIN_HEIGHT - 100
    a = mode(320, rendah, 15.0)
    b = mode(320, rendah, 30.0)
    assert pick_best_mode([a, b]) == b


# --- resolve_saved_index ----------------------------------------------------

@pytest.fixture
def perangkat(monkeypatch):
    """Mengganti daftar perangkat OS dengan daftar yang ditentukan tes."""
    def pasang(names):
        monkeypatch.setattr(camera_manager, "list_device_names", lambda: list(names))
    return pasang


def test_indeks_dan_nama_masih_cocok(perangkat):
    perangkat(["Integrated Camera", "USB Cam"])
    assert resolve_saved_index({"index": 1, "name": "USB Cam"}) == 1


def test_kamera_berpindah_indeks_diikuti_lewat_nama(perangkat):
    # Mencolokkan kamera USB menggeser OBS Virtual Camera dari indeks 1 ke 2
    perangkat(["Integrated Camera", "USB Cam", "OBS Virtual Camera"])
    assert resolve_saved_index({"index": 1, "name": "OBS Virtual Camera"}) == 2


def test_kamera_dicabut_tidak_jatuh_ke_perangkat_lain_di_indeks_lama(perangkat):
    # Indeks 1 kini ditempati perangkat lain; membukanya berarti kamera yang salah
    perangkat(["Integrated Camera", "OBS Virtual Camera"])
    assert resolve_saved_index({"index": 1, "name": "USB Cam"}) is None


def test_berkas_lama_tanpa_nama_memakai_indeks(perangkat):
    perangkat(["Integrated Camera"])
    assert resolve_saved_index({"index": 0}) == 0


def test_daftar_perangkat_tidak_tersedia_memakai_indeks(perangkat):
    # Di luar Windows nama perangkat tidak bisa dibaca
    perangkat([])
    assert resolve_saved_index({"index": 3, "name": "USB Cam"}) == 3
