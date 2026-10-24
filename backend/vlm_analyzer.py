import logging
import time
import cv2
import numpy as np
import threading
from dataclasses import asdict
from typing import Callable, Optional, List
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager, nullcontext
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import cfg
from .local_model_guard import LocalModelGuard, LocalStandby, UNLOADED, LOADING, READY, FAILED
from .api_monitor import api_monitor, ROLE_EMERGENCY
from .internet_monitor import InternetMonitor, NORMAL, SLOW, DISCONNECTED, is_connection_failure
from . import messages
from . import ppe_rules
from . import vlm_selection
from . import vlm_image
from .vlm_providers import profiles as vlm_profiles
from .vlm_providers import create_provider
from .vlm_selection import Choice, Selection, ROLE_PRIMARY, ROLE_BACKUP

logger = logging.getLogger(__name__)


class ItemResult(BaseModel):
    """Hasil pemeriksaan satu item APD.

    Bentuknya sengaja longgar: syarat tambahan seperti `is_valid_color` (rompi)
    atau `is_closed_shoes` (sepatu) masuk sebagai field ekstra sesuai definisi
    di `ppe_rules`, bukan sebagai kelas khusus per item. Dengan begitu item APD
    baru tidak memerlukan kelas model baru.
    """

    model_config = ConfigDict(extra="allow")

    detected: bool = Field(default=False, description="Apakah item terdeteksi dipakai")
    color: str = Field(default="", description="Warna item bila relevan")
    description: str = Field(default="", description="Keterangan singkat item")

    @model_validator(mode="before")
    @classmethod
    def _null_means_not_given(cls, data):
        """`null` dari VLM = nilai tidak diisi, jadi nilai bawaan yang berlaku.

        Gemini menjawab `"color": null` untuk orang tanpa rompi (T39a). Tanpa ini
        seluruh jawaban gagal divalidasi, dianggap kegagalan VLM utama, dilempar ke
        cadangan, dan dua kali berturut-turut membuat pemutus sirkuit menganggap
        utama mati. Syarat (qualifier) yang null dianggap tidak terpenuhi.
        """
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class InspectionResult(BaseModel):
    """Hasil inspeksi APD lengkap, dikunci pada katalog `ppe_rules`."""

    items: dict[str, ItemResult] = Field(default_factory=dict, description="Hasil per item APD, dikunci nama item")
    is_complete: bool = Field(default=False, description="True jika seluruh item wajib terpenuhi")
    missing_items: List[str] = Field(default_factory=list, description="Nama APD yang belum memenuhi syarat")
    notes: str = Field(default="", description="Ringkasan hasil inspeksi dalam Bahasa Indonesia")
    inference_source: str = Field(
        default="",
        description="Sumber keputusan: VLM_LIVE:<penyedia>/<model> (utama) atau VLM_CADANGAN:<penyedia>/<model>",
    )
    inference_time_ms: float = Field(default=0.0, description="Durasi inspeksi dalam milidetik")
    decided_by: str = Field(default="", description="VLM yang memutuskan: 'utama' atau 'cadangan'")
    is_system_unavailable: bool = Field(
        default=False,
        description="True jika utama dan cadangan sama-sama gagal: TIDAK ada keputusan, pekerja diminta menunggu",
    )

    def item(self, key: str) -> ItemResult:
        """Hasil satu item; item yang tidak dinilai dianggap tidak terdeteksi."""
        return self.items.get(key) or ItemResult()


# Nama lama dipertahankan sebagai alias supaya modul lain yang mengimpornya
# tidak perlu diubah pada task ini.
APDInspectionResult = InspectionResult


_SPOOF_MARKER = "bukan orang fisik"


def _is_spoof_rejection(missing_items) -> bool:
    """Apakah model menolak subjek sebagai foto/layar, dengan ejaan apa pun."""
    return any(isinstance(m, str) and _SPOOF_MARKER in m.casefold() for m in (missing_items or []))


# Nama lama dipertahankan untuk pemakai (tes, alat evaluasi); isinya di messages.py
USER_PROMPT = messages.VLM_USER_PROMPT


def build_system_prompt(items=None, zoom: bool = False) -> str:
    """Prompt inspektur K3, dirakit dari item APD yang sedang aktif.

    Sebelumnya prompt ini ditulis tangan sehingga setiap perubahan item APD
    harus disunting manual di sini, terpisah dari tempat lain yang menyimpan
    daftar item yang sama. Kini dirakit ulang setiap kali operator menghidupkan
    atau mematikan item, jadi item mati tidak pernah ditanyakan ke model.
    """
    items = items if items is not None else ppe_rules.get_active_items()
    prompt = messages.VLM_SYSTEM_PROMPT.format(
        rules=ppe_rules.build_prompt_rules(items),
        json_shape=ppe_rules.build_json_shape(items),
    )
    return prompt + (_zoom_note() if zoom else "")


def _zoom_note() -> str:
    """Penjelas panel perbesaran (T86), hanya untuk gambar berpanel (lihat vlm_selection.uses_zoom)."""
    return messages.VLM_ZOOM_NOTE if cfg.VLM_ZOOM_HAND_PANELS else messages.VLM_ZOOM_NOTE_HEAD


def image_for_vlm(crop_bgr: np.ndarray, keypoints: Optional[list] = None, zoom: bool = False) -> bytes:
    """JPEG yang dikirim ke VLM: tubuh + panel kepala (T86, `zoom`), atau tubuh saja (isi T58 persis).

    Bytes ini dikirim apa adanya ke penyedia, tanpa didekode dan dikompres ulang.
    """
    if zoom:
        image = vlm_image.compose(crop_bgr, keypoints)
    else:
        image = vlm_image.fit_body(crop_bgr)
    return cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.VLM_JPEG_QUALITY])[1].tobytes()


def _engine_jpeg(engine: "VLMEngine", crop: np.ndarray, keypoints: Optional[list]) -> bytes:
    """T86: gambar per engine — berpanel untuk VLM online, tubuh saja (isi T58 persis) untuk lokal."""
    return image_for_vlm(crop, keypoints, vlm_selection.uses_zoom(engine.provider_name))


def warmup_image_jpeg(zoom: bool = False) -> bytes:
    """Gambar sintetis seukuran gambar pemeriksaan (termasuk panel T86), tanpa foto orang.

    Dipakai pemanasan VLM lokal (T56) dan uji latensi Pengaturan (T86): ukuran & bentuknya sama
    dengan yang dikirim gerbang, jadi waktu yang terukur mewakili pemeriksaan sungguhan.
    """
    h, w = cfg.VLM_WARMUP_IMAGE_HEIGHT, cfg.VLM_WARMUP_IMAGE_WIDTH
    crop = np.tile(np.linspace(40, 200, h).astype(np.uint8)[:, None, None], (1, w, 3))
    return image_for_vlm(crop, zoom=zoom)


def confirmation_prompts(item, zoom: bool = False) -> tuple[str, str]:
    """(prompt sistem, prompt pengguna) konfirmasi kedua satu larangan (T58)."""
    return messages.VLM_CONFIRM_SYSTEM_PROMPT + (
        _zoom_note() if zoom else ""
    ), f"{item.confirm_prompt}\n{messages.VLM_CONFIRM_SHAPE}"


def parse_confirmation(data) -> tuple[bool, str]:
    """(larangan benar terlihat, benda yang disebut model). Selain `true` tegas = tidak terlihat."""
    if not isinstance(data, dict):
        return False, ""
    return data.get("detected") is True, str(data.get("seen") or "")


def thinking_option(provider_name: str, level: str) -> Optional[str]:
    """Nilai mode berpikir untuk adaptor; peringatan bila tidak dikenal/tidak didukung (T39b)."""
    if level not in vlm_profiles.THINKING_LEVELS:
        logger.warning(
            messages.VLM_THINKING_INVALID.format(value=level, choices=", ".join(vlm_profiles.THINKING_LEVELS))
        )
        level = "off"
    value = vlm_profiles.thinking_value(provider_name, level)
    if value is None and level != "off":
        logger.warning(messages.VLM_THINKING_UNSUPPORTED.format(value=level, provider=provider_name))
    return value


def profile_warnings(provider_name: str, model: str, who: str) -> list[str]:
    """Peringatan katalog profil & validasi model. Gerbang tetap menyala (keputusan pengguna)."""
    warnings = []
    profile = vlm_profiles.get_profile(provider_name)
    if profile is not None and profile.support == vlm_profiles.EXPERIMENTAL:
        warnings.append(messages.VLM_PROVIDER_EXPERIMENTAL.format(who=who))
    version = vlm_selection.prompt_version_for(provider_name)
    status = vlm_profiles.validation_status(provider_name, model, version)
    record = vlm_profiles.find_validation(provider_name, model, version)
    if status == vlm_profiles.UNVALIDATED:
        warnings.append(messages.VLM_MODEL_UNVALIDATED.format(who=who))
        return warnings
    assert record is not None or status == vlm_profiles.VALIDATED, "status lain berasal dari catatan validasi"
    if status == vlm_profiles.UNSAFE and record is not None:
        warnings.append(messages.VLM_MODEL_UNSAFE.format(who=who, missed=record.missed, photos=record.photos))
    elif status == vlm_profiles.OUTDATED and record is not None:
        warnings.append(messages.VLM_MODEL_OUTDATED.format(who=who, old=record.prompt_version, current=version))
    elif status == vlm_profiles.PARTIAL and record is not None:
        warnings.append(messages.VLM_MODEL_PARTIAL.format(who=who, note=record.note))
    return warnings


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


class VLMAnalyzer:
    """Keputusan APD oleh VLM: utama dulu, cadangan otomatis bila utama gagal (T27).

    - Utama gagal (galat, JSON rusak, atau lewat batas waktu) -> cadangan dipakai
      di inspeksi yang SAMA; pekerja tidak perlu mengulang.
    - Setelah VLM_PRIMARY_FAILURES_BEFORE_DOWN kegagalan berturut-turut, utama
      dianggap terputus dan dilewati; dicoba lagi pada pekerja nyata setelah
      VLM_PRIMARY_RETRY_AFTER_SECONDS (tanpa panggilan uji yang memakan kuota).
    - Keduanya gagal -> TIDAK ada keputusan (`is_system_unavailable`): pekerja
      tidak diloloskan dan tidak ditolak, melainkan diminta menunggu.
    """

    def __init__(self):
        self.primary: Optional[VLMEngine] = None
        self.backup: Optional[VLMEngine] = None
        self.local_fallback: Optional[VLMEngine] = None
        # Satu inspeksi pada satu waktu; permintaan lain menunggu gilirannya
        self.api_lock = threading.Lock()
        self.primary_failures = 0
        self.primary_down_since: Optional[float] = None
        self.primary_last_attempt = 0.0
        # Menjaga model lokal tetap penuh di GPU setelah crash Ollama (T38)
        self.standby = LocalStandby(self.api_lock, api_monitor.set_local)
        self.internet = InternetMonitor(on_change=self._internet_changed)
        self._internet_state = None
        self._internet_recovered = threading.Event()
        self._services_on = self._started = False
        self.local_guard = LocalModelGuard(self.api_lock, self._local_engine, self._start_services, self._stop_services)
        # Satu pergantian penyedia pada satu waktu (T28)
        self.apply_lock = threading.Lock()
        self.selection_source = vlm_selection.SOURCE_ENV

    def start(self):
        """Merakit VLM utama & cadangan: pilihan dashboard bila ada, selain itu .env (T28)."""
        selection = vlm_selection.effective_selection()
        self.primary = self._new_engine(ROLE_PRIMARY, selection.primary)
        self.backup = self._new_engine(ROLE_BACKUP, selection.backup) if selection.backup else None
        self.local_fallback = (
            self._new_engine(ROLE_EMERGENCY, selection.local_fallback) if selection.local_fallback else None
        )
        self._started = True
        self._configure_standby()
        self.selection_source = selection.source
        self._reset_breaker()
        self._publish_status()
        self._release_stale_local_model()

    def _release_stale_local_model(self):
        """Tanpa VLM lokal aktif, model lokal sisa sesi lalu tidak boleh tetap memakai GPU (T70/T71).

        Ollama proses terpisah & model dimuat dengan keep_alive=-1, jadi model sesi lalu tetap di
        VRAM walau server dimulai ulang. Uji 19-10: `.env` tanpa cadangan (bawaan sejak T71)
        dulu melewati pembersihan ini sehingga model tertinggal. Diperiksa di latar supaya start
        tidak menunggu Ollama.
        """
        if self.standby.engine is not None:
            self.standby.ensure_cold()
            return
        if self.primary is not None and self.primary.is_local:
            return
        stale = self._new_engine(ROLE_BACKUP, self._stale_local_choice())
        threading.Thread(target=self._unload_if_loaded, args=(stale,), name="VLM_StaleUnload", daemon=True).start()

    @staticmethod
    def _stale_local_choice() -> Choice:
        """Model lokal yang mungkin tertinggal: cadangan lokal di .env, selain itu model bawaan Ollama."""
        if vlm_profiles.is_local(cfg.VLM_BACKUP_PROVIDER):
            return Choice(cfg.VLM_BACKUP_PROVIDER, cfg.VLM_BACKUP_MODEL)
        provider = cfg.VLM_LOCAL_BACKUP_PROVIDER
        return Choice(provider, vlm_profiles.default_model(provider))

    @staticmethod
    def _unload_if_loaded(engine: VLMEngine):
        """Dikeluarkan hanya bila memang dimuat (`/api/ps`). Ollama tak terpasang/tak menyala
        bukan masalah di gerbang tanpa cadangan, jadi cukup dicatat di debug."""
        try:
            loaded = engine.provider is not None and bool(engine.provider.gpu_residency())
        except Exception as e:
            logger.debug(messages.LOG_VLM_STALE_CHECK_SKIPPED.format(who=engine.who, error=e))
            loaded = False
        engine.close(unload=loaded)

    @staticmethod
    def _new_engine(role: str, choice: Choice) -> VLMEngine:
        engine = VLMEngine(
            role,
            choice.provider,
            choice.model,
            vlm_selection.api_key_for(choice.provider, role),
            vlm_selection.base_url_for(choice.provider, role),
        )
        engine.build()
        return engine

    def _reset_breaker(self):
        self.primary_failures = 0
        self.primary_down_since = None
        self.primary_last_attempt = 0.0

    def _configure_standby(self):
        engine = None
        if self.primary is None or not self.primary.is_local:
            engine = next((e for e in (self.local_fallback, self.backup) if e is not None and e.is_local), None)
        self.standby.configure(engine)
        self.internet.configure(engine is not None)
        if self._services_on and engine is not None:
            self.internet.start()
            if cfg.VLM_LOCAL_PRELOAD:
                self.standby.request()
            else:
                self.standby.ensure_cold()

    def _internet_changed(self, status: dict):
        if self._internet_state in (SLOW, DISCONNECTED) and status["state"] == NORMAL:
            self._internet_recovered.set()
        self._internet_state = status["state"]
        api_monitor.set_internet(status)
        self.standby.internet_changed(status["state"])

    def _start_services(self):
        self._services_on = True
        self.standby.start()
        if self.standby.engine is not None:
            self.internet.start()

    def _stop_services(self):
        self._services_on = False
        self.internet.stop()
        self.standby.stop()

    def _local_status(self) -> dict:
        if self.primary is not None and self.primary.is_local:
            return {"role": None, "state": self.primary.warm_state, "since": self.primary.warm_since}
        return self.standby.status()

    # --- Ganti penyedia dari dashboard (T28)
    def active_choices(self) -> list[Choice]:
        return [e.choice() for e in (self.primary, self.backup, self.local_fallback) if e is not None]

    def current_selection(self) -> dict:
        """Bentuk `current` kontrak T28. Tanpa API key."""

        def sel(engine):
            return None if engine is None else {**asdict(engine.choice()), "source": self.selection_source}

        return {"primary": sel(self.primary), "backup": sel(self.backup), "local_fallback": sel(self.local_fallback)}

    def apply_selection(
        self, selection: Selection, lane_empty: Callable[[], bool], client: str = "", user: str = ""
    ) -> dict:
        """Menukar engine utama & cadangan tanpa restart.

        Engine baru dirakit & dipanaskan DULU (di luar gembok inspeksi); gagal =
        engine lama tetap dipakai (`EngineFailed`). Pertukaran terjadi di bawah
        gembok inspeksi, jadi inspeksi yang sedang berjalan selesai dengan engine
        lama, dan hanya bila jalur kosong (`LaneBusy`).
        """
        with self.apply_lock, self._local_operation():
            fresh = self._prepare_selection(selection)
            try:
                old = self._swap(fresh, selection.source, lane_empty)
            except Exception:
                self._discard(fresh, keep=(self.primary, self.backup, self.local_fallback))
                raise
            self._discard(old, keep=fresh)
            for role, before, after in zip((ROLE_PRIMARY, ROLE_BACKUP, ROLE_EMERGENCY), old, fresh):
                before_choice, after_choice = before.choice() if before else None, after.choice() if after else None
                if before_choice != after_choice:
                    vlm_selection.record_change(role, before_choice, after_choice, selection.source, client, user)
            return self.current_selection()

    @contextmanager
    def _local_operation(self):
        # Menunggu pemuat di luar api_lock: inspeksi online tetap berjalan.
        if not self.standby.model_lock.acquire(timeout=cfg.LOCAL_GPU_REPAIR_WAIT_SECONDS):
            raise LaneBusy(messages.VLM_SELECT_LANE_BUSY)
        try:
            yield
        finally:
            self.standby.model_lock.release()

    def _prepare_selection(self, selection: Selection) -> tuple:
        fresh = []
        try:
            for role, choice in zip(
                (ROLE_PRIMARY, ROLE_BACKUP, ROLE_EMERGENCY),
                (selection.primary, selection.backup, selection.local_fallback),
            ):
                fresh.append(self._prepare(role, choice) if choice else None)
        except Exception:
            self._discard(tuple(fresh), keep=(self.primary, self.backup, self.local_fallback))
            raise
        return tuple(fresh)

    def _prepare(self, role: str, choice: Choice) -> VLMEngine:
        """Engine siap pakai: yang sedang berjalan bila sama persis, selain itu rakit + panaskan."""
        for engine in (self.primary, self.backup, self.local_fallback):
            if engine is not None and engine.role == role and engine.matches(choice):
                return engine
        engine = self._new_engine(role, choice)
        cold = engine.is_local and role != ROLE_PRIMARY
        if engine.provider is None or (not cold and self._warm_prepared(engine) is None):
            engine.close()
            raise EngineFailed(
                messages.VLM_SELECT_ENGINE_FAILED.format(
                    role=role, provider=choice.provider, model=choice.model, error=engine.error or engine.warm_error
                )
            )
        return engine

    def _warm_prepared(self, engine: VLMEngine) -> Optional[float]:
        if not engine.is_local:
            return engine.warm_up()
        if not self.api_lock.acquire(timeout=cfg.LOCAL_GPU_REPAIR_WAIT_SECONDS):
            engine.close()
            raise LaneBusy(messages.VLM_SELECT_LANE_BUSY)
        try:
            return engine.warm_up()
        finally:
            self.api_lock.release()

    def _swap(self, fresh: tuple, source: str, lane_empty: Callable[[], bool]) -> tuple:
        lock_wait = sum(e.timeout + e.min_interval for e in self._engines()) + 1.0
        if not self.api_lock.acquire(timeout=lock_wait):
            raise LaneBusy(messages.VLM_SELECT_LANE_BUSY)
        try:
            if not lane_empty():
                raise LaneBusy(messages.VLM_SELECT_LANE_BUSY)
            old = (self.primary, self.backup, self.local_fallback)
            self.primary, self.backup, self.local_fallback = fresh
            self._configure_standby()
            self.selection_source = source
            self._reset_breaker()
        finally:
            self.api_lock.release()
        self._publish_status()
        return old

    def _discard(self, engines: tuple, keep: tuple):
        """Engine yang tidak dipakai lagi dilepas; model lokalnya dikeluarkan dari GPU kecuali model
        yang sama masih dipakai engine yang dipertahankan (T70: cadangan mati = benar-benar mati)."""
        kept_local = {k.local_key() for k in keep if k is not None and k.is_local}
        for engine in engines:
            if engine is not None and all(engine is not k for k in keep):
                engine.close()
                if engine.is_local and engine.local_key() not in kept_local:
                    threading.Thread(target=self._unload_unused, args=(engine,), name="VLM_Unload", daemon=True).start()

    def _unload_unused(self, engine: VLMEngine):
        with self.standby.model_lock, self.api_lock:
            if not any(active.is_local and active.local_key() == engine.local_key() for active in self._engines()):
                engine._unload()

    def test_choice(self, role: str, choice: Choice) -> dict:
        """Tombol "Uji": 1 ping + 1 gambar sintetis lewat engine sementara (memakai kuota penyedia).

        `ok` = penyedia menjawab; `json_ok` = jawaban gambar berupa JSON yang bisa diurai.
        Engine gerbang yang sedang berjalan tidak disentuh.
        """
        guard = self._local_operation() if vlm_profiles.is_local(choice.provider) else nullcontext()
        with self.apply_lock, guard:
            return self._test_choice(role, choice)

    def _test_choice(self, role: str, choice: Choice) -> dict:
        engine = self._new_engine(role, choice)
        unload = engine.is_local and engine.provider is not None and not self._tested_local_is_in_use(engine)
        try:
            if engine.provider is None:
                return {"ok": False, "latency_ms": None, "json_ok": False, "error": engine.error}
            start = time.time()
            provider = engine.provider
            ping_error = self._attempt(
                engine, lambda: engine.executor.submit(provider.ping).result(timeout=engine.timeout)
            )
            latency = round((time.time() - start) * 1000, 1)
            if ping_error:
                return {"ok": False, "latency_ms": latency, "json_ok": False, "error": ping_error}
            json_error = self._attempt(
                engine,
                lambda: engine.call(self._test_image(), system_prompt=build_system_prompt(), user_prompt=USER_PROMPT),
            )
            return {"ok": True, "latency_ms": latency, "json_ok": not json_error, "error": json_error}
        finally:
            engine.close()
            if unload:
                self._unload_test_engine(engine)

    def _tested_local_is_in_use(self, engine: VLMEngine) -> bool:
        return any(
            active.is_local
            and active.local_key() == engine.local_key()
            and (not self.standby.owns(active) or self.standby.state != UNLOADED)
            for active in self._engines()
        )

    def _unload_test_engine(self, engine: VLMEngine):
        # Tidak membongkar saat panggilan uji yang habis waktu masih menyelesaikan I/O.
        engine.executor.shutdown(wait=True)
        with self.api_lock:
            engine._unload()

    def _attempt(self, engine: VLMEngine, call: Callable[[], object]) -> str:
        """Kosong bila berhasil, selain itu alasan singkat untuk Pengaturan admin."""
        try:
            call()
            return ""
        except Exception as e:
            return vlm_selection.redact(self._describe(e, engine), engine.api_key)[: cfg.ERROR_MESSAGE_MAX_CHARS]

    def _test_image(self) -> bytes:
        side = cfg.VLM_TEST_IMAGE_PX
        return self._optimize_image_for_vlm(np.full((side, side // 2, 3), 128, dtype=np.uint8))

    # --- Kompatibilitas: atribut penyedia utama dibaca tes, alat evaluasi, dan dashboard
    @property
    def provider(self):
        return self.primary.provider if self.primary else None

    @property
    def provider_name(self) -> str:
        return self.primary.provider_name if self.primary else cfg.VLM_PROVIDER

    @property
    def model_name(self) -> str:
        return self.primary.model_name if self.primary else cfg.VLM_MODEL

    @property
    def api_key(self) -> str:
        return self.primary.api_key if self.primary else ""

    @property
    def source_label(self) -> str:
        """Label sumber keputusan utama untuk audit, mis. VLM_LIVE:gemini/gemini-3.5-flash-lite."""
        return self.primary.label if self.primary else ""

    def _local_engine(self) -> Optional[VLMEngine]:
        """Engine lokal (Ollama) yang dijaga porsi GPU-nya: cadangan, atau utama bila lokal."""
        for e in (self.local_fallback, self.backup, self.primary):
            if e is not None and e.is_local and e.provider is not None and self.standby.ready(e):
                if e is self.primary and self._started and e.warm_state != READY:
                    continue
                return e
        return None

    def _engines(self) -> list[VLMEngine]:
        return [e for e in (self.primary, self.backup, self.local_fallback) if e is not None and e.provider is not None]

    def is_live_api(self) -> bool:
        """Ada setidaknya satu VLM yang siap memutuskan."""
        return bool(self._engines())

    def warm_up(self) -> Optional[float]:
        """Utama tetap dipanaskan; lokal cadangan/darurat dingin kecuali preload diaktifkan."""
        result = self.primary.warm_up() if self.primary else None
        if self.backup is not None and not self.backup.is_local:
            self.backup.warm_up()
        if cfg.VLM_LOCAL_PRELOAD:
            self.standby.preload()
        self._publish_status()
        return result

    def provider_info(self) -> dict:
        """VLM utama (bidang tingkat atas, bentuk lama) + cadangan. Tanpa API key."""
        info = (
            self.primary.info()
            if self.primary
            else {
                "role": ROLE_PRIMARY,
                "provider": cfg.VLM_PROVIDER,
                "model": cfg.VLM_MODEL,
                "is_local": cfg.VLM_IS_LOCAL,
                "needs_key": not cfg.VLM_IS_LOCAL,
                "has_key": False,
                "is_live": False,
                "timeout_s": 0,
                "error": "belum dimulai",
            }
        )
        info["backup"] = self.backup.info() if self.backup else None
        info["primary_down"] = self.primary_down_since is not None
        return info

    def ping_api(self) -> dict:
        """Uji latensi Pengaturan: setiap VLM aktif (utama & cadangan, online maupun lokal).

        T86: dulu hanya ping teks — uji 20-10 "latensi aman" (±0,5 dtk) padahal pemeriksaan foto
        5 dtk lebih & habis waktu. Kini tiap engine menilai gambar contoh seukuran pemeriksaan,
        lewat antrean yang sama dengan gerbang (tidak berebut kuota/GPU dengan pekerja).
        """
        if not self.api_lock.acquire(timeout=cfg.VLM_PING_LOCK_WAIT_SECONDS):
            return {"status": "BUSY", "latency_ms": 0, "message": messages.VLM_PING_BUSY, "engines": []}
        try:
            # Diambil SETELAH lock (tinjauan Codex T86): pergantian penyedia (_swap) juga di bawah lock
            # lalu menutup engine lama, jadi daftar sebelum lock bisa berisi engine yang sudah ditutup.
            engines = self._engines()
            if not engines:
                return {"status": "OFFLINE", "latency_ms": 0, "message": messages.VLM_NOT_CONFIGURED, "engines": []}
            results = [self._ping_engine(engine) for engine in engines]
        finally:
            self.api_lock.release()
        first = results[0]
        message = "; ".join(
            f"{r['role']}: {'OK ' + str(r['latency_ms']) + ' ms' if r['ok'] else 'gagal (' + r.get('error', '') + ')'}"
            for r in results
        )
        return {
            "status": "ONLINE" if first["ok"] else "ERROR",
            "latency_ms": first["latency_ms"],
            "message": message,
            "engines": results,
        }

    def _ping_engine(self, engine: VLMEngine) -> dict:
        """Satu engine menilai gambar contoh; jeda kuota dijalani SEBELUM stopwatch dimulai."""
        if not self.standby.ready(engine):
            return {
                "role": engine.role,
                "ok": False,
                "latency_ms": 0,
                "error": (
                    messages.VLM_LOCAL_STANDBY_UNLOADED
                    if self.standby.state == UNLOADED
                    else messages.VLM_LOCAL_NOT_READY
                ),
                "is_local": True,
                "timeout_ms": round(engine.timeout * 1000),
                "standby": self.standby.state == UNLOADED,
            }
        wait = engine.min_interval - (time.time() - engine.last_call_time)
        if wait > 0:
            time.sleep(wait)
        start = time.time()
        error = self._attempt(engine, lambda: self._call_answered(engine))
        return {
            "role": engine.role,
            "ok": not error,
            "latency_ms": round((time.time() - start) * 1000, 1),
            "error": error,
            "is_local": engine.is_local,
            "timeout_ms": round(engine.timeout * 1000),
            "standby": False,
        }

    @staticmethod
    def _call_answered(engine: VLMEngine):
        """Panggilan inspeksi atas gambar contoh. Jawaban yang tiba tetapi bukan JSON tetap
        dihitung menjawab: yang diukur di sini kecepatan, bukan isi penilaian."""
        try:
            zoom = vlm_selection.uses_zoom(engine.provider_name)
            engine.call(warmup_image_jpeg(zoom), system_prompt=build_system_prompt(zoom=zoom), user_prompt=USER_PROMPT)
        except ValueError:
            pass

    # --- Pemutus sirkuit utama
    def _has_backup(self) -> bool:
        return any(e is not None and e.provider is not None for e in (self.backup, self.local_fallback))

    def _primary_allowed(self, now: float) -> bool:
        if self.primary is None or self.primary.provider is None:
            return False
        # T87: pemutus sirkuit hanya melewati utama bila ada cadangan aktif
        if not self._has_backup():
            return True
        if self.primary_failures < cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN:
            return True
        return now - self.primary_last_attempt >= cfg.VLM_PRIMARY_RETRY_AFTER_SECONDS

    def _primary_result(self, ok: bool, now: float):
        self.standby.primary_result(ok)
        primary = self.primary
        assert primary is not None, "hanya dipanggil setelah utama dicoba"
        if ok:
            if self.primary_down_since is not None:
                logger.info(
                    messages.LOG_VLM_PRIMARY_RECOVERED.format(who=primary.who, seconds=now - self.primary_down_since)
                )
            self.primary_failures = 0
            self.primary_down_since = None
            return
        self.primary_failures += 1
        if self.primary_failures >= cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN and self.primary_down_since is None:
            self.primary_down_since = now
            if self._has_backup():
                logger.warning(
                    messages.LOG_VLM_PRIMARY_DOWN_BACKUP.format(
                        who=primary.who,
                        count=self.primary_failures,
                        retry=cfg.VLM_PRIMARY_RETRY_AFTER_SECONDS,
                    )
                )
            else:
                logger.warning(
                    messages.LOG_VLM_PRIMARY_DOWN_NO_BACKUP.format(
                        who=primary.who,
                        count=self.primary_failures,
                    )
                )

    def _publish_status(self):
        api_monitor.set_internet(self.internet.status())
        api_monitor.set_local(self._local_status())
        api_monitor.set_emergency(self.local_fallback.info() if self.local_fallback else None)
        api_monitor.set_engines(
            primary=self.primary.info() if self.primary else None,
            backup=self.backup.info() if self.backup else None,
            primary_down=self.primary_down_since is not None,
        )

    def _try(self, engine: VLMEngine, image_jpeg: bytes, aktif) -> InspectionResult:
        call_start = time.time()
        try:
            data = self._timed_call(engine, image_jpeg, aktif)
            result = self._confirm_prohibitions(engine, image_jpeg, self._parse_vlm_payload(data, aktif), aktif)
        except TimeoutError:
            engine.last_call_ok = False
            api_monitor.record_failure(engine.role, f"timeout > {engine.timeout:g} dtk", is_timeout=True)
            raise
        except Exception as e:
            engine.last_call_ok = False
            api_monitor.record_failure(engine.role, vlm_selection.redact(str(e), engine.api_key))
            raise
        engine.last_call_ok = True
        api_monitor.record_success(engine.role, round((time.time() - call_start) * 1000, 1))
        result.inference_source = engine.label
        result.decided_by = engine.role
        return result

    def _timed_call(self, engine: VLMEngine, image_jpeg: bytes, aktif) -> dict:
        """Panggilan inspeksi; untuk VLM lokal waktunya dicatat ke penjaga T56 (hanya panggilan
        ini, bukan konfirmasi larangan — konfirmasi rokok di lokal akan tampak "lambat")."""
        start = time.time()
        try:
            zoom = vlm_selection.uses_zoom(engine.provider_name)
            data = engine.call(image_jpeg, system_prompt=build_system_prompt(aktif, zoom), user_prompt=USER_PROMPT)
        except Exception:
            if engine.is_local:
                self.local_guard.record_call(None, time.time())
            raise
        if engine.is_local:
            self.local_guard.record_call(time.time() - start, time.time())
        return data

    def _confirm_prohibitions(
        self, engine: VLMEngine, image_jpeg: bytes, result: InspectionResult, aktif
    ) -> InspectionResult:
        """Larangan yang terlihat ditanyakan ulang dengan pertanyaan khusus (T58).

        Pekerja ditolak karena larangan hanya bila kedua jawaban sepakat. Bench 13-10:
        jawaban pertama menyebut tangan bernoda semen "rokok menyala"; pertanyaan khusus
        menjawab "tangan kosong". Pemeriksaan tanpa larangan terlihat tidak bertambah panggilan.
        """
        flagged = [item for item in aktif if item.prohibited and result.item(item.key).detected]
        if not flagged:
            return result
        for item in flagged:
            confirmed, seen = self._ask_confirmation(engine, image_jpeg, item)
            result.items[item.key] = ItemResult(detected=confirmed, description=seen)
        return self._reevaluate(result, aktif)

    @staticmethod
    def _ask_confirmation(engine: VLMEngine, image_jpeg: bytes, item) -> tuple[bool, str]:
        """Jawaban ragu = tidak terlihat (keputusan pengguna 13-10: VLM ragu = tidak ada).

        Panggilan GAGAL (galat, habis waktu, jawaban rusak) bukan jawaban ragu: dilempar sebagai
        kegagalan VLM ini, sehingga cadangan memeriksa ulang atau pekerja diminta menunggu (T86,
        keputusan pengguna 20-10). Uji banding 20-10: rokok di mulut terlihat di pemeriksaan
        pertama, tetapi konfirmasi habis waktu lalu dianggap "tidak terlihat" -> pekerja lolos.
        """
        try:
            zoom = vlm_selection.uses_zoom(engine.provider_name)
            confirmed, seen = parse_confirmation(engine.call(image_jpeg, *confirmation_prompts(item, zoom)))
        except Exception as e:
            logger.warning(
                messages.LOG_VLM_CONFIRM_FAILED.format(
                    item=item.key,
                    who=engine.who,
                    error=vlm_selection.redact(str(e), engine.api_key)[: cfg.ERROR_MESSAGE_MAX_CHARS]
                    or type(e).__name__,
                )
            )
            raise
        if confirmed:
            logger.info(f"Larangan '{item.key}' dikonfirmasi VLM {engine.who}: {seen}")
        else:
            logger.warning(f"Larangan '{item.key}' dibatalkan konfirmasi VLM {engine.who}: terlihat '{seen}'.")
        return confirmed, seen

    @staticmethod
    def _reevaluate(result: InspectionResult, aktif) -> InspectionResult:
        """Hitung ulang kelengkapan setelah item berubah; penolakan anti-spoofing dipertahankan."""
        is_complete, missing = ppe_rules.evaluate({k: v.model_dump() for k, v in result.items.items()}, aktif)
        if ppe_rules.SPOOF_MISSING_LABEL in result.missing_items:
            missing, is_complete = [ppe_rules.SPOOF_MISSING_LABEL] + missing, False
        result.is_complete, result.missing_items = is_complete, missing
        return result

    @staticmethod
    def _describe(e: Exception, engine: VLMEngine) -> str:
        if isinstance(e, TimeoutError):
            return f"timeout > {engine.timeout:g} dtk"
        return f"galat: {vlm_selection.redact(str(e), engine.api_key)[: cfg.ERROR_MESSAGE_MAX_CHARS]}"

    def analyze_person(self, person_crop_bgr: np.ndarray, keypoints: Optional[list] = None) -> InspectionResult:
        """Keputusan APD untuk satu crop pekerja (lihat docstring kelas)."""
        start_t = time.time()
        if not self._engines():
            return self._no_decision(start_t, messages.VLM_NOT_CONFIGURED)
        internet = self.internet.status()
        if self.standby.state == LOADING and (
            vlm_selection.requires_local_route(internet["state"], internet["median_ms"]) or not self._online_available()
        ):
            return self._no_decision(start_t, messages.VLM_LOCAL_NOT_READY)

        # Terburuk: utama habis waktu, lalu cadangan menjawab + satu konfirmasi larangan (T58)
        slots = [e.timeout + e.min_interval for e in self._engines()]
        lock_wait = sum(slots) + max(slots) + 1.0
        if not self.api_lock.acquire(timeout=lock_wait):
            return self._no_decision(start_t, messages.VLM_QUEUE_FULL)

        api_monitor.set_locked(True)
        try:
            # Satu potret item aktif untuk seluruh inspeksi, supaya prompt dan
            # penilaian jawaban memakai daftar yang sama walau operator mengubahnya.
            aktif = ppe_rules.get_active_items()
            reasons: list[str] = []
            result = self._inspect_route(person_crop_bgr, keypoints, aktif, reasons)
            if result is not None:
                return self._finish(result, start_t)
            return self._no_decision(start_t, "; ".join(reasons))
        finally:
            self._publish_status()
            api_monitor.set_locked(False)
            self.api_lock.release()

    def _online_available(self) -> bool:
        return any(
            e is not None and e.provider is not None and not e.is_local and e.last_call_ok is not False
            for e in (self.primary, self.backup)
        )

    def _inspect_route(self, crop, keypoints, items, reasons):
        if self._internet_recovered.is_set():
            self._internet_recovered.clear()
            self._reset_breaker()
        internet = self.internet.status()
        state = internet["state"]
        if state in (SLOW, DISCONNECTED):
            self.standby.request()
        route = vlm_selection.inspection_route(
            state, self.primary, self.backup, self.local_fallback, median_ms=internet["median_ms"]
        )
        for engine in route:
            internet = self.internet.status()
            state = internet["state"]
            if not engine.is_local and (
                vlm_selection.requires_local_route(state, internet["median_ms"])
                or (state == SLOW and engine is not self.primary)
            ):
                continue
            if engine is self.primary:
                result = self._attempt_primary(crop, keypoints, items, reasons)
            else:
                result = self._attempt_secondary(engine, crop, keypoints, items, reasons)
            if result is not None:
                return result
        if not self._has_backup():
            reasons.append(messages.VLM_BACKUP_UNAVAILABLE)
        return None

    def _attempt_primary(
        self, crop: np.ndarray, keypoints: Optional[list], aktif, reasons: list[str]
    ) -> Optional[InspectionResult]:
        """VLM utama bila pemutus sirkuit mengizinkan; None = gagal/dilewati (alasan ke `reasons`)."""
        now, primary = time.time(), self.primary
        if primary is None or primary.provider is None:
            return None
        if not self._primary_allowed(now):
            reasons.append("utama: dianggap terputus")
            return None
        self.primary_last_attempt = now
        try:
            result = self._try(primary, _engine_jpeg(primary, crop, keypoints), aktif)
        except Exception as e:
            self._primary_result(False, time.time())
            self._network_failure(primary, e)
            reason = self._describe(e, primary)
            reasons.append(f"utama: {reason}")
            target = self.backup.who if self._has_backup() and self.backup is not None else "-"
            logger.warning(f"VLM {primary.who} gagal ({reason}); beralih ke {target}.")
            return None
        self._primary_result(True, time.time())
        return result

    def _attempt_secondary(
        self, backup: VLMEngine, crop: np.ndarray, keypoints: Optional[list], aktif, reasons: list[str]
    ) -> Optional[InspectionResult]:
        """VLM cadangan; None = tidak ada / gagal (alasan ke `reasons`)."""
        if backup.provider is None:
            reasons.append("cadangan: tidak tersedia")
            return None
        if not self.standby.ready(backup):
            self.standby.request()
            reasons.append(messages.VLM_LOCAL_NOT_READY)
            return None
        try:
            return self._try(backup, _engine_jpeg(backup, crop, keypoints), aktif)
        except Exception as e:
            self._network_failure(backup, e)
            reason = self._describe(e, backup)
            reasons.append(f"cadangan: {reason}")
            logger.warning(messages.LOG_VLM_ROUTE_FAILED.format(who=backup.who, reason=reason))
            if backup.is_local:
                # Crash Ollama bisa meninggalkan model sebagian di CPU (T38)
                self.local_guard.trigger()
            return None

    def _network_failure(self, engine: VLMEngine, error: Exception):
        if not engine.is_local and is_connection_failure(error):
            self.internet.request_check()

    @staticmethod
    def _finish(result: InspectionResult, start_t: float) -> InspectionResult:
        result.inference_time_ms = round((time.time() - start_t) * 1000, 1)
        api_monitor.record_decision(result.decided_by)
        return result

    @staticmethod
    def _no_decision(start_t: float, reason: str) -> InspectionResult:
        """Tidak ada VLM yang menjawab. Tanpa klaim per item dan tanpa keputusan."""
        logger.warning(f"Inspeksi tanpa keputusan: {reason}")
        api_monitor.record_decision(None, reason)
        return InspectionResult(
            items={},
            is_complete=False,
            is_system_unavailable=True,
            notes=messages.VLM_NO_DECISION_NOTES.format(reason=reason),
            inference_source="VLM_GANGGUAN",
            inference_time_ms=round((time.time() - start_t) * 1000, 1),
        )

    @staticmethod
    def _optimize_image_for_vlm(image_bgr: np.ndarray) -> bytes:
        """Resizes and compresses image to ~35KB JPEG for lightning-fast network upload."""
        h, w = image_bgr.shape[:2]
        max_dim = cfg.VLM_IMAGE_MAX_SIZE
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # Compress to JPEG in memory. Bytes JPEG ini yang dikirim apa adanya ke
        # penyedia, tanpa didekode dan dikompres ulang.
        _, buffer = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.VLM_JPEG_QUALITY])
        return buffer.tobytes()

    def _call_vlm_internal(self, image_bgr: np.ndarray, keypoints: Optional[list] = None) -> InspectionResult:
        """Satu panggilan langsung ke VLM utama tanpa batas waktu & tanpa cadangan.

        Hanya untuk alat evaluasi (tools/eval_vlm.py), yang mengukur model apa adanya.
        """
        aktif = ppe_rules.get_active_items()
        primary = self.primary
        assert primary is not None and primary.provider is not None, "alat evaluasi butuh VLM utama yang siap"
        data = primary.provider.analyze(
            image_for_vlm(image_bgr, keypoints, vlm_selection.uses_zoom(primary.provider_name)),
            system_prompt=build_system_prompt(aktif, vlm_selection.uses_zoom(primary.provider_name)),
            user_prompt=USER_PROMPT,
        )
        return self._parse_vlm_payload(data, aktif)

    @staticmethod
    def _parse_vlm_payload(data: dict, aktif=None) -> InspectionResult:
        """Mengubah balasan JSON VLM menjadi hasil yang dikunci pada katalog.

        Keputusan kelengkapan dihitung ulang dari `ppe_rules`, bukan diambil
        mentah dari balasan model: dengan begitu aturan wajib/opsional yang
        berlaku di sistem selalu yang menentukan, bukan tafsir model.

        Penolakan tingkat sistem dari model — terutama anti-spoofing — tetap
        dihormati karena tidak berasal dari katalog item.
        """
        mentah = data.get("items")
        if not isinstance(mentah, dict):
            # Balasan bentuk lama (item di tingkat teratas) tetap diterima
            mentah = {k: data.get(k) for k in ppe_rules.item_keys() if isinstance(data.get(k), dict)}

        aktif = aktif if aktif is not None else ppe_rules.get_active_items()
        items = {}
        for item in aktif:
            nilai = mentah.get(item.key)
            items[item.key] = (
                ItemResult(**nilai) if isinstance(nilai, dict) else ItemResult(description="Tidak dinilai oleh VLM")
            )

        is_complete, missing = ppe_rules.evaluate({k: v.model_dump() for k, v in items.items()}, aktif)

        # Satu-satunya penolakan dari teks bebas model yang dihormati adalah
        # anti-spoofing: aturan itu ada di prompt tetapi bukan item katalog, jadi
        # tidak bisa dihitung ulang dari `items`. Nama item di `missing_items`
        # sengaja diabaikan — sistem menghitungnya sendiri dari `items` — karena
        # model menulisnya dengan ejaan yang berubah-ubah ("Helm keselamatan" vs
        # "Helm Keselamatan") sehingga pencocokan teks menghasilkan duplikat, dan
        # menyebut item yang sedang dimatikan tidak boleh menolak pekerja.
        # Bentuk sekarang: `orang_nyata` = false. Penanda lama di `missing_items`
        # tetap dihormati (balasan penyedia dengan prompt lama / uji lama).
        if data.get(ppe_rules.REAL_PERSON_KEY) is False or _is_spoof_rejection(data.get("missing_items")):
            missing = [ppe_rules.SPOOF_MISSING_LABEL] + missing
            is_complete = False

        return InspectionResult(
            items=items,
            is_complete=is_complete,
            missing_items=missing,
            notes=str(data.get("notes", "")),
        )


vlm_analyzer = VLMAnalyzer()
