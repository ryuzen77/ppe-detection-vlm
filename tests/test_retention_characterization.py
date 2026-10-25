"""Karakterisasi retensi data `ReportManager.cleanup_old_data` (T42f).

Sebelum fungsi ±80 baris itu dipecah, perilaku kode lama direkam di
`golden/retention.json`: puluhan skenario acak berbenih di folder sementara pytest
(audit berumur 0-10 hari, foto ada/hilang/yatim tanpa baris audit, berkas bukan .jpg,
batas hari & ukuran folder bervariasi termasuk dimatikan). Yang direkam: baris audit
yang tersisa beserta nama fotonya, berkas yang tersisa di folder, dan pesan log.
Jam dibekukan, jadi acuan tidak bergantung pada tanggal uji. Refaktor tidak boleh
mengubahnya.

Bila perilaku SENGAJA diubah, bangkitkan ulang acuannya:
    python tests/test_retention_characterization.py --regenerate
"""

import json
import logging
import os
import sys
import time
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOLDEN = Path(__file__).resolve().parent / "golden" / "retention.json"
SCENARIOS, ROWS = 40, 30
NOW = 1_790_000_000.0  # Oktober 2026; dibekukan
DAY = 86400
KB_AS_GB = 1 / (1024 * 1024)


def _scenario(seed, root, monkeypatch, logs):
    import backend.audit.report_manager as rm
    from backend.audit import retention
    from backend.config import cfg

    rng = np.random.default_rng(seed)
    clock = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")})
    clock.time = lambda: NOW
    monkeypatch.setattr(retention, "time", clock)
    monkeypatch.setattr(cfg, "RETENTION_PHOTO_DAYS", int(rng.choice([0, 1, 3])))
    monkeypatch.setattr(cfg, "RETENTION_AUDIT_DAYS", int(rng.choice([0, 2, 5, 7])))
    monkeypatch.setattr(cfg, "RETENTION_MAX_PHOTO_GB", float(rng.choice([0, 150, 400, 1000])) * KB_AS_GB)

    snapshots = root / f"s{seed}" / "snapshots"
    snapshots.mkdir(parents=True)
    mgr = rm.ReportManager(root / f"s{seed}" / "audit.db", snapshots)
    mgr.open()
    conn = mgr._get_connection()
    ages = rng.permutation(np.linspace(0.01, 10, ROWS)) * DAY  # tanpa umur kembar → urutan mtime pasti
    for i, age in enumerate(ages):
        t = NOW - float(age)
        kind = rng.choice(["photo", "photo", "photo", "none", "missing"])
        fname = "" if kind == "none" else f"foto_{i}.jpg"
        conn.execute(
            "INSERT INTO worker_inspections (track_id, timestamp, date_str, time_str, is_complete, items_json, "
            "missing_items, notes, inference_source, inference_time_ms, snapshot_filename) "
            "VALUES (?, ?, '2026-10-01', '12:00', 1, '{}', '[]', '', 'VLM', 1.0, ?)",
            (i, time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)), fname),
        )
        if kind == "photo":
            _write(snapshots / fname, int(rng.integers(20, 60)) * 1024, t)  # KB: log "x MB" ikut terjaga
    for j in range(int(rng.integers(0, 4))):  # yatim (tanpa baris audit) & bukan .jpg
        _write(
            snapshots / f"yatim_{j}.jpg", int(rng.integers(20, 60)) * 1024, NOW - float(rng.uniform(0, 10)) * DAY - j
        )
        _write(snapshots / f"lain_{j}.png", 1500, NOW - 9 * DAY)
    conn.commit()
    if seed % 13 == 12:  # basis data rusak: galat dicatat, tidak ada yang terhapus
        conn.execute("ALTER TABLE worker_inspections RENAME TO rusak")
        conn.commit()

    logs.clear()
    mgr.cleanup_old_data()
    table = "rusak" if seed % 13 == 12 else "worker_inspections"
    rows = [
        [r["track_id"], r["snapshot_filename"]]
        for r in conn.execute(f"SELECT track_id, snapshot_filename FROM {table} ORDER BY track_id")
    ]
    files = sorted(p.name for p in snapshots.iterdir())
    conn.close()
    mgr._opened = False
    return [
        seed,
        cfg.RETENTION_PHOTO_DAYS,
        cfg.RETENTION_AUDIT_DAYS,
        round(cfg.RETENTION_MAX_PHOTO_GB / KB_AS_GB),
        rows,
        files,
        list(logs),
    ]


def _write(path, size, mtime):
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))


class _Logs(logging.Handler):
    def __init__(self, sink):
        super().__init__(logging.INFO)
        self.sink = sink

    def emit(self, record):
        self.sink.append([record.levelname, record.getMessage()])


def run_scenarios(root, monkeypatch):
    import backend.audit.report_manager as rm

    logs = []
    handler = _Logs(logs)
    level = rm.logger.level
    rm.logger.addHandler(handler)
    rm.logger.setLevel(logging.INFO)  # setLevel, bukan atribut: cache isEnabledFor ikut dibersihkan
    try:
        return [_scenario(seed, root, monkeypatch, logs) for seed in range(SCENARIOS)]
    finally:
        rm.logger.removeHandler(handler)
        rm.logger.setLevel(level)


def test_retensi_tidak_berubah(tmp_path, monkeypatch):
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(run_scenarios(tmp_path, monkeypatch)))
    changed = [a for a, e in zip(actual, expected) if a != e]
    assert len(actual) == len(expected) and not changed, f"{len(changed)} skenario berubah, mis. {changed[:1]}"


def test_acuan_mencakup_semua_jalur():
    scenarios = json.loads(GOLDEN.read_text(encoding="utf-8"))
    by_rule = {(s[1] > 0, s[2] > 0, s[3] > 0) for s in scenarios}
    assert len(by_rule) == 8, f"kombinasi batas hari/ukuran tidak lengkap: {by_rule}"
    assert any(not s[6] for s in scenarios), "skenario tanpa penghapusan (tanpa log)"
    assert any(s[6] and s[6][0][0] == "INFO" for s in scenarios)
    assert any(s[6] and s[6][0][0] == "ERROR" for s in scenarios), "jalur galat basis data"
    assert any(s[6] and "(membebaskan 0.0 MB)" not in s[6][0][1] for s in scenarios)
    # pengaman ukuran menghapus foto yatim (tanpa baris audit)
    assert any(s[3] and not any(f.startswith("yatim_") for f in s[5]) and s[5] != [] for s in scenarios)


if __name__ == "__main__" and "--regenerate" in sys.argv:
    import tempfile
    import conftest  # noqa: F401
    import pytest

    mp = pytest.MonkeyPatch()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        data = run_scenarios(Path(tmp), mp)
    mp.undo()
    GOLDEN.write_text(json.dumps(data), encoding="utf-8")
    print(f"acuan ditulis: {GOLDEN}")
