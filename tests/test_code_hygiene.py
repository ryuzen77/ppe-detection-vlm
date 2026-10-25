"""Penjaga daftar periksa kode (AGENTS.md §4.1): rahasia, hardcode warna, fungsi panjang.

Hanya membaca berkas yang dilacak git; `backend/.env` tidak pernah dibaca
(berkas itu memang tidak boleh terlacak, lihat tes kedua).
"""

import ast
import io
import re
import shutil
import subprocess
import tokenize
from collections.abc import Iterable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAX_FUNCTION_LINES = 30
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".mp3", ".wav", ".woff", ".woff2", ".pt", ".onnx", ".db"}
SECRET_PATTERN = re.compile(
    r"AIza[0-9A-Za-z_\-]{30,}"  # Google API key
    r"|sk-[A-Za-z0-9_\-]{20,}"  # OpenAI/OpenRouter
    r"|(?i:password|passwd|secret|api_key|token)\s*=\s*['\"][A-Za-z0-9_\-]{24,}['\"]"
)
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COLOR_SOURCE = "web/src/styles/tokens.css"

# Utang lama (audit 28-09-2026). Daftar ini hanya boleh MENYUSUT: fungsi baru yang
# panjang ditolak, dan entri yang sudah dipendekkan wajib dihapus dari sini.
LONG_FUNCTIONS_DEBT: set[str] = set()
HEX_COLOR_DEBT: set[str] = set()  # T42j: VideoPanel kini memakai token --video-bg


def _tracked_files() -> list[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("git tidak tersedia (mis. image produksi)")
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def _text_files(paths: Iterable[str]):
    for rel in paths:
        path = ROOT / rel
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            yield rel, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


_SKIP_BETWEEN = {tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER}


def _continuation_lines(text: str) -> set[int]:
    """Baris lanjutan setiap pernyataan logis (token pertama s.d. NEWLINE) — berbasis token, jadi
    berlaku untuk kurung, kepala klausa (if/except/with/…), dekorator, string multi-baris, `\\`.
    Komentar & baris kosong DI ANTARA pernyataan tidak termasuk pernyataan mana pun (T44)."""
    lines: set[int] = set()
    start = None
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if start is None:
            if tok.type not in _SKIP_BETWEEN:
                start = tok.start[0]
        elif tok.type == tokenize.NEWLINE:
            lines.update(range(start + 1, tok.end[0] + 1))
            start = None
    return lines


def _uncounted_lines(text: str) -> set[int]:
    """Baris yang bukan baris logis: lanjutan pernyataan + baris kosong. Hanya dua hal itu yang
    diubah `ruff format` (memecah pernyataan, menambah/membuang baris kosong), jadi format saja
    tidak mengubah panjang fungsi (tinjauan Codex T44: 993 fungsi dibandingkan sebelum/sesudah)."""
    blank = {number for number, line in enumerate(text.splitlines(), start=1) if not line.strip()}
    return _continuation_lines(text) | blank


def _body_length(node: ast.FunctionDef | ast.AsyncFunctionDef, uncounted: set[int]) -> int:
    """Panjang badan fungsi tanpa docstring (docstring panjang bukan kerumitan), dalam baris logis.

    `uncounted` (dari `_uncounted_lines` berkas yang sama) tidak dihitung (T44, keputusan pengguna
    22-10 "hitung baris logis"). Komentar tetap dihitung.
    """
    body = node.body
    if isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    if not body:
        return 0
    start, end = body[0].lineno, body[-1].end_lineno or body[-1].lineno
    return end - start + 1 - sum(1 for line in uncounted if start <= line <= end)


def _long_functions(paths: list[str]) -> set[str]:
    found = set()
    for rel, text in _text_files(p for p in paths if p.endswith(".py") and p.startswith(("backend/", "tools/"))):
        uncounted = _uncounted_lines(text)
        for node in ast.walk(ast.parse(text)):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and _body_length(node, uncounted) > MAX_FUNCTION_LINES
            ):
                found.add(f"{rel}::{node.name}")
    return found


def test_no_secrets_in_tracked_files():
    hits = [
        f"{rel}:{i}"
        for rel, text in _text_files(_tracked_files())
        for i, line in enumerate(text.splitlines(), 1)
        if SECRET_PATTERN.search(line)
    ]
    assert not hits, f"Pola rahasia di berkas terlacak (nilai tidak dicetak): {hits}"


def test_env_file_is_not_tracked():
    assert "backend/.env" not in _tracked_files()


def test_ui_colors_only_in_tokens():
    web = [
        p
        for p in _tracked_files()
        if p.startswith("web/src/")
        and p.endswith((".svelte", ".ts", ".css"))
        and p != COLOR_SOURCE
        and ".test." not in p
    ]  # tes boleh memakai warna contoh
    offenders = {
        rel
        for rel, text in _text_files(web)
        if rel not in HEX_COLOR_DEBT
        and any(HEX_COLOR.search(line) for line in text.splitlines() if not line.strip().startswith(("//", "*", "/*")))
    }
    assert not offenders, f"Warna hex di luar {COLOR_SOURCE}: {sorted(offenders)}"


def test_body_length_ignores_formatter_wrapping():
    wrapped = (
        "def f(a):\n"
        "    x = call(\n"
        "        a,\n"
        "        b,\n"
        "    )\n"
        "    # komentar di tengah badan tetap dihitung\n"
        "\n"
        "    if (\n"
        "        x\n"
        "        and a\n"
        "    ):\n"
        "        return x\n"
        "    return a\n"
    )
    # x=, komentar, if, return x, return a = 5 baris logis (lanjutan call/kondisi if & baris kosong tidak dihitung)
    assert _length_of(wrapped) == 5


def _length_of(source: str) -> int:
    fn = ast.parse(source).body[0]
    assert isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
    return _body_length(fn, _uncounted_lines(source))


def test_body_length_except_header_wrapping_not_counted():
    # Tinjauan Codex T44: kepala except (...) yang dipecah formatter dulu terhitung (29 -> 34)
    compact = "def f():\n    try:\n        g()\n    except (ValueError, KeyError) as e:\n        h(e)\n"
    wrapped = (
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    except (\n"
        "        ValueError,\n"
        "        KeyError,\n"
        "    ) as e:\n"
        "        h(e)\n"
    )
    assert _length_of(wrapped) == _length_of(compact) == 4


def test_body_length_counts_comments_at_block_start():
    # Tinjauan Codex T44: komentar/baris kosong di awal blok dulu terbuang
    source = "def f(x):\n    if x:\n        # komentar awal blok\n\n        return 1\n    return 0\n"
    # if, komentar, return 1, return 0 = 4 (komentar dihitung; baris kosong bukan baris logis)
    assert _length_of(source) == 4


def test_long_functions_do_not_grow():
    found = _long_functions(_tracked_files())
    new = found - LONG_FUNCTIONS_DEBT
    fixed = LONG_FUNCTIONS_DEBT - found
    assert not new, f"Fungsi baru > {MAX_FUNCTION_LINES} baris, pecah dulu: {sorted(new)}"
    assert not fixed, f"Sudah dipendekkan, hapus dari LONG_FUNCTIONS_DEBT: {sorted(fixed)}"


def test_secret_pattern_catches_real_shapes():
    """Pola harus menangkap bentuk kunci asli dan tidak menangkap nilai tiruan uji."""
    assert SECRET_PATTERN.search('GEMINI_API_KEY="AIza' + "x" * 35 + '"')
    assert SECRET_PATTERN.search("key = 'sk-" + "a" * 24 + "'")
    assert not SECRET_PATTERN.search('api_key="kunci-uji"')


# Indeks titik pose COCO ditulis langsung, mis. kpts[15] atau LEFT_ANKLE = 15 (T41)
POSE_INDEX_LITERAL = re.compile(
    r"(kpts|keypoints|points|pts)\[\s*\d+\s*\]|^\s*(NOSE|LEFT_\w+|RIGHT_\w+)\s*(,\s*\w+\s*)*=\s*\d+", re.MULTILINE
)
POSE_SOURCE = "backend/pose_keypoints.py"


def test_indeks_pose_hanya_di_satu_sumber():
    offenders = [
        rel
        for rel, text in _text_files(
            p for p in _tracked_files() if p.startswith("backend/") and p.endswith(".py") and p != POSE_SOURCE
        )
        if POSE_INDEX_LITERAL.search(text)
    ]
    assert not offenders, f"Indeks titik pose ditulis langsung (pakai {POSE_SOURCE}): {offenders}"
