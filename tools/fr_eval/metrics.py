"""Metrik akurasi FR (T34m): protokol pasangan LFW, FAR/FRR, ambang. Logika murni.

Skor = kemiripan kosinus embedding ter-normalisasi; pasangan diterima sebagai
orang yang sama bila skor >= ambang.
"""

from dataclasses import dataclass

import numpy as np

# Resolusi histogram skor kosinus [-1, 1]: 0,0001 per bin, cukup halus untuk FAR 0,1%
SCORE_BINS = 20_000


@dataclass(frozen=True)
class Pair:
    left: str
    right: str
    same: bool
    fold: int


def lfw_image(name: str, index: int) -> str:
    return f"{name}/{name}_{index:04d}.jpg"


def parse_pairs(text: str) -> list[Pair]:
    """pairs.txt LFW: baris pertama "<fold> <n>", lalu per fold n pasangan sama
    ("nama i j") disusul n pasangan beda ("nama1 i nama2 j")."""
    lines = [line.split() for line in text.strip().splitlines()]
    folds, per_fold = int(lines[0][0]), int(lines[0][1])
    pairs = []
    for i, parts in enumerate(lines[1:]):
        fold = i // (2 * per_fold)
        if len(parts) == 3:
            pairs.append(Pair(lfw_image(parts[0], int(parts[1])), lfw_image(parts[0], int(parts[2])), True, fold))
        else:
            pairs.append(Pair(lfw_image(parts[0], int(parts[1])), lfw_image(parts[2], int(parts[3])), False, fold))
    if len(pairs) != folds * 2 * per_fold:
        raise ValueError(f"pairs.txt: {len(pairs)} pasangan, harus {folds * 2 * per_fold}")
    return pairs


def best_threshold(scores: np.ndarray, same: np.ndarray) -> float:
    """Ambang dengan akurasi tertinggi, di tengah celah antara dua skor berurutan.

    Ambang tepat di sebuah skor terlalu ketat untuk fold lain: pasangan "sama"
    yang skornya sedikit lebih rendah langsung ditolak.
    """
    order = np.argsort(scores)
    s, y = scores[order], same[order]
    # Ambang di bawah s[k]: pasangan k.. diterima. Benar = beda di bawah k + sama dari k.
    diff_below = np.concatenate([[0], np.cumsum(~y)])[:-1]
    same_from = np.cumsum(y[::-1])[::-1]
    k = int(np.argmax(diff_below + same_from))
    return float(s[0] - 1e-6 if k == 0 else (s[k - 1] + s[k]) / 2)


def accuracy(scores: np.ndarray, same: np.ndarray, threshold: float) -> float:
    return float(np.mean((scores >= threshold) == same))


def tenfold_accuracy(scores: np.ndarray, same: np.ndarray, folds: np.ndarray) -> tuple[float, float]:
    """Protokol resmi LFW: ambang dipilih dari 9 fold, diuji di fold sisanya."""
    results = []
    for fold in np.unique(folds):
        test = folds == fold
        threshold = best_threshold(scores[~test], same[~test])
        results.append(accuracy(scores[test], same[test], threshold))
    return float(np.mean(results)), float(np.std(results))


def score_histogram(scores: np.ndarray) -> np.ndarray:
    index = np.clip(((scores + 1.0) / 2.0 * SCORE_BINS).astype(np.int64), 0, SCORE_BINS - 1)
    return np.bincount(index, minlength=SCORE_BINS)


def bin_threshold(index: int) -> float:
    return -1.0 + 2.0 * index / SCORE_BINS


def accept_rates(hist: np.ndarray) -> np.ndarray:
    """rates[k] = pecahan pasangan dengan skor di bin >= k (diterima pada ambang bin k)."""
    return np.cumsum(hist[::-1])[::-1] / max(int(hist.sum()), 1)


def threshold_at_far(impostor_hist: np.ndarray, target_far: float) -> float:
    """Ambang terendah dengan FAR <= target (FAR = pasangan beda orang yang diterima)."""
    below = accept_rates(impostor_hist) <= target_far
    if not below.any():
        raise ValueError(f"FAR {target_far} tidak tercapai bahkan pada ambang tertinggi")
    return bin_threshold(int(np.argmax(below)))


def rate_at(hist: np.ndarray, threshold: float) -> float:
    index = int(round((threshold + 1.0) / 2.0 * SCORE_BINS))
    return float(accept_rates(hist)[min(max(index, 0), SCORE_BINS - 1)])


@dataclass(frozen=True)
class OpenSetSplit:
    """Pembagian foto untuk uji 1:N: siapa terdaftar, siapa datang, siapa orang asing (indeks foto)."""

    enrolled: list[np.ndarray]  # per pekerja terdaftar: foto pendaftaran
    mated: np.ndarray  # foto lain pekerja terdaftar (datang ke gerbang)
    mated_identity: np.ndarray  # posisi galeri pemilik sebenarnya
    non_mated: np.ndarray  # foto orang yang tidak terdaftar


def _group_by_person(people: list[str]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for i, person in enumerate(people):
        groups.setdefault(person, []).append(i)
    return groups


def split_open_set(people: list[str], enroll_photos: int, distractors: int, seed: int) -> OpenSetSplit:
    """Separuh orang yang punya foto > `enroll_photos` didaftarkan; `distractors` orang lain ikut
    terdaftar (1 foto, memperbesar galeri) tanpa pernah datang; sisanya orang asing."""
    rng = np.random.default_rng(seed)
    groups = _group_by_person(people)
    eligible = sorted(p for p, idx in groups.items() if len(idx) > enroll_photos)
    workers = set(rng.permutation(eligible)[: len(eligible) // 2].tolist())
    others = sorted(set(groups) - workers)
    fillers = set(rng.permutation(others)[:distractors].tolist())
    enrolled, mated, identity = [], [], []
    for position, person in enumerate(sorted(workers) + sorted(fillers)):
        idx = groups[person]
        take = enroll_photos if person in workers else 1
        enrolled.append(np.array(idx[:take]))
        mated += idx[take:] if person in workers else []
        identity += [position] * (len(idx) - take) if person in workers else []
    strangers = [i for p in others if p not in fillers for i in groups[p]]
    return OpenSetSplit(enrolled, np.array(mated), np.array(identity), np.array(strangers))


def gallery_templates(emb: np.ndarray, enrolled: list[np.ndarray]) -> np.ndarray:
    """Satu templat per pekerja: rata-rata embedding foto pendaftaran, dinormalisasi."""
    templates = np.stack([emb[idx].mean(axis=0) for idx in enrolled])
    return templates / np.linalg.norm(templates, axis=1, keepdims=True)


def identify(probes: np.ndarray, gallery: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pencarian 1:N: kandidat terbaik & skornya untuk tiap probe."""
    scores = probes @ gallery.T
    best = np.argmax(scores, axis=1)
    return best, scores[np.arange(len(probes)), best]


def open_set_rates(
    mated_best: np.ndarray, mated_score: np.ndarray, truth: np.ndarray, stranger_score: np.ndarray, threshold: float
) -> dict[str, float]:
    """FPIR = orang asing diberi nama; salah nama = pekerja diberi nama orang lain;
    FNIR = pekerja tidak dikenali dengan nama yang benar (termasuk salah nama)."""
    accepted = mated_score >= threshold
    correct = accepted & (mated_best == truth)
    return {
        "fpir": float(np.mean(stranger_score >= threshold)),
        "wrong_name": float(np.mean(accepted & (mated_best != truth))),
        "fnir": float(1.0 - np.mean(correct)),
    }


def interocular_px(points: np.ndarray) -> float:
    """Jarak antar-mata (landmark 0 & 1 urutan YuNet): ukuran wajah yang tidak terpengaruh helm/rambut."""
    return float(np.linalg.norm(points[0] - points[1]))


def share_at_or_above(values: list[float], threshold: float) -> float:
    return float(np.mean(np.asarray(values) >= threshold)) if values else 0.0
