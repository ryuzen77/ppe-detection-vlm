"""Prompt VLM dirakit dari katalog: ringkas, dan aturan rompi menilai bentuk (T36a)."""

from backend import ppe_rules
from backend.vlm_prompt import build_system_prompt


def test_prompt_tidak_meminta_teks_bebas(catalog_defaults):
    # Kesimpulan dihitung sistem; teks bebas memperlambat VLM tanpa menambah akurasi (T35)
    prompt = build_system_prompt()
    for kunci in ('"description"', '"is_complete"', '"missing_items"', '"notes"'):
        assert kunci not in prompt


def test_prompt_meminta_tanda_orang_nyata(catalog_defaults):
    prompt = build_system_prompt()
    assert f'"{ppe_rules.REAL_PERSON_KEY}": true/false' in prompt
    assert ppe_rules.REAL_PERSON_KEY in ppe_rules.ANTI_SPOOF_RULE


def test_bentuk_json_memuat_syarat_dan_warna_dari_katalog(catalog_defaults):
    shape = ppe_rules.build_json_shape()
    for item in ppe_rules.get_active_items():
        assert f'"{item.key}": {{"detected": true/false' in shape
        if item.qualifier is not None:
            assert f'"{item.qualifier.key}": true/false' in shape
        assert ('"color"' in shape.split(f'"{item.key}"')[1].split("}")[0]) == item.reports_color


def test_item_nonaktif_tidak_ditanyakan(catalog_defaults):
    aktif = {i.key for i in ppe_rules.get_active_items()}
    nonaktif = [i for i in ppe_rules.get_items() if i.key not in aktif]
    assert nonaktif, "katalog bawaan punya item nonaktif (mis. kacamata)"
    prompt = build_system_prompt()
    for item in nonaktif:
        assert f'"{item.key}"' not in prompt


def test_aturan_rompi_membedakan_bentuk_dari_warna():
    # T35: kaos kuning / hitam-kuning dikira rompi ketika aturan hanya menekankan warna
    rompi = ppe_rules.get_item("rompi")
    assert rompi is not None and rompi.qualifier is not None
    assert "TANPA LENGAN" in rompi.prompt_rule
    assert "BUKAN rompi keselamatan" in rompi.prompt_rule
    assert "detected = false" in rompi.prompt_rule
    assert rompi.qualifier.key in rompi.qualifier.prompt_rule
