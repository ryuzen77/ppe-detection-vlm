"""Pindai kamera sebelum ada kamera dipilih (T67).

Tombol "Pindai kemampuan" memanggil `POST /api/cameras/scan`, yang selalu meminta optimasi
kamera aktif. Tanpa kamera aktif, thread pembaca dulu melepas, mengukur, dan membuka
index None, lalu dashboard menampilkan galat palsu "Kamera index None tidak dapat dibuka"
(status SYNTHETIC) padahal operator belum memilih kamera.
"""

import pytest

from backend.video import capture


@pytest.fixture
def svc(monkeypatch):
    calls = []
    monkeypatch.setattr(
        capture.camera_manager, "probe_modes", lambda index, *a, **k: calls.append(("probe", index)) or []
    )
    monkeypatch.setattr(capture.camera_manager, "open_capture", lambda index: calls.append(("open", index)))
    service = capture.VideoCaptureService()
    service.calls = calls  # pyright: ignore[reportAttributeAccessIssue]
    return service


def test_pindai_tanpa_kamera_tetap_siaga(svc):
    assert svc.camera_status == "IDLE" and svc.camera_index is None
    svc.request_optimize()
    svc._handle_requests()
    assert svc.camera_status == "IDLE", "tanpa kamera terpilih gerbang tetap menunggu pilihan operator"
    assert svc.camera_error == "" and not svc.use_synthetic
    assert svc.calls == [], "tidak ada pengukuran / pembukaan index None"
    assert not svc._pending_optimize


def test_kamera_dilepas_sebelum_optimasi_diproses_tetap_siaga(svc):
    # Permintaan masuk saat kamera aktif, tetapi kamera dilepas sebelum thread pembaca memprosesnya
    svc.camera_index = 0
    svc.request_optimize()
    svc.camera_index = None
    svc._handle_requests()
    assert svc.camera_status == "IDLE" and svc.calls == [] and not svc._pending_optimize


def test_optimasi_kamera_aktif_tetap_berjalan(svc, monkeypatch):
    opened = []
    monkeypatch.setattr(svc, "_init_camera", lambda index, mode=None: opened.append(index) or True)
    monkeypatch.setattr(svc, "_restart_reading", lambda: None)
    monkeypatch.setattr(svc, "_resolve_device_name", lambda index: "Kamera uji")
    monkeypatch.setattr(capture.camera_mgr, "record_device_modes", lambda *a: None)
    svc.camera_index = 2
    svc.request_optimize()
    svc._handle_requests()
    assert ("probe", 2) in svc.calls and opened == [2]
