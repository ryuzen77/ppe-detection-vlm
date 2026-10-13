"""Ukur angka kesehatan gambar kamera per kondisi (T57): terhalang benda & buram.

Deteksi "tertutup" T45 dikalibrasi dengan penutup lensa kamera laptop (hitam pekat).
Uji 13-10: C920 ditutup tangan tidak terdeteksi (auto-exposure menerangkan benda,
benda bergradasi). Alat ini mengumpulkan angka nyata untuk menentukan ambang baru.

Per cuplikan (±5 per detik) dicatat:
- mean / std   : kecerahan & keseragaman (sama persis dengan camera_health.is_blocked)
- sharp, edges : ketajaman & porsi tepi (camera_health.image_detail, sama dengan gerbang)
- blocked      : vonis per cuplikan camera_health.is_blocked (sebelum syarat bertahan)
- diff_ref     : beda rata-rata absolut terhadap acuan jalur kosong (kondisi pertama)
- persons      : jumlah orang terdeteksi YOLO (conf >= YOLO_CONF)

Instruksi diucapkan lewat speaker (gTTS seperti suara gerbang). Tidak ada gambar yang
disimpan: hanya angka ke data/eval/<waktu>_camera_probe.csv (+ ringkasan .json).

    python tools/camera_probe.py --find        # cari index kamera yang akan ditutup
    python tools/camera_probe.py --index <n>
"""

import argparse
import csv
import json
import hashlib
import statistics
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import camera_health  # noqa: E402
from backend.camera_manager import CAPTURE_BACKEND  # noqa: E402
from backend.config import cfg  # noqa: E402
from backend.generate_audio import TTS_LANG  # noqa: E402

PREPARE_SECONDS = 6.0
RECORD_SECONDS = 10.0
SAMPLE_SECONDS = 0.2

# (kunci, instruksi yang diucapkan). Kondisi pertama = acuan jalur kosong.
CONDITIONS = [
    ("kosong", "Kosongkan jalur. Jangan ada orang di depan kamera."),
    ("orang", "Berdiri di titik berdiri seperti pekerja."),
    ("dekat", "Berdiri sangat dekat dengan kamera, kira kira setengah meter."),
    ("tangan", "Tutup kamera dengan tangan."),
    ("kardus", "Tutup kamera dengan kardus atau kertas."),
    ("kain", "Tutup kamera dengan kain."),
    ("sebagian", "Tutup setengah lensa saja."),
    ("buram", "Buat lensa buram, misalnya dengan plastik bening atau ditiup sampai berembun."),
]


# Suara sama dengan gerbang (gTTS bahasa Indonesia, diputar pygame): suara Windows
# terdengar tidak jelas/berlogat. MP3 di-cache di folder sementara, bukan di repo.
VOICE_CACHE = Path(tempfile.gettempdir()) / "depro_camera_probe_voice"
FIND_SETTLE_SECONDS = 4.0  # beri waktu auto-exposure menyesuaikan sebelum diukur
FIND_FRAMES = 10
FIND_MAX_INDEX = 3
SYSTEM_TEXTS = ["Mulai", "Selesai", "Pengukuran selesai. Terima kasih."]
FIND_TEXTS = [
    "Biarkan kamera C920 terbuka.",
    "Tutup kamera C920 dengan tangan, tahan sampai selesai.",
    "Selesai. Lepaskan tangan.",
]


def voice_file(text: str) -> Path:
    return VOICE_CACHE / f"{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}.mp3"


def prepare_voice(texts: list[str]):
    """Bangkitkan semua MP3 di awal supaya tidak ada jeda internet di tengah pengukuran."""
    from gtts import gTTS

    VOICE_CACHE.mkdir(parents=True, exist_ok=True)
    for text in texts:
        if not voice_file(text).exists():
            gTTS(text=text, lang=TTS_LANG, slow=False).save(str(voice_file(text)))
    pygame.mixer.init()


def say(text: str):
    print(f">>> {text}", flush=True)
    pygame.mixer.music.load(str(voice_file(text)))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)


def metrics(frame: np.ndarray, reference) -> dict:
    """Angka yang sama persis dengan yang dihitung gerbang (camera_health)."""
    gray = camera_health.detail_gray(frame)
    gray_small = cv2.resize(
        gray, (cfg.CAMERA_HEALTH_SAMPLE_WIDTH, cfg.CAMERA_HEALTH_SAMPLE_HEIGHT), interpolation=cv2.INTER_AREA
    )
    sharpness, edges = camera_health.image_detail(gray)
    diff = None if reference is None else float(np.abs(gray_small.astype(np.float32) - reference).mean())
    return {
        "mean": float(gray_small.mean()),
        "std": float(gray_small.std()),
        "sharp": sharpness,
        "edges": edges,
        "diff_ref": diff,
        "blocked": camera_health.is_blocked(frame),
        "_gray": gray_small,
    }


def count_persons(model, frame) -> int:
    result = model.predict(frame, conf=cfg.YOLO_CONF, classes=[0], verbose=False)[0]
    return 0 if result.boxes is None else len(result.boxes)


def record(cap, model, key: str, reference) -> list[dict]:
    rows, end = [], time.monotonic() + RECORD_SECONDS
    while time.monotonic() < end:
        ok, frame = cap.read()
        if not ok:
            continue
        m = metrics(frame, reference)
        m["persons"] = count_persons(model, frame)
        m["condition"] = key
        rows.append(m)
        time.sleep(SAMPLE_SECONDS)
    return rows


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for key, _ in CONDITIONS:
        part = [r for r in rows if r["condition"] == key]
        if not part:
            continue
        stats = {}
        for field in ("mean", "std", "sharp", "edges", "diff_ref", "persons", "blocked"):
            values = [r[field] for r in part if r[field] is not None]
            if values:
                stats[field] = {
                    "min": round(min(values), 3),
                    "median": round(statistics.median(values), 3),
                    "max": round(max(values), 3),
                }
        summary[key] = {"samples": len(part), **stats}
    return summary


def sample_gray(cap) -> np.ndarray:
    """Median gambar abu-abu kecil dari beberapa cuplikan (meredam derau)."""
    frames = []
    for _ in range(FIND_FRAMES):
        ok, frame = cap.read()
        if ok:
            frames.append(metrics(frame, None)["_gray"])
    return np.median(np.stack(frames), axis=0).astype(np.float32)


def find_camera() -> int:
    """Index yang gambarnya berubah besar saat C920 ditutup tangan = C920."""
    caps = {}
    for i in range(FIND_MAX_INDEX):
        cap = cv2.VideoCapture(i, CAPTURE_BACKEND)
        if cap.isOpened():
            caps[i] = cap
    try:
        say(FIND_TEXTS[0])
        time.sleep(FIND_SETTLE_SECONDS)
        open_gray = {i: sample_gray(c) for i, c in caps.items()}
        say(FIND_TEXTS[1])
        time.sleep(FIND_SETTLE_SECONDS)
        covered_gray = {i: sample_gray(c) for i, c in caps.items()}
        say(FIND_TEXTS[2])
    finally:
        for cap in caps.values():
            cap.release()
    for i in caps:
        change = float(np.abs(open_gray[i] - covered_gray[i]).mean())
        print(f"index {i}: perubahan gambar saat ditutup = {change:.1f}")
    return 0


def open_camera(index: int):
    cap = cv2.VideoCapture(index, CAPTURE_BACKEND)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.CAMERA_DEFAULT_REQ_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.CAMERA_DEFAULT_REQ_HEIGHT)
    return cap


def with_reference(part: list[dict]) -> np.ndarray:
    """Acuan jalur kosong = median cuplikan "kosong"; beda tiap cuplikan kosong diisi ulang."""
    reference = np.median(np.stack([r["_gray"] for r in part]), axis=0).astype(np.float32)
    for r in part:
        r["diff_ref"] = float(np.abs(r["_gray"].astype(np.float32) - reference).mean())
    return reference


def measure_conditions(cap, model, wanted) -> list[dict]:
    rows, reference = [], None
    for key, instruction in CONDITIONS:
        if wanted and key not in wanted:
            continue
        say(f"Persiapan. {instruction}")
        time.sleep(PREPARE_SECONDS)
        say("Mulai")
        part = record(cap, model, key, reference)
        if key == "kosong":
            reference = with_reference(part)
        rows += part
        say("Selesai")
    return rows


def save_results(rows: list[dict]):
    out = cfg.DATA_DIR / "eval" / f"{time.strftime('%Y%m%d-%H%M%S')}_camera_probe"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["condition", "mean", "std", "sharp", "edges", "diff_ref", "persons", "blocked"]
    with open(f"{out}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary = json.dumps(summarize(rows), indent=2, ensure_ascii=False)
    Path(f"{out}.json").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"hasil: {out}.csv/.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, required=False)
    ap.add_argument("--find", action="store_true", help="cari index C920 (tutup dengan tangan saat diminta)")
    ap.add_argument("--only", default="", help="hanya kondisi ini, dipisah koma (kosong pertama tetap diukur)")
    args = ap.parse_args()
    if args.find:
        prepare_voice(FIND_TEXTS)
        return find_camera()
    if args.index is None:
        ap.error("--index wajib (cari dulu dengan --find)")
    prepare_voice(SYSTEM_TEXTS + [f"Persiapan. {text}" for _, text in CONDITIONS])
    from ultralytics import YOLO

    model, cap = YOLO(cfg.YOLO_MODEL_PATH), open_camera(args.index)
    if not cap.isOpened():
        print("Kamera tidak bisa dibuka.")
        return 1
    wanted = {"kosong", *filter(None, args.only.split(","))} if args.only else None
    try:
        rows = measure_conditions(cap, model, wanted)
    finally:
        cap.release()
    say("Pengukuran selesai. Terima kasih.")
    save_results(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
