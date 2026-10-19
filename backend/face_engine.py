"""Mesin pengenalan wajah gerbang (T34b2): deteksi YuNet + embedding Intel 0095 di CPU.

Model dipilih lewat uji nyata T34m/T34m2/T34a (docs/RENCANA.md, Rancangan T34).
Foto tidak pernah disimpan: frame hanya dipakai di memori untuk menghitung embedding.
Model dimuat saat pertama dipakai, jadi server tanpa FR tidak membayar waktu muatnya.
"""

import logging
import threading
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from . import messages
from .config import cfg
from .face_align import align_face, interocular_px

logger = logging.getLogger(__name__)


class FaceEngineError(Exception):
    """Foto tidak layak dipakai; `code` stabil untuk UI (kontrak T34b)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FaceDetection:
    box: tuple[int, int, int, int]  # x, y, lebar, tinggi
    landmarks: np.ndarray  # 5 titik urutan YuNet
    score: float

    @property
    def interocular_px(self) -> float:
        return interocular_px(self.landmarks)

    def quality(self) -> dict:
        return {
            "face_width_px": self.box[2],
            "interocular_px": round(self.interocular_px, 1),
            "det_score": round(self.score, 3),
        }


@dataclass(frozen=True)
class FaceSample:
    detection: FaceDetection
    vector: np.ndarray  # embedding ternormalisasi (norma 1)


def parse_detections(raw: Optional[np.ndarray], min_score: float) -> list[FaceDetection]:
    """Baris keluaran YuNet (x, y, w, h, 10 koordinat landmark, skor) -> deteksi di atas skor minimal."""
    if raw is None:
        return []
    return [
        FaceDetection(
            (int(row[0]), int(row[1]), int(row[2]), int(row[3])),
            row[4:14].reshape(5, 2).astype(np.float32),
            float(row[14]),
        )
        for row in raw
        if float(row[14]) >= min_score
    ]


def pick_enrollment_face(
    detections: list[FaceDetection], min_interocular: float, max_interocular: float = float("inf")
) -> FaceDetection:
    """Foto pendaftaran harus berisi tepat satu wajah yang cukup besar. Wajah kecil di latar
    (orang antre jauh) tidak dihitung, tetapi dua wajah besar ditolak: templat tidak boleh
    tertukar dengan orang lain. T76: wajah yang jauh lebih besar dari wajah di jalur juga ditolak."""
    if not detections:
        raise FaceEngineError("no_face", messages.WORKER_NO_FACE)
    usable = [d for d in detections if d.interocular_px >= min_interocular]
    if len(usable) > 1:
        raise FaceEngineError("multiple_faces", messages.WORKER_MULTIPLE_FACES.format(count=len(usable)))
    if not usable:
        largest = max(detections, key=lambda d: d.interocular_px)
        raise FaceEngineError(
            "face_too_small",
            messages.WORKER_FACE_TOO_SMALL.format(measured=largest.interocular_px, minimum=min_interocular),
        )
    if usable[0].interocular_px > max_interocular:
        raise FaceEngineError(
            "face_too_close",
            messages.WORKER_FACE_TOO_CLOSE.format(measured=usable[0].interocular_px, maximum=max_interocular),
        )
    return usable[0]


def enrollment_bounds(frame_height: int) -> tuple[float, float]:
    """Batas jarak antar-mata foto pendaftaran untuk resolusi kamera saat ini (min, maks piksel).

    Minimal tetap piksel (mutu embedding), maksimal sebanding tinggi frame (meniru jarak di jalur).
    Kamera di bawah resolusi minimal ditolak: wajah di jalur tidak akan cukup besar untuk dikenali."""
    if frame_height < cfg.ENROLLMENT_MIN_FRAME_HEIGHT:
        raise FaceEngineError(
            "camera_low_resolution",
            messages.WORKER_CAMERA_LOW_RESOLUTION.format(height=frame_height, minimum=cfg.ENROLLMENT_MIN_FRAME_HEIGHT),
        )
    return cfg.FACE_MIN_INTEROCULAR_PX, cfg.ENROLLMENT_MAX_INTEROCULAR_RATIO * frame_height


# Kode galat foto -> arahan untuk pendamping (no_face & multiple_faces tetap)
_FIT_BY_ERROR = {"face_too_small": "too_far", "face_too_close": "too_close", "camera_low_resolution": "low_resolution"}


def enrollment_fit(detections: list[FaceDetection], frame_height: int) -> dict:
    """Indikator jarak sebelum memotret (T76), aturan yang sama dengan foto pendaftaran:
    "ok" | "no_face" | "too_far" | "too_close" | "multiple_faces" | "low_resolution"."""
    try:
        face = pick_enrollment_face(detections, *enrollment_bounds(frame_height))
        fit, measured = "ok", face.interocular_px
    except FaceEngineError as e:
        fit = _FIT_BY_ERROR.get(e.code, e.code)
        measured = max((d.interocular_px for d in detections), default=None)
    return {"fit": fit, "faces": len(detections), "interocular_px": None if measured is None else round(measured, 1)}


def pick_subject_face(detections: list[FaceDetection], min_interocular: float) -> Optional[FaceDetection]:
    """Wajah subjek pada potongan tubuh pekerja (T34c1): yang terbesar, asal cukup besar untuk
    dikenali. Berbeda dengan pendaftaran, wajah lain tidak membuat frame ditolak (potongan
    pekerja bisa memuat sebagian orang antre), tetapi juga tidak pernah dipilih bila lebih kecil."""
    usable = [d for d in detections if d.interocular_px >= min_interocular]
    return max(usable, key=lambda d: d.interocular_px) if usable else None


def normalize(vector: np.ndarray) -> np.ndarray:
    flat = np.asarray(vector, dtype=np.float32).ravel()
    return flat / np.linalg.norm(flat)


class FaceEngine:
    def __init__(self):
        self._lock = threading.Lock()  # infer request OpenVINO & detektor YuNet tidak aman lintas thread
        self._detector = None
        self._request = None
        self._detector_size: Optional[tuple[int, int]] = None

    def _models(self):
        """Detektor & infer request, dimuat sekali. Panggil di bawah `_lock`."""
        if self._detector is None or self._request is None:
            import openvino as ov  # diimpor saat dipakai: server tanpa FR tidak memuatnya

            model_dir = cfg.FACE_MODEL_DIR
            try:
                self._detector = cv2.FaceDetectorYN.create(
                    str(model_dir / cfg.FACE_DETECTOR_FILE), "", (320, 320), cfg.FACE_DET_SCORE_MIN
                )
                compiled = ov.Core().compile_model(
                    str(model_dir / cfg.FACE_RECOGNIZER_FILE), "CPU", {"INFERENCE_NUM_THREADS": cfg.FACE_CPU_THREADS}
                )
                self._request = compiled.create_infer_request()
            except Exception as e:
                logger.error(messages.FACE_ENGINE_LOAD_FAILED.format(path=model_dir, error=e))
                raise
        return self._detector, self._request

    def _detect(self, detector, frame: np.ndarray) -> list[FaceDetection]:
        size = (frame.shape[1], frame.shape[0])
        if self._detector_size != size:
            detector.setInputSize(size)
            self._detector_size = size
        return parse_detections(detector.detect(frame)[1], cfg.FACE_DET_SCORE_MIN)

    @staticmethod
    def _embed(request, frame: np.ndarray, detection: FaceDetection) -> np.ndarray:
        crop = align_face(frame, detection.landmarks, cfg.FACE_ALIGN_TEMPLATE, cfg.FACE_INPUT_SIZE)
        # IR Intel 0095: BGR mentah 0..255, NCHW
        blob = crop.transpose(2, 0, 1)[None].astype(np.float32)
        return normalize(request.infer({0: blob})[0])

    def detect(self, frame: np.ndarray) -> list[FaceDetection]:
        with self._lock:
            detector, _ = self._models()
            return self._detect(detector, frame)

    def enrollment_sample(self, frame: np.ndarray) -> FaceSample:
        """Satu templat pendaftaran dari frame kamera; FaceEngineError bila foto tidak layak."""
        bounds = enrollment_bounds(frame.shape[0])
        with self._lock:
            detector, request = self._models()
            detection = pick_enrollment_face(self._detect(detector, frame), *bounds)
            return FaceSample(detection, self._embed(request, frame, detection))

    def subject_embeddings(self, crops: list[np.ndarray]) -> list[Optional[np.ndarray]]:
        """Embedding wajah subjek per potongan pekerja; None bila tidak ada wajah yang cukup besar."""
        with self._lock:
            detector, request = self._models()
            vectors: list[Optional[np.ndarray]] = []
            for crop in crops:
                face = pick_subject_face(self._detect(detector, crop), cfg.FACE_MIN_INTEROCULAR_PX)
                vectors.append(None if face is None else self._embed(request, crop, face))
            return vectors


engine = FaceEngine()
