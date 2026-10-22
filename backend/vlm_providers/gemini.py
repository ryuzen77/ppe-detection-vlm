"""Google Gemini lewat SDK `google-genai` (pengganti `google-generativeai` yang sudah dihentikan)."""

from typing import Any

from .. import messages
from .base import VLMProvider


# Tenggat minimum yang diterima API Gemini untuk satu permintaan
GEMINI_MIN_DEADLINE_SECONDS = 10.0


class GeminiProvider(VLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        thinking_level: str = "",
        http_timeout: float = 0.0,
        temperature: float | None = None,
    ):
        super().__init__(model)
        # None = bawaan model (tidak dikirim); nilai dari config.VLM_TEMPERATURE
        self.temperature = temperature
        # Model Gemini 3.x "berpikir" dulu secara bawaan. Untuk pemeriksaan visual
        # APD itu tidak menambah ketepatan tetapi melipatgandakan latensi (terukur
        # 5,0 dtk vs 1,4 dtk pada gemini-3.5-flash-lite dengan jawaban sama).
        # Kosong = parameter tidak dikirim, untuk model yang tidak mendukungnya.
        self.thinking_level = (thinking_level or "").strip().upper()
        from google import genai  # Impor lambat: SDK hanya dimuat bila penyedia ini dipakai
        from google.genai import types

        self._types = types
        # Membuat klien tidak menghubungi jaringan; kunci yang salah baru ketahuan
        # pada panggilan pertama. Tanpa batas waktu HTTP, panggilan saat Google
        # kelebihan beban menggantung ~60 dtk walau aplikasi sudah berhenti
        # menunggu, dan menyandera thread pemanggil (T27). SDK memakai milidetik.
        # Batas ini dikirim ke server sebagai tenggat, dan Gemini menolak tenggat
        # < 10 dtk ("Minimum allowed deadline is 10s", 400 INVALID_ARGUMENT —
        # terukur 24-09). Aplikasi tetap berhenti menunggu di batasnya sendiri
        # (cloud 4 dtk) lalu beralih ke cadangan; ini hanya melepas thread-nya.
        http_options = (
            types.HttpOptions(timeout=int(max(http_timeout, GEMINI_MIN_DEADLINE_SECONDS) * 1000))
            if http_timeout > 0
            else None
        )
        self._client = genai.Client(api_key=api_key, http_options=http_options)

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
                **self._common(),
            ),
        )
        return response.text or ""

    def ping(self) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=messages.VLM_PING_PROMPT,
            config=self._types.GenerateContentConfig(**self._common()),
        )
        return (response.text or "").strip()

    def _common(self) -> dict[str, Any]:
        # Automatic function calling (model memanggil fungsi Python) aktif secara
        # bawaan di SDK dan memunculkan peringatan "Direct use of automatic
        # function calling" di setiap panggilan, padahal tidak dipakai di sini.
        options: dict[str, Any] = {
            "automatic_function_calling": self._types.AutomaticFunctionCallingConfig(disable=True)
        }
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.thinking_level:
            # SDK menerima nama level berupa str (pydantic mengubahnya ke enum ThinkingLevel)
            options["thinking_config"] = self._types.ThinkingConfig(  # pyright: ignore[reportArgumentType]
                thinking_level=self.thinking_level
            )  # pyright: ignore[reportArgumentType]
        return options
