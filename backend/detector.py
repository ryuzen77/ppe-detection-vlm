import os
import logging
from dataclasses import dataclass
from typing import Optional
import numpy as np

# Ultralytics memasang paket yang kurang secara otomatis saat berjalan (mis. `lap`
# untuk pelacak). Dimatikan: semua dependensi berasal dari requirements.lock, dan
# paket yang hilang harus gagal jelas, bukan diam-diam mengubah environment.
os.environ.setdefault("YOLO_AUTOINSTALL", "false")
from ultralytics import YOLO  # noqa: E402  # pyright: ignore[reportPrivateImportUsage]
import torch
from .config import cfg
from . import zone
from . import messages
from . import pose_keypoints as kp
from . import vlm_image

logger = logging.getLogger(__name__)


class DetectionResult:
    def __init__(
        self,
        track_id: int,
        bbox: list[int],
        is_full_body: bool,
        reason: str,
        is_inside_corridor: bool = True,
        keypoints=None,
        crop_img=None,
        conf: float = 0.0,
        clip_type: str = "OPTIMAL",
        foot_y: Optional[float] = None,
        foot_y_box: Optional[float] = None,
    ):
        self.track_id = track_id
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.is_full_body = is_full_body
        self.reason = reason
        self.is_inside_corridor = is_inside_corridor
        self.keypoints = keypoints
        self.crop_img = crop_img
        self.conf = conf
        self.clip_type = clip_type
        # Posisi kaki relatif tinggi gambar, untuk zona titik berdiri (T36d):
        # dari pergelangan kaki (None bila tertutup) dan dari tepi bawah kotak.
        self.foot_y = foot_y
        self.foot_y_box = foot_y_box
        # T86: titik pose dalam koordinat crop_img (diisi detect_and_track); None = tanpa pose
        self.crop_keypoints: Optional[list] = None
        # Posisi yang dipakai zona setelah ingatan per ID (diisi state_manager)
        self.zone_y = foot_y if foot_y is not None else foot_y_box


class PersonDetector:
    """YOLO26-Small Pose Detector with tracking & robust Full-Body verification."""

    def __init__(self):
        # Model dan GPU baru disentuh di load(), bukan saat modul diimpor
        self.model = None
        self.device = ""
        self.device_label = ""

    def load(self):
        """Memuat bobot YOLO ke GPU (atau CPU bila CUDA tidak ada). Idempoten."""
        if self.model is not None:
            return
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        # Nama perangkat untuk HUD, supaya tidak menyebut GPU yang tidak terpasang
        self.device_label = (
            torch.cuda.get_device_name(0).replace("NVIDIA GeForce ", "") if self.device.startswith("cuda") else "CPU"
        )
        logger.info(f"Initializing YOLO with model {cfg.YOLO_MODEL_PATH} on {self.device}...")
        self.model = YOLO(cfg.YOLO_MODEL_PATH)
        logger.info("Model loaded successfully.")

    def _track(self, frame: np.ndarray):
        """Jalankan pelacak YOLO; (kotak, ID, keyakinan, titik pose | None) atau None bila tak ada orang."""
        model = self.model
        assert model is not None, "model dimuat sebelum frame pertama"
        results = model.track(
            source=frame,
            persist=True,
            tracker=cfg.TRACKER_TYPE,
            classes=[0],  # 0 is Person
            conf=cfg.YOLO_CONF,
            iou=cfg.YOLO_IOU,
            device=self.device,
            verbose=False,
        )
        if not results or len(results) == 0:
            return None
        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            return None
        has_pose = r.keypoints is not None and r.keypoints.data is not None
        # Stub ultralytics menyebut Tensor | ndarray; saat inferensi selalu Tensor (punya .cpu()).
        keypoints_data = r.keypoints.data.cpu().numpy() if has_pose else None  # pyright: ignore
        return (
            r.boxes.xyxy.cpu().numpy(),
            r.boxes.id.int().cpu().numpy(),  # pyright: ignore
            r.boxes.conf.cpu().numpy(),
            keypoints_data,
        )  # pyright: ignore

    def detect_and_track(self, frame: np.ndarray) -> list[DetectionResult]:
        """Runs YOLO tracking and height-adaptive full-body filter on the current frame."""
        self.load()
        h, w = frame.shape[:2]
        tracked = self._track(frame)
        if tracked is None:
            return []
        boxes, track_ids, confs, keypoints_data = tracked
        margins = FrameMargins.for_height(h)
        detections = []
        for idx, (bbox, track_id, conf) in enumerate(zip(boxes, track_ids, confs)):
            kpts = keypoints_data[idx] if keypoints_data is not None and idx < len(keypoints_data) else None
            box = _clip_box(bbox, w, h)
            inside = _inside_corridor(box, w)
            is_full_body, reason, clip_type = _full_body_status(box, kpts, inside, h, margins)
            kpts_to_save = keypoints_data[idx].tolist() if keypoints_data is not None else None
            window = vlm_image.crop_window(h, w, box)
            detection = DetectionResult(
                track_id=int(track_id),
                bbox=list(box),
                is_full_body=is_full_body,
                reason=reason,
                is_inside_corridor=inside,
                keypoints=kpts_to_save,
                crop_img=_crop(frame, window),
                conf=float(conf),
                clip_type=clip_type,
                foot_y=zone.ankle_y(kpts_to_save, h),
                foot_y_box=zone.box_bottom_y(list(box), h),
            )
            # T86: titik pose dalam koordinat crop untuk panel perbesaran kepala & tangan
            detection.crop_keypoints = vlm_image.to_crop_coords(kpts_to_save, window)
            detections.append(detection)
        return detections


# --- Pemeriksaan tubuh utuh (dipecah dari detect_and_track, T42a; perilaku dijaga
# tests/test_detector_fullbody.py). Fungsi murni: mudah dites tanpa YOLO. ----------------


@dataclass(frozen=True)
class FrameMargins:
    """Ambang tepi dalam piksel, dihitung dari tinggi frame agar perilaku gerbang
    full-body tetap sama ketika operator berpindah kamera / resolusi."""

    top: int
    bottom: int
    head_touch_top: int
    ankle_touch_bottom: int
    knee_only_bottom: int

    @staticmethod
    def for_height(h: int) -> "FrameMargins":
        def px(ratio: float) -> int:
            return max(int(h * ratio), 1)

        return FrameMargins(
            px(cfg.BORDER_MARGIN_TOP_RATIO),
            px(cfg.BORDER_MARGIN_BOTTOM_RATIO),
            px(cfg.HEAD_TOUCH_TOP_RATIO),
            px(cfg.ANKLE_TOUCH_BOTTOM_RATIO),
            px(cfg.KNEE_ONLY_BOTTOM_RATIO),
        )


def _clip_box(bbox, w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    return max(0, x1), max(0, y1), min(w, x2), min(h, y2)


def _inside_corridor(box, w: int) -> bool:
    """Titik tengah kotak di dalam koridor pemeriksaan tengah."""
    if not cfg.ENABLE_CORRIDOR_FILTER:
        return True
    center_x = (box[0] + box[2]) / 2
    return int(w * cfg.CORRIDOR_LEFT_RATIO) <= center_x <= int(w * cfg.CORRIDOR_RIGHT_RATIO)


def _confident(kpts, index: int) -> bool:
    return kpts[index][kp.CONFIDENCE] >= cfg.KEYPOINT_CONF_THRESHOLD


def _head_clipped(kpts, y1: int, box_h: int, margins: FrameMargins) -> bool:
    """Kepala/helm terpotong: kotak menyentuh tepi atas, ruang helm di atas hidung keluar
    gambar (orang tinggi), atau wajah sama sekali tak terlihat."""
    nose_y = kpts[kp.NOSE][kp.Y]
    shoulders = [kpts[i][kp.Y] for i in (kp.LEFT_SHOULDER, kp.RIGHT_SHOULDER) if _confident(kpts, i)]
    sh_y = float(np.mean(shoulders)) if shoulders else (y1 + box_h * cfg.POSE_SHOULDER_FALLBACK_RATIO)
    head_scale = (
        max(sh_y - nose_y, box_h * cfg.POSE_HEAD_SCALE_MIN_RATIO)
        if (_confident(kpts, kp.NOSE) and sh_y > nose_y)
        else (box_h * cfg.POSE_HEAD_SCALE_FALLBACK_RATIO)
    )
    expected_helmet_top = nose_y - cfg.POSE_HELMET_HEADROOM_FACTOR * head_scale
    face_invisible = not any(_confident(kpts, i) for i in (kp.NOSE, kp.LEFT_EYE, kp.RIGHT_EYE))
    return y1 <= margins.head_touch_top or expected_helmet_top < 0 or face_invisible


def _feet_status(kpts, y2: int, h: int, margins: FrameMargins) -> Optional[str]:
    """Pesan bila kaki/sepatu terpotong atau tak terlihat; None bila kaki terlihat utuh."""
    ankles = [float(kpts[i][kp.Y]) for i in (kp.LEFT_ANKLE, kp.RIGHT_ANKLE) if _confident(kpts, i)]
    ankle_y_max = max([0.0] + ankles)
    if y2 >= (h - margins.bottom) or (ankle_y_max > 0 and ankle_y_max >= (h - margins.ankle_touch_bottom)):
        return messages.POSE_FEET_CLIPPED
    knees_visible = _confident(kpts, kp.LEFT_KNEE) or _confident(kpts, kp.RIGHT_KNEE)
    if not ankles and (not knees_visible or y2 >= (h - margins.knee_only_bottom)):
        return messages.POSE_FEET_NOT_VISIBLE
    return None


def _thigh_shin_ratio(kpts, hip: int, knee: int, ankle: int) -> Optional[float]:
    """Tinggi tegak paha dibagi tulang kering pada satu sisi tubuh; None bila titiknya kurang.
    Pergelangan kaki tidak di bawah lutut (kaki terangkat/terlipat) dihitung 0 = belum berdiri."""
    if not all(_confident(kpts, i) for i in (hip, knee, ankle)):
        return None
    shin = float(kpts[ankle][kp.Y] - kpts[knee][kp.Y])
    return float(kpts[knee][kp.Y] - kpts[hip][kp.Y]) / shin if shin > 0 else 0.0


def _not_standing(kpts) -> bool:
    """Duduk/jongkok (T73): paha mendatar sehingga lutut hampir sejajar pinggul.

    Cukup satu sisi tegak (orang melangkah tetap berdiri). Titik yang kurang di kedua
    sisi tidak menghalangi: kaki yang tak terlihat sudah ditangani `_feet_status`, dan
    menolak karena titik hilang akan menahan pekerja patuh yang tertutup rompi.
    """
    ratios = [
        r
        for r in (
            _thigh_shin_ratio(kpts, kp.LEFT_HIP, kp.LEFT_KNEE, kp.LEFT_ANKLE),
            _thigh_shin_ratio(kpts, kp.RIGHT_HIP, kp.RIGHT_KNEE, kp.RIGHT_ANKLE),
        )
        if r is not None
    ]
    return bool(ratios) and max(ratios) < cfg.STANDING_MIN_THIGH_SHIN_RATIO


def _pose_status(kpts, box, h: int, margins: FrameMargins) -> tuple[bool, str, str]:
    """Verifikasi anatomis adaptif tinggi badan. Masalah kaki menimpa postur, postur
    menimpa kepala: orang duduk diminta berdiri dulu sebelum posisi kepala dinilai."""
    _, y1, _, y2 = box
    status = (True, messages.POSE_OK, "OPTIMAL")
    if _head_clipped(kpts, y1, y2 - y1, margins):
        status = (False, messages.POSE_HEAD_CLIPPED, "HEAD_CLIPPED")
    if _not_standing(kpts):
        status = (False, messages.POSE_NOT_STANDING, "NOT_STANDING")
    feet = _feet_status(kpts, y2, h, margins)
    return (False, feet, "FEET_CLIPPED") if feet else status


def _edge_status(box, h: int, margins: FrameMargins) -> tuple[bool, str, str]:
    """Tanpa titik pose: hanya tepi kotak yang bisa dinilai."""
    if box[1] <= margins.top:
        return False, messages.POSE_HEAD_CLIPPED_EDGE, "HEAD_CLIPPED"
    if box[3] >= (h - margins.bottom):
        return False, messages.POSE_FEET_CLIPPED_EDGE, "FEET_CLIPPED"
    return True, messages.POSE_OK, "OPTIMAL"


def _full_body_status(box, kpts, inside: bool, h: int, margins: FrameMargins) -> tuple[bool, str, str]:
    """(utuh?, pesan arahan, jenis potongan) untuk satu orang."""
    h_ratio = (box[3] - box[1]) / h
    if not inside:
        return False, messages.POSE_OUTSIDE_CORRIDOR, "OUTSIDE_CORRIDOR"
    if h_ratio < cfg.MIN_PERSON_HEIGHT_RATIO:
        return False, messages.POSE_TOO_FAR, "TOO_FAR"
    if h_ratio > cfg.MAX_PERSON_HEIGHT_RATIO:
        return False, messages.POSE_TOO_CLOSE, "TOO_CLOSE"
    return _pose_status(kpts, box, h, margins) if kpts is not None else _edge_status(box, h, margins)


def _crop(frame: np.ndarray, window) -> np.ndarray:
    """Potongan orang untuk VLM (jendela `vlm_image.crop_window`: kotak + tepi helm & sepatu)."""
    x0, y0, x1, y1 = window
    return frame[y0:y1, x0:x1].copy()


detector = PersonDetector()
