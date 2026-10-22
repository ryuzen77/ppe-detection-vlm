"""Claude lewat Messages API Anthropic (T28).

Ditulis dengan `httpx` yang sudah dipakai adaptor lain, bukan SDK `anthropic`,
supaya tidak menambah dependensi (keputusan rancangan T28 yang disetujui).
"""

import base64

import httpx

from .. import messages
from .base import VLMProvider

API_VERSION = "2023-06-01"
STOP_REFUSAL = "refusal"
STOP_MAX_TOKENS = "max_tokens"


class AnthropicProvider(VLMProvider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        max_tokens: int,
        http_timeout: float = 60.0,
        warmup_timeout: float = 120.0,
    ):
        super().__init__(model)
        if not api_key:
            raise ValueError("Penyedia 'anthropic' butuh API key (ANTHROPIC_API_KEY).")
        # `temperature` sengaja tidak dikirim: model Claude terbaru menolaknya (400);
        # konsistensi jawaban dijaga prompt JSON yang ketat.
        self.max_tokens = max_tokens
        self.warmup_timeout = warmup_timeout
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=http_timeout,
            headers={"x-api-key": api_key, "anthropic-version": API_VERSION, "content-type": "application/json"},
        )

    def generate(self, image_jpeg: bytes, system_prompt: str, user_prompt: str) -> str:
        image = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(image_jpeg).decode("ascii"),
            },
        }
        return self._messages(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": [image, {"type": "text", "text": user_prompt}]}],
            }
        )

    def ping(self) -> str:
        return self._messages(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": messages.VLM_PING_PROMPT}],
            }
        ).strip()

    def _messages(self, body: dict) -> str:
        response = self._client.post("/v1/messages", json=body)
        if response.status_code >= 400:
            # Pesan penyedia ikut dilaporkan (key salah, model tak dikenal, kuota habis, ...)
            raise RuntimeError(f"{self.name} HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        stop = data.get("stop_reason")
        if stop == STOP_REFUSAL:
            raise RuntimeError(f"{self.name}: model {self.model} menolak permintaan (refusal).")
        if stop == STOP_MAX_TOKENS:
            raise RuntimeError(f"{self.name}: jawaban terpotong batas token ({self.max_tokens}).")
        text = "".join(
            block.get("text", "")
            for block in data.get("content") or []
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if not text.strip():
            raise RuntimeError(f"{self.name}: model {self.model} mengirim jawaban kosong.")
        return text
