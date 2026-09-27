"""Zona titik berdiri (T36d): posisi kaki, pita zona, penyimpanan, dan API."""
import pytest
from fastapi.testclient import TestClient

from backend import runtime_settings, zone as zones
from backend.app import app
from backend.config import cfg
from backend.detector import DetectionResult
from backend.state_manager import state_mgr

FRAME_H = 1000


def _kpts(ankle_y=None, conf=0.9):
    """17 titik pose; hanya pergelangan kaki (15, 16) yang diisi."""
    pts = [[0.0, 0.0, 0.0] for _ in range(17)]
    if ankle_y is not None:
        pts[zones.LEFT_ANKLE] = [100.0, ankle_y - 10, conf]
        pts[zones.RIGHT_ANKLE] = [140.0, ankle_y + 10, conf]
    return pts


@pytest.fixture
def store(monkeypatch):
    s = zones.ZoneStore()
    monkeypatch.setattr(zones, "zone_store", s)
    return s


# --- Posisi kaki ------------------------------------------------------------------------

def test_posisi_kaki_dari_rata_rata_pergelangan():
    assert zones.foot_y(_kpts(800), [0, 100, 200, 900], FRAME_H) == pytest.approx(0.8)


def test_pergelangan_tidak_yakin_memakai_tepi_bawah_kotak():
    assert zones.foot_y(_kpts(800, conf=0.1), [0, 100, 200, 900], FRAME_H) == pytest.approx(0.9)
    assert zones.foot_y(None, [0, 100, 200, 900], FRAME_H) == pytest.approx(0.9)


def test_posisi_kaki_dibatasi_0_sampai_1():
    assert zones.foot_y(_kpts(1200), [0, 0, 10, 10], FRAME_H) == 1.0


# --- Pita zona --------------------------------------------------------------------------

def test_zona_nonaktif_menghitung_semua_orang():
    z = zones.Zone(False, 0.7, 0.85)
    assert zones.in_zone(0.1, z) and zones.in_zone(None, z)


def test_zona_aktif_hanya_pita_kaki():
    z = zones.Zone(True, 0.7, 0.85)
    assert zones.in_zone(0.75, z)
    assert not zones.in_zone(0.5, z), "antrean di belakang zona"
    assert not zones.in_zone(0.95, z), "terlalu dekat ke gerbang"
    assert not zones.in_zone(None, z)


@pytest.mark.parametrize("lo,hi", [(0.8, 0.7), (-0.1, 0.5), (0.5, 1.2), (0.7, 0.7)])
def test_batas_tidak_sah_ditolak(lo, hi):
    with pytest.raises(ValueError):
        zones.validated(lo, hi)


def test_pita_terlalu_sempit_ditolak():
    with pytest.raises(ValueError):
        zones.validated(0.70, 0.70 + cfg.ZONE_MIN_HEIGHT / 2)


def test_kalibrasi_mengaktifkan_pita_di_sekitar_kaki():
    z = zones.calibrated(0.78)
    assert z.enabled and z.source == zones.SOURCE_CALIBRATED
    assert z.y_min == pytest.approx(0.78 - cfg.ZONE_CALIBRATE_MARGIN)
    assert z.y_max == pytest.approx(0.78 + cfg.ZONE_CALIBRATE_MARGIN)


# --- Penyimpanan ------------------------------------------------------------------------

def test_bawaan_nonaktif(store):
    assert store.get().enabled is False
    assert store.get().source == zones.SOURCE_DEFAULT


def test_ubah_manual_tersimpan_dan_termuat_ulang(store):
    store.update(enabled=True, y_min=0.6, y_max=0.8)
    fresh = zones.ZoneStore()
    fresh.load()
    assert fresh.get() == zones.Zone(True, 0.6, 0.8, zones.SOURCE_MANUAL)


def test_berkas_rusak_kembali_ke_bawaan(store):
    runtime_settings.update(zones.SETTINGS_KEY, {"y_min": "x"})
    fresh = zones.ZoneStore()
    fresh.load()
    assert fresh.get() == zones.default_zone()


# --- API --------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    s = zones.ZoneStore()
    import backend.api.routes_zone as routes
    import backend.state_manager as sm
    monkeypatch.setattr(routes, "zone_store", s)
    monkeypatch.setattr(sm, "zone_store", s)
    monkeypatch.setattr(state_mgr, "latest_detections", [])
    return TestClient(app), s


def _det(foot, bbox=(400, 100, 600, 900), corridor=True):
    return DetectionResult(track_id=5, bbox=list(bbox), is_full_body=True, reason="",
                           is_inside_corridor=corridor, foot_y=foot)


def test_api_baca_dan_ubah(client):
    c, s = client
    assert c.get("/api/config/zone").json()["enabled"] is False
    r = c.post("/api/config/zone", json={"enabled": True, "y_min": 0.6, "y_max": 0.8})
    assert r.status_code == 200
    assert r.json() == {"enabled": True, "y_min": 0.6, "y_max": 0.8, "source": zones.SOURCE_MANUAL}


def test_api_batas_tidak_sah_400(client):
    c, s = client
    assert c.post("/api/config/zone", json={"y_min": 0.9, "y_max": 0.5}).status_code == 400
    assert c.post("/api/config/zone", json=[1, 2]).status_code == 400
    assert s.get() == zones.default_zone(), "penolakan tidak mengubah zona"


def test_api_kalibrasi_tanpa_orang_409(client):
    c, _ = client
    r = c.post("/api/config/zone/calibrate")
    assert r.status_code == 409


def test_api_kalibrasi_kaki_tidak_terlihat_409(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(state_mgr, "latest_detections", [_det(None)])
    assert c.post("/api/config/zone/calibrate").status_code == 409


def test_api_kalibrasi_dari_orang_terdekat_di_lorong(client, monkeypatch):
    c, s = client
    monkeypatch.setattr(state_mgr, "latest_detections", [
        _det(0.5, bbox=(400, 300, 500, 600)),               # antrean, lebih kecil
        _det(0.8, bbox=(400, 100, 600, 900)),               # berdiri di titik
        _det(0.95, bbox=(0, 0, 900, 999), corridor=False),  # di luar lorong
    ])
    r = c.post("/api/config/zone/calibrate")
    assert r.status_code == 200
    assert r.json()["enabled"] is True and r.json()["source"] == zones.SOURCE_CALIBRATED
    assert r.json()["y_min"] == pytest.approx(0.8 - cfg.ZONE_CALIBRATE_MARGIN)


def test_telemetri_memuat_zona_dan_posisi_kaki(client, monkeypatch):
    c, s = client
    s.update(enabled=True, y_min=0.7, y_max=0.85)
    monkeypatch.setattr(state_mgr, "latest_detections", [_det(0.8), _det(0.5)])
    t = state_mgr.get_telemetry()
    assert t["zone"] == {"enabled": True, "y_min": 0.7, "y_max": 0.85}
    assert [d["in_zone"] for d in t["detections"]] == [True, False]
    assert t["detections"][0]["foot_y"] == 0.8
