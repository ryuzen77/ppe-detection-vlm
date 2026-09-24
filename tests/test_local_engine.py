"""Engine heuristik lokal (mode offline) dan penilaian kelengkapan dari katalog APD."""
import pytest

from backend import ppe_rules
from backend.vlm_analyzer import LocalVisionAnalyzer, VLMAnalyzer

from helpers import person_crop


@pytest.fixture
def engine(catalog_defaults):
    return LocalVisionAnalyzer()


def missing_label(key):
    return ppe_rules.get_item(key).missing_label


# --- Heuristik per item ------------------------------------------------------

def test_apd_lengkap_lolos(engine):
    result = engine.analyze(person_crop())
    assert result.is_complete
    assert result.missing_items == []
    assert result.is_low_confidence, "Keputusan engine lokal harus selalu ditandai akurasi terbatas"


@pytest.mark.parametrize("kurang, key", [
    ({"vest": False}, "rompi"),
    ({"helmet": False}, "helm"),
    ({"long_pants": False}, "celana"),
    ({"closed_shoes": False}, "sepatu"),
])
def test_satu_item_kurang_hanya_item_itu_yang_gagal(engine, kurang, key):
    result = engine.analyze(person_crop(**kurang))
    assert not result.is_complete
    assert result.missing_items == [missing_label(key)]


def test_rompi_berwarna_valid_melaporkan_warnanya(engine):
    rompi = engine.analyze(person_crop()).item("rompi")
    assert rompi.detected and rompi.is_valid_color
    assert rompi.color == "orange"


# --- Item tanpa heuristik lokal ----------------------------------------------

def test_item_tanpa_pemeriksa_lokal_menutup_gerbang(engine, catalog_defaults):
    # Kacamata hanya bisa dinilai VLM. Saat dinyalakan dalam mode offline,
    # pekerja harus ditolak, bukan diloloskan atas pemeriksaan yang tidak terjadi.
    assert not engine.has_local_check("kacamata")
    catalog_defaults.set_active({"kacamata": True})

    result = engine.analyze(person_crop())
    assert not result.is_complete
    assert missing_label("kacamata") in result.missing_items
    assert not result.item("kacamata").detected
    assert "Kacamata" in result.notes


def test_item_yang_dimatikan_tidak_diperiksa(engine, catalog_defaults):
    catalog_defaults.set_active({"sepatu": False})
    result = engine.analyze(person_crop(closed_shoes=False))
    assert result.is_complete
    assert "sepatu" not in result.items


# --- Aturan katalog ------------------------------------------------------------

def test_semua_item_tidak_boleh_dimatikan(catalog_defaults):
    semua_mati = {item.key: False for item in ppe_rules.get_items()}
    with pytest.raises(ValueError):
        catalog_defaults.set_active(semua_mati)
    assert ppe_rules.get_active_items(), "Penolakan tidak boleh meninggalkan katalog kosong"


def test_kunci_item_tidak_dikenal_ditolak(catalog_defaults):
    with pytest.raises(ValueError):
        catalog_defaults.set_active({"topi_koboi": True})


def test_pilihan_item_aktif_tersimpan_di_data_dir(catalog_defaults):
    from backend import runtime_settings
    catalog_defaults.set_active({"sarung_tangan": True})
    assert runtime_settings.load()["ppe_active"]["sarung_tangan"] is True


# --- Balasan VLM ------------------------------------------------------------------

def _balasan_lengkap(**tambahan):
    items = {
        "helm": {"detected": True},
        "rompi": {"detected": True, "is_valid_color": True, "color": "orange"},
        "celana": {"detected": True},
        "sepatu": {"detected": True, "is_closed_shoes": True},
    }
    return {"items": items, "missing_items": [], "notes": "ok", **tambahan}


def test_kelengkapan_dihitung_sistem_bukan_diambil_dari_model(catalog_defaults):
    data = _balasan_lengkap()
    data["items"]["rompi"]["is_valid_color"] = False
    data["is_complete"] = True  # Klaim model diabaikan
    result = VLMAnalyzer._parse_vlm_payload(data)
    assert not result.is_complete
    assert result.missing_items == [missing_label("rompi")]


def test_penolakan_anti_spoofing_dari_model_dipertahankan(catalog_defaults):
    data = _balasan_lengkap(missing_items=[ppe_rules.SPOOF_MISSING_LABEL])
    result = VLMAnalyzer._parse_vlm_payload(data)
    assert not result.is_complete
    assert ppe_rules.SPOOF_MISSING_LABEL in result.missing_items


def test_model_menyebut_item_yang_dimatikan_tidak_menolak_pekerja(catalog_defaults):
    # Kacamata mati secara bawaan; model yang tetap menyebutnya tidak berpengaruh
    data = _balasan_lengkap(missing_items=[missing_label("kacamata")])
    result = VLMAnalyzer._parse_vlm_payload(data)
    assert result.is_complete


def test_item_aktif_yang_tidak_dinilai_model_dianggap_tidak_ada(catalog_defaults):
    data = _balasan_lengkap()
    del data["items"]["helm"]
    result = VLMAnalyzer._parse_vlm_payload(data)
    assert not result.is_complete
    assert missing_label("helm") in result.missing_items


def test_pilihan_tersimpan_baru_berlaku_setelah_load_settings(catalog_defaults):
    # Sejak T16 impor tidak membaca disk; startup memanggil load_settings()
    from backend import runtime_settings
    runtime_settings.update("ppe_active", {"kacamata": True})
    assert "kacamata" not in [i.key for i in ppe_rules.get_active_items()]

    ppe_rules.load_settings()
    assert "kacamata" in [i.key for i in ppe_rules.get_active_items()]


def _balasan_tanpa_apd(missing_items):
    items = {k: {"detected": False} for k in ("helm", "rompi", "celana", "sepatu")}
    return {"items": items, "missing_items": missing_items, "notes": ""}


def test_ejaan_nama_item_dari_model_tidak_menggandakan_daftar_kurang(catalog_defaults):
    # Jawaban nyata gemini-3.5-flash-lite (T21): nama item huruf kecil + label katalog
    data = _balasan_tanpa_apd(["Helm keselamatan", "Rompi keselamatan", "Celana panjang",
                               "Sepatu tertutup", "Helm Keselamatan"])
    result = VLMAnalyzer._parse_vlm_payload(data)
    assert not result.is_complete
    assert result.missing_items == [missing_label(k) for k in ("helm", "rompi", "celana", "sepatu")]


@pytest.mark.parametrize("teks", [
    ppe_rules.SPOOF_MISSING_LABEL,
    "bukan orang fisik nyata (foto di layar ponsel)",
    "BUKAN ORANG FISIK NYATA",
])
def test_penolakan_anti_spoofing_dikenali_dengan_ejaan_apa_pun(catalog_defaults, teks):
    data = _balasan_lengkap(missing_items=[teks])
    result = VLMAnalyzer._parse_vlm_payload(data)
    assert not result.is_complete
    assert result.missing_items == [ppe_rules.SPOOF_MISSING_LABEL]
