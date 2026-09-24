"""Pemeriksaan sebelum commit, sama dengan CI: ruff lalu pytest.

Jalankan dari mana saja dengan Python environment proyek:
    python scripts/check.py
Keluar dengan kode bukan nol bila salah satu langkah gagal.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
]


def main() -> int:
    failed = []
    for name, cmd in STEPS:
        print(f"== {name} ==", flush=True)
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            failed.append(name)
    if failed:
        print(f"GAGAL: {', '.join(failed)}")
        return 1
    print("Semua pemeriksaan lolos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
