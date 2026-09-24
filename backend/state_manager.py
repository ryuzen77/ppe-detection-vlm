import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List
import numpy as np

from .config import cfg
from . import messages
from .detector import DetectionResult
from .vlm_analyzer import vlm_analyzer, APDInspectionResult
from .audio_engine import audio_player
from .notifier import notifier
from .report_manager import report_mgr
from .api_monitor import api_monitor

logger = logging.getLogger(__name__)

class TrackState:
    INITIAL = "INITIAL"
    STEP_BACK_WARNING = "STEP_BACK_WARNING"
    STABILIZING = "STABILIZING"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"


class GateSession:
    """Satu giliran pemeriksaan di gerbang, dari pekerja masuk jalur sampai jalur kosong.

    Keputusan dikunci per sesi, BUKAN per ID pelacak: ByteTrack bisa memberi ID
    baru saat orang yang sama tertutup sesaat atau membungkuk, dan bila keputusan
    dikunci per ID, orang itu diperiksa ulang tanpa pernah meninggalkan gerbang
    (panggilan VLM dan baris audit ganda, dan keputusan bisa berubah). Sesi baru
    dimulai hanya setelah jalur inspeksi kosong selama STANDBY_RESET_DELAY_SECONDS.
    """

    _counter = 0

    def __init__(self, track_id: int, now: float):
        GateSession._counter += 1
        self.session_id = GateSession._counter
        self.track_id = track_id          # ID pelacak terkini, hanya untuk tampilan
        self.state = TrackState.INITIAL
        self.started_at = now
        self.last_seen = now
        self.stable_frames = 0
        self.last_step_back_audio_time = 0.0
        self.step_back_warning_count = 0
        self.vlm_result: Optional[APDInspectionResult] = None
        self.analysis_timestamp: Optional[float] = None
        self.is_full_body_now = False
        self.current_reason = ""
        self.clip_type = "OPTIMAL"


class StateManager:
    """Mesin keadaan gerbang: arahan posisi, satu analisa VLM per sesi, dan keputusan lampu."""
    def __init__(self):
        self.session: Optional[GateSession] = None
        self.executor = ThreadPoolExecutor(max_workers=cfg.VLM_MAX_CONCURRENT, thread_name_prefix="VLM_Worker")
        self.lock = threading.Lock()
        self.inspection_history: List[dict] = []
        self.latest_detections: List[DetectionResult] = []

    @staticmethod
    def _pick_subject(candidates: list[DetectionResult], current_id: Optional[int]) -> DetectionResult:
        """Subjek sesi: ID yang sama bila masih terlihat, bila tidak yang paling dekat (bbox tertinggi)."""
        for det in candidates:
            if det.track_id == current_id:
                return det
        return max(candidates, key=lambda d: d.bbox[3] - d.bbox[1])

    def update_frame_detections(self, detections: list[DetectionResult]):
        """Processes detections from the current frame."""
        now = time.time()

        with self.lock:
            self.latest_detections = detections
            # Hanya orang di jalur inspeksi yang dihitung; orang yang lewat di
            # luar jalur tidak memulai sesi dan tidak menahan reset.
            in_lane = [d for d in detections if getattr(d, "is_inside_corridor", True)]

            if not in_lane:
                if self.session is not None and (now - self.session.last_seen) > cfg.STANDBY_RESET_DELAY_SECONDS:
                    logger.info(f"Sesi #{self.session.session_id} selesai: jalur kosong. Gerbang standby.")
                    self.session = None
                    notifier.set_idle()
                return

            session = self.session
            if session is None:
                session = self.session = GateSession(in_lane[0].track_id, now)
                logger.info(f"Sesi #{session.session_id} dimulai.")

            det = self._pick_subject(in_lane, session.track_id)
            session.track_id = det.track_id
            session.last_seen = now
            session.is_full_body_now = det.is_full_body
            session.current_reason = det.reason
            session.clip_type = getattr(det, "clip_type", "OPTIMAL")

            # Keputusan sesi terkunci sampai jalur kosong: tidak ada panggilan VLM kedua
            if session.state in (TrackState.ANALYZING, TrackState.ANALYZED):
                return

            if not det.is_full_body:
                session.state = TrackState.STEP_BACK_WARNING
                session.stable_frames = 0
                # Arahan posisi hanya lewat suara dan dashboard. LED merah khusus
                # untuk APD tidak lengkap, jadi lampu tidak disentuh di sini.
                # Smart Limiter: Max repeats (default 2x) per session with debounce so it doesn't spam
                if session.step_back_warning_count < cfg.AUDIO_STEP_BACK_MAX_REPEATS:
                    if (now - session.last_step_back_audio_time) > cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS:
                        audio_player.play_step_back(clip_type=session.clip_type)
                        session.last_step_back_audio_time = now
                        session.step_back_warning_count += 1
                return

            session.step_back_warning_count = 0
            session.stable_frames += 1
            session.state = TrackState.STABILIZING

            # Wait for stability before sending exactly 1 frame to the VLM
            if session.stable_frames >= cfg.STABLE_FRAMES_REQUIRED:
                session.state = TrackState.ANALYZING
                crop_to_analyze = det.crop_img.copy() if det.crop_img is not None else None
                logger.info(f"Sesi #{session.session_id}: analisa VLM untuk Track #{det.track_id} (1 frame)...")
                audio_player.play("sedang_analisa", min_interval=cfg.AUDIO_ANALYZING_DEBOUNCE_SECONDS)
                self.executor.submit(self._run_vlm_analysis, session.session_id, det.track_id, crop_to_analyze)

    def _run_vlm_analysis(self, session_id: int, track_id: int, crop_img: Optional[np.ndarray]):
        if crop_img is None:
            self._retry_session(session_id)
            return

        try:
            result = vlm_analyzer.analyze_person(crop_img)

            # Pemeriksaan sudah terjadi, jadi selalu tercatat di audit, termasuk
            # bila pekerjanya sudah pergi sebelum hasil tiba.
            saved_meta = report_mgr.save_inspection(
                track_id=track_id,
                is_complete=result.is_complete,
                items={key: item.model_dump() for key, item in result.items.items()},
                missing_items=result.missing_items,
                notes=result.notes,
                inference_source=result.inference_source,
                inference_time_ms=result.inference_time_ms,
                crop_img=crop_img
            )

            with self.lock:
                record = {
                    "track_id": track_id,
                    "timestamp": time.strftime("%H:%M:%S"),
                    "is_complete": result.is_complete,
                    "items": {key: item.model_dump() for key, item in result.items.items()},
                    "missing_items": result.missing_items,
                    "notes": result.notes,
                    "inference_source": result.inference_source,
                    "inference_time_ms": result.inference_time_ms,
                    "snapshot_filename": saved_meta.get("snapshot_filename", "")
                }
                self.inspection_history.insert(0, record)
                if len(self.inspection_history) > cfg.MAX_HISTORY_RECORDS:
                    self.inspection_history.pop()

                session = self.session
                if session is None or session.session_id != session_id:
                    # Pekerja sudah meninggalkan jalur: lampu dan suara tidak
                    # boleh ditujukan ke orang berikutnya.
                    logger.info(f"Hasil sesi #{session_id} tiba setelah sesi berakhir; gerbang tidak diubah.")
                    return

                session.vlm_result = result
                session.state = TrackState.ANALYZED
                session.analysis_timestamp = time.time()

                if result.is_unverified:
                    logger.warning(f"Sesi #{session_id}: VLM tidak dapat memverifikasi APD. Red Light ON.")
                    notifier.set_incomplete(messages.LIGHT_UNVERIFIED)
                    audio_player.play("verifikasi_gagal", min_interval=cfg.AUDIO_RESULT_DEBOUNCE_SECONDS)
                elif result.is_complete:
                    logger.info(f"Sesi #{session_id}: APD LENGKAP! Green Light ON.")
                    notifier.set_complete(messages.LIGHT_GRANTED)
                    audio_player.play_result(is_complete=True)
                else:
                    logger.info(f"Sesi #{session_id}: APD TIDAK LENGKAP: {result.missing_items}. Red Light ON.")
                    missing_text = ", ".join(result.missing_items)
                    notifier.set_incomplete(messages.LIGHT_DENIED_MISSING.format(missing=missing_text))
                    audio_player.play_result(is_complete=False, missing_items=result.missing_items)

        except Exception as e:
            logger.exception(f"Error during VLM analysis for session #{session_id}: {e}")
            self._retry_session(session_id)

    def _retry_session(self, session_id: int):
        """Analisa tidak menghasilkan keputusan (galat internal): sesi boleh mencoba lagi."""
        with self.lock:
            if self.session is not None and self.session.session_id == session_id:
                self.session.state = TrackState.INITIAL
                self.session.stable_frames = 0

    def reset_all(self):
        with self.lock:
            self.session = None
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
            s = self.session
            if s is not None:
                active_track_data = {
                    "track_id": s.track_id,
                    "session_id": s.session_id,
                    "state": s.state,
                    "is_full_body": s.is_full_body_now,
                    "reason": s.current_reason,
                    "clip_type": s.clip_type,
                    "stable_frames": s.stable_frames,
                    "vlm_result": s.vlm_result.model_dump() if s.vlm_result else None
                }

            return {
                "timestamp": time.time(),
                "frame_width": cfg.FRAME_WIDTH,
                "frame_height": cfg.FRAME_HEIGHT,
                "has_person": len(dets_data) > 0,
                "active_track": active_track_data,
                "detections": dets_data,
                "corridor": {
                    "enabled": cfg.ENABLE_CORRIDOR_FILTER,
                    "left_ratio": cfg.CORRIDOR_LEFT_RATIO,
                    "right_ratio": cfg.CORRIDOR_RIGHT_RATIO
                },
                "light": notifier.get_status(),
                "history": self.inspection_history[:cfg.TELEMETRY_HISTORY_RECORDS],
                # Frontend butuh angka ini untuk indikator "stabil x / y";
                # dulu ditulis tetap "/ 2" dan akan salah begitu config diubah.
                "stable_frames_required": cfg.STABLE_FRAMES_REQUIRED,
                "is_live_vlm": vlm_analyzer.is_live_api(),
                "vlm": vlm_analyzer.provider_info(),
                "api_monitor": api_monitor.get_status(),
                "engine_mode": api_monitor.engine_mode
            }


state_mgr = StateManager()
