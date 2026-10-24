"""Batas modul murni dan kompatibilitas fasad setelah pemisahan T99a."""

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend import vlm_analyzer, vlm_prompt, vlm_result


@pytest.mark.parametrize(
    "module,names",
    [
        (vlm_result, ("ItemResult", "InspectionResult", "APDInspectionResult")),
        (
            vlm_prompt,
            (
                "USER_PROMPT",
                "build_system_prompt",
                "confirmation_prompts",
                "parse_confirmation",
                "thinking_option",
                "profile_warnings",
            ),
        ),
    ],
)
def test_public_facade_keeps_original_objects(module, names):
    for name in names:
        assert getattr(vlm_analyzer, name) is getattr(module, name)


def test_parser_facade_keeps_static_call_without_wrapper():
    parser = inspect.getattr_static(vlm_analyzer.VLMAnalyzer, "_parse_vlm_payload")
    assert isinstance(parser, staticmethod)
    assert parser.__func__ is vlm_result._parse_vlm_payload


def test_thinking_warning_uses_prompt_module_logger(monkeypatch):
    warnings = []
    monkeypatch.setattr(vlm_prompt.logger, "warning", warnings.append)
    assert vlm_prompt.thinking_option("gemini", "nilai-tiruan-tidak-sah") == "minimal"
    assert len(warnings) == 1


_PURE_IMPORT_PROBE = """
import json, sys, threading
before = {thread.ident for thread in threading.enumerate()}
from backend import vlm_result, vlm_prompt
print(json.dumps({
    "analyzer_imported": "backend.vlm_analyzer" in sys.modules,
    "new_threads": len({thread.ident for thread in threading.enumerate()} - before),
    "adapters_imported": any(name in sys.modules for name in (
        "backend.vlm_providers.gemini", "backend.vlm_providers.anthropic",
        "backend.vlm_providers.openai_compatible")),
}))
"""


def test_pure_imports_do_not_create_engines_threads_or_storage(tmp_path):
    data_dir = tmp_path / "not_created"
    env = {**os.environ, "DATA_DIR": str(data_dir)}
    result = subprocess.run(
        [sys.executable, "-c", _PURE_IMPORT_PROBE],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip()) == {
        "analyzer_imported": False,
        "new_threads": 0,
        "adapters_imported": False,
    }
    assert not data_dir.exists()
