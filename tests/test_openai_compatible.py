"""Adaptor OpenAI-compatible diuji terhadap server HTTP lokal yang meniru penyedia."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.config import cfg
from backend.vlm_analyzer import USER_PROMPT, VLMAnalyzer
from backend.vlm_providers import create_provider
from backend.vlm_providers.openai_compatible import PRESETS, OpenAICompatibleProvider

from helpers import person_crop


class FakeProviderServer:
    """Server /v1/chat/completions yang mencatat permintaan dan membalas sesuai skenario."""

    def __init__(self):
        self.requests = []
        self.reply = {"status": 200, "content": '{"ok": true}'}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
                r = outer.reply
                if r["status"] != 200:
                    payload = json.dumps({"error": {"message": r["content"]}}).encode()
                elif r.get("raw") is not None:
                    payload = json.dumps(r["raw"]).encode()
                else:
                    payload = json.dumps({"choices": [{"message": {"role": "assistant", "content": r["content"]}}]}).encode()
                self.send_response(r["status"])
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server():
    s = FakeProviderServer()
    yield s
    s.close()


def _provider(server, **kw):
    return create_provider("openrouter", api_key=kw.pop("api_key", "kunci-uji"), model="qwen/qwen2.5-vl-72b-instruct",
                           base_url=server.base_url, **kw)


# --- Bentuk permintaan --------------------------------------------------------------

def test_permintaan_berformat_openai_dengan_gambar_base64(server):
    jpeg = b"\xff\xd8isi-jpeg-uji\xff\xd9"
    assert _provider(server).analyze(jpeg, system_prompt="SISTEM", user_prompt="PENGGUNA") == {"ok": True}

    (req,) = server.requests
    assert req["path"] == "/v1/chat/completions"
    assert req["auth"] == "Bearer kunci-uji"
    body = req["body"]
    assert body["model"] == "qwen/qwen2.5-vl-72b-instruct"
    assert body["temperature"] == 0.1
    assert body["response_format"] == {"type": "json_object"}
    system, user = body["messages"]
    assert system == {"role": "system", "content": "SISTEM"}
    teks, gambar = user["content"]
    assert teks == {"type": "text", "text": "PENGGUNA"}
    url = gambar["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == jpeg, "Gambar harus terkirim utuh"


def test_model_lokal_tanpa_kunci_tidak_mengirim_authorization(server):
    create_provider("ollama", api_key="", model="qwen2.5vl", base_url=server.base_url).analyze(b"x", "S", "U")
    assert server.requests[0]["auth"] is None


def test_json_mode_bisa_dimatikan_untuk_server_yang_tidak_mengenalnya(server):
    _provider(server, json_mode=False).analyze(b"x", "S", "U")
    assert "response_format" not in server.requests[0]["body"]


def test_ping_teks_saja(server):
    server.reply = {"status": 200, "content": " PONG "}
    assert _provider(server).ping() == "PONG"
    assert server.requests[0]["body"]["messages"] == [{"role": "user", "content": "Ping. Jawab 'PONG'."}]


# --- Jawaban -------------------------------------------------------------------------

def test_content_berupa_daftar_bagian_digabung(server):
    server.reply = {"status": 200, "raw": {"choices": [{"message": {"content": [
        {"type": "text", "text": '{"a": '}, {"type": "text", "text": "1}"}]}}]}}
    assert _provider(server).analyze(b"x", "S", "U") == {"a": 1}


def test_galat_http_menyertakan_pesan_penyedia(server):
    server.reply = {"status": 401, "content": "Invalid API key"}
    with pytest.raises(RuntimeError) as e:
        _provider(server).analyze(b"x", "S", "U")
    assert "401" in str(e.value) and "Invalid API key" in str(e.value)


def test_bentuk_jawaban_asing_ditolak(server):
    server.reply = {"status": 200, "raw": {"hasil": "aneh"}}
    with pytest.raises(RuntimeError):
        _provider(server).analyze(b"x", "S", "U")


# --- Pemilihan penyedia -------------------------------------------------------------------

@pytest.mark.parametrize("nama", ["openai", "openrouter", "qwen", "deepseek", "ollama"])
def test_preset_alamat_bawaan(nama):
    p = create_provider(nama, api_key="k", model="m")
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.base_url == PRESETS[nama].rstrip("/")
    assert p.name == nama


def test_base_url_eksplisit_menang_atas_preset():
    p = create_provider("qwen", api_key="k", model="m", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/")
    assert p.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_vllm_wajib_diberi_base_url():
    with pytest.raises(ValueError):
        create_provider("vllm", api_key="", model="m")


# --- Jalur VLMAnalyzer lengkap lewat HTTP ------------------------------------------------

@pytest.fixture
def analyzer(catalog_defaults, monkeypatch):
    monkeypatch.setattr(cfg, "FREE_TIER_MIN_INTERVAL_SECONDS", 0.0)
    a = VLMAnalyzer()
    a.api_key = "kunci-uji"
    yield a
    a.executor.shutdown(wait=False)


def test_keputusan_vlm_lewat_penyedia_openai_compatible(server, analyzer):
    server.reply = {"status": 200, "content": json.dumps({"items": {
        "helm": {"detected": True},
        "rompi": {"detected": True, "is_valid_color": False, "color": "biru"},
        "celana": {"detected": True},
        "sepatu": {"detected": True, "is_closed_shoes": True},
    }, "missing_items": [], "notes": "rompi biru"})}
    analyzer.provider = _provider(server)

    hasil = analyzer.analyze_person(person_crop())
    assert hasil.is_complete is False, "Kelengkapan dihitung sistem dari items, bukan klaim model"
    assert hasil.missing_items == ["Rompi Keselamatan Orange/Kuning"]
    assert server.requests[0]["body"]["messages"][1]["content"][0]["text"] == USER_PROMPT


def test_penyedia_openai_compatible_gagal_dicoba_ulang_lalu_ditolak(server, analyzer):
    server.reply = {"status": 503, "content": "overloaded"}
    analyzer.provider = _provider(server)
    hasil = analyzer.analyze_person(person_crop())
    assert hasil.is_unverified is True
    assert len(server.requests) == cfg.VLM_MAX_ATTEMPTS
    assert "503" in hasil.notes


def test_jawaban_kosong_hanya_berpikir_diberi_pesan_jelas(server):
    # Perilaku nyata qwen3-vl:4b di Ollama 0.34 (T22): content kosong, isi di "reasoning"
    server.reply = {"status": 200, "raw": {"choices": [{"message": {
        "role": "assistant", "content": "", "reasoning": "<think>Orang memakai helm..."}}]}}
    with pytest.raises(RuntimeError, match="tanpa mode berpikir"):
        _provider(server).analyze(b"x", "S", "U")


def test_jawaban_kosong_ditolak(server):
    server.reply = {"status": 200, "content": ""}
    with pytest.raises(RuntimeError, match="kosong"):
        _provider(server).analyze(b"x", "S", "U")
