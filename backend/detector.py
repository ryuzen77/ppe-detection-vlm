import logging
import cv2
import numpy as np
from ultralytics import YOLO
import torch
from .config import cfg
from . import messages

logger = logging.getLogger(__name__)

class DetectionResult:
    def __init__(self, track_id: int, bbox: list[int], is_full_body: bool, 
                 reason: str, is_inside_corridor: bool = True, keypoints=None, 
                 crop_img=None, conf: float = 0.0, clip_type: str = "OPTIMAL"):
        self.track_id = track_id
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.is_full_body = is_full_body
        self.reason = reason
        self.is_inside_corridor = is_inside_corridor
        self.keypoints = keypoints
        self.crop_img = crop_img
        self.conf = conf
        self.clip_type = clip_type

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

    def detect_and_track(self, frame: np.ndarray) -> list[DetectionResult]:
        """Runs YOLO tracking and height-adaptive full-body filter on the current frame."""
        self.load()
        h, w = frame.shape[:2]

        # Ambang tepi dihitung dari tinggi frame agar perilaku gerbang full-body
        # tetap sama ketika operator berpindah kamera / resolusi.
        margin_top = max(int(h * cfg.BORDER_MARGIN_TOP_RATIO), 1)
        margin_bottom = max(int(h * cfg.BORDER_MARGIN_BOTTOM_RATIO), 1)
        head_touch_top = max(int(h * cfg.HEAD_TOUCH_TOP_RATIO), 1)
        ankle_touch_bottom = max(int(h * cfg.ANKLE_TOUCH_BOTTOM_RATIO), 1)
        knee_only_bottom = max(int(h * cfg.KNEE_ONLY_BOTTOM_RATIO), 1)

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

        detections = []
        if not results or len(results) == 0:
            return detections

        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            return detections

        boxes = r.boxes.xyxy.cpu().numpy()
        track_ids = r.boxes.id.int().cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()

        has_pose = r.keypoints is not None and r.keypoints.data is not None
        keypoints_data = r.keypoints.data.cpu().numpy() if has_pose else None

        # Virtual Corridor Boundaries
        corridor_x1 = int(w * cfg.CORRIDOR_LEFT_RATIO) if cfg.ENABLE_CORRIDOR_FILTER else 0
        corridor_x2 = int(w * cfg.CORRIDOR_RIGHT_RATIO) if cfg.ENABLE_CORRIDOR_FILTER else w

        for idx, (bbox, track_id, conf) in enumerate(zip(boxes, track_ids, confs)):
            x1, y1, x2, y2 = [int(v) for v in bbox]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)

            box_h = y2 - y1
            box_w = x2 - x1
            h_ratio = box_h / h
            center_x = (x1 + x2) / 2

            # Check if person is inside the center inspection corridor
            is_inside_corridor = (corridor_x1 <= center_x <= corridor_x2) if cfg.ENABLE_CORRIDOR_FILTER else True

            # Anatomical Full-Body Verification (Adaptif terhadap Orang Tinggi & Pendek)
            is_full_body = True
            reason = messages.POSE_OK
            clip_type = "OPTIMAL"

            if not is_inside_corridor:
                is_full_body = False
                reason = messages.POSE_OUTSIDE_CORRIDOR
                clip_type = "OUTSIDE_CORRIDOR"

            # 1. Height ratio bounds
            elif h_ratio < cfg.MIN_PERSON_HEIGHT_RATIO:
                is_full_body = False
                reason = messages.POSE_TOO_FAR
                clip_type = "TOO_FAR"
            elif h_ratio > cfg.MAX_PERSON_HEIGHT_RATIO:
                is_full_body = False
                reason = messages.POSE_TOO_CLOSE
                clip_type = "TOO_CLOSE"

            # 2. Keypoint Anatomical Height-Adaptive Verification
            elif has_pose and keypoints_data is not None and idx < len(keypoints_data):
                kpts = keypoints_data[idx]
                
                # Head / Face keypoints: 0=nose, 1=left eye, 2=right eye, 5=left shoulder, 6=right shoulder
                nose_conf = kpts[0][2]
                nose_y = kpts[0][1]
                l_eye_conf = kpts[1][2]
                r_eye_conf = kpts[2][2]
                l_sh_conf = kpts[5][2]
                r_sh_conf = kpts[6][2]

                # Leg / Feet keypoints: 13=left knee, 14=right knee, 15=left ankle, 16=right ankle
                l_ankle_conf = kpts[15][2]
                r_ankle_conf = kpts[16][2]
                l_knee_conf = kpts[13][2]
                r_knee_conf = kpts[14][2]

                # Calculate head scale from shoulder-to-nose distance (for tall person headroom validation)
                sh_y_candidates = []
                if l_sh_conf >= cfg.KEYPOINT_CONF_THRESHOLD: sh_y_candidates.append(kpts[5][1])
                if r_sh_conf >= cfg.KEYPOINT_CONF_THRESHOLD: sh_y_candidates.append(kpts[6][1])
                sh_y = float(np.mean(sh_y_candidates)) if sh_y_candidates else (y1 + box_h * 0.20)

                head_scale = max(sh_y - nose_y, box_h * 0.12) if (nose_conf >= cfg.KEYPOINT_CONF_THRESHOLD and sh_y > nose_y) else (box_h * 0.15)
                expected_helmet_top = nose_y - 0.65 * head_scale

                # Check A: Head / Hard Hat clipping
                # For tall workers, ensure helmet headroom exists above the nose
                if y1 <= head_touch_top or expected_helmet_top < 0 or (nose_conf < cfg.KEYPOINT_CONF_THRESHOLD and l_eye_conf < cfg.KEYPOINT_CONF_THRESHOLD and r_eye_conf < cfg.KEYPOINT_CONF_THRESHOLD):
                    is_full_body = False
                    reason = messages.POSE_HEAD_CLIPPED
                    clip_type = "HEAD_CLIPPED"

                # Check B: Feet / Shoes clipping
                ankles_visible = (l_ankle_conf >= cfg.KEYPOINT_CONF_THRESHOLD or r_ankle_conf >= cfg.KEYPOINT_CONF_THRESHOLD)
                knees_visible = (l_knee_conf >= cfg.KEYPOINT_CONF_THRESHOLD or r_knee_conf >= cfg.KEYPOINT_CONF_THRESHOLD)

                ankle_y_max = 0.0
                if l_ankle_conf >= cfg.KEYPOINT_CONF_THRESHOLD: ankle_y_max = max(ankle_y_max, float(kpts[15][1]))
                if r_ankle_conf >= cfg.KEYPOINT_CONF_THRESHOLD: ankle_y_max = max(ankle_y_max, float(kpts[16][1]))

                if y2 >= (h - margin_bottom) or (ankle_y_max > 0 and ankle_y_max >= (h - ankle_touch_bottom)):
                    is_full_body = False
                    reason = messages.POSE_FEET_CLIPPED
                    clip_type = "FEET_CLIPPED"
                elif not ankles_visible:
                    if not knees_visible or y2 >= (h - knee_only_bottom):
                        is_full_body = False
                        reason = messages.POSE_FEET_NOT_VISIBLE
                        clip_type = "FEET_CLIPPED"

            # Fallback if no pose keypoints available
            else:
                if y1 <= margin_top:
                    is_full_body = False
                    reason = messages.POSE_HEAD_CLIPPED_EDGE
                    clip_type = "HEAD_CLIPPED"
                elif y2 >= (h - margin_bottom):
                    is_full_body = False
                    reason = messages.POSE_FEET_CLIPPED_EDGE
                    clip_type = "FEET_CLIPPED"

            # Extract crop for VLM (add slight margin around bbox for context)
            margin_y = int(box_h * 0.05)
            margin_x = int(box_w * 0.08)
            crop_y1 = max(0, y1 - margin_y)
            crop_y2 = min(h, y2 + margin_y)
            crop_x1 = max(0, x1 - margin_x)
            crop_x2 = min(w, x2 + margin_x)
            crop_img = frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()

            kpts_to_save = keypoints_data[idx].tolist() if has_pose else None
            detections.append(DetectionResult(
                track_id=int(track_id),
                bbox=[x1, y1, x2, y2],
                is_full_body=is_full_body,
                reason=reason,
                is_inside_corridor=is_inside_corridor,
                keypoints=kpts_to_save,
                crop_img=crop_img,
                conf=float(conf),
                clip_type=clip_type
            ))

        return detections


detector = PersonDetector()
