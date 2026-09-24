"""Google Gemini lewat SDK `google-genai` (pengganti `google-generativeai` yang sudah dihentikan)."""
from .base import VLMProvider


class GeminiProvider(VLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, thinking_level: str = ""):
        super().__init__(model)
        # Model Gemini 3.x "berpikir" dulu secara bawaan. Untuk pemeriksaan visual
        # APD itu tidak menambah ketepatan tetapi melipatgandakan latensi (terukur
        # 5,0 dtk vs 1,4 dtk pada gemini-3.5-flash-lite dengan jawaban sama).
        # Kosong = parameter tidak dikirim, untuk model yang tidak mendukungnya.
        self.thinking_level = (thinking_level or "").strip().upper()
        from google import genai  # Impor lambat: SDK hanya dimuat bila penyedia ini dipakai
        from google.genai import types

        self._types = types
        # Membuat klien tidak menghubungi jaringan; kunci yang salah baru ketahuan
        # pada panggilan pertama.
        self._client = genai.Client(api_key=api_key)

    def generate(self, image_jpeg: bytes, system_prompt: str, user_prompt: str) -> str:
        types = self._types
        response = self._client.models.generate_content(
            model=self.model,
            contents=[user_prompt, types.Part.from_bytes(data=image_jpeg, mime_type="image/jpeg")],
            # Prompt sistem dikirim per panggilan, jadi perubahan item APD aktif
            # langsung berlaku tanpa membuat klien ulang.
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.1,
                **self._thinking(),
            ),
        )
        return response.text or ""

    def ping(self) -> str:
        response = self._client.models.generate_content(
            model=self.model, contents="Ping. Jawab 'PONG'.",
            config=self._types.GenerateContentConfig(**self._thinking()),
        )
        return (response.text or "").strip()

    def _thinking(self) -> dict:
        if not self.thinking_level:
            return {}
        return {"thinking_config": self._types.ThinkingConfig(thinking_level=self.thinking_level)}
