import os
import logging
from dataclasses import dataclass
from typing import Optional
import numpy as np
# Ultralytics memasang paket yang kurang secara otomatis saat berjalan (mis. `lap`
# untuk pelacak). Dimatikan: semua dependensi berasal dari requirements.lock, dan
# paket yang hilang harus gagal jelas, bukan diam-diam mengubah environment.
os.environ.setdefault("YOLO_AUTOINSTALL", "false")
from ultralytics import YOLO  # noqa: E402
import torch
from .config import cfg
from . import zone
from . import messages
from . import pose_keypoints as kp

logger = logging.getLogger(__name__)

class DetectionResult:
    def __init__(self, track_id: int, bbox: list[int], is_full_body: bool, 
                 reason: str, is_inside_corridor: bool = True, keypoints=None, 
                 crop_img=None, conf: float = 0.0, clip_type: str = "OPTIMAL",
                 foot_y: Optional[float] = None, foot_y_box: Optional[float] = None):
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
        self.device_label = (torch.cuda.get_device_name(0).replace("NVIDIA GeForce ", "")
                             if self.device.startswith("cuda") else "CPU")
        logger.info(f"Initializing YOLO with model {cfg.YOLO_MODEL_PATH} on {self.device}...")
        self.model = YOLO(cfg.YOLO_MODEL_PATH)
        logger.info("Model loaded successfully.")

    def _track(self, frame: np.ndarray):
        """Jalankan pelacak YOLO; (kotak, ID, keyakinan, titik pose | None) atau None bila tak ada orang."""
        results = self.model.track(
            source=frame,
            persist=True,
            tracker=cfg.TRACKER_TYPE,
            classes=[0],  # 0 is Person
            conf=cfg.YOLO_CONF,
            iou=cfg.YOLO_IOU,
            device=self.device,
            verbose=False
        )
        if not results or len(results) == 0:
            return None
        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            return None
        has_pose = r.keypoints is not None and r.keypoints.data is not None
        keypoints_data = r.keypoints.data.cpu().numpy() if has_pose else None
        return (r.boxes.xyxy.cpu().numpy(), r.boxes.id.int().cpu().numpy(), r.boxes.conf.cpu().numpy(),
                keypoints_data)

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
            detections.append(DetectionResult(
                track_id=int(track_id), bbox=list(box), is_full_body=is_full_body, reason=reason,
                is_inside_corridor=inside, keypoints=kpts_to_save, crop_img=_crop_for_vlm(frame, box),
                conf=float(conf), clip_type=clip_type,
                foot_y=zone.ankle_y(kpts_to_save, h), foot_y_box=zone.box_bottom_y(list(box), h),
            ))
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
        return FrameMargins(px(cfg.BORDER_MARGIN_TOP_RATIO), px(cfg.BORDER_MARGIN_BOTTOM_RATIO),
                            px(cfg.HEAD_TOUCH_TOP_RATIO), px(cfg.ANKLE_TOUCH_BOTTOM_RATIO),
                            px(cfg.KNEE_ONLY_BOTTOM_RATIO))


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
    head_scale = (max(sh_y - nose_y, box_h * cfg.POSE_HEAD_SCALE_MIN_RATIO)
                  if (_confident(kpts, kp.NOSE) and sh_y > nose_y)
                  else (box_h * cfg.POSE_HEAD_SCALE_FALLBACK_RATIO))
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


def _pose_status(kpts, box, h: int, margins: FrameMargins) -> tuple[bool, str, str]:
    """Verifikasi anatomis adaptif tinggi badan. Masalah kaki menimpa masalah kepala
    (urutan pemeriksaan lama dipertahankan)."""
    _, y1, _, y2 = box
    status = (True, messages.POSE_OK, "OPTIMAL")
    if _head_clipped(kpts, y1, y2 - y1, margins):
        status = (False, messages.POSE_HEAD_CLIPPED, "HEAD_CLIPPED")
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


def _crop_for_vlm(frame: np.ndarray, box) -> np.ndarray:
    """Potongan orang untuk VLM, dengan tepi tambahan untuk konteks helm & sepatu."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    margin_y = int((y2 - y1) * cfg.CROP_MARGIN_Y_RATIO)
    margin_x = int((x2 - x1) * cfg.CROP_MARGIN_X_RATIO)
    return frame[max(0, y1 - margin_y):min(h, y2 + margin_y), max(0, x1 - margin_x):min(w, x2 + margin_x)].copy()

detector = PersonDetector()
