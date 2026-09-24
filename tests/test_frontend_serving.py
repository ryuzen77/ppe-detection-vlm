"""UI baru (web/dist) di "/" dan UI lama utuh di "/legacy/" sebagai cadangan (T33)."""
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


def test_ui_lama_utuh_di_legacy(klien):
    r = klien.get("/legacy/")
    assert r.status_code == 200
    assert "js/app.js" in r.text
    # Rujukan relatif UI lama harus terjangkau dari /legacy/
    assert klien.get("/legacy/js/app.js").status_code == 200
    assert klien.get("/legacy/css/style.css").status_code == 200
    assert 'href="/"' in r.text, "UI lama punya jalan kembali ke tampilan baru"


@pytest.mark.parametrize("alamat, tujuan", [("/legacy", "/legacy/"), ("/app", "/"), ("/app/", "/")])
def test_alamat_lama_dan_tanpa_garis_miring_diarahkan(klien, alamat, tujuan):
    r = klien.get(alamat, follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308) and r.headers["location"] == tujuan


def test_api_tidak_tertutup_mount_frontend(klien):
    assert klien.get("/api/config/audio").status_code == 200
