"""Uji kecepatan kandidat FR di CPU (T34m, langkah 2). Jalankan di env `fr_eval`.

Waktu inferensi CNN tidak bergantung isi gambar, jadi uji ini memakai gambar
acak berbenih: tidak ada foto orang. Akurasi diuji terpisah (langkah 3).

Yang diukur per kandidat: waktu muat model, embedding p50/p95 pada potongan
wajah ter-align (ukuran input model), dan estimasi FR per sesi =
percobaan x (deteksi YuNet + align + embedding) + pencarian galeri.

    python tools/fr_eval/fetch_models.py
    python tools/fr_eval/bench_speed.py --threads 0 --threads 2
"""

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from runtimes import align_face, entry_paths, load_detector, load_recognizer
from stats import CATALOG, load_catalog, meets_budget, session_ms, summarize

BUDGET_MS = 50.0  # kriteria T34m yang disetujui: FR <= 50 ms per sesi di CPU
FRAME_SIZES = ((1280, 720), (640, 640))  # frame penuh gerbang vs potongan badan atas
GALLERY_SIZES = (1_000, 10_000)
SEED = 34


def _time_ms(fn: Callable[[], object], warmup: int, runs: int) -> list[float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return samples


def _noise(rng: np.random.Generator, width: int, height: int) -> np.ndarray:
    return rng.integers(0, 256, (height, width, 3), dtype=np.uint8)


def _bench_detector(catalog: dict, rng: np.random.Generator, args) -> dict[str, list[float]]:
    out = {}
    for width, height in FRAME_SIZES:
        detector = load_detector(catalog, width, height)
        frame = _noise(rng, width, height)
        out[f"{width}x{height}"] = _time_ms(lambda: detector.detect(frame), args.warmup, args.runs)
    return out


def _bench_align(rng: np.random.Generator, args) -> list[float]:
    """Align 5 titik (warpAffine ke 112x112) setara cara SFace/ArcFace; dlib memakai chip sendiri."""
    frame = _noise(rng, *FRAME_SIZES[0])
    landmarks = np.float32([[600, 300], [680, 300], [640, 340], [610, 380], [670, 380]])
    return _time_ms(lambda: align_face(frame, landmarks, "arcface", 112), args.warmup, args.runs)


def _bench_recognizer(entry: dict, rng: np.random.Generator, args, threads: int) -> dict:
    paths = entry_paths(entry)
    start = time.perf_counter()
    embed = load_recognizer(entry, threads)
    load_ms = (time.perf_counter() - start) * 1000
    crop = _noise(rng, entry["input"], entry["input"])
    dim = int(np.asarray(embed(crop)).size)
    return {
        "name": entry["name"],
        "load_ms": load_ms,
        "size_mb": sum(p.stat().st_size for p in paths) / 1e6,
        "dim": dim,
        "embed": summarize(_time_ms(lambda: embed(crop), args.warmup, args.runs)),
    }


def _bench_search(dim: int, size: int, rng: np.random.Generator, args) -> float:
    gallery = rng.standard_normal((size, dim)).astype(np.float32)
    gallery /= np.linalg.norm(gallery, axis=1, keepdims=True)
    probe = gallery[size // 2].copy()
    return summarize(_time_ms(lambda: int(np.argmax(gallery @ probe)), args.warmup, args.runs)).p95_ms


def _row(result: dict, detect_p95: float, align_p95: float, search_p95: float, attempts: int) -> dict:
    total = session_ms(detect_p95 + align_p95, result["embed"].p95_ms, search_p95, attempts)
    return {
        **result,
        "embed": vars(result["embed"]),
        "search_p95_ms": search_p95,
        "session_p95_ms": total,
        "meets_budget": meets_budget(total, BUDGET_MS),
    }


def _run(threads: int, args) -> dict:
    cv2.setNumThreads(threads if threads else -1)
    rng = np.random.default_rng(SEED)
    catalog = load_catalog(CATALOG)
    detect = {k: summarize(v) for k, v in _bench_detector(catalog, rng, args).items()}
    align = summarize(_bench_align(rng, args))
    detect_p95 = detect[args.session_frame].p95_ms
    rows = []
    for entry in catalog["recognizers"]:
        if args.only and entry["name"] not in args.only:
            continue
        result = _bench_recognizer(entry, rng, args, threads)
        search = _bench_search(result["dim"], max(GALLERY_SIZES), rng, args)
        rows.append(_row(result, detect_p95, align.p95_ms, search, args.attempts))
    return {
        "threads": threads,
        "detector": {k: vars(v) for k, v in detect.items()},
        "align": vars(align),
        "recognizers": rows,
    }


def _print(report: dict, args) -> None:
    print(
        f"\n== threads={report['threads'] or 'bawaan'} | percobaan/sesi={args.attempts} "
        f"| deteksi pada {args.session_frame} | anggaran {BUDGET_MS:.0f} ms =="
    )
    for size, t in report["detector"].items():
        print(f"YuNet {size:>9}: p50 {t['p50_ms']:6.2f}  p95 {t['p95_ms']:6.2f} ms")
    print(f"align 5 titik  : p50 {report['align']['p50_ms']:6.2f}  p95 {report['align']['p95_ms']:6.2f} ms")
    print(
        f"{'kandidat':12} {'MB':>6} {'dim':>4} {'muat ms':>8} {'emb p50':>8} {'emb p95':>8} "
        f"{'cari p95':>8} {'sesi p95':>9}  lolos"
    )
    for r in report["recognizers"]:
        print(
            f"{r['name']:12} {r['size_mb']:6.1f} {r['dim']:4d} {r['load_ms']:8.0f} {r['embed']['p50_ms']:8.2f} "
            f"{r['embed']['p95_ms']:8.2f} {r['search_p95_ms']:8.3f} {r['session_p95_ms']:9.2f}  "
            f"{'ya' if r['meets_budget'] else 'TIDAK'}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--threads", type=int, action="append", help="0 = bawaan runtime; boleh diulang")
    parser.add_argument("--runs", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--attempts", type=int, default=1, help="frame yang dicoba per sesi")
    parser.add_argument("--session-frame", default="640x640", choices=[f"{w}x{h}" for w, h in FRAME_SIZES])
    parser.add_argument("--only", nargs="*", help="nama kandidat (bawaan: semua)")
    parser.add_argument("--out", type=Path, help="simpan hasil JSON")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    reports = [_run(threads, args) for threads in (args.threads or [0])]
    for report in reports:
        _print(report, args)
    if args.out:
        args.out.write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
