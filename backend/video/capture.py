"""Layanan kamera: membaca frame, menjalankan inferensi, dan menyiapkan JPEG untuk stream."""
import logging
import threading
import time
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from ..config import cfg
from .. import messages
from .. import camera_manager
from ..camera_health import FAULT_FROZEN, CameraHealth
from ..camera_manager import camera_mgr
from ..detector import detector
from ..state_manager import state_mgr
from . import hud

logger = logging.getLogger(__name__)


@dataclass
class _ReaderState:
    """Keadaan thread pembaca di antara putaran (hanya disentuh thread pembaca)."""
    # Mode yang berlaku saat kamera hilang, supaya penyambungan ulang memulihkan
    # mode hasil optimasi dan bukan jatuh ke permintaan bawaan.
    lost_mode: dict | None = None
    consecutive_failures: int = 0
    last_reconnect_attempt: float = 0.0
    # Pemantauan laju baca untuk mendeteksi kamera yang "hidup tapi ambruk"
    window_start: float = 0.0
    window_frames: int = 0
    baseline_fps: float = 0.0
    stall_since: float | None = None
    # Galat tak terduga beruntun (T77): menentukan jeda sebelum putaran berikutnya
    error_streak: int = 0

    def reset_rate(self, now: float):
        self.window_start, self.window_frames, self.baseline_fps, self.stall_since = now, 0, 0.0, None


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
        # Disetel thread pengawas ketika perangkat aktif hilang dari daftar OS,
        # atau oleh pemeriksa kesehatan gambar saat gambar membeku (T45)
        self._device_missing = False
        self._missing_reason = messages.CAMERA_UNPLUGGED
        # Gambar tertutup / membeku (T45); dibaca thread inferensi saja
        self._health = CameraHealth()
        # Gangguan yang dibawa melewati pembukaan ulang kamera (T45b)
        self._carry_fault = None
        # Menunggu kamera dicolok ulang (T45b): kapan mulai & kapan terakhir dicatat
        self._waiting_since = None
        self._waiting_logged_at = 0.0
        # Slot frame mentah terbaru: pembaca kamera dan inferensi dipisah agar
        # inferensi YOLO tidak memblokir pembacaan dan buffer kamera tidak menumpuk.
        self.raw_lock = threading.Lock()
        self.latest_raw = None
        self.raw_seq = 0
        # Dimensi frame yang benar-benar dikirim kamera (bisa berbeda dari yang diminta)
        self.frame_width = cfg.FRAME_WIDTH
        self.frame_height = cfg.FRAME_HEIGHT
        # Keadaan antar-putaran thread pembaca (diganti baru tiap _reader_loop mulai)
        self._reader = _ReaderState()

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
        if self.camera_index is None:
            # T67: belum ada kamera dipilih -> tidak ada yang dioptimasi (dulu: galat palsu index None)
            logger.info(messages.LOG_CAMERA_OPTIMIZE_NO_CAMERA)
            return
        self._pending_optimize = True
        logger.info(f"Permintaan optimasi kamera index {self.camera_index} diterima.")

    def request_idle(self):
        """Melepas kamera dan kembali menunggu operator memilih sumber."""
        self._pending_idle = True
        logger.info("Permintaan melepas kamera diterima.")

    def _camera_fault(self, frame, now: float):
        """Gangguan kamera untuk gerbang (T45): None | "lost" | "blocked" | "frozen".

        Saat kamera sedang dibuka/dipindai atau belum dipilih, gerbang memang tidak
        beroperasi atas perintah operator — itu bukan gangguan.
        """
        if self.camera_status == "LOST" or (self.camera_status == "SYNTHETIC" and self.camera_index is not None):
            self._health.reset(self._carry_fault)
            return FAULT_FROZEN if self.camera_error == messages.CAMERA_FROZEN else "lost"
        if self.camera_status != "OK":
            # Sedang dibuka ulang setelah membeku: gangguan belum selesai
            self._health.reset(self._carry_fault)
            return self._carry_fault
        fault = self._health.update(frame, now)
        if fault is None:
            self._carry_fault = None
        elif fault == FAULT_FROZEN and not self._device_missing:
            # Driver mengirim frame identik: buka ulang lewat jalur "perangkat hilang"
            logger.warning(messages.CAMERA_FROZEN)
            self._missing_reason = messages.CAMERA_FROZEN
            self._carry_fault = FAULT_FROZEN
            self._device_missing = True
        return fault

    def camera_frame(self) -> np.ndarray | None:
        """Salinan frame kamera asli terbaru untuk foto pendaftaran wajah (T34b2); None bila kamera
        belum aktif atau yang tampil frame pesan/sintetis (wajah di frame itu bukan orang nyata)."""
        with self.raw_lock:
            if self.use_synthetic or self.camera_status != "OK" or self.latest_raw is None:
                return None
            return self.latest_raw.copy()

    def get_camera_status(self) -> dict:
        blocked = self.camera_status == "OK" and self._health.fault == "blocked"
        return {
            "index": self.camera_index,
            "name": self.camera_name,
            "selected": self.camera_index is not None,
            "status": "BLOCKED" if blocked else self.camera_status,
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

    def _autostart_camera(self):
        """Membuka kamera otomatis LEWAT NAMA (T29); mengembalikan mode untuk penyambungan ulang.

        Kamera yang belum terlihat sistem tidak diganti kamera lain (dulu: jatuh ke
        indeks 0 = kamera bawaan laptop, diam-diam). Gerbang masuk keadaan "terputus"
        sehingga lampu kuning menyala dan jalur sambung ulang berbasis nama menunggunya.
        """
        name, mode, index_hint = camera_manager.autostart_target()
        if not name:
            self.camera_status = "IDLE"
            logger.warning(messages.CAMERA_AUTOSTART_NO_NAME)
            return None
        index = self._find_index_by_name(name)
        if index is not None and self._init_camera(index, mode):
            logger.info(messages.CAMERA_AUTOSTART_OPENED.format(name=name))
            return None
        logger.warning(messages.CAMERA_AUTOSTART_WAITING.format(name=name))
        self.camera_index = index_hint if index_hint is not None else index or 0
        self.camera_name, self.camera_name_verified = name, True
        self.camera_status = "LOST"
        self.camera_error = messages.CAMERA_AUTOSTART_WAITING.format(name=name)
        return mode

    def _log_waiting(self, now: float):
        """Uji fisik 06-10: kamera yang dicolok ulang tidak muncul ±1 menit dan log diam
        sama sekali. Kini tiap CAMERA_WAITING_LOG_SECONDS dicatat apa yang terlihat sistem."""
        self._waiting_since = self._waiting_since or now
        if now - self._waiting_logged_at < cfg.CAMERA_WAITING_LOG_SECONDS:
            return
        self._waiting_logged_at = now
        try:
            seen = ", ".join(camera_manager.list_device_names()) or "-"
        except Exception as e:
            seen = str(e)[:cfg.ERROR_MESSAGE_MAX_CHARS]
        logger.warning(messages.LOG_CAMERA_WAITING.format(
            name=self.camera_name, seconds=now - self._waiting_since, seen=seen))

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

    def _init_camera(self, index: int, mode: dict | None = None) -> bool:
        """Membuka kamera pada indeks tertentu dengan mode yang diminta.

        `mode` None berarti mode dipilih otomatis lewat pengukuran laju frame,
        karena setiap perangkat punya titik optimal yang berbeda — memaksa satu
        resolusi untuk semua kamera menghasilkan video tersendat di sebagian
        perangkat. Mengembalikan True jika kamera fisik berhasil dipakai.
        """
        self._begin_opening(index)
        if mode is None:
            mode = self._scanned_mode(index)

        target_w, target_h = self._requested_size(mode)
        mjpg = bool(mode) and mode.get("fourcc") == camera_manager.MJPG_TEXT  # pyright: ignore[reportOptionalMemberAccess]
        # MJPG (T34c2): ukuran & format diberikan saat membuka; set() sesudahnya kembali ke YUY2
        self.cap = (camera_manager.open_capture(index, (target_w, target_h)) if mjpg
                    else camera_manager.open_capture(index))
        if not self.cap.isOpened():
            return self._fall_back_to_synthetic(messages.CAMERA_OPEN_FAILED.format(index=index),
                                                f"Kamera {index} tidak tersedia. Memakai generator sintetis.")
        self._limit_driver_buffer()
        if not mjpg:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, target_w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target_h)
            self.cap.set(cv2.CAP_PROP_FPS, cfg.FPS)

        probe = self._probe_frame()
        if probe is None:
            return self._fall_back_to_synthetic(messages.CAMERA_NO_FRAMES.format(index=index),
                                                f"Kamera {index} tidak mengirim frame. Memakai generator sintetis.")
        self._activate(index, probe, mode, target_w, target_h)
        return True

    def _begin_opening(self, index: int):
        self._release_camera()
        self.camera_index = index
        self.camera_name = self._resolve_device_name(index)
        self.camera_status = "OPENING"
        self.camera_error = ""
        logger.info(f"Membuka kamera index {index} ({self.camera_name})...")

    def _scanned_mode(self, index: int) -> dict | None:
        """Mode hasil pemindaian kamera ini, bila ada.

        Mode ditentukan sebelum kamera dibuka: pengukuran membuka dan menutup
        perangkat sendiri, jadi tidak boleh ada handle lain yang menahannya.
        Kamera dibuka seketika. Pengukuran yang akurat butuh belasan detik
        (beberapa kamera USB baru stabil ~3,5 detik setelah dibuka), jadi itu
        dikerjakan oleh "Pindai kamera"/optimasi, bukan di jalur pembukaan.
        """
        known = camera_mgr.get_device(index)
        if known and known.get("selected_mode"):
            logger.info(f"Memakai mode hasil pemindaian untuk index {index}.")
            return known["selected_mode"]
        return None

    def _limit_driver_buffer(self):
        """Minta driver menyimpan 1 frame saja; tidak semua backend menghormatinya,
        karena itu thread pembaca tetap membuang frame lama secara aktif."""
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # pyright: ignore[reportOptionalMemberAccess] (None ikut ditangkap)
        except Exception:
            pass

    @staticmethod
    def _requested_size(mode: dict | None) -> tuple[int, int]:
        """Ukuran yang DIMINTA ke driver.

        Yang diterapkan adalah permintaan yang menghasilkan pengukuran terbaik,
        bukan resolusi hasilnya: driver memilih media type berdasarkan angka yang
        diminta, sehingga meminta hasil akhirnya bisa mendapat laju frame lebih
        rendah untuk resolusi yang persis sama. `req_*` kosong berarti berkas
        state lama, jadi hasil aktual dipakai sebagai cadangan.
        """
        if mode:
            return mode.get("req_width") or mode["width"], mode.get("req_height") or mode["height"]
        if cfg.CAMERA_AUTO_MODE:
            return cfg.CAMERA_DEFAULT_REQ_WIDTH, cfg.CAMERA_DEFAULT_REQ_HEIGHT
        return cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT

    def _probe_frame(self) -> np.ndarray | None:
        """Frame nyata setelah beberapa pembacaan pemanasan; None bila kamera tidak mengirim frame."""
        cap = self.cap
        assert cap is not None, "dipanggil setelah kamera terbuka"
        ok, probe = False, None
        for _ in range(cfg.CAMERA_PROBE_READS):
            ok, probe = cap.read()
        return probe if ok and probe is not None else None

    def _fall_back_to_synthetic(self, error: str, log_message: str) -> bool:
        self._release_camera()
        self.use_synthetic = True
        self.camera_status = "SYNTHETIC"
        self.camera_error = error
        self.active_mode = None
        logger.warning(log_message)
        return False

    def _activate(self, index: int, probe: np.ndarray, mode: dict | None, target_w: int, target_h: int):
        """Kamera siap dipakai; pilihan disimpan untuk penyalaan berikutnya.

        Dimensi dibaca dari frame nyata, bukan dari yang diminta: driver sering
        memberi resolusi terdekat yang didukung, dan overlay canvas di dashboard
        bergantung pada angka yang benar agar tetap sejajar.
        """
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
        logger.info(f"Kamera terbuka: {self.camera_name} {self.frame_width}x{self.frame_height}")
        camera_manager.save_selection(index, self.active_mode, self.camera_name)


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
        self._reader = _ReaderState(lost_mode=self._start_reader(), window_start=time.time())
        try:
            while self.is_running:
                try:
                    self._reader_step()
                    self._reader.error_streak = 0
                except Exception as e:
                    self._recover_reader(e)
        finally:
            self._release_camera()

    def _reader_step(self):
        """Satu putaran: permintaan operator / vonis lepas, atau satu frame."""
        if self._handle_requests():
            return
        raw = self._next_raw_frame()
        if raw is not None:
            self._publish_raw(raw)

    def _recover_reader(self, error: Exception):
        """Galat tak terduga (T77, mis. RAM habis saat `cap.read()`): thread pembaca tidak boleh mati.

        Dulu galat apa pun mengakhiri thread ini selamanya: gerbang buta (kuning) sampai operator
        memilih ulang kamera, dan proses tetap hidup sehingga supervisor tidak me-restart. Kini kamera
        divonis lepas dan disambung ulang lewat jalur LOST biasa, setelah jeda yang berlipat.
        """
        r = self._reader
        r.error_streak += 1
        delay = min(cfg.CAMERA_ERROR_BACKOFF_SECONDS * 2 ** (r.error_streak - 1), cfg.CAMERA_ERROR_BACKOFF_MAX_SECONDS)
        text = str(error)[:cfg.ERROR_MESSAGE_MAX_CHARS]
        logger.exception(messages.LOG_CAMERA_READER_ERROR.format(count=r.error_streak, error=text, delay=delay))
        if self.camera_index is not None:
            try:
                self._mark_lost(messages.CAMERA_READER_ERROR.format(error=text))
            except Exception:
                # Melepas kamera pun bisa gagal saat RAM habis; status tetap LOST agar disambung ulang
                self.cap, self.camera_status = None, "LOST"
        time.sleep(delay)

    def _start_reader(self) -> dict | None:
        """Kamera awal; mengembalikan mode untuk sambung ulang bila kamera autostart belum terlihat.

        Secara bawaan tidak ada kamera yang dibuka: operator memilih sumbernya dari
        dashboard lebih dulu, sehingga tidak ada perangkat yang terlanjur dipakai lalu diganti.
        """
        if cfg.CAMERA_AUTOSTART:
            return self._autostart_camera()
        self.camera_status = "IDLE"
        logger.info("Menunggu operator memilih sumber kamera di dashboard.")
        return None

    # --- Permintaan & vonis lepas (satu putaran = satu tindakan) ------------------------

    def _handle_requests(self) -> bool:
        """Menjalankan permintaan operator / vonis lepas; True bila putaran ini terpakai."""
        if self._pending_index is not None:
            target, target_mode = self._pending_index, self._pending_mode
            self._pending_index, self._pending_mode = None, None
            self._init_camera(target, target_mode)
            self._restart_reading()
        elif self._pending_optimize:
            self._optimize_camera()
        elif self._device_missing and self.camera_status == "OK":
            # Perangkat hilang dari daftar OS (atau gambar membeku) -> vonis lepas
            logger.warning(messages.LOG_CAMERA_RECONNECT.format(reason=self._missing_reason))
            reason, self._missing_reason = self._missing_reason, messages.CAMERA_UNPLUGGED
            self._mark_lost(reason)
            self._device_missing = False
        elif self._pending_idle:
            self._go_idle()
        else:
            return False
        return True

    def _optimize_camera(self):
        """Lepas kamera, ukur seluruh mode, buka lagi yang terbaik."""
        self._pending_optimize = False
        index = self.camera_index
        if index is None:
            # Kamera dilepas di antara permintaan & pemrosesan: tidak ada yang dioptimasi (T67)
            logger.info(messages.LOG_CAMERA_OPTIMIZE_NO_CAMERA)
            return
        self.camera_status = "OPTIMIZING"
        self._release_camera()
        self._set_status_frame(messages.FRAME_OPTIMIZING)
        logger.info(f"Mengukur mode kamera index {index}...")
        modes = camera_manager.probe_modes(index)
        best = camera_manager.pick_best_mode(modes)
        camera_mgr.record_device_modes(index, self._resolve_device_name(index), modes, best)
        self._init_camera(index, asdict(best) if best else None)
        self._restart_reading()

    def _go_idle(self):
        """Melepas kamera dan kembali ke layar pemilihan sumber."""
        self._pending_idle = False
        self._release_camera()
        self.camera_index = None
        self.camera_name = ""
        self.active_mode = None
        self.use_synthetic = False
        self.camera_status = "IDLE"
        self.fps = 0.0
        state_mgr.reset_all()

    def _restart_reading(self):
        """Kamera (baru) dibuka: hitungan gagal & laju baca dari nol, pelacakan bersih.

        ID ByteTrack dari kamera lama / dari sebelum kamera lepas tidak boleh
        bersambung ke subjek baru.
        """
        self._reader.consecutive_failures = 0
        self._device_missing = False
        self._reader.reset_rate(time.time())
        state_mgr.reset_all()

    def _mark_lost(self, error: str):
        """Vonis kamera lepas; mode saat itu disimpan supaya sambung ulang memulihkannya."""
        self._reader.lost_mode = self.active_mode
        self._release_camera()
        self.camera_status = "LOST"
        self.camera_error = error
        self._reader.last_reconnect_attempt = time.time()

    # --- Sumber frame --------------------------------------------------------------------

    def _next_raw_frame(self) -> np.ndarray | None:
        """Frame berikutnya untuk inferensi; None bila putaran ini tidak menghasilkannya."""
        if self.camera_status == "IDLE":
            raw = self._generate_synthetic_frame(messages.FRAME_SELECT_SOURCE)
            time.sleep(cfg.STATUS_FRAME_INTERVAL_SECONDS)
            return raw
        if self.camera_status == "LOST":
            return self._reconnect_step()
        if self.use_synthetic or self.cap is None or not self.cap.isOpened():
            # Tidak ada kamera fisik sama sekali
            raw = self._generate_synthetic_frame()
            time.sleep(cfg.SYNTHETIC_FRAME_INTERVAL_SECONDS)
            return raw
        return self._read_camera_frame()

    def _reconnect_step(self) -> np.ndarray | None:
        """Kamera lepas -> coba sambung ulang secara berkala."""
        r, now = self._reader, time.time()
        if now - r.last_reconnect_attempt >= cfg.CAMERA_RECONNECT_INTERVAL_SECONDS:
            r.last_reconnect_attempt = now
            # Kamera yang dicolok kembali bisa mendapat indeks berbeda,
            # jadi dicari ulang lewat namanya sebelum dibuka.
            target_index = self._find_index_by_name(self.camera_name)
            if target_index is None:
                self._log_waiting(now)
                time.sleep(cfg.STATUS_FRAME_INTERVAL_SECONDS)
                self._set_status_frame(messages.FRAME_WAITING_DEVICE)
                return None
            if self._init_camera(target_index, r.lost_mode):
                logger.info("Kamera tersambung kembali.")
                self._waiting_since = None
                r.lost_mode = None
                self._restart_reading()
                return None
            # _init_camera menandai SYNTHETIC saat gagal; kembalikan ke
            # LOST agar percobaan menyambung ulang terus berjalan.
            self.camera_status = "LOST"
        raw = self._generate_synthetic_frame(messages.FRAME_RECONNECTING)
        time.sleep(cfg.STATUS_FRAME_INTERVAL_SECONDS)
        return raw

    def _read_camera_frame(self) -> np.ndarray | None:
        """Operasi normal: satu frame kamera; None bila gagal dibaca atau kamera divonis lepas."""
        cap = self.cap
        assert cap is not None, "hanya dibaca saat kamera fisik terbuka"
        ret, raw = cap.read()
        if not ret or raw is None:
            self._reader.consecutive_failures += 1
            if self._reader.consecutive_failures >= cfg.CAMERA_LOST_THRESHOLD:
                logger.warning("Kamera berhenti mengirim frame. "
                               "Ditandai terputus, akan dicoba sambung ulang.")
                self._mark_lost(messages.CAMERA_DISCONNECTED)
            time.sleep(cfg.CAMERA_READ_RETRY_SECONDS)
            return None
        self._reader.consecutive_failures = 0
        return None if self._camera_stalled() else raw

    def _camera_stalled(self) -> bool:
        """Laju baca dipantau per jendela; True bila kamera divonis lepas karena lajunya ambruk.

        Kamera yang dicabut bisa tetap "berhasil" dibaca tetapi lajunya ambruk drastis
        (kamera USB penguji: 25 -> 1,1 FPS) sambil mengembalikan frame berisi sampah
        scanline, sehingga hitungan kegagalan baca saja tidak pernah terpicu.
        """
        r = self._reader
        r.window_frames += 1
        elapsed = time.time() - r.window_start
        if elapsed < cfg.CAMERA_RATE_WINDOW_SECONDS:
            return False
        read_fps = r.window_frames / elapsed
        r.window_start, r.window_frames = time.time(), 0
        r.baseline_fps = max(r.baseline_fps, read_fps)
        if r.baseline_fps < cfg.CAMERA_STALL_MIN_BASELINE:
            return False
        if read_fps >= r.baseline_fps * cfg.CAMERA_STALL_FPS_RATIO:
            r.stall_since = None
            return False
        r.stall_since = r.stall_since or time.time()
        if time.time() - r.stall_since < cfg.CAMERA_STALL_SECONDS:
            return False
        logger.warning(f"Laju kamera ambruk ({read_fps:.1f} dari {r.baseline_fps:.1f} FPS). Dianggap terputus.")
        self._mark_lost(messages.CAMERA_STALLED)
        return True

    # --- Slot frame mentah ---------------------------------------------------------------

    def _publish_raw(self, raw: np.ndarray):
        self.frame_height, self.frame_width = raw.shape[:2]
        with self.raw_lock:
            self.latest_raw = raw
            self.raw_seq += 1

    def _set_status_frame(self, message: str):
        """Frame pesan (sedang mengukur / menunggu perangkat), tanpa mengubah dimensi kamera."""
        with self.raw_lock:
            self.latest_raw = self._generate_synthetic_frame(message)
            self.raw_seq += 1

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

                # Kamera terputus/tertutup/membeku: gerbang berhenti memeriksa (T45)
                state_mgr.set_camera_fault(self._camera_fault(frame, now))

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
