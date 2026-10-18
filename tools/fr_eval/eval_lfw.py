"""Uji akurasi kandidat FR pada LFW (T34m langkah 3a). Jalankan di env `fr_eval`.

LFW = foto berita tokoh publik, pengganti sementara foto relawan untuk MEMILIH
model; uji nyata di kamera gerbang tetap wajib setelahnya. Dataset hanya di
cache luar repo (tidak di-commit/diunggah) dan hanya untuk evaluasi.

1. Akurasi 10-fold protokol resmi (pairs.txt): pembanding angka publikasi, untuk
   memastikan align & praproses kita benar.
2. FAR/FRR dari SEMUA pasangan (dibatasi N foto per orang supaya beberapa tokoh
   dengan ratusan foto tidak mendominasi): ambang pada FAR target, FRR di ambang itu.

    python tools/fr_eval/fetch_models.py
    python tools/fr_eval/eval_lfw.py --only sface intel_0095 sface_int8
"""

import argparse
import hashlib
import json
import tarfile
import time
from pathlib import Path

import cv2
import numpy as np

import metrics
import runtimes
from runtimes import align_face, load_detector, load_recognizer
from stats import CATALOG, datasets_dir, load_catalog

TARGET_FARS = (1e-3, 1e-4)  # kriteria T34m: FAR <= 0,1%; 0,01% sebagai pembanding lebih ketat
MAX_FRR = 0.05  # kriteria T34m: FRR <= 5% (tanpa masker)
LFW_SIZE = 250  # semua foto LFW 250x250, wajah di tengah
CHUNK_ROWS = 1024


def lfw_root() -> Path:
    base = datasets_dir() / "lfw"
    images = base / "lfw"
    if not images.is_dir():
        with tarfile.open(base / "lfw.tgz") as archive:
            archive.extractall(base, filter="data")
    return images


def list_images(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.glob("*/*.jpg"))


def center_face(faces: np.ndarray | None) -> np.ndarray | None:
    """Foto LFW bisa memuat beberapa wajah; tokoh yang dilabeli selalu di tengah."""
    if faces is None or len(faces) == 0:
        return None
    centers = faces[:, :2] + faces[:, 2:4] / 2
    nearest = np.argmin(np.linalg.norm(centers - LFW_SIZE / 2, axis=1))
    return faces[nearest, 4:14].reshape(5, 2)


def detect_landmarks(root: Path, images: list[str], catalog: dict, score: float) -> dict[str, np.ndarray]:
    cache = root.parent / f"landmarks_yunet_{score}.npz"
    if cache.is_file():
        data = np.load(cache)
        return dict(zip(data["images"].tolist(), data["points"], strict=True))
    detector = load_detector(catalog, LFW_SIZE, LFW_SIZE, score)
    found = {}
    for rel in images:
        image = cv2.imread(str(root / rel))
        if image is None or image.shape[:2] != (LFW_SIZE, LFW_SIZE):
            continue
        points = center_face(detector.detect(image)[1])
        if points is not None:
            found[rel] = points
    np.savez(cache, images=np.array(list(found)), points=np.array(list(found.values())))
    return found


def _embedding_cache(entry: dict, root: Path) -> Path:
    """Kunci cache = kode align/praproses + entri model: berubah salah satunya, hitung ulang."""
    digest = hashlib.sha256(Path(runtimes.__file__).read_bytes() + json.dumps(entry, sort_keys=True).encode())
    return root.parent / f"embeddings_{entry['name']}_{digest.hexdigest()[:12]}.npz"


def embed_all(entry: dict, root: Path, landmarks: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray, float]:
    cache = _embedding_cache(entry, root)
    if cache.is_file():
        data = np.load(cache)
        return data["names"].tolist(), data["emb"], float(data["ms"])
    names, emb, per_image_ms = _embed_uncached(entry, root, landmarks)
    np.savez(cache, names=np.array(names), emb=emb, ms=per_image_ms)
    return names, emb, per_image_ms


def _embed_uncached(entry: dict, root: Path, landmarks: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray, float]:
    embed = load_recognizer(entry)
    names, vectors = [], []
    start = time.perf_counter()
    for rel, points in landmarks.items():
        crop = align_face(cv2.imread(str(root / rel)), points, entry["align"], entry["input"])
        vectors.append(np.asarray(embed(crop), dtype=np.float32).ravel())
        names.append(rel)
    per_image_ms = (time.perf_counter() - start) * 1000 / max(len(names), 1)
    matrix = np.stack(vectors)
    return names, matrix / np.linalg.norm(matrix, axis=1, keepdims=True), per_image_ms


def _pair_scores(pairs: list[metrics.Pair], index: dict[str, int], emb: np.ndarray) -> tuple[np.ndarray, int]:
    """Pasangan dengan wajah tak terdeteksi diberi skor -1 (ditolak): di gerbang artinya tanpa nama."""
    scores = np.full(len(pairs), -1.0)
    for i, pair in enumerate(pairs):
        if pair.left in index and pair.right in index:
            scores[i] = float(emb[index[pair.left]] @ emb[index[pair.right]])
    return scores, int(np.sum(scores == -1.0))


def capped_subset(names: list[str], cap: int) -> tuple[np.ndarray, np.ndarray]:
    """Indeks foto (maks `cap` per orang, urut nama berkas) dan label orangnya."""
    taken: dict[str, int] = {}
    keep, labels = [], []
    for i, rel in enumerate(names):
        person = rel.split("/")[0]
        if taken.get(person, 0) < cap:
            taken[person] = taken.get(person, 0) + 1
            keep.append(i)
            labels.append(person)
    _, label_ids = np.unique(labels, return_inverse=True)
    return np.array(keep), label_ids


def all_pair_histograms(emb: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    genuine = np.zeros(metrics.SCORE_BINS, dtype=np.int64)
    impostor = np.zeros(metrics.SCORE_BINS, dtype=np.int64)
    for start in range(0, len(emb), CHUNK_ROWS):
        rows = slice(start, start + CHUNK_ROWS)
        scores = emb[rows] @ emb.T
        upper = np.arange(len(emb))[None, :] > np.arange(start, start + scores.shape[0])[:, None]
        same = labels[rows][:, None] == labels[None, :]
        genuine += metrics.score_histogram(scores[upper & same])
        impostor += metrics.score_histogram(scores[upper & ~same])
    return genuine, impostor


def _evaluate(entry: dict, root: Path, landmarks: dict, pairs: list[metrics.Pair], cap: int) -> dict:
    names, emb, per_image_ms = embed_all(entry, root, landmarks)
    scores, missing = _pair_scores(pairs, {n: i for i, n in enumerate(names)}, emb)
    same = np.array([p.same for p in pairs])
    acc, acc_std = metrics.tenfold_accuracy(scores, same, np.array([p.fold for p in pairs]))
    keep, labels = capped_subset(names, cap)
    genuine, impostor = all_pair_histograms(emb[keep], labels)
    at_far = {}
    for far in TARGET_FARS:
        threshold = metrics.threshold_at_far(impostor, far)
        at_far[str(far)] = {
            "threshold": threshold,
            "far": metrics.rate_at(impostor, threshold),
            "frr": 1.0 - metrics.rate_at(genuine, threshold),
        }
    return {
        "name": entry["name"],
        "embed_ms_per_image": per_image_ms,
        "lfw_accuracy": acc,
        "lfw_accuracy_std": acc_std,
        "pairs_without_face": missing,
        "images": len(keep),
        "genuine_pairs": int(genuine.sum()),
        "impostor_pairs": int(impostor.sum()),
        "at_far": at_far,
    }


def _print(results: list[dict], detected: int, total: int) -> None:
    print(f"\nWajah terdeteksi YuNet: {detected}/{total} foto LFW")
    print(
        f"{'kandidat':12} {'akurasi 10-fold':>17} {'tanpa wajah':>11} {'ambang@0,1%':>11} "
        f"{'FRR@0,1%':>9} {'FRR@0,01%':>10}  lolos FRR<={MAX_FRR:.0%}"
    )
    for r in results:
        a, b = r["at_far"][str(TARGET_FARS[0])], r["at_far"][str(TARGET_FARS[1])]
        print(
            f"{r['name']:12} {r['lfw_accuracy']:10.2%} ±{r['lfw_accuracy_std']:5.2%} {r['pairs_without_face']:11d} "
            f"{a['threshold']:11.4f} {a['frr']:9.2%} {b['frr']:10.2%}  {'ya' if a['frr'] <= MAX_FRR else 'TIDAK'}"
        )
    r = results[0] if results else None
    if r:
        print(f"(pasangan semua: {r['genuine_pairs']:,} sama, {r['impostor_pairs']:,} beda, dari {r['images']:,} foto)")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="nama kandidat (bawaan: semua yang punya templat align)")
    parser.add_argument("--max-per-identity", type=int, default=20)
    parser.add_argument("--det-score", type=float, default=0.6, help="ambang skor YuNet")
    parser.add_argument("--out", type=Path, help="simpan hasil JSON")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    catalog = load_catalog(CATALOG)
    root = lfw_root()
    images = list_images(root)
    landmarks = detect_landmarks(root, images, catalog, args.det_score)
    pairs = metrics.parse_pairs((root.parent / "pairs.txt").read_text(encoding="utf-8"))
    entries = [e for e in catalog["recognizers"] if "align" in e and (not args.only or e["name"] in args.only)]
    results = []
    for entry in entries:
        print(f"menilai {entry['name']} ...", flush=True)
        results.append(_evaluate(entry, root, landmarks, pairs, args.max_per_identity))
    _print(results, len(landmarks), len(images))
    if args.out:
        args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
