"""Penyedia berformat OpenAI Chat Completions dengan input gambar.

Satu adaptor untuk OpenRouter, Qwen-VL (DashScope compatible-mode), DeepSeek,
OpenAI, dan model lokal lewat Ollama/vLLM. Syaratnya satu: model yang dipilih
harus menerima gambar.
"""
import base64

import httpx

from .. import messages
from . import profiles
from .base import VLMProvider

# Alamat bawaan per penyedia, dari katalog profil (T39b). VLM_BASE_URL selalu menang.
PRESETS = {name: p.base_url for name, p in profiles.PROFILES.items() if p.api == profiles.API_OPENAI_COMPATIBLE}


class OpenAICompatibleProvider(VLMProvider):
    def __init__(self, api_key: str, model: str, base_url: str, name: str = "openai",
                 json_mode: bool = True, http_timeout: float = 60.0, warmup_timeout: float = 120.0,
                 temperature: float | None = None):
        super().__init__(model)
        if not base_url:
            raise ValueError(f"Penyedia '{name}' butuh base URL (VLM_BASE_URL).")
        self.name = name
        self.base_url = base_url.rstrip("/")
        # Tidak semua server mengenal response_format; bisa dimatikan tanpa
        # kehilangan penguraian JSON karena prompt sudah meminta JSON.
        self.json_mode = json_mode
        headers = {"Content-Type": "application/json"}
        if api_key:
            # Model lokal (Ollama/vLLM) umumnya tidak memakai kunci
            headers["Authorization"] = f"Bearer {api_key}"
        # Batas waktu HTTP = batas waktu inspeksi (+ sedikit), supaya panggilan
        # yang lewat batas dibatalkan dan tidak menyandera thread. Pemuatan model
        # saat pemanasan jauh lebih lama, jadi memakai batasnya sendiri.
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=http_timeout)
        self.warmup_timeout = warmup_timeout
        # None = bawaan server (tidak dikirim); nilai dari config.VLM_TEMPERATURE
        self.temperature = temperature

    def generate(self, image_jpeg: bytes, system_prompt: str, user_prompt: str) -> str:
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
        }
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        return self._chat(body)

    def warm_up(self):
        if self.name == "ollama":
            # Ollama melepas model dari GPU setelah 5 menit menganggur, sehingga
            # pekerja pertama setelah gerbang sepi menunggu ~38 dtk (terukur T22)
            # dan ditolak karena timeout. keep_alive=-1 pada API asli Ollama
            # memuat model sekarang dan menahannya selama server Ollama hidup.
            self._keep_alive(-1)
        self.ping()

    def _keep_alive(self, seconds: int):
        """API asli Ollama: -1 = muat & tahan di GPU, 0 = keluarkan dari GPU sekarang."""
        response = self._client.post(f"{self._ollama_root()}/api/generate",
                                     json={"model": self.model, "keep_alive": seconds}, timeout=self.warmup_timeout)
        if response.status_code >= 400:
            raise RuntimeError(f"{self.name} HTTP {response.status_code}: {response.text[:300]}")

    def _ollama_root(self) -> str:
        return self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url

    def gpu_residency(self):
        """Porsi model di VRAM menurut `/api/ps` Ollama; 0 bila model tidak dimuat."""
        if self.name != "ollama":
            return None
        response = self._client.get(f"{self._ollama_root()}/api/ps", timeout=self.warmup_timeout)
        response.raise_for_status()
        names = {self.model, self.model if ":" in self.model else f"{self.model}:latest"}
        for m in response.json().get("models", []):
            if m.get("name") in names or m.get("model") in names:
                size = m.get("size") or 0
                return min(1.0, (m.get("size_vram") or 0) / size) if size else 0.0
        return 0.0

    def reload(self):
        """Bongkar lalu muat lagi; Ollama mengulang pencarian GPU saat memuat."""
        if self.name != "ollama":
            return
        for seconds in (0, -1):
            self._keep_alive(seconds)

    def unload(self):
        """Cadangan dimatikan (T70): model keluar dari VRAM sekarang, bukan menunggu Ollama restart
        (model dimuat dengan keep_alive=-1, jadi tanpa ini tetap di GPU selamanya)."""
        if self.name == "ollama":
            self._keep_alive(0)

    def ping(self) -> str:
        return self._chat({
            "model": self.model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": messages.VLM_PING_PROMPT}],
        }).strip()

    def _chat(self, body: dict) -> str:
        response = self._client.post("/chat/completions", json=body)
        if response.status_code >= 400:
            # Pesan penyedia ikut dilaporkan, supaya log menunjukkan alasannya
            # (kunci salah, model tanpa dukungan gambar, kuota habis, ...).
            raise RuntimeError(f"{self.name} HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"{self.name}: bentuk jawaban tidak dikenal: {str(data)[:300]}")
        # Sebagian server mengembalikan content sebagai daftar bagian
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not (content or "").strip():
            message = data["choices"][0]["message"]
            if message.get("reasoning") or message.get("reasoning_content"):
                # Terukur pada qwen3-vl:4b di Ollama 0.34: model tetap "berpikir"
                # walau diminta tidak, lalu berhenti sebelum menulis jawaban.
                raise RuntimeError(f"{self.name}: model {self.model} hanya mengirim proses berpikir tanpa jawaban; "
                                   f"pilih model vision tanpa mode berpikir (mis. qwen2.5vl).")
            raise RuntimeError(f"{self.name}: model {self.model} mengirim jawaban kosong.")
        return content
