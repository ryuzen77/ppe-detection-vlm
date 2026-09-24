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
    # Nama perangkat tidak bisa dibaca (OS tanpa pembaca nama, atau pembacanya gagal)
    perangkat([])
    assert resolve_saved_index({"index": 3, "name": "USB Cam"}) == 3


# --- linux_device_names (sysfs palsu) ---------------------------------------

def node(root, n, name=None, index=None):
    d = root / f"video{n}"
    d.mkdir(parents=True)
    if name is not None:
        (d / "name").write_text(name + "\n", encoding="utf-8")
    if index is not None:
        (d / "index").write_text(f"{index}\n")


def test_linux_nama_dibaca_sesuai_nomor_node(tmp_path):
    node(tmp_path, 0, "Integrated Camera", 0)
    node(tmp_path, 2, "USB Cam", 0)
    node(tmp_path, 10, "Cam Sepuluh", 0)  # urutan numerik, bukan leksikal
    names = camera_manager.linux_device_names(tmp_path)
    assert names[0] == "Integrated Camera"
    assert names[2] == "USB Cam"
    assert names[10] == "Cam Sepuluh"
    assert len(names) == 11


def test_linux_node_sekunder_diberi_label_berbeda(tmp_path):
    # Satu kamera USB = node video (index 0) + node metadata (index 1). Nama
    # keduanya identik di sysfs; tanpa pembeda, pencarian lewat nama bisa
    # tertukar ke node metadata yang tidak bisa merekam.
    node(tmp_path, 0, "USB Cam", 0)
    node(tmp_path, 1, "USB Cam", 1)
    names = camera_manager.linux_device_names(tmp_path)
    assert names == ["USB Cam", "USB Cam (node 1)"]
    assert names.index("USB Cam") == 0


def test_linux_nomor_kosong_diisi_label_generik_agar_posisi_tetap(tmp_path):
    node(tmp_path, 1, "USB Cam", 0)
    assert camera_manager.linux_device_names(tmp_path) == ["Kamera 0", "USB Cam"]


def test_linux_berkas_nama_hilang_memakai_label_generik(tmp_path):
    node(tmp_path, 0)
    assert camera_manager.linux_device_names(tmp_path) == ["Kamera 0"]


def test_linux_entri_selain_video_diabaikan(tmp_path):
    (tmp_path / "v4l-subdev0").mkdir()
    (tmp_path / "videoX").mkdir()
    node(tmp_path, 0, "Cam", 0)
    assert camera_manager.linux_device_names(tmp_path) == ["Cam"]


def test_linux_tanpa_sysfs_atau_tanpa_kamera_daftar_kosong(tmp_path):
    assert camera_manager.linux_device_names(tmp_path / "tidak-ada") == []
    assert camera_manager.linux_device_names(tmp_path) == []


def test_pembaca_nama_gagal_tidak_menjatuhkan_daftar(monkeypatch):
    def rusak(*a, **k):
        raise PermissionError("ditolak")
    monkeypatch.setattr(camera_manager, "linux_device_names", rusak)
    monkeypatch.setattr(camera_manager.sys, "platform", "linux")
    assert camera_manager.list_device_names() == []


# --- open_capture ------------------------------------------------------------

class CapPalsu:
    def __init__(self, index, backend=None, opened=True):
        self.index, self.backend, self.opened, self.released = index, backend, opened, False

    def isOpened(self):
        return self.opened

    def release(self):
        self.released = True


def pasang_cv2(monkeypatch, backend_berhasil):
    dibuat = []

    def video_capture(index, backend=None):
        cap = CapPalsu(index, backend, opened=backend_berhasil or backend is None)
        dibuat.append(cap)
        return cap
    monkeypatch.setattr(camera_manager.cv2, "VideoCapture", video_capture)
    monkeypatch.setattr(camera_manager, "CAPTURE_BACKEND", camera_manager.cv2.CAP_V4L2)
    return dibuat


def test_open_capture_memakai_backend_os(monkeypatch):
    dibuat = pasang_cv2(monkeypatch, backend_berhasil=True)
    cap = camera_manager.open_capture(2)
    assert len(dibuat) == 1
    assert cap.backend == camera_manager.cv2.CAP_V4L2 and cap.index == 2


def test_open_capture_jatuh_ke_backend_bawaan_bila_gagal(monkeypatch):
    dibuat = pasang_cv2(monkeypatch, backend_berhasil=False)
    cap = camera_manager.open_capture(1)
    assert len(dibuat) == 2
    assert dibuat[0].released  # percobaan pertama dilepas, tidak bocor
    assert cap.backend is None and cap.isOpened()
