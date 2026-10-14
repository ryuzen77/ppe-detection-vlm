"""Kesehatan VLM lokal (T56): gejala lambat/habis waktu, aplikasi lain di GPU, pemanasan bergambar.

Uji 14-10: VRAM penuh oleh aplikasi lain → Ollama macet padahal /api/ps "100% GPU";
inspeksi pertama setelah pemanasan teks 13 dtk di gerbang (habis waktu 12 dtk).
"""

import json
import subprocess
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend import config as config_mod, gpu_processes, local_model_guard as guard_mod, messages
from backend.config import cfg
from backend.local_model_guard import LocalModelGuard
from backend.vlm_analyzer import USER_PROMPT, VLMAnalyzer, VLMEngine, build_system_prompt
from backend.vlm_providers import VLMProvider

from helpers import person_crop

# --- Proses lain di GPU ---------------------------------------------------------------------

NVSMI = """12572, C:\\Windows\\explorer.exe
13620, C:\\Users\\x\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe
24196, C:\\Users\\x\\AppData\\Local\\Programs\\Ollama\\lib\\ollama\\llama-server.exe
25668, C:\\Users\\x\\AppData\\Local\\Programs\\Ollama\\ollama.exe
7112, C:\\Users\\x\\AppData\\Local\\Discord\\app-1.0\\Discord.exe
7113, C:\\Users\\x\\AppData\\Local\\Discord\\app-1.0\\Discord.exe
555, /usr/bin/python3
bukan baris
"""


def test_daftar_aplikasi_lain_tanpa_proses_gerbang_dan_shell():
    assert gpu_processes.parse_gpu_apps(NVSMI, own_pids={555}) == ["Code.exe", "Discord.exe"]


# Keluaran nyata mode dGPU 15-10 (diringkas): shell Windows & pembantu driver ikut tercantum (T56b)
NVSMI_DGPU = r"""13340, C:\Program Files\NVIDIA Corporation\NVIDIA App\CEF\NVIDIA Overlay.exe
14984, D:\WINDOWS\SystemApps\MicrosoftWindows.Client.CBS_cw5n1h2txyewy\SearchHost.exe
19032, D:\Windows\System32\NahimicSvc64.exe
28484, D:\Windows\ImmersiveControlPanel\SystemSettings.exe
30584, D:\Windows\System32\ShellHost.exe
17244, C:\Program Files (x86)\Microsoft\EdgeWebView\Application\155.0\msedgewebview2.exe
24396, C:\Program Files\WindowsApps\AppUp.IntelGraphicsExperience_1.100_x64\IGCC.exe
24968, C:\Program Files\WindowsApps\A-Volute.Nahimic_1.10_x64\Nahimic3.exe
23904, C:\Program Files\Google\Chrome\Application\chrome.exe
13436, C:\Program Files\WindowsApps\5319275A.WhatsAppDesktop_2.26_x64\WhatsApp.Root.exe
40000, D:\Windowsku\game.exe
"""


def test_proses_bawaan_windows_dan_pembantu_driver_disaring(monkeypatch):
    monkeypatch.setattr(cfg, "LOCAL_GPU_SYSTEM_DIRS", ("d:/windows/",))
    assert gpu_processes.parse_gpu_apps(NVSMI_DGPU, own_pids=set()) == ["chrome.exe", "game.exe", "WhatsApp.Root.exe"]


def test_tanpa_folder_sistem_hanya_daftar_nama_yang_disaring(monkeypatch):
    # Linux: SystemRoot tidak ada → tidak ada folder yang disaring
    monkeypatch.setattr(cfg, "LOCAL_GPU_SYSTEM_DIRS", ())
    assert "SearchHost.exe" in gpu_processes.parse_gpu_apps(NVSMI_DGPU, own_pids=set())


def test_folder_sistem_dari_lingkungan(monkeypatch):
    monkeypatch.setenv("SystemRoot", "E:\\WinNT\\")
    assert config_mod._system_dirs() == ("e:/winnt/",)
    monkeypatch.delenv("SystemRoot")
    monkeypatch.delenv("windir", raising=False)
    assert config_mod._system_dirs() == ()


def test_tanpa_nvidia_smi_daftar_kosong(monkeypatch):
    monkeypatch.setattr(gpu_processes.shutil, "which", lambda name: None)
    assert gpu_processes.other_gpu_apps() == []


def test_nvidia_smi_gagal_daftar_kosong(monkeypatch):
    monkeypatch.setattr(gpu_processes.shutil, "which", lambda name: "nvidia-smi")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("nvidia-smi", 5)

    monkeypatch.setattr(gpu_processes.subprocess, "run", boom)
    assert gpu_processes.other_gpu_apps() == []


# --- Penjaga: gejala & status ------------------------------------------------------------------


class FakeProvider:
    def __init__(self, ratio=1.0):
        self.ratio, self.reloads = ratio, 0

    def gpu_residency(self):
        return self.ratio

    def reload(self):
        self.reloads += 1


class FakeEngine:
    who = "cadangan ollama/qwen2.5vl:7b"

    def __init__(self, provider):
        self.provider, self.warmups = provider, 0

    def warm_up(self):
        self.warmups += 1


@pytest.fixture
def guard(monkeypatch):
    engine = FakeEngine(FakeProvider())
    g = LocalModelGuard(threading.Lock(), lambda: engine)
    g.forced = []
    monkeypatch.setattr(g, "trigger", lambda force=False: g.forced.append(force))
    monkeypatch.setattr(guard_mod.gpu_processes, "other_gpu_apps", lambda: ["Discord.exe"])
    g.engine = engine
    return g


def test_belum_ada_data_status_unknown(guard):
    assert guard.status() == {
        "state": "unknown",
        "gpu_ratio": None,
        "slow_streak": 0,
        "last_latency_s": None,
        "other_gpu_apps": [],
    }
    assert LocalModelGuard(threading.Lock(), lambda: None).status()["state"] == "unknown"


def test_panggilan_normal_status_ok(guard):
    guard.record_call(3.6, now=100.0)
    assert guard.status()["state"] == "ok" and guard.status()["last_latency_s"] == 3.6


def test_lambat_berturut_turut_memicu_muat_ulang_sekali(guard, caplog):
    guard.record_call(cfg.LOCAL_SLOW_SECONDS + 1, now=100.0)
    assert guard.status()["state"] == "ok" and guard.forced == [], "satu kali lambat belum gejala"
    guard.record_call(None, now=101.0)  # habis waktu
    status = guard.status()
    assert status["state"] == "slow" and status["slow_streak"] == 2
    assert guard.forced == [True], "muat ulang paksa walau ollama ps 100% GPU"
    assert status["other_gpu_apps"] == ["Discord.exe"]
    assert any("Discord.exe" in r.getMessage() for r in caplog.records), "operator diberi tahu apa yang ditutup"
    guard.record_call(None, now=102.0)
    assert guard.forced == [True], "tidak berulang selama jeda"
    guard.record_call(None, now=102.0 + cfg.LOCAL_SLOW_RELOAD_COOLDOWN_SECONDS)
    assert guard.forced == [True, True]


def test_panggilan_normal_mengakhiri_gejala(guard):
    guard.record_call(None, now=1.0)
    guard.record_call(None, now=2.0)
    guard.record_call(3.5, now=3.0)
    assert guard.status()["state"] == "ok" and guard.status()["slow_streak"] == 0


def test_sebagian_di_cpu_status_partial(guard):
    guard.engine.provider.ratio = 0.26
    LocalModelGuard.check_and_repair(guard)
    assert guard.status()["state"] == "partial_gpu"


def test_muat_ulang_paksa_lalu_dipanaskan_dengan_gambar(guard):
    assert guard.check_and_repair(force=True) is True
    assert guard.engine.provider.reloads == 1, "porsi GPU 100% tetap dimuat ulang bila dipaksa"
    assert guard.engine.warmups == 1, "model baru dimuat dipanaskan sebelum pekerja berikutnya"


# --- Pemanasan bergambar & pencatatan dari analyzer ---------------------------------------------


def _lengkap():
    return json.dumps(
        {
            "items": {
                "helm": {"detected": True},
                "rompi": {"detected": True, "is_valid_color": True, "color": "orange"},
                "celana": {"detected": True},
                "sepatu": {"detected": True, "is_closed_shoes": True},
            }
        }
    )


class RecordingProvider(VLMProvider):
    name = "palsu"

    def __init__(self, replies=None, delay=0.0):
        super().__init__("model-palsu")
        self.replies, self.delay, self.calls = list(replies or [_lengkap()]), delay, []

    def generate(self, image_jpeg, system_prompt, user_prompt):
        self.calls.append((image_jpeg, system_prompt, user_prompt))
        time.sleep(self.delay)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    def warm_up(self):
        pass

    def ping(self):
        return "PONG"


def _engine(provider, local):
    e = VLMEngine("cadangan" if local else "utama", "ollama" if local else "gemini", "model-palsu", api_key="kunci-uji")
    e.provider, e.min_interval = provider, 0.0
    return e


@pytest.mark.parametrize("local,expected_calls", [(True, 1), (False, 0)])
def test_pemanasan_lokal_memakai_gambar_dan_prompt_produksi(catalog_defaults, local, expected_calls):
    provider = RecordingProvider()
    engine = _engine(provider, local)
    assert engine.warm_up() is not None
    assert len(provider.calls) == expected_calls, "cloud tidak dipanaskan dengan gambar (kuota)"
    if local:
        jpeg, system_prompt, user_prompt = provider.calls[0]
        assert jpeg[:2] == b"\xff\xd8" and system_prompt == build_system_prompt() and user_prompt == USER_PROMPT
    engine.executor.shutdown(wait=False)


def test_jawaban_pemanasan_bukan_json_tidak_menggagalkan(catalog_defaults):
    engine = _engine(RecordingProvider(replies=["bukan json"]), local=True)
    assert engine.warm_up() is not None
    engine.executor.shutdown(wait=False)


def test_analyzer_mencatat_hanya_panggilan_lokal_utama(catalog_defaults, monkeypatch):
    """Konfirmasi rokok tidak ikut dihitung: di lokal ia akan tampak "lambat"."""
    a = VLMAnalyzer()
    data = json.loads(_lengkap())
    data["items"]["rokok"] = {"detected": True}
    a.primary = None
    a.backup = _engine(
        RecordingProvider([json.dumps(data), json.dumps({"detected": True, "seen": "rokok"})]), local=True
    )
    calls = []
    monkeypatch.setattr(a.local_guard, "record_call", lambda latency, now: calls.append(latency))
    a.analyze_person(person_crop())
    assert len(a.backup.provider.calls) == 2 and len(calls) == 1 and calls[0] is not None
    a.backup.executor.shutdown(wait=False)


def test_cadangan_lokal_habis_waktu_dicatat_sebagai_gejala(catalog_defaults, monkeypatch):
    a = VLMAnalyzer()
    a.primary = None
    a.backup = _engine(RecordingProvider(delay=0.5), local=True)
    a.backup.timeout = 0.1
    calls = []
    monkeypatch.setattr(a.local_guard, "record_call", lambda latency, now: calls.append(latency))
    monkeypatch.setattr(a.local_guard, "trigger", lambda force=False: None)
    assert a.analyze_person(person_crop()).is_system_unavailable
    assert calls == [None]
    a.backup.executor.shutdown(wait=False)


def test_health_memuat_status_vlm_lokal():
    from backend.app import app

    body = TestClient(app).get("/api/health").json()
    assert set(body["local_vlm"]) == {"state", "gpu_ratio", "slow_streak", "last_latency_s", "other_gpu_apps"}
    assert body["local_vlm"]["state"] in {"ok", "slow", "partial_gpu", "unknown"}


def test_pesan_lambat_bisa_diformat():
    assert "Discord.exe" in messages.LOCAL_MODEL_SLOW.format(who="x", n=2, latency="habis waktu", apps="Discord.exe")
