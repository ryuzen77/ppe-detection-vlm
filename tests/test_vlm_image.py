"""T86: gambar VLM = tubuh utuh + panel perbesaran kepala & tangan dari crop resolusi asli."""

import cv2
import numpy as np
import pytest

from backend import pose_keypoints as kp
from backend import vlm_image
from backend.config import cfg

CONF = 0.9


def _keypoints(**points):
    """17 titik COCO tak yakin, kecuali yang diberikan: nama=(x, y)."""
    kps = [[0.0, 0.0, 0.0] for _ in range(17)]
    for name, (x, y) in points.items():
        kps[getattr(kp, name.upper())] = [float(x), float(y), CONF]
    return kps


def _crop(h=1000, w=360):
    """Crop bergradien supaya setiap potongan berbeda isinya."""
    ys, xs = np.mgrid[0:h, 0:w]
    return np.dstack([(xs % 256), (ys % 256), ((xs + ys) % 256)]).astype(np.uint8)


def test_jendela_crop_sama_dengan_rumus_detector_lama():
    box, (fh, fw) = (400, 100, 760, 1000), (1080, 1920)
    my, mx = int(900 * cfg.CROP_MARGIN_Y_RATIO), int(360 * cfg.CROP_MARGIN_X_RATIO)
    assert vlm_image.crop_window(fh, fw, box) == (400 - mx, 100 - my, 760 + mx, 1000 + my)
    assert vlm_image.crop_window(fh, fw, (0, 0, 100, 1080)) == (0, 0, 100 + int(100 * cfg.CROP_MARGIN_X_RATIO), 1080)


def test_titik_pose_digeser_ke_koordinat_crop():
    shifted = vlm_image.to_crop_coords([[500.0, 300.0, 0.8]], (400, 250, 900, 1100))
    assert shifted == [[100.0, 50.0, 0.8]]
    assert vlm_image.to_crop_coords(None, (0, 0, 1, 1)) is None


def test_kotak_kepala_di_sekitar_titik_wajah_yang_yakin():
    crop = _crop()
    side = int(1000 * cfg.VLM_ZOOM_HEAD_RATIO)
    box = vlm_image.head_box(_keypoints(nose=(180, 120), left_eye=(170, 110), right_eye=(190, 110)), crop.shape)
    assert box is not None
    x0, y0, x1, y1 = box
    assert abs((x0 + x1) / 2 - 180) <= 1 and abs((y0 + y1) / 2 - 113) <= 1
    assert abs((x1 - x0) - side) <= 1
    assert vlm_image.head_box(_keypoints(), crop.shape) is None, "tanpa titik yakin tidak menebak"


def test_kotak_tangan_digeser_ke_arah_jari_dan_urut_kiri_ke_kanan():
    shape = _crop().shape
    kps = _keypoints(left_wrist=(300, 500), left_elbow=(300, 400), right_wrist=(60, 520))
    first, second = vlm_image.hand_boxes(kps, shape)
    assert first is not None and first[0] < 100, "tangan di kiri gambar lebih dulu"
    assert second is not None
    left_center_y = (second[1] + second[3]) / 2
    assert left_center_y == pytest.approx(500 + 100 * cfg.VLM_ZOOM_HAND_REACH, abs=1), "searah lengan bawah"
    one_hand = vlm_image.hand_boxes(_keypoints(right_wrist=(60, 520)), shape)
    assert one_hand[0] is not None and one_hand[1] is None


def test_gambar_gabungan_panel_dari_resolusi_asli(monkeypatch):
    monkeypatch.setattr(cfg, "VLM_IMAGE_MAX_SIZE", 640)
    monkeypatch.setattr(cfg, "VLM_ZOOM_PANEL_WIDTH", 320)
    crop = _crop()
    kps = _keypoints(nose=(180, 120), left_wrist=(300, 500), right_wrist=(60, 520))
    img = vlm_image.compose(crop, kps)
    body_w = int(360 * 640 / 1000)
    assert img.shape == (640, body_w + 320, 3)
    assert np.array_equal(img[:640, :body_w], vlm_image.fit_body(crop))
    head = vlm_image.head_box(kps, crop.shape)
    assert head is not None
    x0, y0, x1, y1 = head
    expected_head = cv2.resize(crop[y0:y1, x0:x1], (320, 320), interpolation=cv2.INTER_CUBIC)
    assert np.array_equal(img[:320, body_w:], expected_head), "kepala dari crop asli, bukan dari tubuh kecil"


def test_panel_tanpa_titik_yakin_abu_abu_polos():
    img = vlm_image.compose(_crop(), _keypoints())
    body_w = vlm_image.fit_body(_crop()).shape[1]
    assert (img[:, body_w:] == np.array(cfg.VLM_ZOOM_FILL_BGR, np.uint8)).all()


@pytest.mark.parametrize("hands", [False, True])
def test_crop_kecil_tidak_diperbesar_dan_kanvas_cukup_tinggi(monkeypatch, hands):
    monkeypatch.setattr(cfg, "VLM_ZOOM_HAND_PANELS", hands)
    crop = _crop(h=300, w=120)
    img = vlm_image.compose(crop, None)
    side = cfg.VLM_ZOOM_PANEL_WIDTH
    assert img.shape[0] == side + (side // 2 if hands else 0)
    assert np.array_equal(img[:300, :120], crop)


def test_panel_tangan_mati_bawaan_tidak_memperbesar_tangan():
    """Validasi lokal 21-10: helm yang dipegang & kaos kuning diperbesar di panel tangan lalu dikira dipakai."""
    assert cfg.VLM_ZOOM_HAND_PANELS is False
    crop = _crop()
    img = vlm_image.compose(crop, _keypoints(nose=(180, 120), left_wrist=(300, 500), right_wrist=(60, 520)))
    assert img.shape[0] == vlm_image.fit_body(crop).shape[0], "tanpa baris panel tangan di bawah kepala"
