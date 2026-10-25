"""Karakterisasi T42l: alat CLI dan bootstrap tanpa kamera, jaringan, atau model."""

import csv
import asyncio
import copy
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _tool_thread(events):
    class Thread:
        def __init__(self, frame=None):
            self.kind = "sampler" if frame is None else "camera"
            self.samples, self.frames = [101, 105], 25
            self.stop_flag = SimpleNamespace(set=lambda: events.append((self.kind, "stop")))

        def start(self):
            events.append((self.kind, "start"))

        def join(self, timeout):
            events.append((self.kind, "join", timeout))

    return Thread


def crop(frame):
    if "absent" in frame:
        return None
    return SimpleNamespace(crop_img=frame, crop_keypoints=[1], is_full_body=True, is_inside_corridor=True, reason="uji")


def _tool_analyzer(events):
    def predict(frame, *_):
        events.append(("predict", Path(frame).stem))
        if "broken" in frame:
            raise ValueError("galat-uji")
        return SimpleNamespace(is_complete=True, missing_items=[])

    class Analyzer:
        def __init__(self):
            self.provider = SimpleNamespace(name="ollama", model="model-uji")
            self.primary = SimpleNamespace(timeout=4)

        def start(self):
            events.append(("analyzer", "start"))

        def is_live_api(self):
            return True

        def warm_up(self):
            events.append(("analyzer", "warm"))
            return 0.5

        _call_vlm_internal = staticmethod(predict)
        _parse_vlm_payload = staticmethod(lambda *_: SimpleNamespace(is_complete=True, missing_items=[]))

    return Analyzer, predict


def _tool_pool(events):
    class Pool:
        def __init__(self, **kwargs):
            events.append(("pool", kwargs))

        def submit(self, fn, *args):
            return SimpleNamespace(result=lambda **_: fn(*args))

        def shutdown(self, **kwargs):
            events.append(("pool", "shutdown", kwargs))

    return Pool


def _patch_tool_helpers(evaluation, bench, Pool, predict, events, monkeypatch):
    monkeypatch.setattr(evaluation, "ThreadPoolExecutor", Pool)
    monkeypatch.setattr(bench, "encode", lambda frame, size: (frame, "640x480"))
    monkeypatch.setattr(bench, "build_prompts", lambda variant, items: (variant, "user"))
    monkeypatch.setattr(bench, "output_format", lambda *_: "json")
    monkeypatch.setattr(bench, "to_production_payload", lambda parsed, *_: parsed)
    monkeypatch.setattr(bench, "confirm_production_smoking", lambda *args: events.append(("confirm", args[1])))
    monkeypatch.setattr(
        bench.httpx, "Client", lambda: SimpleNamespace(close=lambda: events.append(("client", "close")))
    )

    def call(client, model, system, user, image, *args):
        predict(image)
        return {
            "message": {"content": '{"rokok": true}'},
            "prompt_eval_count": 4,
            "eval_count": 2,
            "eval_duration": 2000000,
        }

    monkeypatch.setattr(bench, "call", call)
    monkeypatch.setattr(evaluation.cv2, "imdecode", lambda frame, _: frame)
    monkeypatch.setattr(evaluation.np, "fromfile", lambda path, _: path)
    monkeypatch.setattr(evaluation.detector, "load", lambda: events.append(("detector", "load")))
    monkeypatch.setattr(evaluation.ppe_rules, "load_settings", lambda: events.append(("catalog", "load")))
    monkeypatch.setattr(evaluation.ppe_rules, "get_active_items", lambda: [SimpleNamespace(key="helm")])


def _tool_data(tmp_path):
    data = tmp_path / "input"
    for category, names in (("ppe_complete", ["a_ok.JPG", "b_broken.png", "c_absent.jpeg"]), ("ppe_incomplete", [])):
        (data / category).mkdir(parents=True)
        for name in names:
            (data / category / name).touch()
    return data


@pytest.fixture
def tool_world(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    evaluation = importlib.import_module("eval_vlm")
    bench = importlib.import_module("bench_vlm")
    events = []
    clock = iter(i / 4 for i in range(1000))
    fake_time = SimpleNamespace(
        time=lambda: next(clock), sleep=lambda value: events.append(("sleep", value)), strftime=lambda _: "run"
    )

    settings = SimpleNamespace(
        DATA_DIR=tmp_path / "output",
        VLM_BACKUP_MODEL="model-uji",
        VLM_PROVIDER="ollama",
        VLM_IS_LOCAL=True,
        VLM_MIN_INTERVAL_SECONDS=1,
        VLM_IMAGE_MAX_SIZE=640,
    )
    Thread = _tool_thread(events)
    Analyzer, predict = _tool_analyzer(events)
    Pool = _tool_pool(events)
    for module in (evaluation, bench):
        monkeypatch.setattr(module, "cfg", settings)
        monkeypatch.setattr(module, "time", fake_time)
        monkeypatch.setattr(module, "GpuSampler", Thread)
        monkeypatch.setattr(module, "CameraLoad", Thread)
        monkeypatch.setattr(module, "VLMAnalyzer", Analyzer)
        monkeypatch.setattr(module, "person_crop", crop)
        monkeypatch.setattr(module, "ollama_residency", lambda model: "100% GPU")
        monkeypatch.setattr(module, "unload_ollama", lambda model: events.append(("unload", model)))
    _patch_tool_helpers(evaluation, bench, Pool, predict, events, monkeypatch)
    data = _tool_data(tmp_path)
    return SimpleNamespace(eval=evaluation, bench=bench, events=events, data=data, output=settings.DATA_DIR / "eval")


def read_outputs(world):
    summary = json.loads(next(world.output.glob("*.json")).read_text(encoding="utf-8"))
    with next(world.output.glob("*.csv")).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return summary, rows


def test_eval_main_preserves_results_order_quota_and_shutdown(tool_world, monkeypatch):
    world = tool_world
    monkeypatch.setattr(sys, "argv", ["eval_vlm.py", str(world.data)])
    world.eval.main()
    summary, rows = read_outputs(world)
    assert [(r["file"], r["status"]) for r in rows] == [
        ("ppe_complete/a_ok.JPG", "ok"),
        ("ppe_complete/b_broken.png", "galat"),
        ("ppe_complete/c_absent.jpeg", "tanpa_orang"),
    ]
    assert summary["foto"] == 3 and summary["dikirim"] == 2 and summary["jawaban_valid"] == 1
    assert summary["galat_format_atau_lainnya"] == summary["tanpa_orang"] == 1
    assert summary["akurasi"] == 0.5 and summary["latensi_median_s"] == 0.25
    assert summary["item_aktif"] == ["helm"] and summary["vram_puncak_mb"] == 105
    assert ("sleep", 0.75) in world.events
    assert world.events[-5:] == [
        ("camera", "stop"),
        ("sampler", "stop"),
        ("camera", "join", 5),
        ("pool", "shutdown", {"wait": False}),
        ("unload", "model-uji"),
    ]


def test_bench_main_preserves_variant_order_confirmation_and_shutdown(tool_world, monkeypatch):
    world = tool_world
    monkeypatch.setattr(sys, "argv", ["bench_vlm.py", str(world.data), "--prompts", "P0,P1", "--sizes", "640,full"])
    world.bench.main()
    summary, rows = read_outputs(world)
    assert [r["variant"] for r in rows] == [f"{p}@{s}" for p in ("P0", "P1") for s in ("640", "full") for _ in range(3)]
    assert [r["status"] for r in rows] == ["ok", "galat", "tanpa_orang", "ok", "galat", "ok"] * 2
    assert world.events.count(("confirm", "model-uji")) == 3
    assert summary["varian"]["P0@640"]["jawaban_valid"] == 1
    assert summary["varian"]["P1@full"]["jawaban_valid"] == 2
    assert world.events[-5:] == [
        ("camera", "stop"),
        ("sampler", "stop"),
        ("camera", "join", 5),
        ("client", "close"),
        ("unload", "model-uji"),
    ]


@pytest.mark.parametrize("tool", ["eval", "bench"])
def test_cli_file_filter_keeps_class_order(tool_world, monkeypatch, tool):
    world = tool_world
    monkeypatch.setattr(sys, "argv", ["tool", str(world.data), "--files", "a_ok"])
    getattr(world, tool).main()
    _, rows = read_outputs(world)
    assert rows and {r["file"] for r in rows} == {"ppe_complete/a_ok.JPG"}


@pytest.mark.parametrize("error", [None, KeyboardInterrupt, SystemExit])
def test_app_run_keeps_setup_order(monkeypatch, error):
    module = importlib.import_module("backend.app")
    uvicorn = importlib.import_module("uvicorn")
    events = []

    class Server:
        def __init__(self, config):
            events.append(("construct", config))

        def run(self):
            events.append("run")
            if error:
                raise error()

    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(module, "setup_logging", lambda _: events.append("logging"))
    monkeypatch.setattr(module, "install_shutdown_hook", lambda: events.append("hook"))
    monkeypatch.setattr(module, "server_config", lambda: events.append("config") or "configuration")
    monkeypatch.setattr(module.logger, "info", lambda _: events.append("done"))
    module.run()
    assert events == ["logging", "hook", "config", ("construct", "configuration"), "run", "done"]


def _signal_server(events, body_error):
    class Server:
        def __init__(self, config):
            pass

        def handle_exit(self, *_):
            pass

        def run(self):
            with getattr(self, "capture_signals")():
                events.append("body")
                if body_error:
                    raise RuntimeError("body failed")

    return Server


@pytest.mark.parametrize("body_error", [False, True])
def test_signal_handlers_restore_after_body_and_os_errors(monkeypatch, body_error):
    module = importlib.import_module("backend.app")
    signal = importlib.import_module("signal")
    uvicorn = importlib.import_module("uvicorn")
    events = []

    def change_handler(sig, handler):
        events.append((sig, handler if isinstance(handler, str) else "exit"))
        if sig == 2:
            raise ValueError("signal unavailable")
        if handler == "old-1":
            raise OSError("restore unavailable")
        return f"old-{sig}"

    Server = _signal_server(events, body_error)

    monkeypatch.setattr(signal, "signal", change_handler)
    monkeypatch.setattr(uvicorn.server, "HANDLED_SIGNALS", (1, 2, 3))
    monkeypatch.setattr(uvicorn, "Server", Server)
    monkeypatch.setattr(module, "setup_logging", lambda _: None)
    monkeypatch.setattr(module, "install_shutdown_hook", lambda: None)
    monkeypatch.setattr(module, "server_config", lambda: None)
    if body_error:
        with pytest.raises(RuntimeError, match="body failed"):
            module.run()
    else:
        module.run()
    assert events == [(1, "exit"), (2, "exit"), (3, "exit"), "body", (1, "old-1"), (3, "old-3")]


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("synthetic", [False, True])
@pytest.mark.parametrize("selected", [None, {"fps": 0}, {"fps": 30}])
def test_camera_catalog_preserves_fallback_modes_and_active_flags(monkeypatch, empty, synthetic, selected):
    module = importlib.import_module("backend.api.routes_cameras")
    device = {
        "index": 0,
        "name": "Kamera uji",
        "available": False,
        "scanned": False,
        "in_use": False,
        "modes": [],
        "selected_mode": selected,
    }
    other = {**device, "index": 1, "name": "Kamera kedua", "selected_mode": None}
    catalog = {"devices": [] if empty else copy.deepcopy([device, other]), "scanning": False}
    mode = {"width": 640, "height": 480, "fps": 0}
    active = {"index": 0, "is_synthetic": synthetic, "mode": mode, "fps": 24, "height": 240}
    monkeypatch.setattr(module.camera_mgr, "get_catalog", lambda: catalog)
    monkeypatch.setattr(module.video_service, "get_camera_status", lambda: active)
    monkeypatch.setattr(module.camera_manager, "list_device_names", lambda: ["Kamera uji", "Kamera kedua"])
    monkeypatch.setattr(module.camera_manager, "load_saved_selection", lambda: {"index": 1})
    monkeypatch.setattr(module, "cfg", SimpleNamespace(CAMERA_QUALITY_WARN_HEIGHT=480))
    result = asyncio.run(module.list_cameras())
    expected_selected = selected if not empty and selected else mode
    expected_selected = {**expected_selected, "fps": expected_selected.get("fps") or 24}
    expected_first = {
        **device,
        "available": not synthetic,
        "scanned": True,
        "in_use": True,
        "selected_mode": expected_selected,
    }
    expected_other = {**other, "available": True} if empty else other
    assert result == {
        "devices": [expected_first, expected_other],
        "scanning": False,
        "saved": {"index": 1},
        "active": active,
        "quality_warning": True,
    }
    assert mode["fps"] == 0 and (selected is None or selected["fps"] in (0, 30)), "FPS fallback must copy the mode"


def test_capture_constructor_has_independent_locks_health_and_initial_state():
    module = importlib.import_module("backend.video.capture")
    first, second = module.VideoCaptureService(), module.VideoCaptureService()
    excluded = {"lock", "raw_lock", "_health", "_reader"}
    expected = dict.fromkeys(
        [
            "cap",
            "current_frame_bytes",
            "camera_index",
            "active_mode",
            "_pending_index",
            "_pending_mode",
            "_carry_fault",
            "_waiting_since",
            "latest_raw",
        ]
    )
    expected.update(
        dict.fromkeys(
            [
                "is_running",
                "use_synthetic",
                "camera_name_verified",
                "_pending_optimize",
                "_pending_idle",
                "_device_missing",
            ],
            False,
        )
    )
    expected.update(
        fps=0.0,
        camera_status="IDLE",
        camera_name="",
        camera_error="",
        _missing_reason=module.messages.CAMERA_UNPLUGGED,
        _waiting_logged_at=0.0,
        raw_seq=0,
        frame_width=module.cfg.FRAME_WIDTH,
        frame_height=module.cfg.FRAME_HEIGHT,
    )
    assert {key: value for key, value in vars(first).items() if key not in excluded} == expected
    for key in excluded:
        assert getattr(first, key) is not getattr(second, key)
    assert not first.lock.locked() and not first.raw_lock.locked()
    assert (
        vars(first._reader)
        == vars(second._reader)
        == {
            "lost_mode": None,
            "consecutive_failures": 0,
            "last_reconnect_attempt": 0.0,
            "window_start": 0.0,
            "window_frames": 0,
            "baseline_fps": 0.0,
            "stall_since": None,
            "error_streak": 0,
        }
    )
