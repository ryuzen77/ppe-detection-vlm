import json
import base64
import os
import time
import io
import cv2
import numpy as np
import threading
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image

from .config import cfg
from .api_monitor import api_monitor
from . import ppe_rules

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
        description="Sumber keputusan: GEMINI_LIVE, LOCAL_FAST_PASS, atau OFFLINE_FALLBACK",
    )
    inference_time_ms: float = Field(default=0.0, description="Durasi inferensi dalam milidetik")
    is_low_confidence: bool = Field(
        default=False,
        description="True jika keputusan berasal dari heuristik lokal yang akurasinya terbatas",
    )

    def item(self, key: str) -> ItemResult:
        """Hasil satu item; item yang tidak dinilai dianggap tidak terdeteksi."""
        return self.items.get(key) or ItemResult()


# Nama lama dipertahankan sebagai alias supaya modul lain yang mengimpornya
# tidak perlu diubah pada task ini.
APDInspectionResult = InspectionResult


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
        self.api_key = cfg.GEMINI_API_KEY
        self.model_name = cfg.GEMINI_MODEL
        self.genai_client = None
        # Prompt yang tertanam pada `genai_client`; klien dibuat ulang bila berbeda
        self._client_prompt = ""
        self.local_analyzer = LocalVisionAnalyzer()
        self.executor = ThreadPoolExecutor(max_workers=cfg.VLM_MAX_CONCURRENT, thread_name_prefix="VLM_Timeout_Guard")
        
        # Free Tier Anti-Spam Guards
        self.api_lock = threading.Lock()
        self.last_api_call_time: float = 0.0

        self._init_gemini()

    def _init_gemini(self):
        if self.api_key and self.api_key.strip():
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key.strip())
                self._build_client(build_system_prompt())
                print(f"[VLMAnalyzer] Successfully connected to Gemini VLM ({self.model_name})")
                api_monitor.status = "ONLINE"
            except Exception as e:
                print(f"[VLMAnalyzer] Error configuring Gemini: {e}")
                self.genai_client = None
                api_monitor.record_error(str(e))
        else:
            self.genai_client = None
            api_monitor.status = "OFFLINE"
            print("[VLMAnalyzer] GEMINI_API_KEY not set. Operating in LOCAL HEURISTIC MODE (akurasi terbatas).")

    def _build_client(self, system_prompt: str):
        """Membuat klien Gemini dengan prompt tertentu. Tidak ada panggilan jaringan."""
        import google.generativeai as genai
        self.genai_client = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
            system_instruction=system_prompt
        )
        self._client_prompt = system_prompt

    def update_api_key(self, new_key: str):
        self.api_key = new_key.strip()
        cfg.GEMINI_API_KEY = self.api_key
        self._init_gemini()

    def is_live_api(self) -> bool:
        return self.genai_client is not None

    def ping_api(self) -> dict:
        """Sends a lightweight ping to verify API connectivity and measure round-trip latency."""
        if not self.is_live_api():
            return {
                "status": "OFFLINE",
                "latency_ms": 0,
                "message": "API Key belum disetel atau offline"
            }

        start = time.time()
        try:
            resp = self.genai_client.generate_content("Ping. Jawab 'PONG'.")
            dur_ms = round((time.time() - start) * 1000, 1)
            api_monitor.record_success(dur_ms)
            return {
                "status": api_monitor.status,
                "latency_ms": dur_ms,
                "reply": resp.text.strip()[:30],
                "message": "Koneksi Gemini API berhasil dan responsif"
            }
        except Exception as e:
            dur_ms = round((time.time() - start) * 1000, 1)
            api_monitor.record_error(str(e))
            return {
                "status": "ERROR",
                "latency_ms": dur_ms,
                "message": str(e)[:cfg.ERROR_MESSAGE_MAX_CHARS]
            }

    def _optimize_image_for_vlm(self, image_bgr: np.ndarray) -> Image.Image:
        """Resizes and compresses image to ~35KB for lightning-fast network upload."""
        h, w = image_bgr.shape[:2]
        max_dim = cfg.VLM_IMAGE_MAX_SIZE
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # Compress to JPEG in memory
        _, buffer = cv2.imencode('.jpg', image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.VLM_JPEG_QUALITY])
        pil_img = Image.open(io.BytesIO(buffer.tobytes()))
        return pil_img

    def analyze_person(self, person_crop_bgr: np.ndarray) -> APDInspectionResult:
        """Hybrid tiered analysis: Runs local check in ~15ms, then Gemini with 2.0s strict timeout
        and Free-Tier Concurrency Lock & Rate Limiting."""
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

        # 3. If Gemini API is not configured, return instant local decision!
        if not self.is_live_api():
            dur_ms = round((time.time() - start_t) * 1000, 1)
            local_result.inference_source = "OFFLINE_FALLBACK" if not self.api_key else "LOCAL_FAST_PASS"
            local_result.inference_time_ms = dur_ms
            api_monitor.record_local_call(is_rate_guard=False)
            return local_result

        # 4. Free Tier Rate Limiter Guard (e.g., minimum 4.0s interval between Gemini calls)
        now = time.time()
        time_since_last = now - self.last_api_call_time
        if time_since_last < cfg.FREE_TIER_MIN_INTERVAL_SECONDS:
            dur_ms = round((time.time() - start_t) * 1000, 1)
            print(f"[VLMAnalyzer] Anti-Spam Free Tier: Jeda baru {time_since_last:.1f}s (< {cfg.FREE_TIER_MIN_INTERVAL_SECONDS}s). Menggunakan Local GPU Fast-Pass.")
            local_result.inference_source = "LOCAL_FAST_PASS (Free-Tier Rate Guard)"
            local_result.inference_time_ms = dur_ms
            local_result.notes = f"[PROTEKSI FREE TIER] Jeda {time_since_last:.1f}s < {cfg.FREE_TIER_MIN_INTERVAL_SECONDS}s, dialihkan ke heuristik lokal agar kuota tidak 429."
            api_monitor.record_local_call(is_rate_guard=True)
            return local_result

        # 5. Free Tier Concurrency Lock (Mencegah spam paralel ganda ke Gemini)
        acquired = self.api_lock.acquire(blocking=False)
        if not acquired:
            dur_ms = round((time.time() - start_t) * 1000, 1)
            print("[VLMAnalyzer] Anti-Spam: API Lock sedang aktif. Dialihkan aman ke Local GPU.")
            local_result.inference_source = "LOCAL_FAST_PASS (API Busy Lock Guard)"
            local_result.inference_time_ms = dur_ms
            local_result.notes = "[API SIBUK] Sedang melayani request lain, verifikasi diselesaikan heuristik lokal."
            api_monitor.record_local_call(is_rate_guard=True)
            return local_result

        # 6. Execute Gemini with Strict Timeout Guard (2.0s)
        api_monitor.set_locked(True)
        try:
            future = self.executor.submit(self._call_gemini_api_internal, person_crop_bgr)
            gemini_result = future.result(timeout=cfg.GEMINI_TIMEOUT_SECONDS)
            dur_ms = round((time.time() - start_t) * 1000, 1)
            gemini_result.inference_source = "GEMINI_LIVE"
            gemini_result.inference_time_ms = dur_ms
            gemini_result.is_low_confidence = False
            api_monitor.record_success(dur_ms)
            return gemini_result
        except TimeoutError:
            print(f"[VLMAnalyzer] Gemini timed out (> {cfg.GEMINI_TIMEOUT_SECONDS}s). Menggunakan Local GPU Fallback!")
            dur_ms = round((time.time() - start_t) * 1000, 1)
            api_monitor.record_timeout(cfg.GEMINI_TIMEOUT_SECONDS)
            local_result.inference_source = "OFFLINE_FALLBACK (API Timeout)"
            local_result.inference_time_ms = dur_ms
            local_result.notes = f"[TIMEOUT {cfg.GEMINI_TIMEOUT_SECONDS}s] API lambat/macet, keputusan dialihkan ke heuristik lokal."
            return local_result
        except Exception as e:
            print(f"[VLMAnalyzer] Network error calling Gemini ({e}). Seamlessly using Local Fallback.")
            dur_ms = round((time.time() - start_t) * 1000, 1)
            api_monitor.record_error(str(e))
            local_result.inference_source = "OFFLINE_FALLBACK"
            local_result.inference_time_ms = dur_ms
            local_result.notes = f"[OFFLINE] Gangguan API ({str(e)[:50]}), keputusan dialihkan ke heuristik lokal."
            return local_result
        finally:
            # Dicatat di finally agar panggilan yang timeout/gagal tetap dihitung
            # oleh rate-guard free tier; kalau tidak, guard 4 detik bocor.
            self.last_api_call_time = time.time()
            api_monitor.set_locked(False)
            self.api_lock.release()

    def _call_gemini_api_internal(self, image_bgr: np.ndarray) -> APDInspectionResult:
        # Satu potret item aktif untuk seluruh panggilan ini, supaya prompt dan
        # penilaian jawaban memakai daftar yang sama walau operator mengubahnya
        # di tengah jalan.
        aktif = ppe_rules.get_active_items()
        system_prompt = build_system_prompt(aktif)
        if system_prompt != self._client_prompt:
            self._build_client(system_prompt)

        pil_img = self._optimize_image_for_vlm(image_bgr)
        prompt = "Periksa kelengkapan APD pekerja pada gambar ini sesuai instruksi K3. Berikan output JSON."
        response = self.genai_client.generate_content([prompt, pil_img])
        
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        data = json.loads(raw_text)
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

        # Alasan penolakan di luar katalog (mis. "Bukan Orang Fisik Nyata")
        # tidak boleh hilang saat kelengkapan dihitung ulang. Label item yang
        # sedang dimatikan tetap dikenali, supaya model yang menyebutnya tidak
        # menolak pekerja atas item yang tidak diwajibkan.
        label_dikenal = {i.missing_label for i in ppe_rules.get_items()}
        tambahan = [
            m for m in (data.get("missing_items") or [])
            if isinstance(m, str) and m not in label_dikenal
        ]
        if tambahan:
            missing = tambahan + missing
            is_complete = False

        return InspectionResult(
            items=items,
            is_complete=is_complete,
            missing_items=missing,
            notes=str(data.get("notes", "")),
        )

vlm_analyzer = VLMAnalyzer()
