"""Metrik akurasi FR (T34m langkah 3a): protokol pasangan LFW, ambang, FAR/FRR, align."""

import sys
from pathlib import Path

import numpy as np
import pytest

from tools.fr_eval import metrics

# runtimes.py mengimpor `stats` sebagai modul skrip (dijalankan dari tools/fr_eval)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "fr_eval"))
import runtimes  # noqa: E402

PAIRS_TXT = """2 2
Ana 1 2
Budi 1 3
Ana 1 Budi 2
Cici 4 Dedi 1
Eka 2 3
Fani 1 2
Eka 1 Fani 1
Gita 3 Hadi 2
"""


def test_baca_pairs_lfw():
    pairs = metrics.parse_pairs(PAIRS_TXT)
    assert len(pairs) == 8
    assert pairs[0] == metrics.Pair("Ana/Ana_0001.jpg", "Ana/Ana_0002.jpg", True, 0)
    assert pairs[3] == metrics.Pair("Cici/Cici_0004.jpg", "Dedi/Dedi_0001.jpg", False, 0)
    assert [p.fold for p in pairs] == [0, 0, 0, 0, 1, 1, 1, 1]


def test_pairs_tidak_lengkap_ditolak():
    with pytest.raises(ValueError):
        metrics.parse_pairs(PAIRS_TXT.rsplit("\n", 2)[0])


def test_ambang_terbaik_memisahkan_sempurna():
    scores = np.array([0.1, 0.2, 0.35, 0.6, 0.7, 0.9])
    same = np.array([False, False, False, True, True, True])
    threshold = metrics.best_threshold(scores, same)
    assert threshold == pytest.approx(0.475), "di tengah celah 0,35 .. 0,6"
    assert metrics.accuracy(scores, same, threshold) == 1.0


def test_akurasi_10fold_ambang_dari_fold_lain():
    # Fold 1 hanya bisa benar bila ambangnya diambil dari fold 0 (bukan dari dirinya sendiri)
    scores = np.array([0.2, 0.8, 0.3, 0.7])
    same = np.array([False, True, False, True])
    mean, std = metrics.tenfold_accuracy(scores, same, np.array([0, 0, 1, 1]))
    assert mean == 1.0 and std == 0.0


def test_ambang_pada_far_dan_frr():
    rng = np.random.default_rng(0)
    impostor = metrics.score_histogram(rng.uniform(-0.2, 0.4, 100_000))
    genuine = metrics.score_histogram(np.concatenate([rng.uniform(0.5, 0.9, 950), rng.uniform(0.0, 0.3, 50)]))
    threshold = metrics.threshold_at_far(impostor, 1e-3)
    assert metrics.rate_at(impostor, threshold) <= 1e-3
    # ambang satu bin lebih rendah sudah melewati target: ambang yang dipilih adalah yang terendah
    assert metrics.rate_at(impostor, threshold - 2 / metrics.SCORE_BINS) > 1e-3
    assert 0.39 < threshold < 0.4
    assert 1 - metrics.rate_at(genuine, threshold) == pytest.approx(0.05)


def test_far_mustahil_ditolak():
    with pytest.raises(ValueError):
        metrics.threshold_at_far(metrics.score_histogram(np.ones(10)), 0.0)


def test_align_memetakan_landmark_ke_templat():
    template = runtimes.template_points("arcface", 112)
    # Wajah buatan: landmark = templat x2 + geser; align harus mengembalikannya ke templat
    landmarks = template * 2 + np.array([40, 30], np.float32)
    image = np.zeros((400, 400, 3), np.uint8)
    for x, y in landmarks.astype(int):
        image[y - 1 : y + 2, x - 1 : x + 2] = 255
    crop = runtimes.align_face(image, landmarks, "arcface", 112)
    for x, y in template.round().astype(int):
        assert crop[y, x].max() > 0, (x, y)


def test_transformasi_kemiripan_memakai_semua_titik():
    rng = np.random.default_rng(1)
    src = rng.uniform(50, 200, (5, 2))
    angle, scale, shift = 0.3, 0.7, np.array([12.0, -5.0])
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    dst = scale * src @ rot.T + shift
    matrix = runtimes.similarity_transform(src, dst)
    assert np.allclose(matrix, np.hstack([scale * rot, shift[:, None]]))
    # Satu titik melenceng: kuadrat terkecil membagi galat ke semua titik (RANSAC akan membuangnya)
    noisy = dst.copy()
    noisy[4] += 6.0
    moved = runtimes.similarity_transform(src, noisy)
    projected = src @ moved[:, :2].T + moved[:, 2]
    assert 0 < np.abs(projected[:4] - dst[:4]).max() < 6.0


def test_templat_omz_untuk_potongan_persegi():
    points = runtimes.template_points("omz", 128)
    assert points.shape == (5, 2) and points[:, 0].max() < 128 and points[:, 1].max() < 128
    assert points[0, 0] < points[1, 0], "mata pertama di kiri gambar (urutan YuNet)"


def test_pembagian_open_set():
    # A,B,C punya 4 foto; D,E,F 1 foto. Daftar dengan 3 foto -> yang memenuhi: A,B,C; separuh (1) jadi pekerja
    people = ["A"] * 4 + ["B"] * 4 + ["C"] * 4 + ["D", "E", "F"]
    split = metrics.split_open_set(people, enroll_photos=3, distractors=2, seed=0)
    assert len(split.enrolled) == 3, "1 pekerja + 2 pengisi galeri"
    assert [len(e) for e in split.enrolled] == [3, 1, 1]
    worker = people[split.enrolled[0][0]]
    assert [people[i] for i in split.mated] == [worker] and split.mated_identity.tolist() == [0]
    fillers = {people[e[0]] for e in split.enrolled[1:]}
    strangers = {people[i] for i in split.non_mated}
    assert worker not in strangers and not fillers & strangers
    assert len(split.non_mated) + len(split.mated) + sum(len(e) for e in split.enrolled) <= len(people)


def test_identifikasi_dan_tingkat_open_set():
    gallery = np.eye(3)
    probes = np.array([[0.9, 0.1, 0.0], [0.1, 0.8, 0.0], [0.0, 0.6, 0.5]])
    best, score = metrics.identify(probes, gallery)
    assert best.tolist() == [0, 1, 1] and np.allclose(score, [0.9, 0.8, 0.6])
    # probe ke-3 milik orang 2 tetapi lebih mirip orang 1 -> salah nama bila diterima
    strangers = np.array([0.3, 0.7])
    rates = metrics.open_set_rates(best, score, np.array([0, 1, 2]), strangers, threshold=0.5)
    assert rates == {"fpir": 0.5, "wrong_name": pytest.approx(1 / 3), "fnir": pytest.approx(1 / 3)}
    strict = metrics.open_set_rates(best, score, np.array([0, 1, 2]), strangers, threshold=0.75)
    assert strict == {"fpir": 0.0, "wrong_name": 0.0, "fnir": pytest.approx(1 / 3)}


def test_templat_galeri_rata_rata_ternormalisasi():
    emb = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
    templates = metrics.gallery_templates(emb, [np.array([0, 1]), np.array([2])])
    assert np.allclose(templates, [[2**-0.5, 2**-0.5], [1.0, 0.0]])


def test_jarak_antar_mata_dan_porsi_lolos_ambang():
    points = np.array([[10.0, 20.0], [40.0, 60.0], [0, 0], [0, 0], [0, 0]])
    assert metrics.interocular_px(points) == 50.0
    assert metrics.share_at_or_above([0.4, 0.55, 0.7, 0.2], 0.55) == 0.5
    assert metrics.share_at_or_above([], 0.55) == 0.0
