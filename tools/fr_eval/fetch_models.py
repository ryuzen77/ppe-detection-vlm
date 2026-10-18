"""Unduh & verifikasi bobot kandidat FR (T34m) ke cache di luar repo.

Berkas yang sudah ada dan hash-nya cocok dilewati. Hash kosong di models.json
berarti belum dipatok: hash hasil unduhan dicetak untuk disalin ke katalog.

    python tools/fr_eval/fetch_models.py
"""

import bz2
import shutil
import sys
import urllib.request
from pathlib import Path

from stats import CATALOG, load_catalog, model_files, models_dir, sha256_of, verify

TIMEOUT_SECONDS = 900


def _download(url: str, target: Path) -> None:
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp, partial.open("wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    partial.replace(target)


def _extract_bz2(archive: Path) -> None:
    """Bobot dlib dikemas .bz2; dlib hanya membaca .dat polos."""
    target = archive.with_suffix("")
    if archive.suffix == ".bz2" and not target.exists():
        with bz2.open(archive, "rb") as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def _fetch_entry(entry: dict, root: Path) -> bool:
    ok = True
    for mf in model_files(entry):
        target = root / entry["name"] / mf.filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if not verify(target, mf.sha256):
            print(f"unduh  {entry['name']}/{mf.filename}")
            _download(mf.url, target)
        valid = verify(target, mf.sha256)
        if valid:
            _extract_bz2(target)
        ok &= valid
        status = "ok" if valid else "HASH BEDA"
        pin = "" if mf.sha256 else "  (belum dipatok)"
        print(f"{status:9} {entry['name']}/{mf.filename} {sha256_of(target)}{pin}")
    return ok


def main() -> int:
    catalog = load_catalog(CATALOG)
    root = models_dir()
    entries = [catalog["detector"], *catalog["recognizers"]]
    results = [_fetch_entry(entry, root) for entry in entries]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
