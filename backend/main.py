import sys

if not __package__:
    # Dijalankan sebagai `python backend/main.py`: impor relatif di bawah akan gagal
    sys.exit("Jalankan server dari akar repo dengan: python -m backend")

import asyncio
import time
import json
import threading
from pathlib import Path
from contextlib import asynccontextmanager
import cv2
import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dataclasses import asdict

from .config import cfg
from . import messages
from . import camera_manager
from .camera_manager import camera_mgr
from .detector import detector
from .state_manager import state_mgr, TrackState
from .vlm_analyzer import vlm_analyzer
from .notifier import notifier
from .audio_engine import audio_player
from .report_manager import report_mgr
from . import ppe_rules
from .api_monitor import api_monitor

# Disetel saat sinyal berhenti diterima. Endpoint streaming dan WebSocket
# memeriksanya supaya ikut berhenti; tanpa ini keduanya berputar selamanya dan
# uvicorn menggantung di "Waiting for connections to close" sampai dipaksa keluar.
SHUTTING_DOWN = threading.Event()


def _install_shutdown_hook():
    """Menyisipkan penanda berhenti ke penangan sinyal uvicorn.

    Ditempelkan pada kelas Server, bukan hanya subkelas di bawah, supaya tetap
    bekerja apa pun cara server dijalankan — `python main.py` maupun
    `uvicorn main:app`.
    """
    import uvicorn

    if getattr(uvicorn.Server, "_safeguard_hooked", False):
        return

    original = uvicorn.Server.handle_exit

    def handle_exit(self, sig, frame):
        SHUTTING_DOWN.set()
        original(self, sig, frame)

    uvicorn.Server.handle_exit = handle_exit
    uvicorn.Server._safeguard_hooked = True


_install_shutdown_hook()


class GracefulStreamingResponse(StreamingResponse):
    """StreamingResponse that catches asyncio.CancelledError on server shutdown (Ctrl+C)."""
    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass

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
        print(f"[VideoCapture] Permintaan pindah ke kamera index {index} diterima.")

    def request_optimize(self):
        """Menjadwalkan pengukuran ulang mode untuk kamera yang sedang aktif.

        Perangkatnya terkunci oleh aliran video, jadi thread pembaca harus
        melepasnya dulu, mengukur, lalu membukanya kembali pada mode terbaik.
        """
        self._pending_optimize = True
        print(f"[VideoCapture] Permintaan optimasi kamera index {self.camera_index} diterima.")

    def request_idle(self):
        """Melepas kamera dan kembali menunggu operator memilih sumber."""
        self._pending_idle = True
        print("[VideoCapture] Permintaan melepas kamera diterima.")

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
        with self.lock:
            if self.cap and self.cap.isOpened():
                try:
                    self.cap.release()
                except Exception:
                    pass
        print("[VideoCapture] Camera released cleanly.")

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
            if self.camera_status != "OK" or self.use_synthetic or not self.camera_name:
                continue
            try:
                names = camera_manager.list_device_names()
            except Exception:
                continue
            if names and self.camera_name not in names:
                print(f"[VideoCapture] '{self.camera_name}' hilang dari daftar perangkat sistem.")
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
                return names[index]
        except Exception:
            pass
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
        print(f"[VideoCapture] Membuka kamera index {index} ({self.camera_name})...")

        # Mode ditentukan sebelum kamera dibuka: pengukuran membuka dan menutup
        # perangkat sendiri, jadi tidak boleh ada handle lain yang menahannya.
        # Kamera dibuka seketika. Pengukuran yang akurat butuh belasan detik
        # (beberapa kamera USB baru stabil ~3,5 detik setelah dibuka), jadi itu
        # dikerjakan oleh "Pindai kamera"/optimasi, bukan di jalur pembukaan.
        if mode is None:
            known = camera_mgr.get_device(index)
            if known and known.get("selected_mode"):
                mode = known["selected_mode"]
                print(f"[VideoCapture] Memakai mode hasil pemindaian untuk index {index}.")

        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print(f"[VideoCapture] CAP_DSHOW gagal untuk index {index}, mencoba backend bawaan...")
            self._release_camera()
            self.cap = cv2.VideoCapture(index)

        if not self.cap.isOpened():
            self._release_camera()
            self.use_synthetic = True
            self.camera_status = "SYNTHETIC"
            self.camera_error = messages.CAMERA_OPEN_FAILED.format(index=index)
            self.active_mode = None
            print(f"[VideoCapture] Kamera {index} tidak tersedia. Memakai generator sintetis.")
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
            print(f"[VideoCapture] Kamera {index} tidak mengirim frame. Memakai generator sintetis.")
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
        print(f"[VideoCapture] Kamera terbuka: {self.camera_name} "
              f"{self.frame_width}x{self.frame_height}")

        camera_manager.save_selection(index, self.active_mode, self.camera_name)
        return True

    def _generate_synthetic_frame(self, message: str = messages.FRAME_NO_CAMERA) -> np.ndarray:
        """Pola uji saat tidak ada kamera, supaya aliran video tidak membeku."""
        w = self.frame_width or cfg.FRAME_WIDTH
        h = self.frame_height or cfg.FRAME_HEIGHT
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:, :] = (30, 30, 35)

        for y in range(0, h, 40):
            cv2.line(img, (0, y), (w, y), (40, 40, 45), 1)
        for x in range(0, w, 40):
            cv2.line(img, (x, 0), (x, h), (40, 40, 45), 1)

        # Teks ditengahkan dan diskalakan terhadap lebar frame agar terbaca wajar
        # pada rasio apa pun, termasuk kamera 4:3.
        scale_title = w / 1100.0
        scale_msg = w / 1500.0
        judul = messages.FRAME_TITLE
        (tw, th), _ = cv2.getTextSize(judul, cv2.FONT_HERSHEY_SIMPLEX, scale_title, 2)
        (mw, _), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, scale_msg, 1)

        pad_x, pad_y = int(w * 0.04), int(h * 0.06)
        box_w = max(tw, mw) + pad_x * 2
        box_x = (w - box_w) // 2
        box_y = h // 2 - pad_y - th
        cv2.rectangle(img, (box_x, box_y), (box_x + box_w, box_y + pad_y * 2 + th),
                      (0, 180, 255), 2)
        cv2.putText(img, judul, ((w - tw) // 2, box_y + pad_y + th // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, scale_title, (0, 180, 255), 2)
        cv2.putText(img, message, ((w - mw) // 2, box_y + pad_y * 2 + th + int(h * 0.06)),
                    cv2.FONT_HERSHEY_SIMPLEX, scale_msg, (150, 150, 150), 1)
        return img

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
                print(f"[VideoCapture] Autostart: memakai {saved.get('name') or resolved}")
                self._init_camera(resolved, saved.get("mode"))
            else:
                self._init_camera(cfg.CAMERA_INDEX)
        else:
            self.camera_status = "IDLE"
            print("[VideoCapture] Menunggu operator memilih sumber kamera di dashboard.")

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

                    print(f"[VideoCapture] Mengukur mode kamera index {index}...")
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
                    print("[VideoCapture] Kamera dicabut. Menunggu untuk disambung ulang.")
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
                            print("[VideoCapture] Kamera tersambung kembali.")
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
                            print("[VideoCapture] Kamera berhenti mengirim frame. "
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
                                    print(f"[VideoCapture] Laju kamera ambruk "
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
            import traceback
            print(f"[VideoCapture] Reader loop berhenti karena galat: {e}")
            traceback.print_exc()
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
                annotated_frame = self._draw_hud(frame, detections)

                # Encode to JPEG
                _, buffer = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.STREAM_JPEG_QUALITY])
                with self.lock:
                    self.current_frame_bytes = buffer.tobytes()
        except Exception as e:
            print(f"[VideoCapture] Inference loop stopped: {e}")

    def _draw_hud(self, frame: np.ndarray, detections) -> np.ndarray:
        # Koridor, bounding box, dan garis panduan sudah digambar oleh canvas
        # frontend (hud_overlay.js). Menggambarnya lagi di sini menghasilkan
        # overlay ganda dan membuat sakelar "Panduan Posisi" terasa rusak.
        if not cfg.ENABLE_SERVER_HUD:
            return frame

        out = frame.copy()
        h, w = out.shape[:2]

        # 1. Virtual Corridor Masking & Guides
        if cfg.ENABLE_CORRIDOR_FILTER:
            cx1 = int(w * cfg.CORRIDOR_LEFT_RATIO)
            cx2 = int(w * cfg.CORRIDOR_RIGHT_RATIO)

            # Darken side areas to focus subject in corridor
            overlay = out.copy()
            cv2.rectangle(overlay, (0, 0), (cx1, h), (10, 10, 15), -1)
            cv2.rectangle(overlay, (cx2, 0), (w, h), (10, 10, 15), -1)
            cv2.addWeighted(overlay, 0.45, out, 0.55, 0, out)

            # Draw vertical neon corridor boundaries
            cv2.line(out, (cx1, 0), (cx1, h), (255, 200, 0), 2)
            cv2.line(out, (cx2, 0), (cx2, h), (255, 200, 0), 2)

            # Corridor title banner
            banner_text = messages.HUD_CORRIDOR_BANNER
            t_size = cv2.getTextSize(banner_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
            banner_x = cx1 + (cx2 - cx1 - t_size[0]) // 2
            cv2.putText(out, banner_text, (banner_x, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2)

        # 2. Draw inspection horizontal boundary guidelines
        margin_top = max(int(h * cfg.BORDER_MARGIN_TOP_RATIO), 1)
        margin_bottom = max(int(h * cfg.BORDER_MARGIN_BOTTOM_RATIO), 1)
        cv2.line(out, (0, margin_top), (w, margin_top), (0, 140, 255), 1)
        cv2.line(out, (0, h - margin_bottom), (w, h - margin_bottom), (0, 140, 255), 1)

        # 3. Draw person bounding boxes
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            is_inside = getattr(det, 'is_inside_corridor', True)

            if not is_inside:
                # Dimmed gray for people outside the corridor
                color = (130, 130, 130)
                label = messages.HUD_OUTSIDE_ZONE.format(track_id=det.track_id)
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 1)
                cv2.putText(out, label, (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            else:
                # Active subject inside corridor: Green if full body, Red if clipped
                color = (0, 255, 0) if det.is_full_body else (0, 69, 255)
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
                
                label = (messages.HUD_FULL_BODY if det.is_full_body else messages.HUD_STEP_BACK).format(track_id=det.track_id)
                cv2.putText(out, label, (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                if not det.is_full_body:
                    cv2.putText(out, f"! {det.reason}", (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 69, 255), 2)

        # Header info
        cv2.putText(out, messages.HUD_HEADER.format(fps=self.fps, device=detector.device_label), (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)
        status_text = messages.HUD_LIGHT.format(state=notifier.current_state)
        status_color = (0, 255, 0) if notifier.current_state == "GREEN" else ((0, 0, 255) if notifier.current_state == "RED" else (180, 180, 180))
        cv2.putText(out, status_text, (w - 200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)


        return out

    def get_latest_jpeg(self):
        with self.lock:
            return self.current_frame_bytes

video_service = VideoCaptureService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    video_service.start()
    yield
    video_service.stop()

app = FastAPI(title="PPE Detection VLM Backend", version="1.0.0", lifespan=lifespan)

# Enable CORS for decoupled frontend.
# Kredensial hanya diizinkan kalau daftar origin eksplisit; browser menolak
# kombinasi wildcard + credentials.
_allow_wildcard_origin = "*" in cfg.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=not _allow_wildcard_origin,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def require_admin(x_admin_token: str | None = Header(default=None)):
    """Guard opsional untuk endpoint yang mengubah state server.

    Server ini bind ke 0.0.0.0, jadi tanpa guard siapa pun di jaringan yang sama
    bisa mengganti API key, me-reset tracking, atau menyalakan lampu gerbang.
    Non-aktif ketika ADMIN_TOKEN kosong agar demo lokal tidak terhambat.
    """
    if not cfg.ADMIN_TOKEN:
        return
    if x_admin_token != cfg.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail=messages.API_INVALID_ADMIN_TOKEN)

# --- REST ENDPOINTS ---

@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "fps": round(video_service.fps, 1),
        "is_live_gemini": vlm_analyzer.is_live_api(),
        "camera_selected": video_service.camera_index is not None,
        "camera_index": video_service.camera_index,
        "camera_name": video_service.camera_name,
        "camera_status": video_service.camera_status,
        "resolution": f"{video_service.frame_width}x{video_service.frame_height}",
        # Saat LOST yang tampil juga frame sintetis, jadi ikut dihitung di sini
        "is_synthetic_camera": video_service.use_synthetic or video_service.camera_status == "LOST"
    }

@app.post("/api/reset", dependencies=[Depends(require_admin)])
async def reset_tracking():
    state_mgr.reset_all()
    return {"status": "success", "message": messages.API_STATE_RESET}

@app.post("/api/config/gemini-key", dependencies=[Depends(require_admin)])
async def update_gemini_key(request: Request):
    data = await request.json()
    new_key = data.get("api_key", "").strip()
    if new_key:
        vlm_analyzer.update_api_key(new_key)
        return {"status": "success", "is_live": vlm_analyzer.is_live_api()}
    return {"status": "error", "message": messages.API_KEY_EMPTY}

# --- CAMERA SOURCE ENDPOINTS ---

@app.get("/api/cameras")
async def list_cameras():
    """Katalog kamera beserta mode terukurnya.

    Mengembalikan hasil pemindaian terakhir seketika; `scanning` menandakan
    pemindaian latar masih berjalan (probing satu perangkat butuh beberapa detik).
    """
    catalog = camera_mgr.get_catalog()
    active = video_service.get_camera_status()

    # Kalau belum pernah dipindai, daftar tetap dibentuk dari nama perangkat.
    # Perangkat yang belum diukur ditandai `scanned: False`, bukan "tidak tersedia":
    # kamera USB yang baru dicolok belum tentu bermasalah, hanya belum diperiksa.
    if not catalog["devices"]:
        catalog["devices"] = [
            {
                "index": i,
                "name": name,
                "available": True,
                "scanned": False,
                "in_use": False,
                "modes": [],
                "selected_mode": None,
            }
            for i, name in enumerate(camera_manager.list_device_names())
        ]

    # Perangkat yang sedang dipakai tidak bisa di-probe karena terkunci oleh
    # aliran video, jadi datanya diisi dari service yang berjalan. Dijalankan
    # setelah daftar terbentuk agar berlaku untuk kedua sumber daftar di atas.
    for dev in catalog["devices"]:
        if dev["index"] != active["index"]:
            continue
        dev["in_use"] = True
        dev["available"] = not active["is_synthetic"]
        dev["scanned"] = True
        if active["mode"] and not dev.get("selected_mode"):
            dev["selected_mode"] = active["mode"]
        # Kamera yang dibuka dengan permintaan bawaan belum punya angka hasil
        # pengukuran, jadi laju yang sedang berjalan dipakai supaya daftar
        # tidak menampilkan "@0 FPS".
        sel = dev.get("selected_mode")
        if sel and not sel.get("fps"):
            sel = dict(sel)
            sel["fps"] = active["fps"]
            dev["selected_mode"] = sel

    # Pilihan terakhir dipakai untuk menyorot bawaan di dialog pemilihan,
    # bukan untuk menyambung otomatis.
    catalog["saved"] = camera_manager.load_saved_selection()
    catalog["active"] = active
    catalog["quality_warning"] = (
        active["height"] > 0 and active["height"] < cfg.CAMERA_QUALITY_WARN_HEIGHT
    )
    return catalog


@app.post("/api/cameras/scan", dependencies=[Depends(require_admin)])
async def scan_cameras():
    """Memulai probing kemampuan seluruh kamera di latar belakang."""
    # Kamera aktif tidak bisa di-probe dari luar karena terkunci aliran video,
    # jadi pengukurannya dititipkan ke thread pembaca yang memilikinya.
    video_service.request_optimize()
    started = camera_mgr.start_scan(skip_index=video_service.camera_index)
    return {
        "status": "started" if started else "already_running",
        "scanning": True,
        "message": messages.API_SCAN_STARTED,
    }


@app.post("/api/config/camera", dependencies=[Depends(require_admin)])
async def set_camera_source(request: Request):
    """Memindahkan sumber video ke kamera lain tanpa menjalankan ulang server."""
    data = await request.json()

    # index null berarti lepaskan kamera dan kembali ke layar pemilihan
    if data.get("index") is None:
        video_service.request_idle()
        return {"status": "scheduled", "pending_index": None,
                "message": messages.API_CAMERA_RELEASED}

    try:
        index = int(data["index"])
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": messages.API_CAMERA_INDEX_INVALID},
        )

    mode = data.get("mode")
    video_service.request_camera(index, mode)
    # Pergantian dikerjakan thread pembaca, jadi belum selesai saat balasan ini
    # dikirim. Status sebenarnya dibaca klien dari telemetri WebSocket.
    return {
        "status": "scheduled",
        "pending_index": index,
        "message": messages.API_CAMERA_SWITCHING.format(index=index),
    }


@app.post("/api/config/corridor", dependencies=[Depends(require_admin)])
async def set_corridor_filter(request: Request):
    """Menyalakan atau mematikan Virtual Inspection Corridor."""
    data = await request.json()
    cfg.ENABLE_CORRIDOR_FILTER = bool(data.get("enabled", True))
    return {"status": "success", "enabled": cfg.ENABLE_CORRIDOR_FILTER}


# --- IOT HARDWARE TEST ENDPOINT ---

@app.post("/api/iot/test", dependencies=[Depends(require_admin)])
async def test_iot_light(request: Request):
    """Allows manual operator testing of physical gate lights (green/red/off) from Settings tab."""
    data = await request.json()
    action = data.get("action", "off").lower()
    if action == "green":
        notifier.set_complete(messages.LIGHT_TEST_GREEN)
    elif action == "red":
        notifier.set_incomplete(messages.LIGHT_TEST_RED)
    else:
        notifier.set_idle()
    return {
        "status": "success",
        "action": action,
        "light_state": notifier.current_state
    }

# --- KATALOG APD ---

def _ppe_catalog_payload() -> dict:
    """Katalog lengkap beserta status aktif dan ketersediaan pemeriksa lokal."""
    local = vlm_analyzer.local_analyzer
    return {
        "items": [
            {**item.to_public_dict(), "local_check": local.has_local_check(item.key)}
            for item in ppe_rules.get_items()
        ]
    }


@app.get("/api/ppe-rules")
async def get_ppe_rules():
    """Katalog item APD untuk dashboard; checklist dan lencana dirender dari sini."""
    return _ppe_catalog_payload()


@app.post("/api/ppe-rules/active", dependencies=[Depends(require_admin)])
async def set_ppe_rules_active(request: Request):
    """Menghidupkan/mematikan item APD. Body: {"active": {"kacamata": true, ...}}.

    Berlaku untuk inspeksi berikutnya dan tersimpan di `runtime_settings.json`.
    """
    data = await request.json()
    changes = data.get("active") if isinstance(data, dict) else None
    if not isinstance(changes, dict) or not all(isinstance(v, bool) for v in changes.values()):
        raise HTTPException(status_code=400, detail=messages.API_PPE_ACTIVE_FORMAT)
    try:
        ppe_rules.set_active(changes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    aktif = [item.label for item in ppe_rules.get_active_items()]
    print(f"[PPERules] Item APD aktif: {', '.join(aktif)}")
    return _ppe_catalog_payload()

# --- AUDIO MUTE CONFIG ENDPOINTS ---

@app.get("/api/config/audio")
async def get_audio_config():
    return {"muted": audio_player.is_muted}

@app.post("/api/config/audio", dependencies=[Depends(require_admin)])
async def set_audio_config(request: Request):
    data = await request.json()
    muted = data.get("muted", False)
    is_muted = audio_player.set_muted(muted)
    return {"status": "success", "muted": is_muted}

# --- WORKER REPORT & AUDIT ENDPOINTS ---

@app.get("/api/reports")
async def get_worker_reports(limit: int = 50, offset: int = 0, status: str = "all", date: str = None):
    """Returns paginated worker inspection records with global compliance statistics."""
    data = report_mgr.get_reports(limit=limit, offset=offset, status_filter=status, date_filter=date)
    return data

@app.get("/api/reports/snapshots/{filename}")
async def get_worker_snapshot(filename: str):
    """Serves an inspection snapshot crop image for a specific worker."""
    path = report_mgr.get_snapshot_path(filename)
    if path and path.exists():
        return FileResponse(str(path), media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"error": messages.API_SNAPSHOT_NOT_FOUND})

@app.get("/api/reports/export")
async def export_worker_reports_csv():
    """Generates and downloads a CSV audit report for HSE/K3 compliance."""
    csv_data = report_mgr.export_csv_text()
    today_str = time.strftime("%Y-%m-%d")
    filename = f"laporan_inspeksi_apd_{today_str}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )

# --- API MONITORING & ENGINE MODE ENDPOINTS ---

@app.get("/api/monitoring/status")
async def get_monitoring_status():
    """Returns real-time Gemini Cloud API health, ping latency, and engine mode."""
    return api_monitor.get_status()

@app.post("/api/monitoring/ping", dependencies=[Depends(require_admin)])
async def ping_gemini_api():
    """Initiates an on-demand latency test to Google Gemini API."""
    res = vlm_analyzer.ping_api()
    return res

@app.post("/api/config/engine-mode", dependencies=[Depends(require_admin)])
async def set_engine_mode(request: Request):
    """Allows operator to toggle between Online (Cloud Gemini) and Offline (heuristik lokal OpenCV)."""
    data = await request.json()
    mode = data.get("engine_mode", "HYBRID_AUTO")
    new_mode = api_monitor.set_engine_mode(mode)
    return {
        "status": "success",
        "engine_mode": new_mode,
        "is_forced_local": new_mode == "FORCE_LOCAL"
    }

@app.get("/api/stream")
async def video_stream(request: Request):
    """MJPEG streaming endpoint with graceful client disconnect handling."""
    async def frame_generator():
        try:
            while not SHUTTING_DOWN.is_set():
                if await request.is_disconnected():
                    break
                frame_bytes = video_service.get_latest_jpeg()
                if frame_bytes is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                await asyncio.sleep(cfg.STREAM_INTERVAL_SECONDS)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return GracefulStreamingResponse(
        frame_generator(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# --- WEBSOCKET FOR REAL-TIME TELEMETRY (<10ms) ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        text_data = json.dumps(data)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(text_data)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while not SHUTTING_DOWN.is_set():
            telemetry = state_mgr.get_telemetry()
            telemetry["fps"] = round(video_service.fps, 1)
            telemetry["audio_muted"] = audio_player.is_muted
            # Dimensi sebenarnya, supaya overlay canvas sejajar walau kamera
            # mengabaikan resolusi yang diminta di config.
            telemetry["frame_width"] = video_service.frame_width
            telemetry["frame_height"] = video_service.frame_height
            telemetry["camera"] = video_service.get_camera_status()
            await websocket.send_json(telemetry)
            await asyncio.sleep(cfg.TELEMETRY_INTERVAL_SECONDS)
        # Server sedang berhenti: tutup rapi agar uvicorn tidak menunggu
        await websocket.close()
    except (WebSocketDisconnect, asyncio.CancelledError):
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


class RevalidatingStaticFiles(StaticFiles):
    """StaticFiles yang mewajibkan browser memvalidasi ulang setiap berkas.

    Tanpa `Cache-Control`, browser memakai cache heuristik dan terus menjalankan
    JS versi lama setelah server diperbarui — padahal bentuk data API ikut
    berubah. `no-cache` tetap memakai cache, hanya saja dicek dulu lewat ETag
    (304 bila tidak berubah), jadi biayanya kecil.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Mount frontend directory if exists
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", RevalidatingStaticFiles(directory=str(frontend_dir), html=True), name="frontend")

def run():
    """Menjalankan server. Dipanggil dari `python -m backend` (lihat `__main__.py`)."""
    import contextlib
    import signal
    import uvicorn
    from uvicorn.server import HANDLED_SIGNALS

    class GracefulServer(uvicorn.Server):
        """Custom Uvicorn Server that suppresses Windows SIGINT/CancelledError traceback on Ctrl+C."""
        @contextlib.contextmanager
        def capture_signals(self):
            original_handlers = {}
            for sig in HANDLED_SIGNALS:
                try:
                    original_handlers[sig] = signal.signal(sig, self.handle_exit)
                except (ValueError, OSError):
                    pass
            try:
                yield
            finally:
                for sig, handler in original_handlers.items():
                    try:
                        signal.signal(sig, handler)
                    except (ValueError, OSError):
                        pass
                # Intentionally avoid re-raising SIGINT on Windows so event loop exits with zero error trace

    # Objek app dioper langsung, bukan lewat string "backend.main:app". Bentuk
    # string membuat uvicorn mengimpor modul ini lewat jalur impornya sendiri;
    # begitu jalur itu berbeda dari cara modul ini dimuat, terbentuk dua salinan
    # modul: dua VideoCaptureService, dua app, dan dua SHUTTING_DOWN. Penangan
    # sinyal lalu menyetel penanda pada salinan yang salah, sehingga endpoint
    # streaming tidak pernah berhenti dan server menggantung di "Waiting for
    # connections to close".
    config = uvicorn.Config(app, host=cfg.HOST, port=cfg.PORT, reload=False, log_level="info")
    server = GracefulServer(config)
    try:
        server.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    print("\n[Server] Shutdown selesai secara bersih. Sampai jumpa!")
