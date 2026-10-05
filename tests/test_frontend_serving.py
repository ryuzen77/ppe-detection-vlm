"""UI baru (web/dist) di "/". UI lama telah dihapus."""
import re

import pytest
from fastapi.testclient import TestClient

from backend.app import app, web_dist_dir

butuh_build = pytest.mark.skipif(not web_dist_dir.exists(), reason="web/dist belum dibangun (npm run build)")


@pytest.fixture
def klien():
    # Tanpa lifespan: kamera, model, dan VLM tidak dinyalakan
    return TestClient(app)


@butuh_build
def test_ui_baru_di_akar(klien):
    r = klien.get("/")
    assert r.status_code == 200
    assert '<div id="app">' in r.text
    assert r.headers["cache-control"] == "no-cache"
    # Aset hasil build dirujuk dari akar dan benar-benar tersedia
    aset = re.findall(r'(?:src|href)="(/assets/[^"]+)"', r.text)
    assert aset, "index.html harus merujuk aset build"
    for path in aset:
        assert klien.get(path).status_code == 200, path


def test_ui_lama_sudah_dihapus_404(klien):
    assert klien.get("/legacy/").status_code == 404
    assert klien.get("/legacy/index.html").status_code == 404




def test_api_tidak_tertutup_mount_frontend(klien):
    assert klien.get("/api/config/audio").status_code == 200
