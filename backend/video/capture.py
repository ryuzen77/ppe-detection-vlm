"""Layanan kamera: membaca frame, menjalankan inferensi, dan menyiapkan JPEG untuk stream."""
import logging
import threading
import time
from dataclasses import asdict

import cv2
import numpy as np

from ..config import cfg
from .. import messages
from .. import camera_manager
from ..camera_manager import camera_mgr
from ..detector import detector
from ..state_manager import state_mgr
from . import hud

logger = logging.getLogger(__name__)

class VideoCaptureService:
    """Manages camera video capture, inference, and MJPEG encoding."""
    def __init__(self):
        self.cap = None
        self.is_running = False
        self.current_frame_bytes = None
        self.lock = threading.Lock()
        self.fps = 0.0
        self.camera_index = None
        self.use_synthetic = False

        # Status kamera untuk ribbon dashboard:
        # IDLE (belum dipilih) / OPENING / OK / LOST (terputus, dicoba ulang) / SYNTHETIC
        self.camera_status = "IDLE"
        self.camera_name = ""
        # True bila camera_name adalah nama asli dari OS, bukan label generik
        # "Kamera N" karena daftar nama sesaat tidak terbaca
        self.camera_name_verified = False
        self.camera_error = ""
        self.active_mode = None
        # Permintaan pindah kamera; hanya diset dari luar, dieksekusi thread pembaca
        # supaya tidak ada dua thread yang menyentuh perangkat yang sama.
        self._pending_index = None
        self._pending_mode = None
        self._pending_optimize = False
        self._pending_idle = False
        # Disetel thread pengawas ketika perangkat aktif hilang dari daftar OS
        self._device_missing = False
        # Slot frame mentah terbaru: pembaca kamera dan inferensi dipisah agar
        # inferensi YOLO tidak memblokir pembacaan dan buffer kamera tidak menumpuk.
        self.raw_lock = threading.Lock()
        self.latest_raw = None
        self.raw_seq = 0
        # Dimensi frame yang benar-benar dikirim kamera (bisa berbeda dari yang diminta)
        self.frame_width = cfg.FRAME_WIDTH
        self.frame_height = cfg.FRAME_HEIGHT

    def start(self):
        self.is_running = True
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self.watchdog_thread = threading.Thread(target=self._presence_watchdog, daemon=True)
        self.watchdog_thread.start()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def request_camera(self, index: int, mode: dict | None = None):
        """Menjadwalkan pergantian kamera; dieksekusi oleh thread pembaca.

        Tidak ada thread yang dimatikan atau dibuat ulang — `_reader_loop` adalah
        satu-satunya pemilik `self.cap`, jadi ia yang melepas dan membuka ulang.
        """
        self._pending_index = int(index)
        self._pending_mode = mode
        self.camera_status = "OPENING"
        logger.info(f"Permintaan pindah ke kamera index {index} diterima.")

    def request_optimize(self):
        """Menjadwalkan pengukuran ulang mode untuk kamera yang sedang aktif.

        Perangkatnya terkunci oleh aliran video, jadi thread pembaca harus
        melepasnya dulu, mengukur, lalu membukanya kembali pada mode terbaik.
        """
        self._pending_optimize = True
        logger.info(f"Permintaan optimasi kamera index {self.camera_index} diterima.")

    def request_idle(self):
        """Melepas kamera dan kembali menunggu operator memilih sumber."""
        self._pending_idle = True
        logger.info("Permintaan melepas kamera diterima.")

    def get_camera_status(self) -> dict:
        return {
            "index": self.camera_index,
            "name": self.camera_name,
            "selected": self.camera_index is not None,
            "status": self.camera_status,
            "error": self.camera_error,
            "mode": self.active_mode,
            "optimizing": self.camera_status == "OPTIMIZING",
            "width": self.frame_width,
            "height": self.frame_height,
            "fps": round(self.fps, 1),
            "is_synthetic": self.use_synthetic,
        }

    def stop(self):
        self.is_running = False
        # Thread harus benar-benar selesai sebelum interpreter menutup. Thread
        # inferensi menjalankan YOLO terus-menerus (juga atas frame "menunggu
        # kamera"); bila Python mulai finalisasi saat thread daemon itu masih di
        # dalam torch, proses sesekali mati dengan "pybind11::handle::dec_ref()
        # PyGILState_Check() failure" (kode keluar 134) — terukur 1 dari 20
        # kali di Linux. Pembaca ditunggu sebelum kamera dilepas karena ia
        # satu-satunya pemilik `self.cap`. Batas waktu mencegah shutdown
        # menggantung bila pembaca sedang membuka/mengukur kamera.
        for name, attr in (("inferensi", "thread"), ("pembaca kamera", "reader_thread")):
            t = getattr(self, attr, None)  # belum ada bila start() tak pernah dipanggil
            if t is not None and t.is_alive():
                t.join(timeout=cfg.THREAD_STOP_TIMEOUT_SECONDS)
                if t.is_alive():
                    logger.warning(f"Thread {name} belum berhenti setelah "
                                   f"{cfg.THREAD_STOP_TIMEOUT_SECONDS:.0f} dtk; shutdown dilanjutkan.")
        with self.lock:
            if self.cap and self.cap.isOpened():
                try:
                    self.cap.release()
                except Exception:
                    pass
        logger.info("Camera released cleanly.")

    def _presence_watchdog(self):
        """Memeriksa berkala apakah kamera aktif masih terdaftar di sistem operasi.

        Penanda paling tegas bahwa kamera dicabut: driver bisa saja terus
        mengembalikan frame sampah yang dianggap "berhasil" oleh OpenCV, tetapi
        perangkatnya hilang dari enumerasi DirectShow seketika. Dijalankan di
        thread terpisah karena enumerasi cukup mahal untuk dipanggil dari loop
        pembacaan frame.
        """
        while self.is_running:
            time.sleep(cfg.CAMERA_PRESENCE_CHECK_SECONDS)
            self._check_presence()

    def _check_presence(self):
        """Satu putaran pemeriksaan keberadaan kamera aktif (lihat _presence_watchdog)."""
        if self.camera_status != "OK" or self.use_synthetic or not self.camera_name:
            return
        try:
            names = camera_manager.list_device_names()
        except Exception:
            return
        if not names:
            return
        if not self.camera_name_verified:
            # Nama generik "Kamera N" tidak pernah cocok dengan daftar asli; dulu
            # hal ini membuat kamera yang sehat dianggap dicabut (24-09).
            # Pulihkan nama aslinya alih-alih memutus kamera.
            idx = self.camera_index
            if idx is not None and 0 <= idx < len(names):
                logger.info(f"Nama kamera index {idx} dipulihkan: '{names[idx]}'.")
                self.camera_name = names[idx]
                self.camera_name_verified = True
            return
        if self.camera_name not in names:
            logger.warning(f"'{self.camera_name}' hilang dari daftar perangkat sistem.")
            self._device_missing = True

    def _find_index_by_name(self, name: str) -> int | None:
        """Mencari indeks terkini sebuah kamera berdasarkan namanya."""
        try:
            names = camera_manager.list_device_names()
        except Exception:
            return None
        return names.index(name) if name in names else None

    def _release_camera(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def _resolve_device_name(self, index: int) -> str:
        try:
            names = camera_manager.list_device_names()
            if 0 <= index < len(names):
                self.camera_name_verified = True
                return names[index]
        except Exception:
            pass
        self.camera_name_verified = False
        return messages.CAMERA_FALLBACK_NAME.format(index=index)

    def _init_camera(self, index: int | None = None, mode: dict | None = None) -> bool:
        """Membuka kamera pada indeks tertentu dengan mode yang diminta.

        `mode` None berarti mode dipilih otomatis lewat pengukuran laju frame,
        karena setiap perangkat punya titik optimal yang berbeda — memaksa satu
        resolusi untuk semua kamera menghasilkan video tersendat di sebagian
        perangkat. Mengembalikan True jika kamera fisik berhasil dipakai.
        """
        if index is None:
            index = self.camera_index

        self._release_camera()
        self.camera_index = index
        self.camera_name = self._resolve_device_name(index)
        self.camera_status = "OPENING"
        self.camera_error = ""
        logger.info(f"Membuka kamera index {index} ({self.camera_name})...")

        # Mode ditentukan sebelum kamera dibuka: pengukuran membuka dan menutup
        # perangkat sendiri, jadi tidak boleh ada handle lain yang menahannya.
        # Kamera dibuka seketika. Pengukuran yang akurat butuh belasan detik
        # (beberapa kamera USB baru stabil ~3,5 detik setelah dibuka), jadi itu
        # dikerjakan oleh "Pindai kamera"/optimasi, bukan di jalur pembukaan.
        if mode is None:
            known = camera_mgr.get_device(index)
            if known and known.get("selected_mode"):
                mode = known["selected_mode"]
                logger.info(f"Memakai mode hasil pemindaian untuk index {index}.")

        self.cap = camera_manager.open_capture(index)

        if not self.cap.isOpened():
            self._release_camera()
            self.use_synthetic = True
            self.camera_status = "SYNTHETIC"
            self.camera_error = messages.CAMERA_OPEN_FAILED.format(index=index)
            self.active_mode = None
            logger.warning(f"Kamera {index} tidak tersedia. Memakai generator sintetis.")
            return False

        # Minta driver menyimpan 1 frame saja; tidak semua backend menghormatinya,
        # karena itu thread pembaca tetap membuang frame lama secara aktif.
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        # Yang diterapkan adalah PERMINTAAN yang menghasilkan pengukuran terbaik,
        # bukan resolusi hasilnya: driver memilih media type berdasarkan angka yang
        # diminta, sehingga meminta hasil akhirnya bisa mendapat laju frame lebih
        # rendah untuk resolusi yang persis sama. `req_*` kosong berarti berkas
        # state lama, jadi hasil aktual dipakai sebagai cadangan.
        if mode:
            target_w = mode.get("req_width") or mode["width"]
            target_h = mode.get("req_height") or mode["height"]
        elif cfg.CAMERA_AUTO_MODE:
            target_w = cfg.CAMERA_DEFAULT_REQ_WIDTH
            target_h = cfg.CAMERA_DEFAULT_REQ_HEIGHT
        else:
            target_w, target_h = cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
        self.cap.set(cv2.CAP_PROP_FPS, cfg.FPS)

        # Dimensi dibaca dari frame nyata, bukan dari yang diminta: driver sering
        # memberi resolusi terdekat yang didukung, dan overlay canvas di dashboard
        # bergantung pada angka yang benar agar tetap sejajar.
        ok, probe = False, None
        for _ in range(5):
            ok, probe = self.cap.read()
        if not ok or probe is None:
            self._release_camera()
            self.use_synthetic = True
            self.camera_status = "SYNTHETIC"
            self.camera_error = messages.CAMERA_NO_FRAMES.format(index=index)
            self.active_mode = None
            logger.warning(f"Kamera {index} tidak mengirim frame. Memakai generator sintetis.")
            return False

        self.frame_height, self.frame_width = probe.shape[:2]
        self.active_mode = {
            "width": self.frame_width,
            "height": self.frame_height,
            "fps": mode.get("fps", 0.0) if mode else 0.0,
            "fourcc": mode.get("fourcc", "") if mode else "",
            "req_width": target_w,
            "req_height": target_h,
        }
        self.use_synthetic = False
        self.camera_status = "OK"
        self.fps = 0.0
        logger.info(f"Kamera terbuka: {self.camera_name} "
                    f"{self.frame_width}x{self.frame_height}")

        camera_manager.save_selection(index, self.active_mode, self.camera_name)
        return True


    def _generate_synthetic_frame(self, message: str = messages.FRAME_NO_CAMERA) -> np.ndarray:
        """Pola uji saat tidak ada kamera, supaya aliran video tidak membeku."""
        return hud.draw_synthetic_frame(self.frame_width or cfg.FRAME_WIDTH,
                                        self.frame_height or cfg.FRAME_HEIGHT, message)

    def _reader_loop(self):
        """Membaca kamera terus-menerus dan hanya menyimpan frame terbaru.

        Dipisahkan dari inferensi supaya frame yang tertahan di buffer driver
        selama YOLO bekerja langsung dibuang, bukan ditumpuk jadi latensi.
        Thread ini adalah satu-satunya pemilik `self.cap`, jadi pergantian kamera
        dan penyambungan ulang juga dikerjakan di sini.
        """
        # Secara bawaan tidak ada kamera yang dibuka: operator memilih sumbernya
        # dari dashboard lebih dulu, sehingga tidak ada perangkat yang terlanjur
        # dipakai lalu diganti.
        if cfg.CAMERA_AUTOSTART:
            saved = camera_manager.load_saved_selection()
            resolved = camera_manager.resolve_saved_index(saved) if saved else None
            if resolved is not None:
                logger.info(f"Autostart: memakai {saved.get('name') or resolved}")
                self._init_camera(resolved, saved.get("mode"))
            else:
                self._init_camera(cfg.CAMERA_INDEX)
        else:
            self.camera_status = "IDLE"
            logger.info("Menunggu operator memilih sumber kamera di dashboard.")

        consecutive_failures = 0
        last_reconnect_attempt = 0.0
        # Mode yang berlaku saat kamera hilang, supaya penyambungan ulang memulihkan
        # mode hasil optimasi dan bukan jatuh ke permintaan bawaan.
        lost_mode = None

        # Pemantauan laju baca untuk mendeteksi kamera yang "hidup tapi ambruk"
        window_start = time.time()
        window_frames = 0
        baseline_fps = 0.0
        stall_since = None

        def reset_rate_tracking():
            nonlocal window_start, window_frames, baseline_fps, stall_since
            window_start = time.time()
            window_frames = 0
            baseline_fps = 0.0
            stall_since = None

        try:
            while self.is_running:
                # 1. Permintaan pindah kamera dari operator
                if self._pending_index is not None:
                    target, target_mode = self._pending_index, self._pending_mode
                    self._pending_index, self._pending_mode = None, None
                    self._init_camera(target, target_mode)
                    consecutive_failures = 0
                    self._device_missing = False
                    reset_rate_tracking()
                    # ID ByteTrack dari kamera lama tidak boleh bocor ke kamera baru
                    state_mgr.reset_all()
                    continue

                # 2. Optimasi: lepas kamera, ukur seluruh mode, buka lagi yang terbaik
                if self._pending_optimize:
                    self._pending_optimize = False
                    index = self.camera_index
                    self.camera_status = "OPTIMIZING"
                    self._release_camera()
                    with self.raw_lock:
                        self.latest_raw = self._generate_synthetic_frame(
                            messages.FRAME_OPTIMIZING
                        )
                        self.raw_seq += 1

                    logger.info(f"Mengukur mode kamera index {index}...")
                    modes = camera_manager.probe_modes(index)
                    best = camera_manager.pick_best_mode(modes)
                    camera_mgr.record_device_modes(index, self._resolve_device_name(index), modes, best)

                    self._init_camera(index, asdict(best) if best else None)
                    state_mgr.reset_all()
                    consecutive_failures = 0
                    self._device_missing = False
                    reset_rate_tracking()
                    continue

                # 3. Perangkat hilang dari daftar OS -> vonis lepas
                if self._device_missing and self.camera_status == "OK":
                    logger.warning("Kamera dicabut. Menunggu untuk disambung ulang.")
                    lost_mode = self.active_mode
                    self._release_camera()
                    self.camera_status = "LOST"
                    self.camera_error = messages.CAMERA_UNPLUGGED
                    self._device_missing = False
                    last_reconnect_attempt = time.time()
                    continue

                # 4. Permintaan melepas kamera (pilih ulang sumber)
                if self._pending_idle:
                    self._pending_idle = False
                    self._release_camera()
                    self.camera_index = None
                    self.camera_name = ""
                    self.active_mode = None
                    self.use_synthetic = False
                    self.camera_status = "IDLE"
                    self.fps = 0.0
                    state_mgr.reset_all()
                    continue

                # 5. Belum ada kamera dipilih
                if self.camera_status == "IDLE":
                    raw = self._generate_synthetic_frame(
                        messages.FRAME_SELECT_SOURCE
                    )
                    time.sleep(cfg.STATUS_FRAME_INTERVAL_SECONDS)

                # 6. Kamera lepas -> coba sambung ulang secara berkala
                elif self.camera_status == "LOST":
                    now = time.time()
                    if now - last_reconnect_attempt >= cfg.CAMERA_RECONNECT_INTERVAL_SECONDS:
                        last_reconnect_attempt = now
                        # Kamera yang dicolok kembali bisa mendapat indeks berbeda,
                        # jadi dicari ulang lewat namanya sebelum dibuka.
                        target_index = self._find_index_by_name(self.camera_name)
                        if target_index is None:
                            time.sleep(cfg.STATUS_FRAME_INTERVAL_SECONDS)
                            with self.raw_lock:
                                self.latest_raw = self._generate_synthetic_frame(
                                    messages.FRAME_WAITING_DEVICE
                                )
                                self.raw_seq += 1
                            continue
                        if self._init_camera(target_index, lost_mode):
                            logger.info("Kamera tersambung kembali.")
                            consecutive_failures = 0
                            lost_mode = None
                            self._device_missing = False
                            reset_rate_tracking()
                            # Pelacakan dimulai bersih: ID ByteTrack dari sebelum
                            # kamera lepas tidak boleh bersambung ke subjek baru.
                            state_mgr.reset_all()
                            continue
                        # _init_camera menandai SYNTHETIC saat gagal; kembalikan ke
                        # LOST agar percobaan menyambung ulang terus berjalan.
                        self.camera_status = "LOST"
                    raw = self._generate_synthetic_frame(
                        messages.FRAME_RECONNECTING
                    )
                    time.sleep(cfg.STATUS_FRAME_INTERVAL_SECONDS)

                # 7. Tidak ada kamera fisik sama sekali
                elif self.use_synthetic or self.cap is None or not self.cap.isOpened():
                    raw = self._generate_synthetic_frame()
                    time.sleep(cfg.SYNTHETIC_FRAME_INTERVAL_SECONDS)

                # 8. Operasi normal
                else:
                    ret, raw = self.cap.read()
                    if not ret or raw is None:
                        consecutive_failures += 1
                        if consecutive_failures >= cfg.CAMERA_LOST_THRESHOLD:
                            logger.warning("Kamera berhenti mengirim frame. "
                                           "Ditandai terputus, akan dicoba sambung ulang.")
                            lost_mode = self.active_mode
                            self._release_camera()
                            self.camera_status = "LOST"
                            self.camera_error = messages.CAMERA_DISCONNECTED
                            last_reconnect_attempt = time.time()
                        time.sleep(cfg.CAMERA_READ_RETRY_SECONDS)
                        continue
                    consecutive_failures = 0

                    # Laju baca dipantau per jendela 1 detik. Kamera yang dicabut
                    # bisa tetap "berhasil" dibaca tetapi laju-nya ambruk drastis
                    # (kamera USB penguji: 25 -> 1,1 FPS) sambil mengembalikan
                    # frame berisi sampah scanline, sehingga hitungan kegagalan
                    # baca saja tidak pernah terpicu.
                    window_frames += 1
                    elapsed = time.time() - window_start
                    if elapsed >= 1.0:
                        read_fps = window_frames / elapsed
                        window_start = time.time()
                        window_frames = 0

                        if read_fps > baseline_fps:
                            baseline_fps = read_fps

                        if baseline_fps >= cfg.CAMERA_STALL_MIN_BASELINE:
                            if read_fps < baseline_fps * cfg.CAMERA_STALL_FPS_RATIO:
                                stall_since = stall_since or time.time()
                                if time.time() - stall_since >= cfg.CAMERA_STALL_SECONDS:
                                    logger.warning(f"Laju kamera ambruk "
                                                   f"({read_fps:.1f} dari {baseline_fps:.1f} FPS). "
                                                   f"Dianggap terputus.")
                                    lost_mode = self.active_mode
                                    self._release_camera()
                                    self.camera_status = "LOST"
                                    self.camera_error = messages.CAMERA_STALLED
                                    last_reconnect_attempt = time.time()
                                    continue
                            else:
                                stall_since = None

                self.frame_height, self.frame_width = raw.shape[:2]
                with self.raw_lock:
                    self.latest_raw = raw
                    self.raw_seq += 1
        except Exception as e:
            # Tanpa penjaga ini, galat apa pun mematikan thread pembaca diam-diam
            # dan aliran video berhenti tanpa pesan sama sekali.
            logger.exception(f"Reader loop berhenti karena galat: {e}")
            self.camera_status = "LOST"
            self.camera_error = str(e)[:cfg.ERROR_MESSAGE_MAX_CHARS]
        finally:
            self._release_camera()

    def _capture_loop(self):
        prev_time = time.time()
        last_seq = -1
        seen_first_frame = False

        try:
            while self.is_running:
                with self.raw_lock:
                    if self.latest_raw is None or self.raw_seq == last_seq:
                        frame = None
                    else:
                        frame = self.latest_raw
                        last_seq = self.raw_seq

                if frame is None:
                    # Belum ada frame baru sejak inferensi terakhir
                    time.sleep(cfg.INFERENCE_POLL_SECONDS)
                    continue

                # Compute FPS antar frame yang benar-benar diproses.
                # Frame pertama dilewati karena jedanya termasuk waktu buka kamera.
                now = time.time()
                dt = now - prev_time
                prev_time = now
                if dt > 0 and seen_first_frame:
                    self.fps = (1 - cfg.FPS_SMOOTHING) * self.fps + cfg.FPS_SMOOTHING * (1.0 / dt)
                seen_first_frame = True

                # Run YOLO Person & Pose Detection
                detections = detector.detect_and_track(frame)

                # Update State Machine & Anti-spam logic
                state_mgr.update_frame_detections(detections)

                # Draw HUD on frame for low-latency visual stream
                annotated_frame = hud.draw_hud(frame, detections, self.fps)

                # Encode to JPEG
                _, buffer = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.STREAM_JPEG_QUALITY])
                with self.lock:
                    self.current_frame_bytes = buffer.tobytes()
        except Exception as e:
            logger.exception(f"Inference loop stopped: {e}")

    def get_latest_jpeg(self):
        with self.lock:
            return self.current_frame_bytes

video_service = VideoCaptureService()
