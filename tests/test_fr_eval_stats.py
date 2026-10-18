"""Logika murni alat uji FR (T34m): ringkasan waktu, estimasi sesi, verifikasi hash."""

import hashlib

import pytest

from tools.fr_eval import stats


def test_ringkasan_persentil():
    timing = stats.summarize([float(i) for i in range(1, 101)])
    assert timing.p50_ms == pytest.approx(50.5)
    assert timing.p95_ms == pytest.approx(95.05)
    assert timing.mean_ms == pytest.approx(50.5)


def test_ringkasan_tanpa_sampel_ditolak():
    with pytest.raises(ValueError):
        stats.summarize([])


def test_estimasi_sesi_pencarian_hanya_sekali():
    assert stats.session_ms(detect_ms=5, embed_ms=10, search_ms=1, attempts=3) == 46
    with pytest.raises(ValueError):
        stats.session_ms(5, 10, 1, attempts=0)


def test_batas_anggaran_inklusif():
    assert stats.meets_budget(50.0, 50.0) and not stats.meets_budget(50.01, 50.0)


def test_verifikasi_hash(tmp_path):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"bobot uji")
    digest = hashlib.sha256(b"bobot uji").hexdigest()
    assert stats.verify(path, digest) and stats.verify(path, digest.upper())
    assert stats.verify(path, ""), "hash kosong = belum dipatok, cukup berkasnya ada"
    assert not stats.verify(path, "0" * 64)
    assert not stats.verify(tmp_path / "hilang.onnx", "")


def test_katalog_lengkap_dan_berlisensi():
    catalog = stats.load_catalog(stats.CATALOG)
    entries = [catalog["detector"], *catalog["recognizers"]]
    names = [e["name"] for e in entries]
    assert len(names) == len(set(names))
    for entry in entries:
        assert entry["license"]
        for mf in stats.model_files(entry):
            assert mf.url.startswith("https://") and mf.filename
            assert mf.sha256, f"{entry['name']}/{mf.filename} belum dipatok hash-nya"


def test_folder_model_bisa_diganti_env(monkeypatch, tmp_path):
    monkeypatch.setenv(stats.MODELS_DIR_ENV, str(tmp_path))
    assert stats.models_dir() == tmp_path
    monkeypatch.delenv(stats.MODELS_DIR_ENV)
    assert stats.models_dir() == stats.DEFAULT_MODELS_DIR
