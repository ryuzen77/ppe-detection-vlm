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
        default="LOCAL_FAST_PASS",
        description="Sumber keputusan: VLM_LIVE:<penyedia>/<model>, LOCAL_FAST_PASS, OFFLINE_FALLBACK, atau VLM_GAGAL",
    )
    inference_time_ms: float = Field(default=0.0, description="Durasi inferensi dalam milidetik")
    is_low_confidence: bool = Field(
        default=False,
        description="True jika keputusan berasal dari heuristik lokal yang akurasinya terbatas",
    )
    is_unverified: bool = Field(
        default=False,
        description="True jika VLM aktif tetapi gagal menjawab; pekerja ditolak tanpa penilaian item",
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


USER_PROMPT = "Periksa kelengkapan APD pekerja pada gambar ini sesuai instruksi K3. Berikan output JSON."


def build_system_prompt(items=None) -> str:
    """Prompt inspektur K3, dirakit dari item APD yang sedang aktif.

    Sebelumnya prompt ini ditulis tangan sehingga setiap perubahan item APD
    harus disunting manual di sini, terpisah dari tempat lain yang menyimpan
    daftar item yang sama. Kini dirakit ulang setiap kali operator menghidupkan
    atau mematikan item, jadi item mati tidak pernah ditanyakan ke model.
    """
    items = items if items is not None else ppe_rules.get_active_items()
    return (
        "\nAnda adalah AI Inspektur K3 (Keselamatan dan Kesehatan Kerja) profesional.\n"
        "Tugas Anda adalah memeriksa kelengkapan Alat Pelindung Diri (APD) pada orang "
        "dalam gambar yang dikirimkan.\n\n"
        "Aturan Penilaian APD:\n"
        f"{ppe_rules.build_prompt_rules(items)}\n\n"
        f"{len(items) + 1}. {ppe_rules.build_completeness_rule(items)}\n\n"
        "Kembalikan hasil dalam format JSON yang valid persis seperti bentuk berikut:\n"
        f"{ppe_rules.build_json_shape(items)}\n"
    )


class LocalVisionAnalyzer:
    """Heuristik visi komputer lokal berbasis OpenCV (~15ms di CPU).

    Berfungsi sebagai Tier 1 Fast-Pass dan cadangan 100% offline bila internet mati.
    Ini BUKAN model deep learning: keputusannya berasal dari segmentasi warna HSV
    dan rasio piksel per ROI, sehingga akurasinya jauh di bawah VLM. Setiap hasil
    ditandai `is_low_confidence=True` agar operator tahu asal keputusannya.
    """
    def __init__(self):
        # Satu-satunya tempat yang menghubungkan kunci katalog APD dengan kode
        # pemeriksanya. Item yang tidak terdaftar di sini TIDAK lolos diam-diam;
        # `analyze()` menandainya sebagai tidak terverifikasi, meneruskan prinsip
        # yang sama dengan penanganan helm dan sepatu sebelumnya.
        self._detectors = {
            "helm": self._check_helm,
            "rompi": self._check_rompi,
            "celana": self._check_celana,
            "sepatu": self._check_sepatu,
        }

    @staticmethod
    def _center_band(roi: np.ndarray, ratio: float) -> np.ndarray:
        """Memotong pita tengah horizontal dari sebuah ROI.

        Kepala dan kaki berada di tengah crop, sedangkan tepi kiri/kanan berisi
        latar belakang. Tanpa pemotongan ini, dinding terang atau lantai gelap
        di belakang subjek ikut terhitung sebagai helm atau sepatu.
        """
        w = roi.shape[1]
        band = max(int(w * ratio), 1)
        x1 = max((w - band) // 2, 0)
        return roi[:, x1:x1 + band]

    @staticmethod
    def _skin_ratio(hsv_roi: np.ndarray) -> float:
        """Porsi piksel bernuansa kulit pada sebuah ROI."""
        total = max(hsv_roi.shape[0] * hsv_roi.shape[1], 1)
        skin_mask = cv2.inRange(hsv_roi, np.array(cfg.HSV_SKIN_LOWER), np.array(cfg.HSV_SKIN_UPPER))
        return cv2.countNonZero(skin_mask) / total

    def _detect_helmet(self, head_roi: np.ndarray) -> tuple[bool, float]:
        """Mencari helm pada mahkota kepala: warna solid bersaturasi tinggi atau putih terang.

        Mengembalikan (terdeteksi, rasio cakupan mahkota).
        """
        if head_roi is None or head_roi.size == 0:
            return False, 0.0

        hsv_head = cv2.cvtColor(head_roi, cv2.COLOR_BGR2HSV)
        crown_h = max(int(head_roi.shape[0] * cfg.HELMET_CROWN_RATIO), 1)
        hsv_crown = self._center_band(hsv_head[0:crown_h, :], cfg.HELMET_CROWN_CENTER_RATIO)
        total_crown = max(hsv_crown.shape[0] * hsv_crown.shape[1], 1)

        saturation = hsv_crown[:, :, 1]
        value = hsv_crown[:, :, 2]

        # Helm berwarna (saturasi tinggi) ATAU helm putih (sangat terang)
        colored = saturation >= cfg.HELMET_MIN_SATURATION
        bright = value >= cfg.HELMET_MIN_VALUE_BRIGHT
        helmet_mask = np.logical_or(colored, bright)

        # Kulit wajah juga bersaturasi, jadi dikurangkan agar tidak terhitung helm
        skin_mask = cv2.inRange(hsv_crown, np.array(cfg.HSV_SKIN_LOWER), np.array(cfg.HSV_SKIN_UPPER)) > 0
        helmet_mask = np.logical_and(helmet_mask, np.logical_not(skin_mask))

        coverage = float(np.count_nonzero(helmet_mask)) / total_crown
        skin_ratio = self._skin_ratio(self._center_band(hsv_head, cfg.HELMET_CROWN_CENTER_RATIO))

        detected = coverage >= cfg.HELMET_MIN_COVERAGE and skin_ratio < cfg.HELMET_SKIN_MAX_RATIO
        return detected, coverage

    def _detect_closed_shoes(self, shoe_roi: np.ndarray) -> tuple[bool, float]:
        """Mencari alas kaki tertutup: area gelap padat tanpa kulit dominan.

        Mengembalikan (terdeteksi, rasio piksel gelap).
        """
        if shoe_roi is None or shoe_roi.size == 0:
            return False, 0.0

        hsv_shoe = self._center_band(cv2.cvtColor(shoe_roi, cv2.COLOR_BGR2HSV), cfg.SHOE_ROI_CENTER_RATIO)
        total = max(hsv_shoe.shape[0] * hsv_shoe.shape[1], 1)

        dark_ratio = float(np.count_nonzero(hsv_shoe[:, :, 2] <= cfg.SHOE_MAX_VALUE_DARK)) / total
        skin_ratio = self._skin_ratio(hsv_shoe)

        detected = dark_ratio >= cfg.SHOE_MIN_DARK_RATIO and skin_ratio < cfg.SHOE_SKIN_MAX_RATIO
        return detected, dark_ratio

    # ------------------------------------------------------------------
    # Pemeriksa per item. Masing-masing menerima crop penuh dan definisi
    # itemnya, lalu mengembalikan satu ItemResult. Nama field syarat tambahan
    # diambil dari katalog (`item.qualifier.key`), bukan ditulis tetap, supaya
    # item baru dengan syaratnya sendiri tidak memerlukan perubahan di sini.
    # ------------------------------------------------------------------

    @staticmethod
    def _with_qualifier(item, detected: bool, description: str, qualifier_value=None,
                        color: str = "") -> ItemResult:
        extra = {}
        if item.qualifier is not None:
            extra[item.qualifier.key] = bool(
                detected if qualifier_value is None else qualifier_value
            )
        return ItemResult(detected=detected, color=color, description=description, **extra)

    def _check_helm(self, image_bgr: np.ndarray, item) -> ItemResult:
        """Helm proyek berwarna solid dan kontras terhadap rambut maupun kulit."""
        h = image_bgr.shape[0]
        head = image_bgr[0:max(int(h * cfg.HELMET_ROI_TOP_RATIO), 1), :]
        detected, coverage = self._detect_helmet(head)
        return self._with_qualifier(
            item, detected,
            f"Helm keselamatan terdeteksi (cakupan mahkota {coverage:.0%})" if detected
            else "Helm tidak terverifikasi oleh engine lokal",
            color="bebas",
        )

    def _check_rompi(self, image_bgr: np.ndarray, item) -> ItemResult:
        """Rompi hi-vis dikenali dari porsi piksel orange/kuning dan pita reflektif."""
        h = image_bgr.shape[0]
        torso = image_bgr[int(h * cfg.TORSO_ROI_TOP_RATIO):int(h * cfg.TORSO_LEGS_SPLIT_RATIO), :]
        hsv_torso = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)

        orange_px = cv2.countNonZero(
            cv2.inRange(hsv_torso, np.array(cfg.HSV_ORANGE_LOWER), np.array(cfg.HSV_ORANGE_UPPER)))
        yellow_px = cv2.countNonZero(
            cv2.inRange(hsv_torso, np.array(cfg.HSV_YELLOW_LOWER), np.array(cfg.HSV_YELLOW_UPPER)))
        silver_px = cv2.countNonZero(
            cv2.inRange(hsv_torso, np.array(cfg.HSV_SILVER_LOWER), np.array(cfg.HSV_SILVER_UPPER)))

        total_px = max(torso.shape[0] * torso.shape[1], 1)
        hi_vis_ratio = (orange_px + yellow_px + silver_px) / total_px
        detected = hi_vis_ratio > cfg.HI_VIS_MIN_RATIO
        warna = "orange" if orange_px >= yellow_px else "kuning"

        return self._with_qualifier(
            item, detected,
            f"Rompi keselamatan warna {warna} reflektif" if detected
            else "Rompi tidak terdeteksi atau bukan orange/kuning",
            color=warna if detected else "tidak sesuai",
        )

    def _check_celana(self, image_bgr: np.ndarray, item) -> ItemResult:
        """Celana pendek menampakkan kulit di area kaki; rasio kulit jadi penandanya."""
        h = image_bgr.shape[0]
        legs = image_bgr[int(h * cfg.TORSO_LEGS_SPLIT_RATIO):int(h * cfg.LEGS_ROI_BOTTOM_RATIO), :]
        skin_ratio = self._skin_ratio(cv2.cvtColor(legs, cv2.COLOR_BGR2HSV))
        detected = skin_ratio < cfg.SKIN_MAX_RATIO
        return self._with_qualifier(
            item, detected,
            "Celana panjang kerja terpasang" if detected
            else "Terdeteksi celana pendek / lutut terbuka",
        )

    def _check_sepatu(self, image_bgr: np.ndarray, item) -> ItemResult:
        """Sepatu tertutup tampak gelap dan padat; sandal menampakkan kulit."""
        h = image_bgr.shape[0]
        shoe_top = min(int(h * (1.0 - cfg.SHOE_ROI_BOTTOM_RATIO)), h - 1)
        detected, dark_ratio = self._detect_closed_shoes(image_bgr[shoe_top:h, :])
        return self._with_qualifier(
            item, detected,
            f"Alas kaki tertutup terdeteksi (area gelap {dark_ratio:.0%})" if detected
            else "Sepatu tertutup tidak terverifikasi oleh engine lokal",
        )

    @staticmethod
    def _unverified(item) -> ItemResult:
        """Item tanpa heuristik lokal.

        Dikembalikan sebagai TIDAK terdeteksi, bukan lolos. Menambah item APD di
        katalog tanpa menyediakan pemeriksanya akan menutup gerbang di mode
        offline — sengaja, karena kebalikannya berarti meloloskan pekerja atas
        dasar pemeriksaan yang tidak pernah terjadi.
        """
        extra = {item.qualifier.key: False} if item.qualifier is not None else {}
        return ItemResult(
            detected=False,
            description=f"{item.label} tidak dapat diperiksa engine lokal",
            **extra,
        )

    def has_local_check(self, key: str) -> bool:
        """Apakah item ini punya pemeriksa heuristik lokal (untuk mode offline)."""
        return key in self._detectors

    def analyze(self, image_bgr: np.ndarray) -> InspectionResult:
        """Memeriksa seluruh item APD yang sedang aktif."""
        start_t = time.time()

        aktif = ppe_rules.get_active_items()
        items = {}
        tanpa_heuristik = []
        for item in aktif:
            pemeriksa = self._detectors.get(item.key)
            if pemeriksa is None:
                items[item.key] = self._unverified(item)
                tanpa_heuristik.append(item.label)
            else:
                items[item.key] = pemeriksa(image_bgr, item)

        # Kelengkapan diputuskan `ppe_rules.evaluate()`, aturan yang sama dengan
        # prompt VLM, sehingga kedua jalur tidak bisa menyimpang satu sama lain.
        is_complete, missing = ppe_rules.evaluate(
            {k: v.model_dump() for k, v in items.items()}, aktif
        )

        catatan = "[ENGINE LOKAL - FAST PASS] Heuristik warna OpenCV, akurasi terbatas dibanding VLM."
        if tanpa_heuristik:
            catatan += " Tanpa pemeriksa lokal: " + ", ".join(tanpa_heuristik) + "."

        return InspectionResult(
            items=items,
            is_complete=is_complete,
            missing_items=missing,
            notes=catatan,
            inference_source="LOCAL_FAST_PASS",
            inference_time_ms=round((time.time() - start_t) * 1000, 1),
            is_low_confidence=True,
        )


class VLMAnalyzer:
    """Hybrid VLM Analyzer with instant Tier 1 Local Pre-check, optimized upload,
    strict 2.0s timeout, and Free-Tier Anti-Spam Concurrency Lock & Rate Limiter."""
    def __init__(self):
        self.provider_name = cfg.VLM_PROVIDER
        self.api_key = cfg.VLM_API_KEY
        self.model_name = cfg.VLM_MODEL
        # Adaptor penyedia VLM (lihat vlm_providers); None = tanpa VLM, engine lokal
        self.provider = None
        self.local_analyzer = LocalVisionAnalyzer()
        self.executor = ThreadPoolExecutor(max_workers=cfg.VLM_MAX_CONCURRENT, thread_name_prefix="VLM_Timeout_Guard")
        
        # Free Tier Anti-Spam Guards
        self.api_lock = threading.Lock()
        self.last_api_call_time: float = 0.0

    def start(self):
        """Merakit adaptor penyedia VLM sesuai konfigurasi. Dipanggil saat startup."""
        self._init_provider()

    @property
    def source_label(self) -> str:
        """Label sumber keputusan untuk audit, mis. VLM_LIVE:gemini/gemini-3.5-flash-lite."""
        return f"VLM_LIVE:{self.provider_name}/{self.model_name}"

    def _provider_options(self) -> dict:
        if self.provider_name == "gemini":
            return {"thinking_level": cfg.GEMINI_THINKING_LEVEL}
        return {"base_url": cfg.VLM_BASE_URL, "json_mode": cfg.VLM_JSON_MODE}

    def _init_provider(self):
        local = self.provider_name in LOCAL_VLM_PROVIDERS
        if not (self.api_key and self.api_key.strip()) and not local:
            self.provider = None
            api_monitor.status = "OFFLINE"
            logger.warning(f"API key VLM ({self.provider_name}) belum disetel. "
                           f"Operating in LOCAL HEURISTIC MODE (akurasi terbatas).")
            return
        if not self.model_name:
            self.provider = None
            api_monitor.status = "OFFLINE"
            logger.error(f"VLM_MODEL wajib diisi untuk penyedia '{self.provider_name}'. VLM nonaktif.")
            return
        try:
            self.provider = create_provider(self.provider_name, api_key=(self.api_key or "").strip(),
                                            model=self.model_name, **self._provider_options())
            logger.info(f"VLM siap: {self.provider_name} ({self.model_name})")
            api_monitor.status = "ONLINE"
        except Exception as e:
            logger.error(f"Gagal menyiapkan VLM {self.provider_name}: {e}")
            self.provider = None
            api_monitor.record_error(str(e))

    def warm_up(self) -> Optional[float]:
        """Pemanasan VLM saat startup. Mengembalikan durasinya, atau None bila gagal/nonaktif.

        Tanpa ini, pekerja pertama menanggung waktu buka koneksi (Gemini ~3 dtk)
        atau memuat model lokal (Ollama ~38 dtk), yang melebihi batas waktu dan
        membuatnya ditolak sebagai "tidak dapat diverifikasi".
        """
        if self.provider is None:
            return None
        start = time.time()
        try:
            self.executor.submit(self.provider.warm_up).result(timeout=cfg.VLM_WARMUP_TIMEOUT_SECONDS)
        except Exception as e:
            logger.warning(f"Pemanasan VLM {self.provider_name} gagal ({e}); pekerja pertama mungkin lebih lambat.")
            return None
        duration = time.time() - start
        logger.info(f"Pemanasan VLM {self.provider_name} ({self.model_name}) selesai dalam {duration:.1f} dtk.")
        return duration

    def update_api_key(self, new_key: str):
        """Mengganti API key penyedia yang sedang aktif (dari dashboard)."""
        self.api_key = new_key.strip()
        cfg.VLM_API_KEY = self.api_key
        self._init_provider()

    def provider_info(self) -> dict:
        """Penyedia aktif untuk dashboard. Tidak pernah menyertakan API key."""
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "is_local": self.provider_name in LOCAL_VLM_PROVIDERS,
            "needs_key": self.provider_name not in LOCAL_VLM_PROVIDERS,
            "has_key": bool(self.api_key and self.api_key.strip()),
            "is_live": self.is_live_api(),
        }

    def is_live_api(self) -> bool:
        return self.provider is not None

    def ping_api(self) -> dict:
        """Sends a lightweight ping to verify API connectivity and measure round-trip latency."""
        if not self.is_live_api():
            return {
                "status": "OFFLINE",
                "latency_ms": 0,
                "message": "VLM belum aktif (API key belum disetel atau model kosong)"
            }

        start = time.time()
        try:
            reply = self.provider.ping()
            dur_ms = round((time.time() - start) * 1000, 1)
            api_monitor.record_success(dur_ms)
            return {
                "status": api_monitor.status,
                "latency_ms": dur_ms,
                "reply": reply[:30],
                "message": f"Koneksi VLM {self.provider_name} ({self.model_name}) berhasil dan responsif"
            }
        except Exception as e:
            dur_ms = round((time.time() - start) * 1000, 1)
            api_monitor.record_error(str(e))
            return {
                "status": "ERROR",
                "latency_ms": dur_ms,
                "message": str(e)[:cfg.ERROR_MESSAGE_MAX_CHARS]
            }

    def _optimize_image_for_vlm(self, image_bgr: np.ndarray) -> bytes:
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

    def analyze_person(self, person_crop_bgr: np.ndarray) -> APDInspectionResult:
        """Keputusan APD untuk satu crop pekerja.

        Tanpa VLM (tanpa API key, atau operator memilih mode offline) keputusan
        diambil engine lokal dan ditandai akurasi terbatas. Dengan VLM aktif,
        hanya VLM yang boleh memutuskan: panggilan dicoba hingga
        `VLM_MAX_ATTEMPTS` kali dengan batas waktu per percobaan, dan bila semua
        gagal pekerja ditolak sebagai "tidak dapat diverifikasi".
        """
        start_t = time.time()
        
        # 1. Tier 1: Local Real-Time GPU Analysis (~15ms)
        local_result = self.local_analyzer.analyze(person_crop_bgr)

        # 2. Check if Operator Forced Offline Mode (heuristik lokal OpenCV)
        if api_monitor.engine_mode == "FORCE_LOCAL":
            dur_ms = round((time.time() - start_t) * 1000, 1)
            local_result.inference_source = "LOCAL_GPU"
            local_result.inference_time_ms = dur_ms
            local_result.notes = "[MODE OFFLINE AKTIF] Keputusan diambil heuristik lokal OpenCV, akurasi terbatas."
            api_monitor.record_local_call(is_rate_guard=False)
            return local_result

        # 3. VLM belum dikonfigurasi: keputusan engine lokal seketika
        if not self.is_live_api():
            dur_ms = round((time.time() - start_t) * 1000, 1)
            local_result.inference_source = "OFFLINE_FALLBACK" if not self.api_key else "LOCAL_FAST_PASS"
            local_result.inference_time_ms = dur_ms
            api_monitor.record_local_call(is_rate_guard=False)
            return local_result

        # 4. Satu inspeksi VLM pada satu waktu. Permintaan lain MENUNGGU gilirannya,
        # tidak dialihkan ke heuristik lokal: selama VLM aktif, pekerja tidak boleh
        # diloloskan atas dasar heuristik yang terbukti salah dua arah (T21).
        lock_wait = cfg.VLM_MAX_ATTEMPTS * (cfg.VLM_TIMEOUT_SECONDS + cfg.VLM_MIN_INTERVAL_SECONDS) + 1.0
        if not self.api_lock.acquire(timeout=lock_wait):
            return self._unverified_result(start_t, attempts=0, reason="antrean VLM penuh")

        api_monitor.set_locked(True)
        try:
            reason = ""
            for attempt in range(1, cfg.VLM_MAX_ATTEMPTS + 1):
                # 5. Jeda minimum antar panggilan (kuota free tier) ditunggu, bukan dilewati
                wait = cfg.VLM_MIN_INTERVAL_SECONDS - (time.time() - self.last_api_call_time)
                if wait > 0:
                    logger.info(f"Menunggu jeda free tier {wait:.1f}s sebelum panggilan VLM (percobaan {attempt}).")
                    time.sleep(wait)

                # 6. Panggilan VLM dengan batas waktu ketat
                call_start = time.time()
                try:
                    future = self.executor.submit(self._call_vlm_internal, person_crop_bgr)
                    vlm_result = future.result(timeout=cfg.VLM_TIMEOUT_SECONDS)
                    dur_ms = round((time.time() - start_t) * 1000, 1)
                    vlm_result.inference_source = self.source_label
                    vlm_result.inference_time_ms = dur_ms
                    vlm_result.is_low_confidence = False
                    api_monitor.record_success(round((time.time() - call_start) * 1000, 1))
                    return vlm_result
                except TimeoutError:
                    reason = f"timeout > {cfg.VLM_TIMEOUT_SECONDS:g} dtk"
                    logger.warning(f"VLM timeout (> {cfg.VLM_TIMEOUT_SECONDS}s) pada percobaan {attempt}/{cfg.VLM_MAX_ATTEMPTS}.")
                    api_monitor.record_timeout(cfg.VLM_TIMEOUT_SECONDS)
                except Exception as e:
                    reason = f"galat: {str(e)[:60]}"
                    logger.warning(f"VLM gagal pada percobaan {attempt}/{cfg.VLM_MAX_ATTEMPTS}: {e}")
                    api_monitor.record_error(str(e))
                finally:
                    # Dicatat per percobaan agar jeda free tier juga berlaku untuk
                    # percobaan ulang dan panggilan yang gagal/timeout.
                    self.last_api_call_time = time.time()

            return self._unverified_result(start_t, attempts=cfg.VLM_MAX_ATTEMPTS, reason=reason)
        finally:
            api_monitor.set_locked(False)
            self.api_lock.release()

    @staticmethod
    def _unverified_result(start_t: float, attempts: int, reason: str) -> InspectionResult:
        """Penolakan saat VLM aktif tetapi tidak memberi jawaban.

        Tidak memuat klaim per item: tidak ada yang benar-benar diperiksa.
        """
        return InspectionResult(
            items={},
            is_complete=False,
            is_unverified=True,
            missing_items=[messages.VLM_UNVERIFIED_LABEL],
            notes=messages.VLM_UNVERIFIED_NOTES.format(attempts=attempts, reason=reason),
            inference_source="VLM_GAGAL (API Timeout)" if reason.startswith("timeout") else "VLM_GAGAL",
            inference_time_ms=round((time.time() - start_t) * 1000, 1),
            is_low_confidence=False,
        )

    def _call_vlm_internal(self, image_bgr: np.ndarray) -> APDInspectionResult:
        # Satu potret item aktif untuk seluruh panggilan ini, supaya prompt dan
        # penilaian jawaban memakai daftar yang sama walau operator mengubahnya
        # di tengah jalan.
        aktif = ppe_rules.get_active_items()
        data = self.provider.analyze(
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
