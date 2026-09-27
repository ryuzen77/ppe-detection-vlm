import logging
import time
import threading
from queue import Empty, Queue
import pygame
from .config import cfg
from . import ppe_rules

logger = logging.getLogger(__name__)

class AudioEngine:
    """Thread-safe, non-blocking audio player using pygame.mixer."""
    def __init__(self):
        self.audio_dir = cfg.AUDIO_DIR
        self.queue: Queue = Queue()
        self.is_running = False
        self.is_muted = False
        self.last_played_time = {}
        # Perangkat audio baru dibuka di start(); sebelum itu play() diabaikan
        self.enabled = False
        self.channel = None
        self.worker = None
        # Diset saat suara penting (hasil keputusan) masuk: suara biasa yang masih
        # menunggu giliran dibuang, supaya hasil tidak tertahan "mohon tunggu".
        self._urgent = threading.Event()

    def start(self):
        """Membuka mixer pygame dan menyalakan thread pemutar. Idempoten."""
        if self.is_running:
            return
        try:
            pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self.channel = pygame.mixer.Channel(0)
            self.channel.set_volume(cfg.AUDIO_VOLUME)
            self.enabled = True
        except Exception as e:
            logger.warning(f"Warning: Failed to init pygame mixer: {e}")
            self.enabled = False

        self.is_running = True
        self.worker = threading.Thread(target=self._process_queue, daemon=True)
        self.worker.start()

    def set_muted(self, muted: bool) -> bool:
        self.is_muted = bool(muted)
        if self.is_muted and hasattr(self, 'channel') and self.channel:
            try:
                self.channel.stop()
            except Exception:
                pass
        return self.is_muted

    def _process_queue(self):
        while self.is_running:
            try:
                item = self.queue.get(timeout=cfg.AUDIO_POLL_SECONDS)
            except Empty:
                continue
            try:
                self._handle(*item)
            finally:
                self.queue.task_done()

    def _load(self, audio_file):
        return pygame.mixer.Sound(str(audio_file))

    def _handle(self, sound_name: str, min_interval: float, urgent: bool):
        """Memutar satu suara. Suara penting memotong yang sedang berbunyi;
        suara biasa menunggu channel kosong dan dibuang bila suara penting datang."""
        if urgent:
            # Direset paling awal: bila suara penting ini ternyata dilewati (jeda
            # ulang, senyap, berkas hilang), tanda yang tertinggal akan membuang
            # diam-diam setiap suara biasa berikutnya yang harus menunggu channel.
            self._urgent.clear()
        if not self.enabled or self.is_muted:
            return
        now = time.time()
        if now - self.last_played_time.get(sound_name, 0) < min_interval:
            return
        audio_file = self.audio_dir / f"{sound_name}.mp3"
        if not audio_file.exists():
            logger.warning(f"File not found: {audio_file}")
            return

        try:
            if urgent:
                self.channel.stop()
            else:
                while self.channel.get_busy() and self.is_running:
                    if self._urgent.is_set():
                        return
                    time.sleep(cfg.AUDIO_POLL_SECONDS)
            self.channel.play(self._load(audio_file))
            self.last_played_time[sound_name] = now
        except Exception as e:
            logger.warning(f"Error playing {sound_name}: {e}")

    def _drop_pending(self):
        """Membuang suara yang belum sempat diputar."""
        while True:
            try:
                self.queue.get_nowait()
            except Empty:
                return
            self.queue.task_done()

    def play(self, sound_name: str, min_interval: float = 1.0, urgent: bool = False):
        """Mengantrekan suara. `urgent` (hasil keputusan, gangguan sistem) langsung
        memotong suara yang sedang berbunyi dan membuang antrean sebelumnya: di T35
        suara hasil tertahan ~1,3 dtk menunggu "sedang menganalisa" selesai."""
        if not self.enabled:
            return
        if urgent:
            self._drop_pending()
            self._urgent.set()
        self.queue.put((sound_name, min_interval, urgent))

    def play_step_back(self, clip_type: str = "FEET_CLIPPED"):
        """Audio cue tailored to which part of the body is clipped (head or feet)."""
        if clip_type == "HEAD_CLIPPED":
            self.play("mundur_kepala", min_interval=cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS)
        elif clip_type == "FEET_CLIPPED":
            self.play("mundur_kaki", min_interval=cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS)
        else:
            self.play("mundur", min_interval=cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS)

    def result_sound(self, is_complete: bool, missing_items: list[str] = None) -> str:
        """Nama suara untuk hasil inspeksi.

        Satu item kurang → suara khusus item itu, diambil dari `audio_missing`
        pada katalog. Lebih dari satu, alasan di luar katalog (mis. anti-spoofing),
        atau berkas MP3 item belum dibangkitkan → peringatan umum, supaya pekerja
        tidak pernah ditolak dalam diam.
        """
        if is_complete:
            return "lengkap"
        missing_items = missing_items or []
        if len(missing_items) == 1:
            item = ppe_rules.get_item_by_missing_label(missing_items[0])
            if item is not None and (self.audio_dir / f"{item.audio_missing}.mp3").exists():
                return item.audio_missing
        return "tidak_lengkap"

    def play_result(self, is_complete: bool, missing_items: list[str] = None):
        """Plays corresponding voice based on PPE detection result."""
        self.play(self.result_sound(is_complete, missing_items), min_interval=cfg.AUDIO_RESULT_DEBOUNCE_SECONDS,
                  urgent=True)

    def stop(self):
        self.is_running = False
        if self.enabled:
            pygame.mixer.stop()

audio_player = AudioEngine()
