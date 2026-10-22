"""Pemeriksaan sebelum commit, sama dengan CI: ruff, pyright, lalu pytest.

Jalankan dari mana saja dengan Python environment proyek:
    python scripts/check.py            # semua langkah
    python scripts/check.py pyright    # hanya langkah bernama itu (dipakai CI)
Keluar dengan kode bukan nol bila salah satu langkah gagal.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
# Versi tetap supaya hasil sama di semua mesin & CI (T66); pengaturan di pyrightconfig.json
PYRIGHT_VERSION = "1.1.408"

STEPS = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "."], ROOT),
]
# Pemeriksaan tipe (mesin yang sama dengan Pylance); butuh Node.js (npx)
_npx = shutil.which("npx")
if _npx:
    STEPS.append(("pyright", [_npx, "-y", f"pyright@{PYRIGHT_VERSION}", "--pythonpath", sys.executable], ROOT))
STEPS.append(("pytest", [sys.executable, "-m", "pytest", "-q"], ROOT))

# UI baru (web/): hanya bila Node.js terpasang. Build ikut dijalankan supaya
# web/dist yang dicommit selalu sesuai sumbernya (CI memeriksa hal yang sama).
_npm = shutil.which("npm")
if _npm and (WEB / "node_modules").exists():
    STEPS += [
        ("web: cek tipe", [_npm, "run", "check"], WEB),
        ("web: tes unit", [_npm, "test"], WEB),
        ("web: build", [_npm, "run", "build"], WEB),
    ]


def main(only: list[str]) -> int:
    steps = [s for s in STEPS if not only or s[0] in only]
    missing = set(only) - {name for name, _, _ in steps}
    if missing:
        print(f"Langkah tidak tersedia: {', '.join(sorted(missing))}")
        return 1
    failed = []
    for name, cmd, cwd in steps:
        print(f"== {name} ==", flush=True)
        if subprocess.run(cmd, cwd=cwd).returncode != 0:
            failed.append(name)
    if not only and not any(name == "pyright" for name, _, _ in STEPS):
        print("(pyright dilewati: Node.js/npx tidak ada)")
    if not only and not any(name.startswith("web:") for name, _, _ in STEPS):
        print("(langkah web/ dilewati: Node.js atau web/node_modules tidak ada; jalankan 'npm ci' di web/)")
    if failed:
        print(f"GAGAL: {', '.join(failed)}")
        return 1
    print("Semua pemeriksaan lolos.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
