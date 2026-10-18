"""Uji 1:N pada LFW: pekerja terdaftar vs orang asing (T34m langkah 3a). Env `fr_eval`.

Gerbang tidak membandingkan dua foto (1:1) tetapi mencari wajah di seluruh daftar
pekerja (1:N). Orang asing dibandingkan dengan SEMUA pekerja, jadi peluangnya
"mirip seseorang" naik seiring jumlah pekerja: ambang 1:1 (FAR 0,1%) tidak cukup.

Diukur:
1. Ketepatan: FPIR (orang asing diberi nama), salah nama (pekerja diberi nama orang
   lain), FNIR (pekerja tidak dikenali dengan benar), pada beberapa ukuran galeri.
2. Waktu dari foto sampai keputusan (deteksi + align + embedding + cari), terpisah
   untuk pekerja terdaftar dan orang asing.

    python tools/fr_eval/eval_openset.py --only sface intel_0095 sface_int8
"""

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

import metrics
from eval_lfw import LFW_SIZE, all_pair_histograms, capped_subset, center_face, detect_landmarks, embed_all
from eval_lfw import list_images, lfw_root
from runtimes import align_face, load_detector, load_recognizer
from stats import CATALOG, load_catalog, summarize

TARGET_RATE = 1e-3  # kriteria T34m: salah terima <= 0,1% (di sini: orang asing diberi nama)
ENROLL_PHOTOS = 3  # rancangan T34: admin mendaftarkan 3-5 foto per pekerja
SEED = 34


def _people(names: list[str]) -> list[str]:
    return [n.split("/")[0] for n in names]


def _one_to_one_threshold(names: list[str], emb: np.ndarray) -> float:
    keep, labels = capped_subset(names, 20)
    _, impostor = all_pair_histograms(emb[keep], labels)
    return metrics.threshold_at_far(impostor, TARGET_RATE)


def _accuracy(names: list[str], emb: np.ndarray, distractors: int, thr_1to1: float) -> dict:
    split = metrics.split_open_set(_people(names), ENROLL_PHOTOS, distractors, SEED)
    gallery = metrics.gallery_templates(emb, split.enrolled)
    mated_best, mated_score = metrics.identify(emb[split.mated], gallery)
    _, stranger_score = metrics.identify(emb[split.non_mated], gallery)
    thr_1toN = metrics.threshold_at_far(metrics.score_histogram(stranger_score), TARGET_RATE)
    rates = {
        name: metrics.open_set_rates(mated_best, mated_score, split.mated_identity, stranger_score, thr)
        for name, thr in (("ambang_1to1", thr_1to1), ("ambang_1toN", thr_1toN))
    }
    return {
        "gallery": len(gallery),
        "mated_probes": len(split.mated),
        "strangers": len(split.non_mated),
        "threshold_1to1": thr_1to1,
        "threshold_1toN": thr_1toN,
        **rates,
    }


def _probe_once(image: np.ndarray, detector, embed, entry: dict, gallery: np.ndarray) -> list[float]:
    """Satu foto -> keputusan, seperti di gerbang. Kembali: waktu tiap tahap (ms)."""
    t0 = time.perf_counter()
    points = center_face(detector.detect(image)[1])
    t1 = time.perf_counter()
    if points is None:
        return [(t1 - t0) * 1000, 0.0, 0.0]
    vector = np.asarray(embed(align_face(image, points, entry["align"], entry["input"])), np.float32).ravel()
    t2 = time.perf_counter()
    metrics.identify((vector / np.linalg.norm(vector))[None], gallery)
    t3 = time.perf_counter()
    return [(t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000]


def _latency(entry: dict, root: Path, names: list[str], emb: np.ndarray, distractors: int, samples: int) -> dict:
    split = metrics.split_open_set(_people(names), ENROLL_PHOTOS, distractors, SEED)
    gallery = metrics.gallery_templates(emb, split.enrolled)
    detector = load_detector(load_catalog(CATALOG), LFW_SIZE, LFW_SIZE)
    embed = load_recognizer(entry)
    rng = np.random.default_rng(SEED)
    out = {}
    for group, pool in (("terdaftar", split.mated), ("asing", split.non_mated)):
        images = [cv2.imread(str(root / names[i])) for i in rng.choice(pool, samples, replace=False)]
        for image in images[:10]:  # pemanasan
            _probe_once(image, detector, embed, entry, gallery)
        stages = np.array([_probe_once(image, detector, embed, entry, gallery) for image in images])
        out[group] = {
            stage: vars(summarize(stages[:, k].tolist())) for k, stage in enumerate(("deteksi", "embedding", "cari"))
        }
        out[group]["total"] = vars(summarize(stages.sum(axis=1).tolist()))
    return out


def _evaluate(entry: dict, root: Path, landmarks: dict, args) -> dict:
    names, emb, _ = embed_all(entry, root, landmarks)
    thr = _one_to_one_threshold(names, emb)
    accuracy = [_accuracy(names, emb, d, thr) for d in args.distractors]
    latency = _latency(entry, root, names, emb, max(args.distractors), args.samples)
    return {"name": entry["name"], "accuracy": accuracy, "latency": latency}


def _print(results: list[dict]) -> None:
    for r in results:
        print(f"\n== {r['name']} ==")
        for a in r["accuracy"]:
            one, many = a["ambang_1to1"], a["ambang_1toN"]
            print(f"galeri {a['gallery']:5d} pekerja | {a['mated_probes']} kedatangan, {a['strangers']} orang asing")
            print(
                f"  ambang 1:1 {a['threshold_1to1']:.4f}: asing diberi nama {one['fpir']:.2%}, "
                f"salah nama {one['wrong_name']:.2%}, tak dikenali {one['fnir']:.2%}"
            )
            print(
                f"  ambang 1:N {a['threshold_1toN']:.4f}: asing diberi nama {many['fpir']:.2%}, "
                f"salah nama {many['wrong_name']:.2%}, tak dikenali {many['fnir']:.2%}"
            )
        for group, stages in r["latency"].items():
            parts = ", ".join(f"{k} p50 {v['p50_ms']:.1f}/p95 {v['p95_ms']:.1f}" for k, v in stages.items())
            print(f"  waktu {group:9}: {parts} ms")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="nama kandidat (bawaan: semua yang punya templat align)")
    parser.add_argument(
        "--distractors",
        type=int,
        nargs="*",
        default=[0, 3000],
        help="orang tambahan di galeri (1 foto) untuk memperbesar daftar pekerja",
    )
    parser.add_argument("--samples", type=int, default=300, help="foto per kelompok untuk uji waktu")
    parser.add_argument("--out", type=Path, help="simpan hasil JSON")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    catalog = load_catalog(CATALOG)
    root = lfw_root()
    landmarks = detect_landmarks(root, list_images(root), catalog, 0.6)
    entries = [e for e in catalog["recognizers"] if "align" in e and (not args.only or e["name"] in args.only)]
    results = [_evaluate(entry, root, landmarks, args) for entry in entries]
    _print(results)
    if args.out:
        args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
