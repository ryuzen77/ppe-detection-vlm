import logging
import time
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Optional, List
import numpy as np

from .config import cfg
from . import messages
from .detector import DetectionResult
from . import face_identity, frame_quality, worker_voice
from .readiness import ReadinessTracker
from .vlm_analyzer import vlm_analyzer, InspectionResult
from .audio_engine import audio_player
from .notifier import notifier
from .report_manager import report_mgr
from .api_monitor import api_monitor
from . import zone as zones
from .zone import zone_store

logger = logging.getLogger(__name__)

class TrackState:
    INITIAL = "INITIAL"
    STEP_BACK_WARNING = "STEP_BACK_WARNING"
    STABILIZING = "STABILIZING"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    # Tidak ada VLM yang menjawab (utama & cadangan gagal): belum ada keputusan,
    # pekerja diminta menunggu dan diperiksa ulang otomatis (T27)
    WAITING_SYSTEM = "WAITING_SYSTEM"


def bbox_iou(a, b) -> float:
    """Irisan per gabungan dua kotak [x1, y1, x2, y2]."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class GateSession:
    """Satu giliran pemeriksaan di gerbang, dari pekerja masuk jalur sampai jalur kosong.

    Keputusan dikunci per sesi, BUKAN per ID pelacak: ByteTrack bisa memberi ID
    baru saat orang yang sama tertutup sesaat atau membungkuk, dan bila keputusan
    dikunci per ID, orang itu diperiksa ulang tanpa pernah meninggalkan gerbang
    (panggilan VLM dan baris audit ganda, dan keputusan bisa berubah). Sesi baru
    dimulai hanya setelah jalur inspeksi kosong selama STANDBY_RESET_DELAY_SECONDS.

    Sejak T36c jeda itu dipersingkat, dan sebagai gantinya keputusan LOLOS per ID
    pelacak diingat DECIDED_TRACK_MEMORY_SECONDS: bila sesi baru dimulai untuk ID
    yang baru saja lolos (mis. keluar jalur sesaat saat berjalan ke gerbang),
    keputusan itu dipakai ulang tanpa VLM, audit, maupun suara ulang.
    Keputusan DITOLAK sengaja tidak diingat: pekerja yang mundur selangkah,
    memperbaiki APD, lalu maju lagi biasanya masih ber-ID sama dan harus
    diperiksa ulang, bukan ditolak lagi (temuan tinjauan Gemini, T36c).

    T59: "jalur kosong" saja tidak cukup untuk mengakhiri sesi — poster K3 bergambar
    orang (atau orang antre) di koridor membuat jalur tidak pernah kosong, dan sesi
    dulu berpindah ke mereka membawa keputusan. Kini setelah keputusan, sesi hanya
    mengikuti subjek yang diputuskan; ID baru dianggap orang yang sama hanya bila
    belum pernah terlihat bersamaan dengan subjek, muncul segera, dan kotaknya hampir
    sama. Selain itu sesi ditutup setelah subjek hilang STANDBY_RESET_DELAY_SECONDS.
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
        self.vlm_result: Optional[InspectionResult] = None
        # Kapan pemeriksaan diulang setelah gangguan sistem (WAITING_SYSTEM)
        self.retry_at = 0.0
        self.analysis_timestamp: Optional[float] = None
        self.is_full_body_now = False
        self.current_reason = ""
        self.clip_type = "OPTIMAL"
        # Frame tubuh-utuh berturut-turut yang sedang dikumpulkan (T25a)
        self.candidates: List[frame_quality.FrameCandidate] = []
        # Kotak tubuh frame sebelum kandidat pertama, untuk menilai gerakan
        self.prev_bbox: Optional[list] = None
        # T59: kotak terakhir subjek & track lain yang pernah terlihat bersamaannya
        self.subject_bbox: Optional[list] = None
        self.seen_with_subject: set[int] = set()
        # Jendela "diam & menghadap kamera" sebelum dipotret (T46)
        self.readiness = ReadinessTracker()
        # Siapa pekerjanya (T34c1); None = belum/tidak dicoba
        self.identity: Optional[face_identity.Identity] = None

    def restart_candidates(self, bbox: list):
        """Rangkaian kandidat terputus: frame lama tidak boleh ikut dinilai."""
        self.stable_frames = 0
        self.candidates = []
        self.prev_bbox = bbox

    def add_candidate(self, candidate: "frame_quality.FrameCandidate"):
        """Menyimpan kandidat terbaru; yang tertua dibuang di atas READY_MAX_CANDIDATES."""
        self.stable_frames += 1
        self.candidates.append(candidate)
        if len(self.candidates) > cfg.READY_MAX_CANDIDATES:
            # Kotak frame yang dibuang jadi acuan gerak kandidat tertua berikutnya
            self.prev_bbox = self.candidates.pop(0).bbox


class StateManager:
    """Mesin keadaan gerbang: arahan posisi, satu analisa VLM per sesi, dan keputusan lampu."""
    def __init__(self):
        self.session: Optional[GateSession] = None
        self.executor = ThreadPoolExecutor(max_workers=cfg.VLM_MAX_CONCURRENT, thread_name_prefix="VLM_Worker")
        # Pengenalan wajah paralel dengan VLM (T34c1): keputusan APD tidak menunggu FR
        self.fr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="FR_Worker")
        self.lock = threading.Lock()
        self.inspection_history: List[dict] = []
        self.latest_detections: List[DetectionResult] = []
        # Posisi kaki terakhir yang jelas per ID, saat kaki tertutup (T36d)
        self.foot_memory = zones.FootMemory()
        # ID pelacak -> (waktu, keputusan) untuk sesi yang LOLOS (T36c)
        self.recent_decisions: dict[int, tuple[float, InspectionResult]] = {}
        # Gangguan kamera yang sedang berlaku (T45): None | "lost" | "blocked" | "frozen"
        self.camera_fault: Optional[str] = None
        self.camera_fault_since = 0.0
        # Kapan tiap suara gangguan terakhir diputar (per jenis suara, T45b)
        self.camera_fault_sound_at: dict[str, float] = {}
        # Jeda pendaftaran wajah (T75): batas waktu (time.time) dari denyut terakhir; 0 = tidak aktif
        self.enrollment_until = 0.0

    def set_camera_fault(self, fault: Optional[str]):
        """Dipanggil tiap frame oleh thread inferensi; hanya PERUBAHAN keadaan yang bertindak.

        Selama kamera bermasalah gerbang tidak boleh memutuskan apa pun dari gambar
        yang tidak bisa dipercaya: sesi & keputusan dibatalkan (termasuk hijau yang
        sedang menyala), lampu kuning tetap, suara gangguan sekali (keputusan pengguna).
        """
        with self.lock:
            if fault == self.camera_fault:
                return
            previous, self.camera_fault = self.camera_fault, fault
            now = time.time()
            if fault is None:
                logger.info(messages.LOG_CAMERA_FAULT_END.format(fault=previous, seconds=now - self.camera_fault_since))
                self._show_resting_light(now)
                return
            if previous is None:
                self.camera_fault_since = now
            logger.warning(messages.LOG_CAMERA_FAULT_START.format(fault=fault))
            # T75: wajah yang didekatkan ke kamera saat pendaftaran terbaca "terhalang"; admin ada di
            # tempat, jadi suara gangguan tidak diputar (lampu kembali ke gangguan saat jeda selesai)
            if not self._enrolling(now):
                self._announce_camera_fault(fault, previous, now)
            # Hasil VLM yang tiba belakangan untuk sesi ini diabaikan (cek id sesi)
            self.session = None
            self._show_resting_light(now)

    def enrollment_active(self) -> bool:
        with self.lock:
            return self._enrolling(time.time())

    def _enrolling(self, now: float) -> bool:
        return now < self.enrollment_until

    def _show_resting_light(self, now: float):
        """Lampu saat tidak ada keputusan: jeda pendaftaran > gangguan kamera > siaga."""
        if self._enrolling(now):
            notifier.set_waiting(messages.LIGHT_ENROLLMENT)
        elif self.camera_fault is not None:
            notifier.set_waiting(messages.LIGHT_CAMERA_FAULT[self.camera_fault])
        else:
            notifier.set_idle()

    def hold_for_enrollment(self) -> bool:
        """Admin memotret wajah pendaftaran (T75): gerbang jeda, dipanggil ulang sebagai denyut.

        Orang yang didaftarkan berdiri di depan kamera gerbang; tanpa jeda ia langsung diperiksa
        (sesi, arahan posisi, VLM) dan foto ditolak `camera_busy` (uji nyata 19-10). Sesi yang
        berjalan dibatalkan, termasuk hijau yang menyala: jeda tidak pernah meloloskan orang.
        True = jeda baru dimulai (bukan denyut).
        """
        with self.lock:
            now = time.time()
            started = not self._enrolling(now)
            self.enrollment_until = now + cfg.ENROLLMENT_HOLD_SECONDS
            if started:
                logger.info(messages.LOG_ENROLLMENT_HOLD_START)
                self.session = None     # hasil VLM yang tiba belakangan diabaikan (cek id sesi)
                self._show_resting_light(now)
            return started

    def release_enrollment(self) -> bool:
        """Modal foto ditutup. True = jeda memang sedang berlaku."""
        with self.lock:
            if not self._enrolling(time.time()):
                return False
            self._finish_enrollment(messages.LOG_ENROLLMENT_HOLD_END)
            return True

    def _finish_enrollment(self, reason: str):
        self.enrollment_until = 0.0
        logger.info(reason)
        self._show_resting_light(time.time())

    def _enrollment_paused(self, now: float) -> bool:
        """True selama jeda pendaftaran; jeda yang kehabisan denyut ditutup di sini (per frame)."""
        if self.enrollment_until == 0.0:
            return False
        if self._enrolling(now):
            return True
        self._finish_enrollment(messages.LOG_ENROLLMENT_HOLD_EXPIRED)
        return False

    def _announce_camera_fault(self, fault: str, previous: Optional[str], now: float):
        """Suara gangguan: terputus & terhalang dibedakan (uji fisik 06-10).

        Pengulangan suara yang SAMA ditahan CAMERA_FAULT_SOUND_COOLDOWN_SECONDS (mis. kamera
        putus-sambung), tetapi pergantian jenis (terhalang -> terputus) tetap diumumkan.
        """
        sound = messages.CAMERA_FAULT_SOUND[fault]
        if previous is not None and messages.CAMERA_FAULT_SOUND[previous] == sound:
            return
        if now - self.camera_fault_sound_at.get(sound, float("-inf")) < cfg.CAMERA_FAULT_SOUND_COOLDOWN_SECONDS:
            return
        self.camera_fault_sound_at[sound] = now
        audio_player.play(sound, urgent=True)

    @staticmethod
    def _pick_subject(candidates: list[DetectionResult], current_id: Optional[int],
                      locked: bool = False) -> DetectionResult:
        """Subjek sesi: ID yang sama bila masih terlihat, bila tidak yang paling dekat (bbox tertinggi).

        T59: sebelum keputusan, orang bertubuh utuh didahulukan. Poster K3 bergambar orang
        terdeteksi terus tetapi tidak pernah utuh; tanpa ini sesi terus mengikuti poster dan
        pekerja yang datang tidak pernah diperiksa. Setelah keputusan (`locked`) subjek tetap.
        """
        current = next((d for d in candidates if d.track_id == current_id), None)
        full = [d for d in candidates if d.is_full_body]
        if current is not None and (locked or current.is_full_body or not full):
            return current
        return max(full or candidates, key=lambda d: d.bbox[3] - d.bbox[1])

    def _remember_decision(self, track_id: int, result: InspectionResult, now: float):
        # Hanya lolos: yang ditolak harus bisa diperiksa ulang setelah memperbaiki APD
        if result.is_complete:
            self.recent_decisions[track_id] = (now, result)

    def _recent_decision(self, track_id: int, now: float) -> Optional[InspectionResult]:
        """Keputusan untuk ID ini bila masih dalam ingatan; entri kedaluwarsa dibuang."""
        for tid, (at, _) in list(self.recent_decisions.items()):
            if now - at > cfg.DECIDED_TRACK_MEMORY_SECONDS:
                del self.recent_decisions[tid]
        entry = self.recent_decisions.get(track_id)
        return entry[1] if entry else None

    @staticmethod
    def _show_decision(result: InspectionResult):
        """Lampu untuk keputusan APD (suara diputar terpisah oleh pemanggil)."""
        if result.is_complete:
            notifier.set_complete(messages.LIGHT_GRANTED)
        else:
            notifier.set_incomplete(messages.LIGHT_DENIED_MISSING.format(missing=", ".join(result.missing_items)))

    def update_frame_detections(self, detections: list[DetectionResult]):
        """Satu frame: siapa di jalur -> sesi -> arahan posisi / kumpulkan frame -> analisa VLM.

        Dipecah per langkah (T42a/b); perilaku dijaga tests/test_state_characterization.py.
        """
        now = time.time()
        with self.lock:
            self.latest_detections = detections
            if self._enrollment_paused(now):
                return          # admin memotret wajah pendaftaran: tidak ada sesi (T75)
            if self.camera_fault is not None:
                return          # gambar tidak bisa dipercaya: tidak ada sesi baru (T45)
            in_lane = self._people_in_lane(detections, now)
            if not in_lane:
                self._close_session_if_lane_empty(now)
                return
            session = self._session_for(in_lane, now)
            if self._decided_subject_absent(session, in_lane, now):
                return
            det = self._follow_subject(session, in_lane, now)
            if not self._may_inspect(session, det, now):
                return
            if not det.is_full_body:
                self._guide_position(session, det, now)
                return
            if self._collect_candidate(session, det, now):
                self._start_analysis(session, det, now)

    def _people_in_lane(self, detections: list[DetectionResult], now: float) -> list[DetectionResult]:
        """Hanya orang di jalur inspeksi yang dihitung; orang yang lewat di luar jalur
        tidak memulai sesi dan tidak menahan reset. Bila zona titik berdiri aktif
        (T36d), antrean di belakang zona juga diabaikan, jadi sesi berakhir begitu
        subjek keluar zona dan orang berikutnya maju."""
        for d in detections:
            d.zone_y = self.foot_memory.resolve(d.track_id, getattr(d, "foot_y", None),
                                                getattr(d, "foot_y_box", None), now)
        active_zone = zone_store.get()
        return [d for d in detections if getattr(d, "is_inside_corridor", True)
                and zones.in_zone(getattr(d, "zone_y", None), active_zone)]

    def _close_session_if_lane_empty(self, now: float):
        if self.session is None or (now - self.session.last_seen) <= cfg.STANDBY_RESET_DELAY_SECONDS:
            return
        self._end_session(now, messages.LOG_SESSION_LANE_EMPTY)

    def _decided_subject_absent(self, session: GateSession, in_lane: list[DetectionResult], now: float) -> bool:
        """Keputusan terikat pada track pekerja yang diputuskan (T59).

        Uji 14-10: poster K3 bergambar orang terdeteksi stabil di koridor, jadi jalur
        tidak pernah kosong; sesi lalu mengikuti poster dan pekerja berikutnya mewarisi
        keputusan tanpa diperiksa. Setelah ada keputusan (atau analisa berjalan), sesi
        tidak lagi berpindah ke orang lain: bila track subjek hilang lebih lama dari
        STANDBY_RESET_DELAY_SECONDS, sesi ditutup. True = frame ini tidak diproses lanjut.
        """
        if session.state not in (TrackState.ANALYZING, TrackState.ANALYZED):
            return False
        if any(d.track_id == session.track_id for d in in_lane):
            session.seen_with_subject.update(d.track_id for d in in_lane if d.track_id != session.track_id)
            return False
        same = self._same_person_new_id(session, in_lane, now)
        if same is not None:
            logger.info(f"Sesi #{session.session_id}: Track #{session.track_id} berganti ID menjadi "
                        f"#{same.track_id} (orang yang sama); keputusan tetap.")
            session.track_id = same.track_id
            return False
        if now - session.last_seen > cfg.STANDBY_RESET_DELAY_SECONDS:
            self._end_session(now, messages.LOG_SESSION_SUBJECT_LEFT)
        return True

    @staticmethod
    def _same_person_new_id(session: GateSession, in_lane: list[DetectionResult],
                            now: float) -> Optional[DetectionResult]:
        """ID baru pelacak untuk subjek yang sama (ByteTrack bisa mengganti ID orang yang diam)."""
        if session.subject_bbox is None or now - session.last_seen > cfg.SUBJECT_REID_MAX_GAP_SECONDS:
            return None
        fresh = [d for d in in_lane if d.track_id not in session.seen_with_subject]
        best = max(fresh, key=lambda d: bbox_iou(d.bbox, session.subject_bbox), default=None)
        if best is None or bbox_iou(best.bbox, session.subject_bbox) < cfg.SUBJECT_REID_MIN_IOU:
            return None
        return best

    def _end_session(self, now: float, reason: str):
        session = self.session
        assert session is not None, "hanya dipanggil saat ada sesi"
        logger.info(reason.format(session_id=session.session_id))
        if session.vlm_result is not None:
            # ID terakhir subjek (bisa berbeda dari ID saat dianalisa)
            self._remember_decision(session.track_id, session.vlm_result, now)
        self.session = None
        notifier.set_idle()

    def _session_for(self, in_lane: list[DetectionResult], now: float) -> GateSession:
        """Sesi yang berjalan, atau sesi baru untuk orang paling dekat di jalur."""
        if self.session is not None:
            return self.session
        subject = self._pick_subject(in_lane, None)
        session = self.session = GateSession(subject.track_id, now)
        logger.info(f"Sesi #{session.session_id} dimulai.")
        previous = self._recent_decision(subject.track_id, now)
        if previous is not None:
            # Orang yang sama baru saja diputuskan: keputusan tetap berlaku
            session.vlm_result = previous
            session.state = TrackState.ANALYZED
            session.analysis_timestamp = now
            self._show_decision(previous)
            logger.info(f"Sesi #{session.session_id}: Track #{subject.track_id} baru saja diputuskan; "
                        f"keputusan dipakai ulang tanpa analisa baru.")
        return session

    def _follow_subject(self, session: GateSession, in_lane: list[DetectionResult], now: float) -> DetectionResult:
        det = self._pick_subject(in_lane, session.track_id,
                                 locked=session.state in (TrackState.ANALYZING, TrackState.ANALYZED))
        session.track_id = det.track_id
        session.last_seen = now
        session.is_full_body_now = det.is_full_body
        session.current_reason = det.reason
        session.clip_type = getattr(det, "clip_type", "OPTIMAL")
        session.subject_bbox = list(det.bbox)
        return det

    def _may_inspect(self, session: GateSession, det: DetectionResult, now: float) -> bool:
        """False selama menunggu ulang gangguan sistem atau keputusan sesi sudah terkunci."""
        # Gangguan sistem: tunggu jeda, lalu kumpulkan frame dan periksa ulang
        # orang yang sama selama ia masih di jalur
        if session.state == TrackState.WAITING_SYSTEM:
            if now < session.retry_at:
                return False
            logger.info(f"Sesi #{session.session_id}: mencoba ulang pemeriksaan setelah gangguan sistem.")
            session.state = TrackState.INITIAL
            session.restart_candidates(det.bbox)
            session.readiness.reset()
        # Keputusan sesi terkunci sampai jalur kosong: tidak ada panggilan VLM kedua
        return session.state not in (TrackState.ANALYZING, TrackState.ANALYZED)

    def _guide_position(self, session: GateSession, det: DetectionResult, now: float):
        """Tubuh belum utuh: arahan posisi lewat suara & dashboard. LED merah khusus APD
        tidak lengkap, jadi lampu tidak disentuh di sini."""
        session.state = TrackState.STEP_BACK_WARNING
        # Kandidat hanya dari rangkaian tubuh-utuh yang tidak terputus
        session.restart_candidates(det.bbox)
        session.readiness.reset()
        # Batas pengulangan suara per sesi (bawaan 2x) dengan jeda, supaya tidak berisik
        if session.step_back_warning_count >= cfg.AUDIO_STEP_BACK_MAX_REPEATS:
            return
        if (now - session.last_step_back_audio_time) > cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS:
            audio_player.play_step_back(clip_type=session.clip_type)
            session.last_step_back_audio_time = now
            session.step_back_warning_count += 1

    def _collect_candidate(self, session: GateSession, det: DetectionResult, now: float) -> bool:
        """Tubuh utuh: kumpulkan frame selama pekerja diam (T46). True = siap dianalisa."""
        session.step_back_warning_count = 0
        session.state = TrackState.STABILIZING
        # Pekerja masih melangkah atau menyamping: kumpulan kandidat dimulai ulang (T46)
        if session.readiness.update(det.bbox, det.keypoints, now):
            session.restart_candidates(session.candidates[-1].bbox if session.candidates else det.bbox)
        if not session.readiness.holding:
            return False
        if det.crop_img is not None:
            session.add_candidate(frame_quality.FrameCandidate(
                crop=det.crop_img.copy(), bbox=list(det.bbox), keypoints=det.keypoints, track_id=det.track_id,
                crop_keypoints=getattr(det, "crop_keypoints", None)))
        else:
            session.stable_frames += 1
        # Setelah pekerja diam READY_HOLD_SECONDS (minimal STABLE_FRAMES_REQUIRED frame)
        return session.stable_frames >= cfg.STABLE_FRAMES_REQUIRED and session.readiness.ready(now)

    def _start_analysis(self, session: GateSession, det: DetectionResult, now: float):
        """Kirim SATU frame terbaik (paling tajam, paling diam, pose paling jelas) dari
        jendela diam ke VLM; keputusan sesi terkunci sejak titik ini."""
        logger.info(messages.LOG_SESSION_READY.format(
            session=session.session_id, held=session.readiness.held_seconds(now),
            restarts=session.readiness.restarts, frames=session.stable_frames))
        session.state = TrackState.ANALYZING
        crop_to_analyze, track_id, identity, crop_keypoints = None, det.track_id, None, None
        if session.candidates:
            best = frame_quality.choose_best(session.candidates, session.prev_bbox)
            identity = self._start_identity(session)
            crop_to_analyze, track_id, crop_keypoints = best.crop, best.track_id, best.crop_keypoints
            logger.info(
                f"Sesi #{session.session_id}: frame terbaik #{session.candidates.index(best) + 1} dari "
                f"{len(session.candidates)} | skor " + ", ".join(
                    f"{c.score:.2f} (tajam {c.sharpness:.0f}, gerak {c.motion:.3f}, pose {c.pose:.2f})"
                    for c in session.candidates))
        session.candidates = []
        logger.info(f"Sesi #{session.session_id}: analisa VLM untuk Track #{track_id} (1 frame)...")
        audio_player.play("sedang_analisa", min_interval=cfg.AUDIO_ANALYZING_DEBOUNCE_SECONDS)
        self.executor.submit(self._run_vlm_analysis, session.session_id, track_id, crop_to_analyze, identity,
                             crop_keypoints)

    def _start_identity(self, session: GateSession) -> Optional[Future]:
        """FR pada FACE_VOTE_FRAMES potongan terbaik (skor `choose_best`), paralel dengan VLM.
        Nama dipasang ke sesi begitu selesai, supaya Monitoring menampilkannya lebih awal."""
        if not face_identity.identifier.store.face_ready():
            return None  # FR mati (tanpa kunci): gerbang berperilaku persis seperti sebelum T34
        ranked = sorted(session.candidates, key=lambda c: c.score, reverse=True)[:cfg.FACE_VOTE_FRAMES]
        return self.fr_executor.submit(self._identify_session, session.session_id, [c.crop for c in ranked])

    def _identify_session(self, session_id: int, crops: list[np.ndarray]) -> face_identity.Identity:
        """Dijalankan di thread FR. Nama dipasang ke sesi DI SINI, bukan lewat add_done_callback:
        callback future yang sudah selesai berjalan di thread pemanggil (_start_analysis, yang
        memegang self.lock) sehingga mengambil kunci lagi = deadlock (terjadi saat T34c1 diuji)."""
        identity = face_identity.identifier.identify(crops, session_id)
        with self.lock:
            if self.session is not None and self.session.session_id == session_id:
                self.session.identity = identity
        return identity

    @staticmethod
    def _await_identity(session_id: int, future: Optional[Future]) -> Optional[face_identity.Identity]:
        """Identitas untuk audit: tunggu sebentar bila FR belum selesai; lewat = tidak dikenali."""
        if future is None:
            return None
        try:
            return future.result(timeout=cfg.FACE_IDENTIFY_TIMEOUT_SECONDS)
        except FutureTimeout:
            logger.warning(messages.LOG_FACE_TIMEOUT.format(session=session_id,
                                                            seconds=cfg.FACE_IDENTIFY_TIMEOUT_SECONDS))
            return face_identity.Identity(face_identity.UNKNOWN)

    def _run_vlm_analysis(self, session_id: int, track_id: int, crop_img: Optional[np.ndarray],
                          identity_future: Optional[Future] = None, crop_keypoints: Optional[list] = None):
        if crop_img is None:
            self._retry_session(session_id)
            return

        try:
            result = vlm_analyzer.analyze_person(crop_img, crop_keypoints)

            if result.is_system_unavailable:
                self._wait_for_system(session_id, result)
                return

            # Pemeriksaan sudah terjadi, jadi selalu tercatat di audit, termasuk
            # bila pekerjanya sudah pergi sebelum hasil tiba.
            identity = self._await_identity(session_id, identity_future)
            saved_meta = self._save_audit(track_id, result, crop_img, identity)
            with self.lock:
                self._record_history(track_id, result, saved_meta, identity)
                self._apply_decision(session_id, track_id, result)

        except Exception as e:
            logger.exception(f"Error during VLM analysis for session #{session_id}: {e}")
            self._retry_session(session_id)

    @staticmethod
    def _items_payload(result: InspectionResult) -> dict:
        return {key: item.model_dump() for key, item in result.items.items()}

    def _save_audit(self, track_id: int, result: InspectionResult, crop_img: np.ndarray,
                    identity: Optional[face_identity.Identity] = None) -> dict:
        extra = {} if identity is None else {"identity": {
            "worker_id": identity.worker_id, "employee_no": identity.employee_no, "name": identity.name,
            "status": identity.status, "score": identity.score,
            "department": identity.department, "company": identity.company}}
        return report_mgr.save_inspection(
            track_id=track_id,
            is_complete=result.is_complete,
            items=self._items_payload(result),
            missing_items=result.missing_items,
            notes=result.notes,
            inference_source=result.inference_source,
            inference_time_ms=result.inference_time_ms,
            crop_img=crop_img,
            **extra,
        )

    def _record_history(self, track_id: int, result: InspectionResult, saved_meta: dict,
                        identity: Optional[face_identity.Identity] = None):
        """Riwayat dashboard (terbaru di depan, dibatasi MAX_HISTORY_RECORDS). Pemanggil memegang lock."""
        self.inspection_history.insert(0, {
            "track_id": track_id,
            "timestamp": time.strftime("%H:%M:%S"),
            "is_complete": result.is_complete,
            "items": self._items_payload(result),
            "missing_items": result.missing_items,
            "notes": result.notes,
            "inference_source": result.inference_source,
            "inference_time_ms": result.inference_time_ms,
            "decided_by": result.decided_by,
            "snapshot_filename": saved_meta.get("snapshot_filename", ""),
            # Identitas dari pengenalan wajah (T34c1); None = tanpa FR
            "worker_name": identity.name if identity else None,
            "employee_no": identity.employee_no if identity else None,
            "fr_status": identity.status if identity else None,
        })
        if len(self.inspection_history) > cfg.MAX_HISTORY_RECORDS:
            self.inspection_history.pop()

    def _apply_decision(self, session_id: int, track_id: int, result: InspectionResult):
        """Kunci keputusan ke sesi, lalu lampu & suara. Pemanggil memegang lock."""
        session = self.session
        if session is None or session.session_id != session_id:
            # Pekerja sudah meninggalkan jalur: lampu dan suara tidak
            # boleh ditujukan ke orang berikutnya.
            logger.info(f"Hasil sesi #{session_id} tiba setelah sesi berakhir; gerbang tidak diubah.")
            return

        session.vlm_result = result
        session.state = TrackState.ANALYZED
        session.analysis_timestamp = time.time()
        self._remember_decision(track_id, result, session.analysis_timestamp)

        if result.is_complete:
            logger.info(f"Sesi #{session_id}: APD LENGKAP! Green Light ON.")
        else:
            logger.info(f"Sesi #{session_id}: APD TIDAK LENGKAP: {result.missing_items}. Red Light ON.")
        self._show_decision(result)
        audio_player.play_result(is_complete=result.is_complete, missing_items=result.missing_items,
                                 **self._named_voice(session, result))

    @staticmethod
    def _named_voice(session: GateSession, result: InspectionResult) -> dict:
        """Suara "Silakan masuk, Pak/Bu <nama>" (T34d): hanya saat LOLOS dan pekerja DIKENALI FR;
        selain itu suara umum. Kosong = argumen tidak dikirim (pemanggil lama tidak berubah)."""
        identity = session.identity
        if not result.is_complete or identity is None or identity.status != face_identity.RECOGNIZED:
            return {}
        voice = worker_voice.pass_voice(identity.worker_id)
        return {} if voice is None else {"named_voice": voice}

    def _wait_for_system(self, session_id: int, result: InspectionResult):
        """Utama & cadangan gagal: tanpa keputusan, tanpa baris audit, tanpa LED merah.

        Pekerja diminta menunggu lewat suara; bila ia masih di jalur setelah
        VLM_SYSTEM_RETRY_SECONDS, pemeriksaan diulang otomatis. Gangguan cukup
        dicatat di log (keputusan pengguna).
        """
        with self.lock:
            session = self.session
            if session is None or session.session_id != session_id:
                return
            session.state = TrackState.WAITING_SYSTEM
            # vlm_result sengaja tidak diisi: tidak ada item yang dinilai, jadi
            # dashboard menampilkan "belum dinilai" (kuning), bukan hasil kosong.
            session.retry_at = time.time() + cfg.VLM_SYSTEM_RETRY_SECONDS
            logger.warning(f"Sesi #{session_id}: sistem gangguan, pekerja diminta menunggu; "
                           f"diperiksa ulang dalam {cfg.VLM_SYSTEM_RETRY_SECONDS:g} dtk.")
            notifier.set_waiting()
            audio_player.play("sistem_gangguan", min_interval=cfg.AUDIO_SYSTEM_WAIT_DEBOUNCE_SECONDS, urgent=True)

    def _retry_session(self, session_id: int):
        """Analisa tidak menghasilkan keputusan (galat internal): sesi boleh mencoba lagi."""
        with self.lock:
            if self.session is not None and self.session.session_id == session_id:
                self.session.state = TrackState.INITIAL
                self.session.stable_frames = 0

    def reset_all(self):
        with self.lock:
            self.session = None
            # Reset operator = mulai bersih: orang yang sama boleh diperiksa ulang
            self.recent_decisions.clear()
            self.foot_memory.clear()
            # Gangguan kamera TIDAK dihapus di sini (mis. thread pembaca me-reset gerbang
            # setelah kamera dibuka ulang): baru selesai bila gambarnya sehat lagi (T45b).
            # Jeda pendaftaran (T75) juga tetap berlaku.
            self._show_resting_light(time.time())

    def get_telemetry(self) -> dict:
        """Constructs comprehensive real-time payload for WebSocket clients."""
        with self.lock:
            active_zone = zone_store.get()
            dets_data = [self._detection_payload(d, active_zone) for d in self.latest_detections]
            return {
                "timestamp": time.time(),
                "frame_width": cfg.FRAME_WIDTH,
                "frame_height": cfg.FRAME_HEIGHT,
                "has_person": len(dets_data) > 0,
                "active_track": self._session_payload(self.session),
                "detections": dets_data,
                **self._lane_payload(active_zone),
                "light": notifier.get_status(),
                "camera_fault": self.camera_fault,
                "enrollment": self._enrollment_payload(time.time()),
                "history": self.inspection_history[:cfg.TELEMETRY_HISTORY_RECORDS],
                # Frontend butuh angka ini untuk indikator "stabil x / y";
                # dulu ditulis tetap "/ 2" dan akan salah begitu config diubah.
                "stable_frames_required": cfg.STABLE_FRAMES_REQUIRED,
                # Ambang yang sama dengan detektor, agar overlay tidak menggambar
                # titik pose yang diabaikan backend
                "keypoint_conf_threshold": cfg.KEYPOINT_CONF_THRESHOLD,
                "is_live_vlm": vlm_analyzer.is_live_api(),
                "vlm": vlm_analyzer.provider_info(),
                "api_monitor": api_monitor.get_status(),
            }

    @staticmethod
    def _lane_payload(active_zone) -> dict:
        """Garis koridor & zona berdiri untuk overlay video."""
        return {
            "corridor": {
                "enabled": cfg.ENABLE_CORRIDOR_FILTER,
                "left_ratio": cfg.CORRIDOR_LEFT_RATIO,
                "right_ratio": cfg.CORRIDOR_RIGHT_RATIO
            },
            "zone": {"enabled": active_zone.enabled, "y_min": active_zone.y_min, "y_max": active_zone.y_max},
        }

    def _enrollment_payload(self, now: float) -> dict:
        active = self._enrolling(now)
        return {"active": active, "remaining_s": round(self.enrollment_until - now, 1) if active else None}

    @staticmethod
    def _detection_payload(d: DetectionResult, active_zone) -> dict:
        return {
            "track_id": d.track_id,
            "bbox": d.bbox,
            "is_full_body": d.is_full_body,
            "is_inside_corridor": getattr(d, 'is_inside_corridor', True),
            "reason": d.reason,
            "clip_type": getattr(d, 'clip_type', 'OPTIMAL'),
            "conf": round(d.conf, 2),
            "keypoints": d.keypoints,
            "foot_y": getattr(d, "zone_y", None),
            "in_zone": zones.in_zone(getattr(d, "zone_y", None), active_zone),
        }

    @staticmethod
    def _session_payload(s: Optional[GateSession]) -> Optional[dict]:
        if s is None:
            return None
        return {
            "track_id": s.track_id,
            "session_id": s.session_id,
            "state": s.state,
            "is_full_body": s.is_full_body_now,
            "reason": s.current_reason,
            "clip_type": s.clip_type,
            "stable_frames": s.stable_frames,
            "retry_in_s": max(0.0, round(s.retry_at - time.time(), 1))
            if s.state == TrackState.WAITING_SYSTEM else None,
            "vlm_result": s.vlm_result.model_dump() if s.vlm_result else None,
            "identity": s.identity.payload() if s.identity else None,
        }


state_mgr = StateManager()
