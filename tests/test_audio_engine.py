"""Antrean suara gerbang: suara hasil memotong suara lain (T36b), tanpa speaker."""
import threading
import time

import pytest

from backend import generate_audio, messages, ppe_rules
from backend.audio_engine import AudioEngine


class FakeChannel:
    """Channel pygame tiruan: 'berbunyi' sampai stop() atau suara berikutnya."""

    def __init__(self):
        self.busy = False
        self.played = []
        self.stops = 0

    def get_busy(self):
        return self.busy

    def play(self, sound):
        self.played.append(sound)
        self.busy = True

    def stop(self):
        self.stops += 1
        self.busy = False


@pytest.fixture
def engine(tmp_path):
    e = AudioEngine()
    e.audio_dir = tmp_path
    for name in ("sedang_analisa", "lengkap", "mundur"):
        (tmp_path / f"{name}.mp3").write_bytes(b"x")
    e.channel = FakeChannel()
    e.enabled = True
    e.is_running = True
    e._load = lambda path: path.stem  # nama suara sebagai "Sound"
    return e


def test_suara_penting_memotong_suara_yang_sedang_berbunyi(engine):
    engine._handle("sedang_analisa", 0, False)
    assert engine.channel.busy
    engine._handle("lengkap", 0, True)
    assert engine.channel.played == ["sedang_analisa", "lengkap"]
    assert engine.channel.stops == 1


def test_suara_biasa_menunggu_lalu_dibuang_saat_suara_penting_datang(engine):
    engine._handle("sedang_analisa", 0, False)  # channel sibuk
    done = threading.Event()

    def waiting_cue():
        engine._handle("mundur", 0, False)  # menunggu channel kosong
        done.set()

    threading.Thread(target=waiting_cue, daemon=True).start()
    time.sleep(0.15)
    assert not done.is_set(), "suara biasa harus menunggu suara yang sedang berbunyi"
    engine.play("lengkap", urgent=True)
    assert done.wait(1.0), "suara biasa yang menunggu harus dibuang"
    assert "mundur" not in engine.channel.played


def test_suara_penting_membuang_antrean_lama(engine):
    engine.play("sedang_analisa")
    engine.play("mundur")
    engine.play("lengkap", urgent=True)
    queued = []
    while not engine.queue.empty():
        queued.append(engine.queue.get_nowait()[0])
    assert queued == ["lengkap"]


def test_hasil_keputusan_selalu_suara_penting(engine, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "play", lambda name, min_interval=1.0, urgent=False: calls.append(urgent))
    engine.play_result(True)
    engine.play_result(False, ["Helm Keselamatan"])
    assert calls == [True, True]


def test_suara_dilewati_saat_senyap(engine):
    engine.is_muted = True
    engine._handle("lengkap", 0, True)
    assert engine.channel.played == []


# --- Pembangkit MP3 -------------------------------------------------------------------

def test_semua_suara_punya_teks():
    prompts = generate_audio.build_prompts()
    for key in messages.VOICE_TEXTS:
        assert prompts[key]
    for item in ppe_rules.get_items():
        assert prompts[item.audio_missing] == item.audio_missing_text


def test_hanya_berkas_baru_atau_teks_berubah_yang_dibangkitkan():
    prompts = {"a": "satu", "b": "dua", "c": "tiga"}
    recorded = {"a": "satu", "b": "dua lama"}
    existing = {"a", "b"}
    assert generate_audio.stale_keys(prompts, recorded, existing) == ["b", "c"]


def test_suara_penting_yang_dilewati_tidak_meninggalkan_tanda(engine):
    # Hasil yang sama dua kali dalam jeda ulang: yang kedua dilewati, tetapi
    # suara biasa sesudahnya tetap harus diputar setelah channel kosong.
    engine._handle("lengkap", 0, True)
    engine.play("lengkap", min_interval=60, urgent=True)
    engine._handle(*engine.queue.get_nowait())
    assert not engine._urgent.is_set()

    done = threading.Event()
    threading.Thread(target=lambda: (engine._handle("mundur", 0, False), done.set()), daemon=True).start()
    time.sleep(0.1)
    engine.channel.busy = False  # suara "lengkap" selesai
    assert done.wait(1.0)
    assert engine.channel.played[-1] == "mundur"
