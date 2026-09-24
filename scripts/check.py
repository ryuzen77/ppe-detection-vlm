"""Pemeriksaan sebelum commit, sama dengan CI: ruff lalu pytest.

Jalankan dari mana saja dengan Python environment proyek:
    python scripts/check.py
Keluar dengan kode bukan nol bila salah satu langkah gagal.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

STEPS = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "."], ROOT),
    ("pytest", [sys.executable, "-m", "pytest", "-q"], ROOT),
]

# UI baru (web/): hanya bila Node.js terpasang. Build ikut dijalankan supaya
# web/dist yang dicommit selalu sesuai sumbernya (CI memeriksa hal yang sama).
_npm = shutil.which("npm")
if _npm and (WEB / "node_modules").exists():
    STEPS += [
        ("web: cek tipe", [_npm, "run", "check"], WEB),
        ("web: tes unit", [_npm, "test"], WEB),
        ("web: build", [_npm, "run", "build"], WEB),
    ]


def main() -> int:
    failed = []
    for name, cmd, cwd in STEPS:
        print(f"== {name} ==", flush=True)
        if subprocess.run(cmd, cwd=cwd).returncode != 0:
            failed.append(name)
    if not any(name.startswith("web:") for name, _, _ in STEPS):
        print("(langkah web/ dilewati: Node.js atau web/node_modules tidak ada; jalankan 'npm ci' di web/)")
    if failed:
        print(f"GAGAL: {', '.join(failed)}")
        return 1
    print("Semua pemeriksaan lolos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
