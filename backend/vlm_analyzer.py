import logging
import time
import cv2
import numpy as np
import threading
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pydantic import BaseModel, ConfigDict, Field

from .config import cfg, LOCAL_VLM_PROVIDERS
from .api_monitor import api_monitor
from . import messages
from . import ppe_rules
from .vlm_providers import create_provider

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
        completeness_number=len(items) + 1,
        completeness_rule=ppe_rules.build_completeness_rule(items),
        json_shape=ppe_rules.build_json_shape(items),
    )


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
        self.is_local = self.provider_name in LOCAL_VLM_PROVIDERS
        self.timeout = cfg.VLM_LOCAL_TIMEOUT_SECONDS if self.is_local else cfg.VLM_CLOUD_TIMEOUT_SECONDS
        self.min_interval = 0.0 if self.is_local else cfg.VLM_MIN_INTERVAL_SECONDS
        self.provider = None
        self.error = ""
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
                # Klien HTTP dibatalkan sedikit sesudah batas waktu aplikasi
                http_timeout = self.timeout + 1.0
                common = {"http_timeout": http_timeout, "temperature": cfg.VLM_TEMPERATURE}
                options = ({**common, "thinking_level": cfg.GEMINI_THINKING_LEVEL}
                           if self.provider_name == "gemini" else
                           {**common, "base_url": self.base_url, "json_mode": cfg.VLM_JSON_MODE,
                            "warmup_timeout": cfg.VLM_WARMUP_TIMEOUT_SECONDS})
                self.provider = create_provider(self.provider_name, api_key=self.api_key,
                                                model=self.model_name, **options)
                self.error = ""
            except Exception as e:
                self.error = str(e)
        if self.provider is None:
            logger.warning(f"VLM {self.role} ({self.provider_name}) nonaktif: {self.error}")
        else:
            logger.info(f"VLM {self.role} siap: {self.provider_name} ({self.model_name}), "
                        f"batas waktu {self.timeout:g} dtk")
        return self.provider is not None

    def warm_up(self) -> Optional[float]:
        if self.provider is None:
            return None
        start = time.time()
        try:
            self.executor.submit(self.provider.warm_up).result(timeout=cfg.VLM_WARMUP_TIMEOUT_SECONDS)
        except Exception as e:
            # Tidak fatal: server tetap menyala; VLM ini dicoba lagi pada pekerja
            # pertama dan, bila gagal, inspeksi dialihkan ke VLM lain (T27).
            logger.warning(f"Pemanasan VLM {self.role} {self.provider_name} gagal ({str(e)[:160]}). "
                           f"Server tetap berjalan; VLM ini dicoba lagi saat inspeksi.")
            return None
        duration = time.time() - start
        logger.info(f"Pemanasan VLM {self.role} {self.provider_name} ({self.model_name}) selesai dalam {duration:.1f} dtk.")
        return duration

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

    def start(self):
        """Merakit VLM utama & cadangan sesuai konfigurasi. Dipanggil saat startup."""
        self.primary = VLMEngine(ROLE_PRIMARY, cfg.VLM_PROVIDER, cfg.VLM_MODEL, cfg.VLM_API_KEY, cfg.VLM_BASE_URL)
        self.primary.build()
        self.backup = None
        if cfg.VLM_BACKUP_PROVIDER and cfg.VLM_BACKUP_PROVIDER != "none":
            self.backup = VLMEngine(ROLE_BACKUP, cfg.VLM_BACKUP_PROVIDER, cfg.VLM_BACKUP_MODEL,
                                    cfg.VLM_BACKUP_API_KEY, cfg.VLM_BACKUP_BASE_URL)
            self.backup.build()
        self.primary_failures = 0
        self.primary_down_since = None
        self._publish_status()

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

    def update_api_key(self, new_key: str):
        """Mengganti API key VLM utama (dari dashboard)."""
        cfg.VLM_API_KEY = new_key.strip()
        if self.primary is None:
            self.start()
            return
        self.primary.api_key = cfg.VLM_API_KEY
        self.primary.build()
        self.primary_failures = 0
        self.primary_down_since = None
        self._publish_status()

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
            data = engine.call(image_jpeg, system_prompt=build_system_prompt(aktif), user_prompt=USER_PROMPT)
            result = self._parse_vlm_payload(data, aktif)
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

        lock_wait = sum(e.timeout + e.min_interval for e in self._engines()) + 1.0
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
        if _is_spoof_rejection(data.get("missing_items")):
            missing = [ppe_rules.SPOOF_MISSING_LABEL] + missing
            is_complete = False

        return InspectionResult(
            items=items,
            is_complete=is_complete,
            missing_items=missing,
            notes=str(data.get("notes", "")),
        )

vlm_analyzer = VLMAnalyzer()
