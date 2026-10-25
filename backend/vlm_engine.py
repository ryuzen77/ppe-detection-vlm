"""Mesin VLM dan gambar bersama; lock inspeksi/pergantian tetap dimiliki VLMAnalyzer."""

import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import cv2
import numpy as np
from .config import cfg
from . import messages, vlm_selection, vlm_image
from .api_monitor import ROLE_EMERGENCY
from .local_model_guard import UNLOADED, LOADING, READY, FAILED
from .vlm_providers import create_provider
from .vlm_providers import profiles as vlm_profiles
from .vlm_selection import Choice, ROLE_PRIMARY
from .vlm_prompt import USER_PROMPT, build_system_prompt, thinking_option, profile_warnings

logger = logging.getLogger(__name__)


def image_for_vlm(crop_bgr: np.ndarray, keypoints: Optional[list] = None, zoom: bool = False) -> bytes:
    """JPEG yang dikirim ke VLM: tubuh + panel kepala (T86, `zoom`), atau tubuh saja (isi T58 persis).

    Bytes ini dikirim apa adanya ke penyedia, tanpa didekode dan dikompres ulang.
    """
    if zoom:
        image = vlm_image.compose(crop_bgr, keypoints)
    else:
        image = vlm_image.fit_body(crop_bgr)
    return cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.VLM_JPEG_QUALITY])[1].tobytes()


def warmup_image_jpeg(zoom: bool = False) -> bytes:
    """Gambar sintetis seukuran gambar pemeriksaan (termasuk panel T86), tanpa foto orang.

    Dipakai pemanasan VLM lokal (T56) dan uji latensi Pengaturan (T86): ukuran & bentuknya sama
    dengan yang dikirim gerbang, jadi waktu yang terukur mewakili pemeriksaan sungguhan.
    """
    h, w = cfg.VLM_WARMUP_IMAGE_HEIGHT, cfg.VLM_WARMUP_IMAGE_WIDTH
    crop = np.tile(np.linspace(40, 200, h).astype(np.uint8)[:, None, None], (1, w, 3))
    return image_for_vlm(crop, zoom=zoom)


class LaneBusy(Exception):
    """Pekerja di jalur (atau inspeksi tak kunjung selesai): penyedia tidak diganti."""


class EngineFailed(Exception):
    """Engine baru gagal dirakit/dipanaskan: engine lama tetap dipakai."""


class VLMEngine:
    """Satu VLM (utama atau cadangan): adaptor penyedia + batas waktu + jeda kuota.

    Batas waktu mengikuti letak model (cloud pendek, lokal longgar) dan dipasang
    juga di klien HTTP, sehingga panggilan yang melewatinya benar-benar
    dibatalkan alih-alih menggantung dan menyandera thread.
    """

    def __init__(self, role: str, provider_name: str, model: str, api_key: str = "", base_url: str = ""):
        self.role = role
        self.provider_name = (provider_name or "").strip().lower()
        self.model_name = model or ""
        self.api_key = (api_key or "").strip()
        self.base_url = base_url or ""
        self.is_local = vlm_profiles.is_local(self.provider_name)
        self.timeout = cfg.VLM_LOCAL_TIMEOUT_SECONDS if self.is_local else cfg.VLM_CLOUD_TIMEOUT_SECONDS
        self.min_interval = 0.0 if self.is_local else cfg.VLM_MIN_INTERVAL_SECONDS
        self.provider = None
        self.error = ""
        self.warm_error = ""
        self.last_call_time = 0.0
        self.last_call_ok: Optional[bool] = None
        self._warm_future = None
        self.warm_state, self.warm_since = UNLOADED, time.strftime(cfg.TELEMETRY_TIME_FORMAT)
        self.executor = ThreadPoolExecutor(max_workers=cfg.VLM_MAX_CONCURRENT, thread_name_prefix=f"VLM_{role}")

    @property
    def who(self) -> str:
        """Identitas lengkap untuk log, mis. "utama gemini/gemini-3.5-flash-lite".

        Nama penyedia & model hanya ditulis di log (dan Pengaturan admin), tidak di
        tampilan operator — keputusan pengguna."""
        return f"{self.role} {self.provider_name}/{self.model_name}"

    @property
    def label(self) -> str:
        if self.role == ROLE_EMERGENCY:
            return f"{vlm_selection.LOCAL_FALLBACK_SOURCE_PREFIX}{self.provider_name}/{self.model_name}"
        prefix = "VLM_LIVE" if self.role == ROLE_PRIMARY else "VLM_CADANGAN"
        return f"{prefix}:{self.provider_name}/{self.model_name}"

    def build(self) -> bool:
        """Merakit adaptor penyedia. Tidak ada panggilan jaringan."""
        self.provider = None
        if not self.is_local and not self.api_key:
            self.error = f"API key {self.provider_name} belum disetel"
        elif not self.model_name:
            self.error = f"model untuk penyedia '{self.provider_name}' belum diisi"
        else:
            try:
                self.provider = create_provider(
                    self.provider_name, api_key=self.api_key, model=self.model_name, **self._adapter_options()
                )
                self.error = ""
            except Exception as e:
                self.error = vlm_selection.redact(str(e), self.api_key)
        if self.provider is None:
            logger.warning(f"VLM {self.role} ({self.provider_name}) nonaktif: {self.error}")
        else:
            logger.info(
                f"VLM {self.role} siap: {self.provider_name} ({self.model_name}), batas waktu {self.timeout:g} dtk"
            )
            for warning in profile_warnings(self.provider_name, self.model_name, self.who):
                logger.warning(warning)
        return self.provider is not None

    def _adapter_options(self) -> dict:
        # Klien HTTP dibatalkan sedikit sesudah batas waktu aplikasi
        common = {"http_timeout": self.timeout + 1.0, "temperature": cfg.VLM_TEMPERATURE}
        if self.provider_name == "gemini":
            return {**common, "thinking_level": thinking_option(self.provider_name, cfg.VLM_THINKING) or ""}
        options = {
            **common,
            "base_url": self.base_url,
            "json_mode": cfg.VLM_JSON_MODE,
            "warmup_timeout": cfg.VLM_WARMUP_TIMEOUT_SECONDS,
        }
        profile = vlm_profiles.get_profile(self.provider_name)
        if profile is not None and profile.api == vlm_profiles.API_ANTHROPIC:
            options["max_tokens"] = cfg.VLM_ANTHROPIC_MAX_TOKENS
        return options

    def matches(self, choice: Choice) -> bool:
        """Engine ini sudah melayani pilihan itu dengan key & alamat yang sama (boleh dipakai ulang)."""
        return (
            self.provider is not None
            and (self.provider_name, self.model_name) == (choice.provider, choice.model)
            and self.api_key == vlm_selection.api_key_for(choice.provider, self.role)
            and self.base_url == vlm_selection.base_url_for(choice.provider, self.role)
        )

    def choice(self) -> Choice:
        return Choice(self.provider_name, self.model_name)

    def close(self, unload: bool = False):
        """Melepas thread engine yang sudah diganti; panggilan yang berjalan tidak dipotong.
        `unload` (T70): model lokal juga dikeluarkan dari GPU, di latar supaya admin tidak menunggu."""
        self.executor.shutdown(wait=False)
        if unload and self.is_local and self.provider is not None:
            threading.Thread(target=self._unload, name="VLM_Unload", daemon=True).start()

    def _unload(self):
        try:
            self.provider.unload()  # pyright: ignore[reportOptionalMemberAccess] (dicek di close)
            logger.info(messages.LOG_VLM_LOCAL_UNLOADED.format(who=self.who))
        except Exception as e:
            logger.warning(messages.LOG_VLM_LOCAL_UNLOAD_FAILED.format(who=self.who, error=e))

    def local_key(self) -> tuple:
        """Model lokal yang sama = penyedia, alamat, dan nama model sama."""
        return self.provider_name, self.base_url, self.model_name

    def warm_up(self) -> Optional[float]:
        self.warm_error = ""
        if self.provider is None:
            return None
        self._set_warm_state(LOADING)
        start = time.time()
        try:
            self._warm_future = self.executor.submit(self.provider.warm_up)
            self._warm_future.result(timeout=cfg.VLM_WARMUP_TIMEOUT_SECONDS)
            if self.is_local:
                self._warm_with_image()
        except Exception as e:
            self._set_warm_state(FAILED)
            self.warm_error = (
                vlm_selection.redact(str(e), self.api_key)[: cfg.ERROR_MESSAGE_MAX_CHARS] or type(e).__name__
            )
            # Tidak fatal: server tetap menyala; VLM ini dicoba lagi pada pekerja
            # pertama dan, bila gagal, inspeksi dialihkan ke VLM lain (T27).
            logger.warning(
                f"Pemanasan VLM {self.role} {self.provider_name} gagal ({self.warm_error}). "
                f"Server tetap berjalan; VLM ini dicoba lagi saat inspeksi."
            )
            return None
        duration = time.time() - start
        self._set_warm_state(READY)
        logger.info(
            f"Pemanasan VLM {self.role} {self.provider_name} ({self.model_name}) selesai dalam {duration:.1f} dtk."
        )
        return duration

    def _set_warm_state(self, state: str):
        self.warm_state, self.warm_since = state, time.strftime(cfg.TELEMETRY_TIME_FORMAT)

    @property
    def warm_pending(self) -> bool:
        return self._warm_future is not None and not self._warm_future.done()

    def _warm_with_image(self):
        """Satu panggilan seperti inspeksi (prompt produksi + gambar), hanya untuk VLM lokal:
        ping teks meninggalkan penyandi gambar & prompt sistem "dingin" sehingga pekerja
        pertama habis waktu (uji 14-10: 13 dtk > batas 12). Cloud tidak, karena memakan kuota."""
        start = time.time()
        provider = self.provider
        assert provider is not None, "pemanasan hanya untuk engine yang siap"
        future = self.executor.submit(
            provider.analyze, warmup_image_jpeg(), system_prompt=build_system_prompt(), user_prompt=USER_PROMPT
        )
        self._warm_future = future
        try:
            future.result(timeout=cfg.VLM_WARMUP_TIMEOUT_SECONDS)
        except ValueError:
            pass  # jawaban untuk gambar sintetis tidak dipakai; yang penting GPU sudah bekerja
        logger.info(messages.LOCAL_MODEL_WARMUP_IMAGE.format(who=self.who, seconds=time.time() - start))

    def call(self, image_jpeg: bytes, system_prompt: str, user_prompt: str) -> dict:
        """Satu panggilan dengan batas waktu keras. Galat & timeout dilempar ke pemanggil."""
        wait = self.min_interval - (time.time() - self.last_call_time)
        if wait > 0:
            logger.info(f"Menunggu jeda kuota {wait:.1f} dtk sebelum panggilan VLM {self.role}.")
            time.sleep(wait)
        provider = self.provider
        assert provider is not None, "call() hanya untuk engine yang siap"
        try:
            future = self.executor.submit(
                provider.analyze, image_jpeg, system_prompt=system_prompt, user_prompt=user_prompt
            )
            return future.result(timeout=self.timeout)
        finally:
            # Dicatat untuk panggilan gagal juga, agar jeda kuota tetap berlaku
            self.last_call_time = time.time()

    def info(self) -> dict:
        """Untuk dashboard. Tidak pernah menyertakan API key."""
        return {
            "role": self.role,
            "provider": self.provider_name,
            "model": self.model_name,
            "is_local": self.is_local,
            "needs_key": not self.is_local,
            "has_key": bool(self.api_key),
            "is_live": self.provider is not None,
            "timeout_s": self.timeout,
            "error": self.error,
            # T39b, untuk Pengaturan admin (T28): resmi/eksperimental & status validasi model
            "support": getattr(vlm_profiles.get_profile(self.provider_name), "support", None),
            "validated": vlm_profiles.validation_status(
                self.provider_name, self.model_name, vlm_selection.prompt_version_for(self.provider_name)
            ),
        }
