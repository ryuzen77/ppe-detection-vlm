"""scripts/check.py: langkah yang dilewati tidak boleh terbaca "lolos" (T93)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_script", ROOT / "scripts" / "check.py")
assert _spec and _spec.loader
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def _names(steps) -> list[str]:
    return [name for name, _, _ in steps]


def test_all_steps_when_node_available():
    steps, skipped = check.build_steps("npx", "npm", has_node_modules=True)
    assert not skipped
    assert "pyright" in _names(steps)
    assert "web: build" in _names(steps)


def test_missing_npm_skips_pyright_and_web_with_reasons():
    # Kejadian 22-10: npm/npx terhapus dari folder Node
    steps, skipped = check.build_steps(None, None, has_node_modules=True)
    assert _names(steps) == ["ruff", "ruff format", "pytest"]
    assert any("pyright" in s for s in skipped)
    assert any("npm tidak ditemukan" in s for s in skipped)


def test_missing_node_modules_is_reported():
    _, skipped = check.build_steps("npx", "npm", has_node_modules=False)
    assert skipped == ["web/ (web/node_modules tidak ada; jalankan 'npm ci' di web/)"]


def test_skipped_steps_fail_without_flag():
    code, message = check.verdict([], ["pyright (npx tidak ditemukan)"], allow_skip=False)
    assert code == 1
    assert "TIDAK LENGKAP" in message and "lolos" not in message.lower()


def test_skipped_steps_pass_with_flag_but_are_named():
    code, message = check.verdict([], ["pyright (npx tidak ditemukan)"], allow_skip=True)
    assert code == 0
    assert "pyright" in message


def test_failure_wins_over_skip():
    code, message = check.verdict(["pytest"], ["pyright (npx tidak ditemukan)"], allow_skip=True)
    assert code == 1
    assert message.startswith("GAGAL")


def test_all_ran_and_passed():
    assert check.verdict([], [], allow_skip=False) == (0, "Semua pemeriksaan lolos.")
