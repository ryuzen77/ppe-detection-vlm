"""Pemeriksaan sebelum commit, sama dengan CI: ruff, pyright, pytest, lalu UI web.

Jalankan dari mana saja dengan Python environment proyek:
    python scripts/check.py                # semua langkah
    python scripts/check.py pyright        # hanya langkah bernama itu (dipakai CI)
    python scripts/check.py --allow-skip   # mesin tanpa Node.js: langkah yang butuh Node boleh dilewati
Keluar dengan kode bukan nol bila salah satu langkah gagal, atau bila ada langkah
yang dilewati tanpa `--allow-skip` (T93).
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
# Versi tetap supaya hasil sama di semua mesin & CI (T66); pengaturan di pyrightconfig.json
PYRIGHT_VERSION = "1.1.408"
ALLOW_SKIP_FLAG = "--allow-skip"

Step = tuple[str, list[str], Path]


def build_steps(npx: str | None, npm: str | None, has_node_modules: bool) -> tuple[list[Step], list[str]]:
    """Daftar langkah yang bisa dijalankan di mesin ini + alasan langkah yang dilewati.

    Fungsi murni (alat dioper sebagai argumen) supaya bisa dites tanpa Node.js."""
    steps: list[Step] = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "."], ROOT),
        # T44: seluruh Python sudah terformat; kode baru wajib ikut (`ruff format .` untuk merapikan)
        ("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."], ROOT),
    ]
    skipped: list[str] = []
    # Pemeriksaan tipe (mesin yang sama dengan Pylance); butuh Node.js (npx)
    if npx:
        steps.append(("pyright", [npx, "-y", f"pyright@{PYRIGHT_VERSION}", "--pythonpath", sys.executable], ROOT))
    else:
        skipped.append("pyright (npx tidak ditemukan)")
    steps.append(("pytest", [sys.executable, "-m", "pytest", "-q"], ROOT))

    # Build ikut dijalankan supaya web/dist yang dicommit selalu sesuai sumbernya (CI memeriksa hal yang sama)
    if not npm:
        skipped.append("web/ (npm tidak ditemukan)")
    elif not has_node_modules:
        skipped.append("web/ (web/node_modules tidak ada; jalankan 'npm ci' di web/)")
    else:
        steps += [
            # T44: Prettier (gaya) & ESLint (bug nyata); `npm run format` untuk merapikan
            ("web: format", [npm, "run", "format:check"], WEB),
            ("web: lint", [npm, "run", "lint"], WEB),
            ("web: cek tipe", [npm, "run", "check"], WEB),
            ("web: tes unit", [npm, "test"], WEB),
            ("web: build", [npm, "run", "build"], WEB),
        ]
    return steps, skipped


def verdict(failed: list[str], skipped: list[str], allow_skip: bool) -> tuple[int, str]:
    """Kode keluar & pesan akhir. Langkah yang dilewati tidak boleh terbaca "lolos" (T93:
    22-10 npm hilang, Pyright & seluruh web dilewati, tetapi tertulis lolos)."""
    if failed:
        return 1, f"GAGAL: {', '.join(failed)}"
    if skipped and not allow_skip:
        return 1, (
            f"TIDAK LENGKAP — dilewati: {'; '.join(skipped)}. "
            f"Pasang Node.js/npm, atau jalankan dengan {ALLOW_SKIP_FLAG} bila mesin ini memang tanpa Node."
        )
    if skipped:
        return 0, f"Lolos, tetapi dilewati ({ALLOW_SKIP_FLAG}): {'; '.join(skipped)}"
    return 0, "Semua pemeriksaan lolos."


def main(args: list[str]) -> int:
    allow_skip = ALLOW_SKIP_FLAG in args
    only = [a for a in args if a != ALLOW_SKIP_FLAG]
    all_steps, skipped = build_steps(shutil.which("npx"), shutil.which("npm"), (WEB / "node_modules").exists())
    steps = [s for s in all_steps if not only or s[0] in only]
    missing = set(only) - {name for name, _, _ in steps}
    if missing:
        print(f"Langkah tidak tersedia: {', '.join(sorted(missing))}")
        return 1
    failed = []
    for name, cmd, cwd in steps:
        print(f"== {name} ==", flush=True)
        if subprocess.run(cmd, cwd=cwd).returncode != 0:
            failed.append(name)
    # Langkah bernama (mis. CI `check.py pyright`) sudah dicek tersedia di atas
    code, message = verdict(failed, [] if only else skipped, allow_skip)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
