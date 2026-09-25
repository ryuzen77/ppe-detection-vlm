"""Adaptor OpenAI-compatible diuji terhadap server HTTP lokal yang meniru penyedia."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.config import cfg

from backend.vlm_analyzer import USER_PROMPT, VLMAnalyzer, VLMEngine
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
    provider = _provider(server, temperature=cfg.VLM_TEMPERATURE)
    assert provider.analyze(jpeg, system_prompt="SISTEM", user_prompt="PENGGUNA") == {"ok": True}

    (req,) = server.requests
    assert req["path"] == "/v1/chat/completions"
    assert req["auth"] == "Bearer kunci-uji"
    body = req["body"]
    assert body["model"] == "qwen/qwen2.5-vl-72b-instruct"
    assert body["temperature"] == cfg.VLM_TEMPERATURE
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
def analyzer(catalog_defaults):
    a = VLMAnalyzer()

    def pasang(provider):
        """Utama = penyedia HTTP sungguhan ke server uji lokal; tanpa cadangan."""
        engine = VLMEngine("utama", "openrouter", provider.model, api_key="kunci-uji")
        engine.provider, engine.min_interval = provider, 0.0
        a.primary, a.backup = engine, None

    a.pasang = pasang
    yield a
    if a.primary is not None:
        a.primary.executor.shutdown(wait=False)


def test_keputusan_vlm_lewat_penyedia_openai_compatible(server, analyzer):
    server.reply = {"status": 200, "content": json.dumps({"items": {
        "helm": {"detected": True},
        "rompi": {"detected": True, "is_valid_color": False, "color": "biru"},
        "celana": {"detected": True},
        "sepatu": {"detected": True, "is_closed_shoes": True},
    }, "missing_items": [], "notes": "rompi biru"})}
    analyzer.pasang(_provider(server))

    hasil = analyzer.analyze_person(person_crop())
    assert hasil.decided_by == "utama"
    assert hasil.is_complete is False, "Kelengkapan dihitung sistem dari items, bukan klaim model"
    assert hasil.missing_items == ["Rompi Keselamatan Orange/Kuning"]
    assert server.requests[0]["body"]["messages"][1]["content"][0]["text"] == USER_PROMPT


def test_penyedia_openai_compatible_gagal_tanpa_cadangan_tanpa_keputusan(server, analyzer):
    server.reply = {"status": 503, "content": "overloaded"}
    analyzer.pasang(_provider(server))
    hasil = analyzer.analyze_person(person_crop())
    assert hasil.is_system_unavailable is True and hasil.is_complete is False
    assert len(server.requests) == 1, "Satu panggilan per VLM; kegagalan dialihkan, bukan diulang"
    assert "503" in hasil.notes


def test_batas_waktu_http_terpisah_dari_pemanasan(server):
    # Panggilan inspeksi dibatalkan di batas waktu aplikasi (+1 dtk), tetapi
    # pemuatan model Ollama saat pemanasan boleh jauh lebih lama (T27).
    p = create_provider("ollama", api_key="", model="m", base_url=server.base_url,
                        http_timeout=13.0, warmup_timeout=120.0)
    assert p._client.timeout.read == 13.0
    assert p.warmup_timeout == 120.0


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


# --- Pemanasan (T23) ------------------------------------------------------------------------

def test_pemanasan_ollama_menahan_model_tetap_termuat(server):
    p = create_provider("ollama", api_key="", model="qwen2.5vl:3b", base_url=server.base_url)
    p.warm_up()
    muat, ping = server.requests
    assert muat["path"] == "/api/generate", "API asli Ollama, bukan /v1"
    assert muat["body"] == {"model": "qwen2.5vl:3b", "keep_alive": -1}
    assert ping["path"] == "/v1/chat/completions"


def test_pemanasan_penyedia_cloud_cukup_ping(server):
    _provider(server).warm_up()
    assert [r["path"] for r in server.requests] == ["/v1/chat/completions"]


def test_pemanasan_gagal_tidak_menghentikan_server(server, analyzer):
    server.reply = {"status": 503, "content": "overloaded"}
    analyzer.pasang(_provider(server))
    assert analyzer.warm_up() is None


def test_pemanasan_berhasil_melaporkan_durasi(server, analyzer):
    analyzer.pasang(_provider(server))
    assert analyzer.warm_up() >= 0


def test_tanpa_penyedia_pemanasan_dilewati(analyzer):
    assert analyzer.primary is None and analyzer.backup is None
    assert analyzer.warm_up() is None


def test_temperature_tidak_dikirim_bila_tidak_disetel(server):
    _provider(server).analyze(b"x", system_prompt="S", user_prompt="U")
    assert "temperature" not in server.requests[0]["body"]
