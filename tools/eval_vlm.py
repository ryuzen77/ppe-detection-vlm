"""Evaluasi akurasi & latensi VLM pada foto berlabel (T26).

Jalur masukan sama dengan produksi: YOLO + pelacak → pemeriksaan tubuh utuh →
potongan orang → VLM (prompt dari item APD aktif). Hasil TIDAK ditulis ke audit.

Folder data berisi dua subfolder kelas:
    <data>/ppe_complete/    foto APD lengkap
    <data>/ppe_incomplete/  foto APD tidak lengkap

Penyedia & model dipilih lewat variabel lingkungan yang sama dengan aplikasi
(VLM_PROVIDER, VLM_MODEL, VLM_BASE_URL); API key dibaca dari backend/.env oleh
config dan tidak pernah dicetak. Contoh, dari akar repo:
    VLM_PROVIDER=ollama VLM_MODEL=qwen2.5vl:7b python tools/eval_vlm.py picture_test

Selama evaluasi, detektor gerbang terus berinferensi ~25 FPS di latar belakang
untuk meniru beban kamera, sehingga latensi & VRAM terukur dalam kondisi nyata.
Tiap foto dikirim SEKALI tanpa percobaan ulang, dengan batas waktu longgar
(EVAL_TIMEOUT_SECONDS) agar akurasi model lambat tetap terukur; porsi yang
selesai di bawah batas waktu produksi (VLM_CLOUD/LOCAL_TIMEOUT_SECONDS) dilaporkan
terpisah. Yang dievaluasi hanya VLM utama; cadangan dimatikan agar tidak ikut
memakan VRAM dan mengacaukan pengukuran.
"""
import csv
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("VLM_BACKUP_PROVIDER", "none")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from backend.config import cfg  # noqa: E402
from backend import ppe_rules  # noqa: E402
from backend.detector import detector  # noqa: E402
from backend.vlm_analyzer import VLMAnalyzer  # noqa: E402

CLASSES = {"ppe_complete": True, "ppe_incomplete": False}
EVAL_TIMEOUT_SECONDS = float(os.getenv("EVAL_TIMEOUT_SECONDS", "90"))
LOAD_FPS = 25.0
STABLE_FRAMES = cfg.STABLE_FRAMES_REQUIRED


class GpuSampler(threading.Thread):
    """Mencatat pemakaian VRAM total (nvidia-smi) tiap 0,5 dtk."""

    def __init__(self):
        super().__init__(daemon=True)
        self.samples: list[int] = []
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout
                self.samples.append(int(out.split()[0]))
            except Exception:
                pass
            self.stop_flag.wait(0.5)


class CameraLoad(threading.Thread):
    """Detektor gerbang yang terus berinferensi, meniru thread kamera produksi.

    Memakai `detector` yang sama (potongan foto sudah disiapkan sebelum beban dimulai),
    bukan YOLO kedua: di mode GPU dGPU (14-10) YOLO kedua membuat VRAM 8 GB penuh dan
    Ollama macet, padahal gerbang sungguhan hanya memuat satu YOLO.
    """

    def __init__(self, frame):
        super().__init__(daemon=True)
        self.frame = frame
        self.stop_flag = threading.Event()
        self.frames = 0

    def run(self):
        while not self.stop_flag.is_set():
            t = time.time()
            detector.detect_and_track(self.frame)
            self.frames += 1
            self.stop_flag.wait(max(0.0, 1.0 / LOAD_FPS - (time.time() - t)))


def reset_tracker():
    predictor = getattr(detector.model, "predictor", None)
    for tracker in getattr(predictor, "trackers", None) or []:
        tracker.reset()


def person_crop(frame):
    """Potongan orang terbesar setelah STABLE_FRAMES frame identik, seperti orang diam di gerbang."""
    reset_tracker()
    dets = []
    for _ in range(STABLE_FRAMES):
        dets = detector.detect_and_track(frame)
    if not dets:
        return None
    return max(dets, key=lambda d: (d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]))


def ollama_residency(model: str) -> str:
    """Porsi model di GPU menurut Ollama (mis. '100% GPU' atau '23% CPU')."""
    try:
        import httpx
        base = (cfg.VLM_BASE_URL or "http://localhost:11434/v1").rsplit("/v1", 1)[0]
        for m in httpx.get(f"{base}/api/ps", timeout=5).json().get("models", []):
            names = {model, model if ":" in model else f"{model}:latest"}
            if m.get("name") in names or m.get("model") in names:
                size, vram = m.get("size", 0), m.get("size_vram", 0)
                if not size:
                    return "?"
                gpu = round(100 * vram / size)
                return "100% GPU" if gpu >= 100 else f"{gpu}% GPU / {100 - gpu}% CPU"
    except Exception as e:
        return f"? ({e})"
    return "tidak dimuat"


def unload_ollama(model: str):
    """Membongkar model dari RAM/VRAM. Pemanasan aplikasi memakai keep_alive=-1
    (model tertahan selamanya, benar untuk gerbang), yang untuk evaluasi berarti
    beberapa GB tetap terpakai setelah skrip selesai."""
    try:
        import httpx
        base = (cfg.VLM_BASE_URL or "http://localhost:11434/v1").rsplit("/v1", 1)[0]
        httpx.post(f"{base}/api/generate", json={"model": model, "keep_alive": 0}, timeout=30)
    except Exception as e:
        print(f"gagal membongkar {model}: {e}", flush=True)


def main():
    data = Path(sys.argv[1]).resolve()
    # --files a,b,c : hanya foto dengan nama (tanpa ekstensi) ini — menghemat kuota
    # VLM cloud saat cukup menguji sebagian foto (mis. T39a, 10 gambar)
    wanted = set(sys.argv[sys.argv.index("--files") + 1].split(",")) if "--files" in sys.argv else None
    files = [(f, label) for sub, label in CLASSES.items()
             for f in sorted((data / sub).glob("*")) if f.suffix.lower() in (".jpg", ".jpeg", ".png")
             and (wanted is None or f.stem in wanted)]
    if not files:
        sys.exit(f"Tidak ada foto di {data}/ppe_complete atau ppe_incomplete")

    ppe_rules.load_settings()
    detector.load()
    analyzer = VLMAnalyzer()
    analyzer.start()
    if not analyzer.is_live_api():
        sys.exit(f"VLM {cfg.VLM_PROVIDER} tidak aktif (API key belum disetel?)")
    assert analyzer.provider is not None
    provider, model = analyzer.provider.name, analyzer.provider.model
    active = [i.key for i in ppe_rules.get_active_items()]
    print(f"penyedia {provider} | model {model} | {len(files)} foto | item aktif {active}", flush=True)

    # 1. Potongan YOLO dihitung sekali, sebelum beban & pengukuran dimulai
    crops = []
    for f, label in files:
        frame = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR)
        crops.append((f, label, frame, person_crop(frame)))

    sampler = GpuSampler()
    sampler.start()
    time.sleep(1.5)
    vram_before = max(sampler.samples) if sampler.samples else None

    t = time.time()
    warm = analyzer.warm_up()
    print(f"pemanasan: {warm if warm is not None else 'GAGAL'} dtk ({time.time() - t:.1f} dtk)", flush=True)

    load = CameraLoad(crops[0][2])
    load_start = time.time()
    load.start()
    residency = ollama_residency(model) if cfg.VLM_IS_LOCAL else "-"

    rows = []
    pool = ThreadPoolExecutor(max_workers=1)
    last_call = 0.0
    for n, (f, label, frame, det) in enumerate(crops, 1):
        row = {"file": f"{f.parent.name}/{f.name}", "label_complete": label}
        if det is None:
            row.update(status="tanpa_orang")
            rows.append(row)
            print(f"[{n}/{len(crops)}] {row['file']}: TIDAK ADA ORANG", flush=True)
            continue
        row.update(full_body=det.is_full_body, in_corridor=det.is_inside_corridor, body_reason=det.reason)

        wait = cfg.VLM_MIN_INTERVAL_SECONDS - (time.time() - last_call)
        if wait > 0:
            time.sleep(wait)  # jeda kuota free tier; di luar pengukuran latensi
        start = time.time()
        try:
            # T86: titik pose ikut, supaya gambar yang dinilai sama dengan di gerbang (panel kepala & tangan)
            res = pool.submit(analyzer._call_vlm_internal, det.crop_img,
                              getattr(det, "crop_keypoints", None)).result(timeout=EVAL_TIMEOUT_SECONDS)
            row.update(status="ok", pred_complete=res.is_complete, missing="; ".join(res.missing_items))
        except Exception as e:
            kind = "timeout" if e.__class__.__name__ == "TimeoutError" else "galat"
            row.update(status=kind, error=str(e)[:200])
        row["latency_s"] = round(time.time() - start, 2)
        last_call = time.time()
        rows.append(row)
        verdict = ("BENAR" if row["pred_complete"] == label else "SALAH") if row["status"] == "ok" else row["status"].upper()
        print(f"[{n}/{len(crops)}] {row['file']}: {verdict} {row['latency_s']} dtk "
              f"(pred {'lengkap' if row.get('pred_complete') else 'tidak'}; kurang: {row.get('missing', '-')})", flush=True)

    load.stop_flag.set()
    sampler.stop_flag.set()
    load.join(5)
    pool.shutdown(wait=False)
    if cfg.VLM_IS_LOCAL:
        unload_ollama(model)
    elapsed = time.time() - load_start

    # 2. Ringkasan
    ok = [r for r in rows if r["status"] == "ok"]
    sent = [r for r in rows if r["status"] != "tanpa_orang"]
    lat = sorted(r["latency_s"] for r in ok)
    inc = [r for r in ok if not r["label_complete"]]
    com = [r for r in ok if r["label_complete"]]
    q = statistics.quantiles(lat, n=20) if len(lat) >= 2 else lat
    assert analyzer.primary is not None
    limit = analyzer.primary.timeout
    summary = {
        "provider": provider, "model": model, "foto": len(rows), "dikirim": len(sent),
        "jawaban_valid": len(ok), "galat_format_atau_lainnya": sum(r["status"] == "galat" for r in rows),
        "timeout": sum(r["status"] == "timeout" for r in rows),
        # Semua kegagalan dihitung SALAH: di produksi pekerja itu ditolak "tidak dapat diverifikasi"
        "akurasi": round(sum(r["pred_complete"] == r["label_complete"] for r in ok) / len(sent), 3) if sent else None,
        "apd_kurang_terdeteksi": f"{sum(not r['pred_complete'] for r in inc)}/{sum(not r['label_complete'] for r in sent)}",
        "lolos_padahal_kurang": sum(r["pred_complete"] for r in inc),
        "lengkap_ditolak": sum(not r["pred_complete"] for r in com),
        "latensi_median_s": round(statistics.median(lat), 2) if lat else None,
        "latensi_p95_s": round(q[-1], 2) if lat else None,
        "selesai_dalam_batas_produksi": f"{sum(x <= limit for x in lat)}/{len(sent)} (<= {limit:g} dtk)",
        "vram_sebelum_mb": vram_before, "vram_puncak_mb": max(sampler.samples) if sampler.samples else None,
        "porsi_gpu_ollama": residency,
        "yolo_paralel_fps": round(load.frames / elapsed, 1),
        "tubuh_utuh_ditolak": sum(r.get("full_body") is False for r in rows),
        "tanpa_orang": sum(r["status"] == "tanpa_orang" for r in rows),
        "item_aktif": active,
    }
    out_dir = cfg.DATA_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{time.strftime('%Y%m%d-%H%M%S')}_{provider}_{model.replace(':', '-').replace('/', '-')}"
    with open(out_dir / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    (out_dir / f"{stem}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nRINGKASAN " + json.dumps(summary, ensure_ascii=False), flush=True)
    print(f"hasil: {out_dir / stem}.csv/.json", flush=True)


if __name__ == "__main__":
    main()
