"""Pembacaan variabel lingkungan di config."""

import pytest

from backend import config


@pytest.mark.parametrize("nilai", ["", "   "])
def test_nilai_kosong_di_env_memakai_bawaan(monkeypatch, nilai):
    # `.env` salinan contoh sering berisi `GEMINI_MODEL=`; itu harus berarti "pakai bawaan"
    monkeypatch.setenv("GEMINI_MODEL", nilai)
    assert config._env("GEMINI_MODEL", "gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"


def test_variabel_tidak_ada_memakai_bawaan(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert config._env("GEMINI_MODEL", "bawaan") == "bawaan"


def test_nilai_terisi_dipakai_tanpa_spasi_tepi(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "  gemini-3.8-flash ")
    assert config._env("GEMINI_MODEL", "bawaan") == "gemini-3.8-flash"


def test_model_bawaan_bukan_generasi_yang_sudah_ditutup():
    assert config.Config.VLM_PROVIDER == "gemini"
    assert not config.Config.VLM_MODEL.startswith("gemini-2.5"), config.Config.VLM_MODEL
