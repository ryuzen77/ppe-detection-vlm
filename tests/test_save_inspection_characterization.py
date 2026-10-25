"""Karakterisasi penulisan audit `ReportManager.save_inspection` (T42h).

Sebelum fungsi ±60 baris itu dipecah, perilaku kode lama direkam di
`golden/save_inspection.json`: ratusan panggilan acak berbenih di folder sementara
pytest (isi item & catatan Unicode, daftar kurang kosong/berisi, potongan gambar
tidak ada/kosong/sah, foto gagal ditulis, ID & detik sama → nama berakhiran nomor (T64)). Yang direkam: nilai kembali, log per
panggilan, baris SQLite apa adanya (kolom mentah), dan berkas foto yang ada. Jam dibekukan per
panggilan, jadi acuan tidak bergantung pada tanggal uji. Refaktor tidak boleh
mengubahnya.

Bila perilaku SENGAJA diubah, bangkitkan ulang acuannya:
    python tests/test_save_inspection_characterization.py --regenerate
"""

import json
import logging
import sys
import time
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOLDEN = Path(__file__).resolve().parent / "golden" / "save_inspection.json"
CALLS = 300
START = 1_790_000_000.0  # Oktober 2026; dibekukan, maju beberapa detik per panggilan
ITEM_KEYS = ["helm", "rompi", "celana", "sepatu", "rokok"]
NOTES = ["", "Helm terlihat jelas", "Rompi oranye — reflektif ✓", 'kemeja "bergaris"\nbaris kedua', "日本語 & émoji 🦺"]
SOURCES = ["VLM_LIVE:gemini", "VLM_CADANGAN:ollama", "SIMULASI"]


def _crop(rng):
    kind = rng.choice(["none", "empty", "ok", "ok", "ok"])
    if kind == "none":
        return None
    if kind == "empty":
        return np.zeros((0, 4, 3), np.uint8)
    h, w = int(rng.integers(8, 40)), int(rng.integers(4, 20))
    return rng.integers(0, 255, (h, w, 3)).astype(np.uint8)


def _items(rng):
    keys = list(rng.choice(ITEM_KEYS, size=int(rng.integers(0, 5)), replace=False))
    return {
        k: {
            "present": bool(rng.random() < 0.6),
            "confidence": round(float(rng.random()), 3),
            "note": str(rng.choice(NOTES)),
        }
        for k in keys
    }


class _Logs(logging.Handler):
    def __init__(self, sink):
        super().__init__(logging.INFO)
        self.sink = sink

    def emit(self, record):
        self.sink.append([record.levelname, record.getMessage()])


def run_calls(root, monkeypatch):
    import backend.audit.report_manager as rm
    from backend.audit import db as audit_db, snapshots as snapshot_store

    logs = []
    handler = _Logs(logs)
    loggers = (rm.logger, snapshot_store.logger)
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)  # setLevel, bukan atribut: cache isEnabledFor ikut dibersihkan

    clock_now = [START]
    clock = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")})
    # gmtime: acuan sama di zona waktu mana pun
    clock.localtime = lambda t=None: time.gmtime(clock_now[0] if t is None else t)
    clock.time = lambda: clock_now[0]
    monkeypatch.setattr(audit_db, "time", clock)
    real_replace = snapshot_store.os.replace
    fail = [False]

    def replace(src, dst):
        if fail[0]:
            raise OSError("disk penuh tiruan")
        real_replace(src, dst)

    monkeypatch.setattr(snapshot_store.os, "replace", replace)
    snapshots = root / "snapshots"
    mgr = rm.ReportManager(root / "audit.db", snapshots)
    mgr.open()
    rng = np.random.default_rng(42)
    out = []
    try:
        for i in range(CALLS):
            # Kadang dua inspeksi di detik yang sama (nama foto bisa sama untuk ID yang sama)
            clock_now[0] += float(rng.choice([0, 1, 7, 3600]))
            fail[0] = bool(rng.random() < 0.08)
            missing = [
                str(m)
                for m in rng.choice(
                    ["Helm Keselamatan", "Rompi Keselamatan", "Larangan Rokok"],
                    size=int(rng.integers(0, 3)),
                    replace=False,
                )
            ]
            meta = mgr.save_inspection(
                track_id=int(rng.integers(1, 6)),
                is_complete=not missing,
                items=_items(rng),
                missing_items=missing,
                notes=str(rng.choice(NOTES)),
                inference_source=str(rng.choice(SOURCES)),
                inference_time_ms=round(float(rng.uniform(800, 9000)), 2),
                crop_img=_crop(rng),
            )
            out.append(["panggilan", i, meta, list(logs)])
            logs.clear()
        conn = mgr._get_connection()
        rows = [list(r) for r in conn.execute("SELECT * FROM worker_inspections ORDER BY id")]
        conn.close()
    finally:
        mgr._opened = False
        for logger, level in zip(loggers, levels):
            logger.removeHandler(handler)
            logger.setLevel(level)
    files = sorted(p.name for p in snapshots.iterdir())
    out.append(["baris", rows])
    out.append(["berkas", files])
    return out


def test_penulisan_audit_tidak_berubah(tmp_path, monkeypatch):
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # T83 menambahkan satu kolom nullable; nilai/perilaku lama tetap dibandingkan utuh.
    for entry in expected:
        if entry[0] == "panggilan":
            entry[2]["gate_hold"] = None
        elif entry[0] == "baris":
            for row in entry[1]:
                row.append(None)
    actual = json.loads(json.dumps(run_calls(tmp_path, monkeypatch)))
    changed = [a for a, e in zip(actual, expected) if a != e]
    assert len(actual) == len(expected) and not changed, f"{len(changed)} entri berubah, mis. {changed[:1]}"


def test_acuan_mencakup_semua_jalur():
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    metas = [e[2] for e in data if e[0] == "panggilan"]
    rows = next(e[1] for e in data if e[0] == "baris")
    assert any(m["snapshot_filename"] for m in metas) and any(not m["snapshot_filename"] for m in metas)
    assert {m["is_complete"] for m in metas} == {True, False}
    assert any("🦺" in r[8] for r in rows) and any("\\u" not in r[6] and "é" in r[6] for r in rows), (
        "Unicode apa adanya"
    )
    names = [m["snapshot_filename"] for m in metas if m["snapshot_filename"]]
    # T64: ID & detik sama tidak lagi menimpa foto; nama berikutnya berakhiran _2, _3, ...
    assert len(names) == len(set(names)), "nama foto tidak boleh kembar"
    assert any(n.endswith("_2.jpg") for n in names), "jalur nama berakhiran nomor harus terekam"
    assert any(e[3] for e in data if e[0] == "panggilan"), "log gagal tulis foto harus terekam"


if __name__ == "__main__" and "--regenerate" in sys.argv:
    import tempfile

    import conftest  # noqa: F401
    import pytest

    mp = pytest.MonkeyPatch()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        data = run_calls(Path(tmp), mp)
    mp.undo()
    GOLDEN.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"acuan ditulis: {GOLDEN}")
