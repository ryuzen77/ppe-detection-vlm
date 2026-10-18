"""Uji wajah di kamera gerbang (T34a). Jalankan di env `fr_eval` dengan server gerbang MATI
(kamera hanya bisa dipakai satu proses).

Berdiri di posisi pemeriksaan; tiap kondisi diawali hitung mundur + 1 bunyi, direkam
beberapa detik, diakhiri 2 bunyi. Kondisi pertama menjadi acuan "pendaftaran"
sementara; kondisi lain dibandingkan dengannya terhadap ambang.

TIDAK menyimpan foto maupun embedding: templat acuan hanya di memori selama proses
berjalan. `--out` hanya berisi angka ringkasan.

    conda activate fr_eval
    python tools/fr_eval/face_probe.py --size 1280x720
    python tools/fr_eval/face_probe.py --size 1920x1080 --conditions "tanpa helm,helm,jauh"
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

import metrics
from runtimes import align_face, load_detector, load_recognizer
from stats import CATALOG, load_catalog, summarize

DEFAULT_CONDITIONS = "tanpa helm,helm,kacamata,helm + kacamata"
# Ambang awal 1:N dari LFW (galeri ±300, FPIR 0,1%; keputusan 18-10), dikalibrasi ulang dengan data nyata
DEFAULT_THRESHOLD = 0.55
BEEP_HZ, BEEP_MS = 880, 200
WINDOW = "T34a uji wajah (q = berhenti)"
# Warna BGR pratinjau: kuning = bersiap, merah = merekam, hijau = lolos ambang
READY, RECORDING, PASS = (0, 215, 255), (0, 0, 255), (0, 200, 0)


@dataclass
class ConditionLog:
    label: str
    frames: int = 0
    widths: list[float] = field(default_factory=list)
    interocular: list[float] = field(default_factory=list)
    det_scores: list[float] = field(default_factory=list)
    det_ms: list[float] = field(default_factory=list)
    embed_ms: list[float] = field(default_factory=list)
    vectors: list[np.ndarray] = field(default_factory=list)


def _beep(times: int) -> None:
    for _ in range(times):
        if os.name == "nt":
            import winsound

            winsound.Beep(BEEP_HZ, BEEP_MS)
        else:
            print("\a", end="", flush=True)
        time.sleep(0.15)


def _open_camera(index: int, width: int, height: int) -> cv2.VideoCapture:
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened() or cap.read()[1] is None:
        sys.exit(f"Kamera {index} tidak bisa dibuka (server gerbang masih jalan?)")
    return cap


def _largest_face(faces: np.ndarray | None) -> np.ndarray | None:
    if faces is None or len(faces) == 0:
        return None
    return faces[int(np.argmax(faces[:, 2] * faces[:, 3]))]


def _measure(frame: np.ndarray, detector, embed, entry: dict, log: ConditionLog) -> np.ndarray | None:
    log.frames += 1
    t0 = time.perf_counter()
    face = _largest_face(detector.detect(frame)[1])
    log.det_ms.append((time.perf_counter() - t0) * 1000)
    if face is None:
        return None
    points = face[4:14].reshape(5, 2)
    log.widths.append(float(face[2]))
    log.interocular.append(metrics.interocular_px(points))
    log.det_scores.append(float(face[14]))
    t1 = time.perf_counter()
    vector = np.asarray(embed(align_face(frame, points, entry["align"], entry["input"])), np.float32).ravel()
    log.embed_ms.append((time.perf_counter() - t1) * 1000)
    log.vectors.append(vector / np.linalg.norm(vector))
    return face


def _show(frame: np.ndarray, face: np.ndarray | None, lines: list[str], color: tuple) -> None:
    """Pratinjau dicerminkan (seperti cermin bagi orang di depan kamera); teks berbingkai hitam."""
    view = frame.copy()
    if face is not None:
        x, y, w, h = face[:4].astype(int)
        cv2.rectangle(view, (x, y), (x + w, y + h), color, 3)
    view = cv2.flip(view, 1)
    scale = view.shape[1] / 900
    for i, text in enumerate(lines):
        origin = (20, int((i + 1) * 45 * scale))
        cv2.putText(view, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), int(6 * scale) + 1)
        cv2.putText(view, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, color, int(2 * scale) + 1)
    cv2.imshow(WINDOW, view)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        raise KeyboardInterrupt


def _face_info(face: np.ndarray | None, similarity: float | None = None, threshold: float = 0.0) -> list[str]:
    if face is None:
        return ["wajah tidak terdeteksi"]
    lines = [f"lebar wajah {face[2]:.0f} px, mata {metrics.interocular_px(face[4:14].reshape(5, 2)):.0f} px"]
    if similarity is not None:
        lines.append(f"mirip acuan {similarity:.2f} ({'LOLOS' if similarity >= threshold else 'di bawah'} {threshold})")
    return lines


def _countdown(cap, detector, label: str, args, seconds: float) -> None:
    end = time.time() + seconds
    while (left := end - time.time()) > 0:
        print(f"\r>>> Bersiap: {label.upper()} - mulai dalam {left:.0f} dtk   ", end="", flush=True)
        ok, frame = cap.read()  # sekaligus membuang frame lama
        if ok and args.preview:
            face = _largest_face(detector.detect(frame)[1])
            _show(frame, face, [f"BERSIAP: {label}", f"mulai dalam {left:.0f} dtk", *_face_info(face)], READY)


def _record(cap, detector, embed, entry: dict, label: str, args, reference: np.ndarray | None) -> ConditionLog:
    # Kondisi pertama boleh diberi jeda lebih lama: waktu untuk berjalan ke posisi pemeriksaan
    first = reference is None and args.first_pause is not None
    _countdown(cap, detector, label, args, args.first_pause if first else args.pause)
    print(f"\r>>> MEREKAM: {label.upper()} ({args.seconds:g} dtk)          ", flush=True)
    _beep(1)
    log, end = ConditionLog(label), time.time() + args.seconds
    while time.time() < end:
        ok, frame = cap.read()
        if not ok:
            continue
        face = _measure(frame, detector, embed, entry, log)
        if args.preview:
            sim = float(log.vectors[-1] @ reference) if face is not None and reference is not None else None
            color = PASS if sim is not None and sim >= args.threshold else RECORDING
            _show(frame, face, [f"MEREKAM: {label}", *_face_info(face, sim, args.threshold)], color)
    _beep(2)
    return log


def _template(vectors: list[np.ndarray]) -> np.ndarray:
    mean = np.mean(vectors, axis=0)
    return mean / np.linalg.norm(mean)


def _record_all(cap, detector, embed, entry: dict, args) -> tuple[list[ConditionLog], np.ndarray | None]:
    logs, reference = [], None
    for label in args.conditions.split(","):
        log = _record(cap, detector, embed, entry, label.strip(), args, reference)
        logs.append(log)
        if reference is None and log.vectors:
            reference = _template(log.vectors)
    return logs, reference


def _median(values: list[float]) -> float:
    return float(np.median(values)) if values else 0.0


def _summary(log: ConditionLog, reference: np.ndarray, threshold: float) -> dict:
    similarity = [float(v @ reference) for v in log.vectors]
    return {
        "condition": log.label,
        "frames": log.frames,
        "detected": len(log.vectors) / max(log.frames, 1),
        "face_width_px": _median(log.widths),
        "interocular_px": _median(log.interocular),
        "det_score": _median(log.det_scores),
        "similarity_median": _median(similarity),
        "similarity_min": min(similarity) if similarity else 0.0,
        "frames_over_threshold": metrics.share_at_or_above(similarity, threshold),
        "det_ms": vars(summarize(log.det_ms)) if log.det_ms else {},
        "embed_ms": vars(summarize(log.embed_ms)) if log.embed_ms else {},
    }


def _print(rows: list[dict], size: tuple[int, int], threshold: float) -> None:
    print(f"\nFrame {size[0]}x{size[1]} | ambang {threshold} | kondisi pertama = acuan pendaftaran")
    print(
        f"{'kondisi':18} {'frame':>5} {'wajah%':>6} {'lebar':>6} {'mata':>5} {'skorDet':>7} "
        f"{'mirip med':>9} {'min':>6} {'>=ambang':>8} {'det p95':>7} {'emb p95':>7}"
    )
    for r in rows:
        det, emb = r["det_ms"].get("p95_ms", 0.0), r["embed_ms"].get("p95_ms", 0.0)
        print(
            f"{r['condition'][:18]:18} {r['frames']:5d} {r['detected']:6.0%} {r['face_width_px']:6.0f} "
            f"{r['interocular_px']:5.0f} {r['det_score']:7.2f} {r['similarity_median']:9.3f} "
            f"{r['similarity_min']:6.3f} {r['frames_over_threshold']:8.0%} {det:7.1f} {emb:7.1f}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--size", default="1280x720", help="resolusi yang diminta, mis. 1920x1080")
    parser.add_argument("--conditions", default=DEFAULT_CONDITIONS, help="dipisah koma; yang pertama = acuan")
    parser.add_argument("--seconds", type=float, default=6.0, help="lama rekam per kondisi")
    parser.add_argument("--pause", type=float, default=8.0, help="hitung mundur sebelum tiap kondisi")
    parser.add_argument("--first-pause", type=float, help="hitung mundur kondisi pertama (bawaan = --pause)")
    parser.add_argument("--model", default="intel_0095")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--no-preview", dest="preview", action="store_false", help="tanpa jendela pratinjau")
    parser.add_argument("--out", type=Path, help="simpan ringkasan angka (JSON, tanpa gambar/embedding)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    catalog = load_catalog(CATALOG)
    entry = next(e for e in catalog["recognizers"] if e["name"] == args.model)
    width, height = (int(v) for v in args.size.lower().split("x"))
    cap = _open_camera(args.camera, width, height)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    detector, embed = load_detector(catalog, *size), load_recognizer(entry)
    try:
        logs, reference = _record_all(cap, detector, embed, entry, args)
    finally:
        cap.release()
        cv2.destroyAllWindows()
    if reference is None or not logs[0].vectors:
        sys.exit("Kondisi acuan tanpa wajah terdeteksi: tidak ada pembanding.")
    rows = [_summary(log, reference, args.threshold) for log in logs]
    _print(rows, size, args.threshold)
    if args.out:
        args.out.write_text(json.dumps({"size": size, "threshold": args.threshold, "rows": rows}, indent=2), "utf-8")


if __name__ == "__main__":
    main()
