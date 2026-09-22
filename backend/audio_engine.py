import os
import time
import threading
from pathlib import Path
from queue import Queue
import pygame
from config import cfg

class AudioEngine:
    """Thread-safe, non-blocking audio player using pygame.mixer."""
    def __init__(self):
        self.audio_dir = cfg.AUDIO_DIR
        self.queue: Queue = Queue()
        self.is_running = True
        self.is_muted = False
        self.last_played_time = {}

        try:
            pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self.channel = pygame.mixer.Channel(0)
            self.channel.set_volume(cfg.AUDIO_VOLUME)
            self.enabled = True
        except Exception as e:
            print(f"[AudioEngine] Warning: Failed to init pygame mixer: {e}")
            self.enabled = False

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
                sound_name, min_interval = self.queue.get(timeout=0.1)
            except Exception:
                continue

            if not self.enabled or self.is_muted:
                self.queue.task_done()
                continue

            now = time.time()
            last_time = self.last_played_time.get(sound_name, 0)
            if now - last_time < min_interval:
                self.queue.task_done()
                continue

            audio_file = self.audio_dir / f"{sound_name}.mp3"
            if not audio_file.exists():
                print(f"[AudioEngine] File not found: {audio_file}")
                self.queue.task_done()
                continue

            try:
                while self.channel.get_busy() and self.is_running:
                    time.sleep(0.05)

                sound = pygame.mixer.Sound(str(audio_file))
                self.channel.play(sound)
                self.last_played_time[sound_name] = now
            except Exception as e:
                print(f"[AudioEngine] Error playing {sound_name}: {e}")

            self.queue.task_done()

    def play(self, sound_name: str, min_interval: float = 1.0):
        if not self.enabled:
            return
        self.queue.put((sound_name, min_interval))

    def play_step_back(self, clip_type: str = "FEET_CLIPPED"):
        """Audio cue tailored to which part of the body is clipped (head or feet)."""
        if clip_type == "HEAD_CLIPPED":
            self.play("mundur_kepala", min_interval=cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS)
        elif clip_type == "FEET_CLIPPED":
            self.play("mundur_kaki", min_interval=cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS)
        else:
            self.play("mundur", min_interval=cfg.AUDIO_STEP_BACK_DEBOUNCE_SECONDS)

    def play_result(self, is_complete: bool, missing_items: list[str] = None):
        """Plays corresponding voice based on PPE detection result."""
        if is_complete:
            self.play("lengkap", min_interval=3.0)
        else:
            missing_items = missing_items or []
            if len(missing_items) == 1:
                item = missing_items[0].lower()
                if "helm" in item:
                    self.play("kurang_helm", min_interval=3.0)
                elif "rompi" in item:
                    self.play("kurang_rompi", min_interval=3.0)
                elif "celana" in item:
                    self.play("kurang_celana", min_interval=3.0)
                elif "sepatu" in item:
                    self.play("kurang_sepatu", min_interval=3.0)
                else:
                    self.play("tidak_lengkap", min_interval=3.0)
            else:
                self.play("tidak_lengkap", min_interval=3.0)

    def stop(self):
        self.is_running = False
        if self.enabled:
            pygame.mixer.stop()

audio_player = AudioEngine()
