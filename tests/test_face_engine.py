"""Mesin FR gerbang (T34b2): pilihan wajah pendaftaran, model asli, keutuhan berkas model."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from backend import face_engine
from backend.config import cfg

ROOT = Path(__file__).resolve().parents[1]


def _row(x=100, eye_gap=40.0, score=0.9):
    """Satu baris keluaran YuNet: kotak, 5 landmark (mata berjarak `eye_gap`), skor."""
    eyes = [x + 20, 120, x + 20 + eye_gap, 120]
    rest = [x + 40, 140, x + 25, 160, x + 55, 160]
    return [x, 100, 80, 100, *eyes, *rest, score]


def _detections(*rows):
    return face_engine.parse_detections(np.array(rows, dtype=np.float32), cfg.FACE_DET_SCORE_MIN)


def test_deteksi_di_bawah_skor_minimal_dibuang():
    found = _detections(_row(score=0.9), _row(x=300, score=0.3))
    assert len(found) == 1 and found[0].score == pytest.approx(0.9)
    assert found[0].landmarks.shape == (5, 2) and found[0].interocular_px == pytest.approx(40.0)
    assert face_engine.parse_detections(None, 0.6) == []


def test_satu_wajah_besar_dipakai_wajah_kecil_di_latar_diabaikan():
    chosen = face_engine.pick_enrollment_face(_detections(_row(eye_gap=40), _row(x=400, eye_gap=10)), 24)
    assert chosen.interocular_px == pytest.approx(40.0)


@pytest.mark.parametrize(
    "rows, code",
    [
        ((), "no_face"),
        ((_row(eye_gap=40), _row(x=400, eye_gap=35)), "multiple_faces"),
        ((_row(eye_gap=18),), "face_too_small"),
    ],
)
def test_foto_pendaftaran_tidak_layak_ditolak(rows, code):
    with pytest.raises(face_engine.FaceEngineError) as e:
        face_engine.pick_enrollment_face(_detections(*rows) if rows else [], 24)
    assert e.value.code == code and e.value.message


def test_pesan_wajah_kecil_menyebut_ukuran():
    with pytest.raises(face_engine.FaceEngineError) as e:
        face_engine.pick_enrollment_face(_detections(_row(eye_gap=18)), 24)
    assert "18" in e.value.message and "24" in e.value.message


def test_kualitas_untuk_admin():
    assert _detections(_row(eye_gap=40, score=0.91))[0].quality() == {
        "face_width_px": 80,
        "interocular_px": 40.0,
        "det_score": pytest.approx(0.91, abs=1e-3),
    }


def test_berkas_model_utuh_sesuai_hash_yang_diuji():
    """Bobot yang ikut repo harus persis yang diuji di T34m (hash dipatok di tools/fr_eval/models.json)."""
    catalog = json.loads((ROOT / "tools/fr_eval/models.json").read_text(encoding="utf-8"))
    entries = [catalog["detector"], *catalog["recognizers"]]
    pinned = {f["url"].rsplit("/", 1)[-1]: f["sha256"] for e in entries for f in e["files"]}
    for name in (cfg.FACE_DETECTOR_FILE, cfg.FACE_RECOGNIZER_FILE, cfg.FACE_RECOGNIZER_FILE.replace(".xml", ".bin")):
        digest = hashlib.sha256((cfg.FACE_MODEL_DIR / name).read_bytes()).hexdigest()
        assert digest == pinned[name], name
    licenses = {p.name for p in cfg.FACE_MODEL_DIR.glob("LICENSE-*")}
    assert licenses == {"LICENSE-yunet-MIT.txt", "LICENSE-open_model_zoo-Apache-2.0.txt"}


@pytest.fixture(scope="module")
def engine():
    pytest.importorskip("openvino")
    return face_engine.FaceEngine()


def test_frame_tanpa_wajah_ditolak_model_asli(engine):
    frame = np.full((cfg.ENROLLMENT_MIN_FRAME_HEIGHT, 1920, 3), 128, np.uint8)
    assert engine.detect(frame) == []
    with pytest.raises(face_engine.FaceEngineError) as e:
        engine.enrollment_sample(frame)
    assert e.value.code == "no_face"


def test_embedding_model_asli_256_dimensi_ternormalisasi(engine):
    detection = _detections(_row(eye_gap=40))[0]
    frame = np.random.default_rng(0).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    _, request = engine._models()
    vector = engine._embed(request, frame, detection)
    assert vector.shape == (256,) and vector.dtype == np.float32
    assert np.linalg.norm(vector) == pytest.approx(1.0, abs=1e-5)
    assert np.allclose(vector, engine._embed(request, frame, detection)), "deterministik"


# --- Pendaftaran terpandu (T76) ---


def test_foto_terlalu_dekat_ditolak_dengan_ukurannya():
    """Uji nyata 19-10: foto daftar 200-246 px tidak cocok dengan wajah ±30 px di jalur."""
    with pytest.raises(face_engine.FaceEngineError) as e:
        face_engine.pick_enrollment_face(_detections(_row(eye_gap=200)), 24, 60)
    assert e.value.code == "face_too_close" and "200" in e.value.message and "60" in e.value.message
    assert face_engine.pick_enrollment_face(_detections(_row(eye_gap=60)), 24, 60).interocular_px == 60


@pytest.mark.parametrize(
    "rows, fit, measured",
    [
        ((), "no_face", None),
        ((_row(eye_gap=18),), "too_far", 18.0),
        ((_row(eye_gap=40),), "ok", 40.0),
        ((_row(eye_gap=120),), "too_close", 120.0),
        ((_row(eye_gap=40), _row(x=400, eye_gap=35)), "multiple_faces", 40.0),
    ],
)
def test_indikator_jarak_sama_dengan_aturan_foto(rows, fit, measured):
    detections = _detections(*rows) if rows else []
    assert face_engine.enrollment_fit(detections, 1080) == {
        "fit": fit,
        "faces": len(detections),
        "interocular_px": measured,
    }


def test_batas_maksimal_sebanding_resolusi(monkeypatch):
    """Wajah di jalur sebanding resolusi: batas piksel tetap lolos foto dekat di resolusi lain."""
    monkeypatch.setattr(cfg, "ENROLLMENT_MIN_FRAME_HEIGHT", 720)
    low_min, low_max = face_engine.enrollment_bounds(720)
    high_min, high_max = face_engine.enrollment_bounds(1440)
    assert low_min == high_min == cfg.FACE_MIN_INTEROCULAR_PX, "mutu embedding tetap piksel"
    assert high_max == pytest.approx(2 * low_max)


def test_kamera_resolusi_rendah_ditolak():
    """Uji nyata 19-10: kamera 720p, foto 48-59 px lolos padahal wajah di jalur ±17-22 px."""
    height = cfg.ENROLLMENT_MIN_FRAME_HEIGHT - 360
    with pytest.raises(face_engine.FaceEngineError) as e:
        face_engine.enrollment_bounds(height)
    assert e.value.code == "camera_low_resolution" and str(height) in e.value.message
    fit = face_engine.enrollment_fit(_detections(_row(eye_gap=40)), height)
    assert fit == {"fit": "low_resolution", "faces": 1, "interocular_px": 40.0}


def test_foto_dekat_di_1080p_ditolak():
    """Jarak foto uji 19-10 (48-59 px di 720p ~ 72-88 px di 1080p) melewati batas di 1080p."""
    _, maximum = face_engine.enrollment_bounds(1080)
    assert 33 < maximum < 72, "jarak di jalur (26-33 px) lolos, foto dekat tidak"
