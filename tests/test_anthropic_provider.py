"""Adaptor Claude (T28) diuji terhadap server HTTP lokal yang meniru Messages API (tanpa kuota)."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.config import cfg
from backend.vlm_analyzer import VLMEngine
from backend.vlm_providers import create_provider
from backend.vlm_providers.anthropic import API_VERSION, AnthropicProvider


class FakeMessagesServer:
    def __init__(self):
        self.requests = []
        self.reply = {"status": 200, "body": _text_reply('{"ok": true}')}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                payload = json.dumps(outer.reply["body"]).encode()
                self.send_response(outer.reply["status"])
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


def _text_reply(text, stop="end_turn"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": stop}


@pytest.fixture
def server():
    s = FakeMessagesServer()
    yield s
    s.close()


def _provider(server):
    return create_provider("anthropic", api_key="kunci-uji", model="model-uji", base_url=server.base_url,
                           max_tokens=512, temperature=0.1, json_mode=True)


def test_permintaan_messages_api_dengan_gambar_base64(server):
    jpeg = b"\xff\xd8isi-jpeg\xff\xd9"
    assert _provider(server).analyze(jpeg, system_prompt="SISTEM", user_prompt="PENGGUNA") == {"ok": True}
    (req,) = server.requests
    assert req["path"] == "/v1/messages"
    headers = {k.lower(): v for k, v in req["headers"].items()}
    assert headers["x-api-key"] == "kunci-uji" and headers["anthropic-version"] == API_VERSION
    body = req["body"]
    assert (body["model"], body["max_tokens"], body["system"]) == ("model-uji", 512, "SISTEM")
    assert "temperature" not in body, "model Claude terbaru menolak temperature"
    image, text = body["messages"][0]["content"]
    assert image["source"] == {"type": "base64", "media_type": "image/jpeg",
                               "data": base64.b64encode(jpeg).decode()}
    assert text == {"type": "text", "text": "PENGGUNA"}


def test_jawaban_berpagar_json_tetap_diurai(server):
    server.reply["body"] = {"content": [{"type": "thinking", "thinking": ""},
                                        {"type": "text", "text": '```json\n{"ok": true}\n```'}],
                            "stop_reason": "end_turn"}
    assert _provider(server).analyze(b"x", "S", "U") == {"ok": True}


@pytest.mark.parametrize("reply, status, pesan", [
    ({"type": "error", "error": {"message": "invalid x-api-key"}}, 401, "HTTP 401"),
    (_text_reply("", stop="refusal"), 200, "menolak"),
    (_text_reply('{"ok": tr', stop="max_tokens"), 200, "terpotong"),
    (_text_reply("   "), 200, "kosong"),
])
def test_galat_penyedia_dilaporkan_jelas(server, reply, status, pesan):
    server.reply = {"status": status, "body": reply}
    with pytest.raises(RuntimeError, match=pesan):
        _provider(server).generate(b"x", "S", "U")


def test_tanpa_key_ditolak_saat_dirakit():
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="", model="m", base_url="http://127.0.0.1:1", max_tokens=1)


def test_engine_memakai_batas_token_dari_config(server, monkeypatch):
    monkeypatch.setattr(cfg, "VLM_ANTHROPIC_MAX_TOKENS", 777)
    engine = VLMEngine("utama", "anthropic", "model-uji", api_key="kunci-uji", base_url=server.base_url)
    assert engine.build() is True
    engine.provider.ping()
    assert server.requests[-1]["body"]["max_tokens"] == 777
    engine.close()
