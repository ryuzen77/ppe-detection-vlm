"""UI baru (web/dist) di /app/ dan UI lama tetap di / sebagai cadangan (T33)."""
import pytest
from fastapi.testclient import TestClient

from backend.app import app, web_dist_dir


@pytest.fixture
def klien():
    # Tanpa lifespan: kamera, model, dan VLM tidak dinyalakan
    return TestClient(app)


def test_ui_lama_tetap_di_akar(klien):
    r = klien.get("/")
    assert r.status_code == 200
    assert "js/app.js" in r.text, "Halaman akar masih UI lama (cadangan)"


@pytest.mark.skipif(not web_dist_dir.exists(), reason="web/dist belum dibangun (npm run build)")
def test_ui_baru_disajikan_di_app(klien):
    r = klien.get("/app/")
    assert r.status_code == 200
    assert '<div id="app">' in r.text
    assert r.headers["cache-control"] == "no-cache"
    # Aset hasil build dirujuk dengan awalan /app/ (Vite base) dan benar-benar tersedia
    import re
    aset = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', r.text)
    assert aset, "index.html harus merujuk aset build"
    for path in aset:
        assert klien.get(path).status_code == 200, path


def test_api_tidak_tertutup_mount_frontend(klien):
    assert klien.get("/api/config/audio").status_code == 200
