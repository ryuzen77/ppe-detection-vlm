import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, List
import cv2
import numpy as np

from config import cfg
from detector import DetectionResult
from vlm_analyzer import vlm_analyzer, APDInspectionResult
from audio_engine import audio_player
from notifier import notifier
from report_manager import report_mgr
from api_monitor import api_monitor

class TrackState:
    INITIAL = "INITIAL"
    STEP_BACK_WARNING = "STEP_BACK_WARNING"
    STABILIZING = "STABILIZING"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"

class PersonTrackInfo:
    def __init__(self, track_id: int):
        self.track_id = track_id
        self.state = TrackState.INITIAL
        self.first_seen = time.time()
        self.last_seen = time.time()
        self.stable_frames = 0
        self.last_step_back_audio_time = 0.0
        self.vlm_result: Optional[APDInspectionResult] = None
        self.latest_crop: Optional[np.ndarray] = None
        self.analysis_timestamp: Optional[float] = None
        self.is_full_body_now = False
        self.current_reason = ""
        self.clip_type = "OPTIMAL"
        self.bbox: list[int] = [0, 0, 0, 0]

class StateManager:
    """Manages person tracking states, full-body step back voice triggers, and anti-spam API calls."""
    def __init__(self):
        self.tracks: Dict[int, PersonTrackInfo] = {}
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="VLM_Worker")
        self.lock = threading.Lock()
        self.inspection_history: List[dict] = []
        self.active_person_id: Optional[int] = None
        self.latest_detections: List[DetectionResult] = []

    def update_frame_detections(self, detections: list[DetectionResult]):
        """Processes detections from the current frame."""
        now = time.time()
        active_ids = set()
        corridor_candidate_ids = []

        with self.lock:
            self.latest_detections = detections
            for det in detections:
                tid = det.track_id
                active_ids.add(tid)

                if tid not in self.tracks:
                    self.tracks[tid] = PersonTrackInfo(tid)

                track = self.tracks[tid]
                track.last_seen = now
                track.is_full_body_now = det.is_full_body
                track.current_reason = det.reason
                track.clip_type = getattr(det, 'clip_type', 'OPTIMAL')
                track.latest_crop = det.crop_img
                track.bbox = det.bbox

                # If outside inspection corridor, ignore for audio warning and VLM trigger
                if not getattr(det, 'is_inside_corridor', True):
                    track.stable_frames = 0
                    continue

                corridor_candidate_ids.append(tid)

                # Anti-spam: If already analyzed, DO NOT trigger API again
                if track.state == TrackState.ANALYZED:
                    continue

                if track.state == TrackState.ANALYZING:
                    continue

                if not det.is_full_body:
                    track.state = TrackState.STEP_BACK_WARNING
                    track.stable_frames = 0
                    
                    # Play voice prompt tailored to head vs feet clipping
                    # Debounced so it doesn't spam speaker
                    if (now - track.last_step_back_audio_time) > cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS:
                        audio_player.play_step_back(clip_type=track.clip_type)
                        track.last_step_back_audio_time = now
                        notifier.set_incomplete(f"Peringatan: {det.reason}")
                else:
                    # Full body confirmed inside corridor
                    track.stable_frames += 1
                    track.state = TrackState.STABILIZING

                    # Wait for stability before sending exactly 1 frame to Gemini VLM
                    if track.stable_frames >= cfg.STABLE_FRAMES_REQUIRED:
                        track.state = TrackState.ANALYZING
                        crop_to_analyze = det.crop_img.copy() if det.crop_img is not None else None
                        print(f"[StateManager] Triggering Gemini VLM analysis for Track ID #{tid} (1 frame)...")
                        audio_player.play("sedang_analisa", min_interval=2.0)
                        
                        self.executor.submit(self._run_vlm_analysis, tid, crop_to_analyze)

            # Prioritize candidate inside the corridor as active person
            if corridor_candidate_ids:
                self.active_person_id = corridor_candidate_ids[0]
            elif active_ids:
                self.active_person_id = list(active_ids)[0]
            else:
                self.active_person_id = None
                if (now - notifier.last_change_time) > cfg.STANDBY_RESET_DELAY_SECONDS and notifier.current_state != "OFF":
                    notifier.set_idle()


            # Clean stale tracks (> TRACK_TIMEOUT_SECONDS absent)
            stale_ids = [tid for tid, t in self.tracks.items() if (now - t.last_seen) > cfg.TRACK_TIMEOUT_SECONDS]
            for tid in stale_ids:
                del self.tracks[tid]

    def _run_vlm_analysis(self, track_id: int, crop_img: Optional[np.ndarray]):
        if crop_img is None:
            return

        try:
            result = vlm_analyzer.analyze_person(crop_img)

            # Persist inspection to SQLite database and archive snapshot crop
            saved_meta = report_mgr.save_inspection(
                track_id=track_id,
                is_complete=result.is_complete,
                helm_data=result.helm.model_dump(),
                rompi_data=result.rompi.model_dump(),
                celana_data=result.celana_panjang.model_dump(),
                sepatu_data=result.sepatu_tertutup.model_dump(),
                missing_items=result.missing_items,
                notes=result.notes,
                inference_source=result.inference_source,
                inference_time_ms=result.inference_time_ms,
                crop_img=crop_img
            )

            with self.lock:
                if track_id in self.tracks:
                    track = self.tracks[track_id]
                    track.vlm_result = result
                    track.state = TrackState.ANALYZED
                    track.analysis_timestamp = time.time()

                    record = {
                        "track_id": track_id,
                        "timestamp": time.strftime("%H:%M:%S"),
                        "is_complete": result.is_complete,
                        "helm": result.helm.model_dump(),
                        "rompi": result.rompi.model_dump(),
                        "celana": result.celana_panjang.model_dump(),
                        "sepatu": result.sepatu_tertutup.model_dump(),
                        "missing_items": result.missing_items,
                        "notes": result.notes,
                        "inference_source": result.inference_source,
                        "inference_time_ms": result.inference_time_ms,
                        "snapshot_filename": saved_meta.get("snapshot_filename", "")
                    }
                    self.inspection_history.insert(0, record)
                    if len(self.inspection_history) > cfg.MAX_HISTORY_RECORDS:
                        self.inspection_history.pop()

                    if result.is_complete:
                        print(f"[StateManager] Track #{track_id}: APD LENGKAP! Green Light ON.")
                        notifier.set_complete("AKSES DIIZINKAN - APD LENGKAP")
                        audio_player.play_result(is_complete=True)
                    else:
                        print(f"[StateManager] Track #{track_id}: APD TIDAK LENGKAP: {result.missing_items}. Red Light ON.")
                        missing_text = ", ".join(result.missing_items)
                        notifier.set_incomplete(f"AKSES DITOLAK - Belum memakai: {missing_text}")
                        audio_player.play_result(is_complete=False, missing_items=result.missing_items)

        except Exception as e:
            print(f"[StateManager] Error during VLM analysis for track #{track_id}: {e}")
            with self.lock:
                if track_id in self.tracks:
                    self.tracks[track_id].state = TrackState.INITIAL

    def reset_track(self, track_id: int):
        with self.lock:
            if track_id in self.tracks:
                self.tracks[track_id].state = TrackState.INITIAL
                self.tracks[track_id].stable_frames = 0
                self.tracks[track_id].vlm_result = None

    def reset_all(self):
        with self.lock:
            self.tracks.clear()
            self.active_person_id = None
            notifier.set_idle()

    def get_telemetry(self) -> dict:
        """Constructs comprehensive real-time payload for WebSocket clients."""
        with self.lock:
            dets_data = []
            for d in self.latest_detections:
                dets_data.append({
                    "track_id": d.track_id,
                    "bbox": d.bbox,
                    "is_full_body": d.is_full_body,
                    "is_inside_corridor": getattr(d, 'is_inside_corridor', True),
                    "reason": d.reason,
                    "clip_type": getattr(d, 'clip_type', 'OPTIMAL'),
                    "conf": round(d.conf, 2),
                    "keypoints": d.keypoints
                })

            active_track_data = None
            if self.active_person_id is not None and self.active_person_id in self.tracks:
                t = self.tracks[self.active_person_id]
                active_track_data = {
                    "track_id": t.track_id,
                    "state": t.state,
                    "is_full_body": t.is_full_body_now,
                    "reason": t.current_reason,
                    "clip_type": t.clip_type,
                    "stable_frames": t.stable_frames,
                    "vlm_result": t.vlm_result.model_dump() if t.vlm_result else None
                }

            return {
                "timestamp": time.time(),
                "has_person": len(dets_data) > 0,
                "active_track": active_track_data,
                "detections": dets_data,
                "corridor": {
                    "enabled": cfg.ENABLE_CORRIDOR_FILTER,
                    "left_ratio": cfg.CORRIDOR_LEFT_RATIO,
                    "right_ratio": cfg.CORRIDOR_RIGHT_RATIO
                },
                "light": notifier.get_status(),
                "history": self.inspection_history[:8],
                "is_live_gemini": vlm_analyzer.is_live_api(),
                "api_monitor": api_monitor.get_status(),
                "engine_mode": api_monitor.engine_mode
            }


state_mgr = StateManager()
