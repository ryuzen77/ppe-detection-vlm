import logging
import time
import cv2
import numpy as np
import threading
from dataclasses import asdict
from typing import Callable, Optional, List
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import cfg
from .local_model_guard import LocalModelGuard
from .api_monitor import api_monitor
from . import messages
from . import ppe_rules
from . import vlm_selection
from .vlm_providers import profiles as vlm_profiles
from .vlm_providers import create_provider
from .vlm_selection import Choice, Selection

logger = logging.getLogger(__name__)

ROLE_PRIMARY = "utama"
ROLE_BACKUP = "cadangan"

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

    items: dict[str, ItemResult] = Field(
        default_factory=dict, description="Hasil per item APD, dikunci nama item"
    )
    is_complete: bool = Field(default=False, description="True jika seluruh item wajib terpenuhi")
    missing_items: List[str] = Field(
        default_factory=list, description="Nama APD yang belum memenuhi syarat"
    )
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


def build_system_prompt(items=None) -> str:
    """Prompt inspektur K3, dirakit dari item APD yang sedang aktif.

    Sebelumnya prompt ini ditulis tangan sehingga setiap perubahan item APD
    harus disunting manual di sini, terpisah dari tempat lain yang menyimpan
    daftar item yang sama. Kini dirakit ulang setiap kali operator menghidupkan
    atau mematikan item, jadi item mati tidak pernah ditanyakan ke model.
    """
    items = items if items is not None else ppe_rules.get_active_items()
    return messages.VLM_SYSTEM_PROMPT.format(
        rules=ppe_rules.build_prompt_rules(items),
        json_shape=ppe_rules.build_json_shape(items),
    )


def warmup_image_jpeg() -> bytes:
    """Gambar sintetis seukuran potongan pekerja: memanaskan penyandi gambar tanpa foto orang (T56)."""
    h, w = cfg.VLM_WARMUP_IMAGE_HEIGHT, cfg.VLM_WARMUP_IMAGE_WIDTH
    img = np.tile(np.linspace(40, 200, h).astype(np.uint8)[:, None, None], (1, w, 3))
    return cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.VLM_JPEG_QUALITY])[1].tobytes()


def confirmation_prompts(item) -> tuple[str, str]:
    """(prompt sistem, prompt pengguna) konfirmasi kedua satu larangan (T58)."""
    return messages.VLM_CONFIRM_SYSTEM_PROMPT, f"{item.confirm_prompt}\n{messages.VLM_CONFIRM_SHAPE}"


def parse_confirmation(data) -> tuple[bool, str]:
    """(larangan benar terlihat, benda yang disebut model). Selain `true` tegas = tidak terlihat."""
    if not isinstance(data, dict):
        return False, ""
    return data.get("detected") is True, str(data.get("seen") or "")


def thinking_option(provider_name: str, level: str) -> Optional[str]:
    """Nilai mode berpikir untuk adaptor; peringatan bila tidak dikenal/tidak didukung (T39b)."""
    if level not in vlm_profiles.THINKING_LEVELS:
        logger.warning(messages.VLM_THINKING_INVALID.format(value=level, choices=", ".join(vlm_profiles.THINKING_LEVELS)))
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
    status = vlm_profiles.validation_status(provider_name, model, messages.PROMPT_VERSION)
    record = vlm_profiles.find_validation(provider_name, model, messages.PROMPT_VERSION)
    if status == vlm_profiles.UNVALIDATED:
        warnings.append(messages.VLM_MODEL_UNVALIDATED.format(who=who))
    elif status == vlm_profiles.UNSAFE:
        warnings.append(messages.VLM_MODEL_UNSAFE.format(who=who, missed=record.missed, photos=record.photos))
    elif status == vlm_profiles.OUTDATED:
        warnings.append(messages.VLM_MODEL_OUTDATED.format(who=who, old=record.prompt_version,
                                                           current=messages.PROMPT_VERSION))
    elif status == vlm_profiles.PARTIAL:
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
        self.executor = ThreadPoolExecutor(max_workers=cfg.VLM_MAX_CONCURRENT,
                                           thread_name_prefix=f"VLM_{role}")

    @property
    def who(self) -> str:
        """Identitas lengkap untuk log, mis. "utama gemini/gemini-3.5-flash-lite".

        Nama penyedia & model hanya ditulis di log (dan Pengaturan admin), tidak di
        tampilan operator — keputusan pengguna."""
        return f"{self.role} {self.provider_name}/{self.model_name}"

    @property
    def label(self) -> str:
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
                self.provider = create_provider(self.provider_name, api_key=self.api_key,
                                                model=self.model_name, **self._adapter_options())
                self.error = ""
            except Exception as e:
                self.error = str(e)
        if self.provider is None:
            logger.warning(f"VLM {self.role} ({self.provider_name}) nonaktif: {self.error}")
        else:
            logger.info(f"VLM {self.role} siap: {self.provider_name} ({self.model_name}), "
                        f"batas waktu {self.timeout:g} dtk")
            for warning in profile_warnings(self.provider_name, self.model_name, self.who):
                logger.warning(warning)
        return self.provider is not None

    def _adapter_options(self) -> dict:
        # Klien HTTP dibatalkan sedikit sesudah batas waktu aplikasi
        common = {"http_timeout": self.timeout + 1.0, "temperature": cfg.VLM_TEMPERATURE}
        if self.provider_name == "gemini":
            return {**common, "thinking_level": thinking_option(self.provider_name, cfg.VLM_THINKING) or ""}
        options = {**common, "base_url": self.base_url, "json_mode": cfg.VLM_JSON_MODE,
                   "warmup_timeout": cfg.VLM_WARMUP_TIMEOUT_SECONDS}
        profile = vlm_profiles.get_profile(self.provider_name)
        if profile is not None and profile.api == vlm_profiles.API_ANTHROPIC:
            options["max_tokens"] = cfg.VLM_ANTHROPIC_MAX_TOKENS
        return options

    def matches(self, choice: Choice) -> bool:
        """Engine ini sudah melayani pilihan itu dengan key & alamat yang sama (boleh dipakai ulang)."""
        return (self.provider is not None and (self.provider_name, self.model_name) == (choice.provider, choice.model)
                and self.api_key == vlm_selection.api_key_for(choice.provider)
                and self.base_url == vlm_selection.base_url_for(choice.provider))

    def choice(self) -> Choice:
        return Choice(self.provider_name, self.model_name)

    def close(self):
        """Melepas thread engine yang sudah diganti; panggilan yang berjalan tidak dipotong."""
        self.executor.shutdown(wait=False)

    def warm_up(self) -> Optional[float]:
        self.warm_error = ""
        if self.provider is None:
            return None
        start = time.time()
        try:
            self.executor.submit(self.provider.warm_up).result(timeout=cfg.VLM_WARMUP_TIMEOUT_SECONDS)
            if self.is_local:
                self._warm_with_image()
        except Exception as e:
            self.warm_error = vlm_selection.redact(str(e), self.api_key)[:cfg.ERROR_MESSAGE_MAX_CHARS] or type(e).__name__
            # Tidak fatal: server tetap menyala; VLM ini dicoba lagi pada pekerja
            # pertama dan, bila gagal, inspeksi dialihkan ke VLM lain (T27).
            logger.warning(f"Pemanasan VLM {self.role} {self.provider_name} gagal ({str(e)[:160]}). "
                           f"Server tetap berjalan; VLM ini dicoba lagi saat inspeksi.")
            return None
        duration = time.time() - start
        logger.info(f"Pemanasan VLM {self.role} {self.provider_name} ({self.model_name}) selesai dalam {duration:.1f} dtk.")
        return duration

    def _warm_with_image(self):
        """Satu panggilan seperti inspeksi (prompt produksi + gambar), hanya untuk VLM lokal:
        ping teks meninggalkan penyandi gambar & prompt sistem "dingin" sehingga pekerja
        pertama habis waktu (uji 14-10: 13 dtk > batas 12). Cloud tidak, karena memakan kuota."""
        start = time.time()
        future = self.executor.submit(self.provider.analyze, warmup_image_jpeg(),
                                      system_prompt=build_system_prompt(), user_prompt=USER_PROMPT)
        try:
            future.result(timeout=cfg.VLM_WARMUP_TIMEOUT_SECONDS)
        except ValueError:
            pass        # jawaban untuk gambar sintetis tidak dipakai; yang penting GPU sudah bekerja
        logger.info(messages.LOCAL_MODEL_WARMUP_IMAGE.format(who=self.who, seconds=time.time() - start))

    def call(self, image_jpeg: bytes, system_prompt: str, user_prompt: str) -> dict:
        """Satu panggilan dengan batas waktu keras. Galat & timeout dilempar ke pemanggil."""
        wait = self.min_interval - (time.time() - self.last_call_time)
        if wait > 0:
            logger.info(f"Menunggu jeda kuota {wait:.1f} dtk sebelum panggilan VLM {self.role}.")
            time.sleep(wait)
        try:
            future = self.executor.submit(self.provider.analyze, image_jpeg,
                                          system_prompt=system_prompt, user_prompt=user_prompt)
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
            "validated": vlm_profiles.validation_status(self.provider_name, self.model_name, messages.PROMPT_VERSION),
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
        # Satu inspeksi pada satu waktu; permintaan lain menunggu gilirannya
        self.api_lock = threading.Lock()
        self.primary_failures = 0
        self.primary_down_since: Optional[float] = None
        self.primary_last_attempt = 0.0
        # Menjaga model lokal tetap penuh di GPU setelah crash Ollama (T38)
        self.local_guard = LocalModelGuard(self.api_lock, self._local_engine)
        # Satu pergantian penyedia pada satu waktu (T28)
        self.apply_lock = threading.Lock()
        self.selection_source = vlm_selection.SOURCE_ENV

    def start(self):
        """Merakit VLM utama & cadangan: pilihan dashboard bila ada, selain itu .env (T28)."""
        selection = vlm_selection.effective_selection()
        self.primary = self._new_engine(ROLE_PRIMARY, selection.primary)
        self.backup = self._new_engine(ROLE_BACKUP, selection.backup) if selection.backup else None
        self.selection_source = selection.source
        self._reset_breaker()
        self._publish_status()

    @staticmethod
    def _new_engine(role: str, choice: Choice) -> VLMEngine:
        engine = VLMEngine(role, choice.provider, choice.model,
                           vlm_selection.api_key_for(choice.provider), vlm_selection.base_url_for(choice.provider))
        engine.build()
        return engine

    def _reset_breaker(self):
        self.primary_failures = 0
        self.primary_down_since = None
        self.primary_last_attempt = 0.0

    # --- Ganti penyedia dari dashboard (T28)
    def active_choices(self) -> list[Choice]:
        return [e.choice() for e in (self.primary, self.backup) if e is not None]

    def current_selection(self) -> dict:
        """Bentuk `current` kontrak T28. Tanpa API key."""
        def sel(engine):
            return None if engine is None else {**asdict(engine.choice()), "source": self.selection_source}
        return {"primary": sel(self.primary), "backup": sel(self.backup)}

    def apply_selection(self, selection: Selection, lane_empty: Callable[[], bool],
                        client: str = "", user: str = "") -> dict:
        """Menukar engine utama & cadangan tanpa restart.

        Engine baru dirakit & dipanaskan DULU (di luar gembok inspeksi); gagal =
        engine lama tetap dipakai (`EngineFailed`). Pertukaran terjadi di bawah
        gembok inspeksi, jadi inspeksi yang sedang berjalan selesai dengan engine
        lama, dan hanya bila jalur kosong (`LaneBusy`).
        """
        with self.apply_lock:
            fresh = self._prepare(ROLE_PRIMARY, selection.primary), (
                self._prepare(ROLE_BACKUP, selection.backup) if selection.backup else None)
            try:
                old = self._swap(fresh, selection.source, lane_empty)
            except Exception:
                self._discard(fresh, keep=(self.primary, self.backup))
                raise
            self._discard(old, keep=fresh)
            for role, before, after in ((ROLE_PRIMARY, old[0], fresh[0]), (ROLE_BACKUP, old[1], fresh[1])):
                before_choice, after_choice = before.choice() if before else None, after.choice() if after else None
                if before_choice != after_choice:
                    vlm_selection.record_change(role, before_choice, after_choice, selection.source, client, user)
            return self.current_selection()

    def _prepare(self, role: str, choice: Choice) -> VLMEngine:
        """Engine siap pakai: yang sedang berjalan bila sama persis, selain itu rakit + panaskan."""
        for engine in (self.primary, self.backup):
            if engine is not None and engine.role == role and engine.matches(choice):
                return engine
        engine = self._new_engine(role, choice)
        if engine.provider is None or engine.warm_up() is None:
            engine.close()
            raise EngineFailed(messages.VLM_SELECT_ENGINE_FAILED.format(
                role=role, provider=choice.provider, model=choice.model,
                error=engine.error or engine.warm_error))
        return engine

    def _swap(self, fresh: tuple, source: str, lane_empty: Callable[[], bool]) -> tuple:
        lock_wait = sum(e.timeout + e.min_interval for e in self._engines()) + 1.0
        if not self.api_lock.acquire(timeout=lock_wait):
            raise LaneBusy(messages.VLM_SELECT_LANE_BUSY)
        try:
            if not lane_empty():
                raise LaneBusy(messages.VLM_SELECT_LANE_BUSY)
            old = (self.primary, self.backup)
            self.primary, self.backup = fresh
            self.selection_source = source
            self._reset_breaker()
        finally:
            self.api_lock.release()
        self._publish_status()
        return old

    @staticmethod
    def _discard(engines: tuple, keep: tuple):
        for engine in engines:
            if engine is not None and all(engine is not k for k in keep):
                engine.close()

    def test_choice(self, role: str, choice: Choice) -> dict:
        """Tombol "Uji": 1 ping + 1 gambar sintetis lewat engine sementara (memakai kuota penyedia).

        `ok` = penyedia menjawab; `json_ok` = jawaban gambar berupa JSON yang bisa diurai.
        Engine gerbang yang sedang berjalan tidak disentuh.
        """
        engine = self._new_engine(role, choice)
        try:
            if engine.provider is None:
                return {"ok": False, "latency_ms": None, "json_ok": False, "error": engine.error}
            start = time.time()
            ping_error = self._attempt(engine, lambda: engine.executor.submit(engine.provider.ping)
                                       .result(timeout=engine.timeout))
            latency = round((time.time() - start) * 1000, 1)
            if ping_error:
                return {"ok": False, "latency_ms": latency, "json_ok": False, "error": ping_error}
            json_error = self._attempt(engine, lambda: engine.call(
                self._test_image(), system_prompt=build_system_prompt(), user_prompt=USER_PROMPT))
            return {"ok": True, "latency_ms": latency, "json_ok": not json_error, "error": json_error}
        finally:
            engine.close()

    def _attempt(self, engine: VLMEngine, call: Callable[[], object]) -> str:
        """Kosong bila berhasil, selain itu alasan singkat untuk Pengaturan admin."""
        try:
            call()
            return ""
        except Exception as e:
            return vlm_selection.redact(self._describe(e, engine), engine.api_key)[:cfg.ERROR_MESSAGE_MAX_CHARS]

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
        for e in (self.backup, self.primary):
            if e is not None and e.is_local and e.provider is not None:
                return e
        return None

    def _engines(self) -> list[VLMEngine]:
        return [e for e in (self.primary, self.backup) if e is not None and e.provider is not None]

    def is_live_api(self) -> bool:
        """Ada setidaknya satu VLM yang siap memutuskan."""
        return bool(self._engines())

    def warm_up(self) -> Optional[float]:
        """Memanaskan utama DAN cadangan saat startup.

        Cadangan juga dipanaskan (model lokal dimuat & ditahan di GPU) supaya
        peralihan saat utama gagal tidak menunggu ~40 dtk pemuatan model.
        Mengembalikan durasi pemanasan utama (None bila gagal/nonaktif).
        """
        result = self.primary.warm_up() if self.primary else None
        if self.backup is not None:
            self.backup.warm_up()
        return result

    def provider_info(self) -> dict:
        """VLM utama (bidang tingkat atas, bentuk lama) + cadangan. Tanpa API key."""
        info = self.primary.info() if self.primary else {
            "role": ROLE_PRIMARY, "provider": cfg.VLM_PROVIDER, "model": cfg.VLM_MODEL,
            "is_local": cfg.VLM_IS_LOCAL, "needs_key": not cfg.VLM_IS_LOCAL, "has_key": False,
            "is_live": False, "timeout_s": 0, "error": "belum dimulai"}
        info["backup"] = self.backup.info() if self.backup else None
        info["primary_down"] = self.primary_down_since is not None
        return info

    def ping_api(self) -> dict:
        """Uji latensi utama dan cadangan."""
        if not self._engines():
            return {"status": "OFFLINE", "latency_ms": 0, "message": messages.VLM_NOT_CONFIGURED}
        results = []
        for engine in self._engines():
            start = time.time()
            try:
                engine.executor.submit(engine.provider.ping).result(timeout=engine.timeout)
                dur = round((time.time() - start) * 1000, 1)
                results.append({"role": engine.role, "ok": True, "latency_ms": dur})
            except Exception as e:
                results.append({"role": engine.role, "ok": False,
                                "latency_ms": round((time.time() - start) * 1000, 1),
                                "error": str(e)[:cfg.ERROR_MESSAGE_MAX_CHARS]})
        first = results[0]
        message = "; ".join(
            f"{r['role']}: {'OK ' + str(r['latency_ms']) + ' ms' if r['ok'] else 'gagal (' + r.get('error', '') + ')'}"
            for r in results)
        return {"status": "ONLINE" if first["ok"] else "ERROR", "latency_ms": first["latency_ms"],
                "message": message, "engines": results}

    # --- Pemutus sirkuit utama
    def _primary_allowed(self, now: float) -> bool:
        if self.primary is None or self.primary.provider is None:
            return False
        if self.primary_failures < cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN:
            return True
        return now - self.primary_last_attempt >= cfg.VLM_PRIMARY_RETRY_AFTER_SECONDS

    def _primary_result(self, ok: bool, now: float):
        if ok:
            if self.primary_down_since is not None:
                logger.info(f"VLM {self.primary.who} pulih setelah {now - self.primary_down_since:.0f} dtk.")
            self.primary_failures = 0
            self.primary_down_since = None
            return
        self.primary_failures += 1
        if self.primary_failures >= cfg.VLM_PRIMARY_FAILURES_BEFORE_DOWN and self.primary_down_since is None:
            self.primary_down_since = now
            logger.warning(f"VLM {self.primary.who} dianggap terputus setelah {self.primary_failures} kegagalan berturut-turut; "
                           f"inspeksi langsung ke cadangan, utama dicoba lagi setiap "
                           f"{cfg.VLM_PRIMARY_RETRY_AFTER_SECONDS:g} dtk.")

    def _publish_status(self):
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
            api_monitor.record_failure(engine.role, f"timeout > {engine.timeout:g} dtk", is_timeout=True)
            raise
        except Exception as e:
            api_monitor.record_failure(engine.role, str(e))
            raise
        api_monitor.record_success(engine.role, round((time.time() - call_start) * 1000, 1))
        result.inference_source = engine.label
        result.decided_by = engine.role
        return result

    def _timed_call(self, engine: VLMEngine, image_jpeg: bytes, aktif) -> dict:
        """Panggilan inspeksi; untuk VLM lokal waktunya dicatat ke penjaga T56 (hanya panggilan
        ini, bukan konfirmasi larangan — konfirmasi rokok di lokal akan tampak "lambat")."""
        start = time.time()
        try:
            data = engine.call(image_jpeg, system_prompt=build_system_prompt(aktif), user_prompt=USER_PROMPT)
        except Exception:
            if engine.is_local:
                self.local_guard.record_call(None, time.time())
            raise
        if engine.is_local:
            self.local_guard.record_call(time.time() - start, time.time())
        return data

    def _confirm_prohibitions(self, engine: VLMEngine, image_jpeg: bytes, result: InspectionResult,
                              aktif) -> InspectionResult:
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
        """Gagal/habis waktu = tidak terlihat (keputusan pengguna 13-10: VLM ragu = tidak ada)."""
        try:
            confirmed, seen = parse_confirmation(engine.call(image_jpeg, *confirmation_prompts(item)))
        except Exception as e:
            logger.warning(f"Konfirmasi larangan '{item.key}' oleh VLM {engine.who} gagal "
                           f"({str(e)[:80] or type(e).__name__}); dianggap tidak terlihat.")
            return False, ""
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
        return f"galat: {str(e)[:80]}"

    def analyze_person(self, person_crop_bgr: np.ndarray) -> InspectionResult:
        """Keputusan APD untuk satu crop pekerja (lihat docstring kelas)."""
        start_t = time.time()
        if not self._engines():
            return self._no_decision(start_t, messages.VLM_NOT_CONFIGURED)

        # Terburuk: utama habis waktu, lalu cadangan menjawab + satu konfirmasi larangan (T58)
        slots = [e.timeout + e.min_interval for e in self._engines()]
        lock_wait = sum(slots) + max(slots) + 1.0
        if not self.api_lock.acquire(timeout=lock_wait):
            return self._no_decision(start_t, "antrean VLM penuh")

        api_monitor.set_locked(True)
        try:
            # Satu potret item aktif untuk seluruh inspeksi, supaya prompt dan
            # penilaian jawaban memakai daftar yang sama walau operator mengubahnya.
            aktif = ppe_rules.get_active_items()
            image_jpeg = self._optimize_image_for_vlm(person_crop_bgr)
            reasons = []

            now = time.time()
            if self._primary_allowed(now):
                self.primary_last_attempt = now
                try:
                    result = self._try(self.primary, image_jpeg, aktif)
                    self._primary_result(True, time.time())
                    return self._finish(result, start_t)
                except Exception as e:
                    self._primary_result(False, time.time())
                    reason = self._describe(e, self.primary)
                    reasons.append(f"utama: {reason}")
                    target = self.backup.who if self.backup is not None and self.backup.provider is not None else "-"
                    logger.warning(f"VLM {self.primary.who} gagal ({reason}); beralih ke {target}.")
            elif self.primary is not None and self.primary.provider is not None:
                reasons.append("utama: dianggap terputus")

            if self.backup is not None and self.backup.provider is not None:
                try:
                    return self._finish(self._try(self.backup, image_jpeg, aktif), start_t)
                except Exception as e:
                    reason = self._describe(e, self.backup)
                    reasons.append(f"cadangan: {reason}")
                    logger.warning(f"VLM {self.backup.who} gagal ({reason}).")
                    if self.backup.is_local:
                        # Crash Ollama bisa meninggalkan model sebagian di CPU (T38)
                        self.local_guard.trigger()
            else:
                reasons.append("cadangan: tidak tersedia")

            return self._no_decision(start_t, "; ".join(reasons))
        finally:
            self._publish_status()
            api_monitor.set_locked(False)
            self.api_lock.release()

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
        _, buffer = cv2.imencode('.jpg', image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.VLM_JPEG_QUALITY])
        return buffer.tobytes()

    def _call_vlm_internal(self, image_bgr: np.ndarray) -> InspectionResult:
        """Satu panggilan langsung ke VLM utama tanpa batas waktu & tanpa cadangan.

        Hanya untuk alat evaluasi (tools/eval_vlm.py), yang mengukur model apa adanya.
        """
        aktif = ppe_rules.get_active_items()
        data = self.primary.provider.analyze(
            self._optimize_image_for_vlm(image_bgr),
            system_prompt=build_system_prompt(aktif),
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
            items[item.key] = ItemResult(**nilai) if isinstance(nilai, dict) else ItemResult(
                description="Tidak dinilai oleh VLM"
            )

        is_complete, missing = ppe_rules.evaluate(
            {k: v.model_dump() for k, v in items.items()}, aktif
        )

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
