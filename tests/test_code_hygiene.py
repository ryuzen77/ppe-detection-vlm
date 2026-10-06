"""Penjaga daftar periksa kode (AGENTS.md §4.1): rahasia, hardcode warna, fungsi panjang.

Hanya membaca berkas yang dilacak git; `backend/.env` tidak pernah dibaca
(berkas itu memang tidak boleh terlacak, lihat tes kedua).
"""
import ast
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAX_FUNCTION_LINES = 30
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".mp3", ".wav", ".woff", ".woff2", ".pt", ".onnx", ".db"}
SECRET_PATTERN = re.compile(
    r"AIza[0-9A-Za-z_\-]{30,}"                       # Google API key
    r"|sk-[A-Za-z0-9_\-]{20,}"                       # OpenAI/OpenRouter
    r"|(?i:password|passwd|secret|api_key|token)\s*=\s*['\"][A-Za-z0-9_\-]{24,}['\"]"
)
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COLOR_SOURCE = "web/src/styles/tokens.css"

# Utang lama (audit 28-09-2026). Daftar ini hanya boleh MENYUSUT: fungsi baru yang
# panjang ditolak, dan entri yang sudah dipendekkan wajib dihapus dari sini.
LONG_FUNCTIONS_DEBT = {
    "backend/video/capture.py::_reader_loop",
    "backend/detector.py::detect_and_track",
    "tools/bench_vlm.py::main",
    "tools/eval_vlm.py::main",
    "backend/state_manager.py::update_frame_detections",
    "backend/video/capture.py::_init_camera",
    "backend/report_manager.py::cleanup_old_data",
    "backend/video/hud.py::draw_hud",
    "backend/state_manager.py::_run_vlm_analysis",
    "backend/state_manager.py::get_telemetry",
    "backend/report_manager.py::get_reports",
    "backend/app.py::run",
    "backend/vlm_analyzer.py::analyze_person",
    "backend/camera_manager.py::probe_modes",
    "backend/api/routes_cameras.py::list_cameras",
    "backend/report_manager.py::save_inspection",
    "backend/video/capture.py::_capture_loop",
    "backend/camera_manager.py::_scan_worker",
    "backend/vlm_analyzer.py::_parse_vlm_payload",
    "backend/report_manager.py::_migrate_v0_to_v1",
    "backend/storage.py::migrate_legacy_data",
    "backend/video/capture.py::__init__",
    "backend/app.py::__call__",
    "backend/report_manager.py::_migrate",
}
HEX_COLOR_DEBT = {"web/src/components/monitoring/VideoPanel.svelte"}


def _tracked_files() -> list[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("git tidak tersedia (mis. image produksi)")
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def _text_files(paths: list[str]):
    for rel in paths:
        path = ROOT / rel
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            yield rel, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def _body_length(node: ast.AST) -> int:
    """Panjang badan fungsi tanpa docstring (docstring panjang bukan kerumitan)."""
    body = node.body
    if isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    return body[-1].end_lineno - body[0].lineno + 1 if body else 0


def _long_functions(paths: list[str]) -> set[str]:
    found = set()
    for rel, text in _text_files(p for p in paths if p.endswith(".py") and p.startswith(("backend/", "tools/"))):
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _body_length(node) > MAX_FUNCTION_LINES:
                found.add(f"{rel}::{node.name}")
    return found


def test_no_secrets_in_tracked_files():
    hits = [f"{rel}:{i}" for rel, text in _text_files(_tracked_files())
            for i, line in enumerate(text.splitlines(), 1) if SECRET_PATTERN.search(line)]
    assert not hits, f"Pola rahasia di berkas terlacak (nilai tidak dicetak): {hits}"


def test_env_file_is_not_tracked():
    assert "backend/.env" not in _tracked_files()


def test_ui_colors_only_in_tokens():
    web = [p for p in _tracked_files()
           if p.startswith("web/src/") and p.endswith((".svelte", ".ts", ".css"))
           and p != COLOR_SOURCE and ".test." not in p]  # tes boleh memakai warna contoh
    offenders = {rel for rel, text in _text_files(web) if rel not in HEX_COLOR_DEBT
                 and any(HEX_COLOR.search(line) for line in text.splitlines()
                         if not line.strip().startswith(("//", "*", "/*")))}
    assert not offenders, f"Warna hex di luar {COLOR_SOURCE}: {sorted(offenders)}"


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
POSE_INDEX_LITERAL = re.compile(r"(kpts|keypoints|points|pts)\[\s*\d+\s*\]|^\s*(NOSE|LEFT_\w+|RIGHT_\w+)\s*(,\s*\w+\s*)*=\s*\d+",
                                re.MULTILINE)
POSE_SOURCE = "backend/pose_keypoints.py"


def test_indeks_pose_hanya_di_satu_sumber():
    offenders = [rel for rel, text in _text_files(p for p in _tracked_files()
                                                  if p.startswith("backend/") and p.endswith(".py") and p != POSE_SOURCE)
                 if POSE_INDEX_LITERAL.search(text)]
    assert not offenders, f"Indeks titik pose ditulis langsung (pakai {POSE_SOURCE}): {offenders}"
