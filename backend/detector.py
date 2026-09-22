import cv2
import numpy as np
from ultralytics import YOLO
import torch
from config import cfg

class DetectionResult:
    def __init__(self, track_id: int, bbox: list[int], is_full_body: bool, 
                 reason: str, is_inside_corridor: bool = True, keypoints=None, 
                 crop_img=None, conf: float = 0.0):
        self.track_id = track_id
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.is_full_body = is_full_body
        self.reason = reason
        self.is_inside_corridor = is_inside_corridor
        self.keypoints = keypoints
        self.crop_img = crop_img
        self.conf = conf

class PersonDetector:
    """YOLOv8-Small Pose Detector with tracking & robust Full-Body verification."""
    def __init__(self):
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        print(f"[PersonDetector] Initializing YOLO with model {cfg.YOLO_MODEL_PATH} on {self.device}...")
        self.model = YOLO(cfg.YOLO_MODEL_PATH)
        print("[PersonDetector] Model loaded successfully.")

    def detect_and_track(self, frame: np.ndarray) -> list[DetectionResult]:
        """Runs YOLO tracking and full-body filter on the current frame."""
        h, w = frame.shape[:2]
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

            # Check Full-Body Conditions
            is_full_body = True
            reason = "Full body terdeteksi sempurna"

            if not is_inside_corridor:
                is_full_body = False
                reason = "Di luar jalur inspeksi (silakan ke tengah)"

            # 1. Height ratio check (avoid people too far in background)
            elif h_ratio < cfg.MIN_PERSON_HEIGHT_RATIO:
                is_full_body = False
                reason = "Terlalu jauh, silakan mendekat ke area inspeksi"

            # 2. Border clipping check (approaching too close to camera)
            elif y1 <= cfg.BORDER_MARGIN_TOP_PX:
                is_full_body = False
                reason = "Kepala terpotong di tepi atas"
            elif y2 >= (h - cfg.BORDER_MARGIN_BOTTOM_PX):
                is_full_body = False
                reason = "Kaki terpotong di tepi bawah"

            # 3. Pose Keypoints check (Head and Ankles/Feet)
            elif has_pose and keypoints_data is not None and idx < len(keypoints_data):
                kpts = keypoints_data[idx]
                nose_conf = kpts[0][2]
                left_ankle_conf = kpts[15][2]
                right_ankle_conf = kpts[16][2]
                left_knee_conf = kpts[13][2]
                right_knee_conf = kpts[14][2]

                # Head visibility check
                if nose_conf < cfg.KEYPOINT_CONF_THRESHOLD and kpts[1][2] < cfg.KEYPOINT_CONF_THRESHOLD:
                    is_full_body = False
                    reason = "Kepala/Wajah belum terlihat jelas"

                # Feet / Ankle visibility check
                ankles_visible = (left_ankle_conf >= cfg.KEYPOINT_CONF_THRESHOLD or 
                                  right_ankle_conf >= cfg.KEYPOINT_CONF_THRESHOLD)
                knees_visible = (left_knee_conf >= cfg.KEYPOINT_CONF_THRESHOLD or 
                                 right_knee_conf >= cfg.KEYPOINT_CONF_THRESHOLD)

                if not ankles_visible:
                    if not knees_visible or y2 >= (h - cfg.BORDER_MARGIN_BOTTOM_PX * 2):
                        is_full_body = False
                        reason = "Kaki/Sepatu terpotong atau belum terlihat"

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
                conf=float(conf)
            ))

        return detections


detector = PersonDetector()
