"""Uji kecepatan VLM lokal: varian prompt & ukuran gambar (T35, Uji 1).

Membandingkan beberapa bentuk prompt dan ukuran gambar pada foto berlabel yang
sama, langsung lewat API asli Ollama supaya waktu baca input (prefill) dan waktu
menulis jawaban (decode) tercatat terpisah. Kode gerbang TIDAK diubah; prompt
varian di sini hanya eksperimen, prompt produksi tetap di messages.py/ppe_rules.

Jalur gambar sama dengan produksi dan T26: YOLO + pelacak → potongan orang, lalu
diperkecil & dikompres seperti `VLMAnalyzer._optimize_image_for_vlm`. Selama uji,
YOLO kedua berjalan di latar (beban kamera). Foto hanya dikirim ke Ollama lokal,
tidak ke penyedia cloud. Hasil ke data/eval/, bukan ke audit.

Contoh, dari akar repo:
    python tools/bench_vlm.py picture_test --prompts P0,P1,P2 --sizes 640
    python tools/bench_vlm.py picture_test --prompts P1 --sizes 448,896,full

Varian prompt:
    P0  prompt produksi apa adanya (jawaban lengkap: deskripsi, notes, missing_items)
    P1  aturan produksi + larangan rokok, jawaban RINGKAS (nilai benar/salah saja)
    P2  aturan RINGKAS + larangan rokok, jawaban ringkas
    P1N seperti P1 tanpa larangan rokok (mengisolasi pengaruh aturan rokok)
    P3  seperti P1, tiap item diawali alasan <=5 kata sebelum nilainya
Ukuran: sisi terpanjang crop dalam piksel, atau `full` = frame utuh (kontrol).
"""
import argparse
import base64
import csv
import json
import statistics
import time
from dataclasses import replace
from typing import Any
from pathlib import Path

import eval_vlm  # noqa: F401  (menyetel VLM_BACKUP_PROVIDER=none sebelum config dimuat)
from eval_vlm import CameraLoad, GpuSampler, ollama_residency, person_crop, unload_ollama

import cv2  # noqa: E402
import httpx  # noqa: E402
import numpy as np  # noqa: E402

from backend import messages, ppe_rules  # noqa: E402
from backend.config import cfg  # noqa: E402
from backend.detector import detector  # noqa: E402
from backend.vlm_analyzer import (  # noqa: E402
    VLMAnalyzer,
    build_system_prompt,
    confirmation_prompts,
    parse_confirmation,
)

CLASSES = eval_vlm.CLASSES
TIMEOUT_S = 90.0
NS_PER_MS = 1_000_000
FULL = "full"
FULL_GPU = "100% GPU"  # teks dari eval_vlm.ollama_residency

# --- Prompt eksperimen (bukan produksi) ---------------------------------------------

SMOKING_KEY = "rokok"
SMOKING_RULE = (
    "LARANGAN ROKOK: rokok = true jika orang terlihat merokok, memegang rokok batangan, "
    "atau membawa bungkus rokok yang terlihat (di tangan/saku). Pulpen, sedotan, atau "
    "tusuk gigi BUKAN rokok. Jika tidak terlihat, rokok = false."
)
REAL_PERSON_KEY = "orang_nyata"
REAL_PERSON_RULE = (
    "orang_nyata = false jika subjek hanya foto/layar HP/laptop/cetakan yang diarahkan ke kamera."
)
# Aturan ringkas per item (P2). Item lain di katalog memakai prompt_rule produksi.
COMPACT_RULES = {
    "helm": "helm: helm keselamatan proyek, warna bebas. Topi kain/kupluk = false.",
    "rompi": "rompi: rompi keselamatan; is_valid_color = true hanya jika oranye atau kuning/lime hi-vis.",
    "celana": "celana: celana panjang sampai mata kaki. Celana pendek/selutut = false.",
    "sepatu": "sepatu: is_closed_shoes = true untuk sepatu tertutup penuh. Sandal/selop/telanjang kaki = false.",
}
SHORT_HEADER = "Anda inspektur K3. Nilai APD orang di gambar. Jawab HANYA JSON sesuai bentuk di bawah, tanpa teks lain."
SHORT_USER = "Nilai gambar ini. JSON saja."


# Aturan rompi yang lebih ketat (usulan 27-09): memisahkan "apakah ini rompi"
# (bentuk) dari "apakah warnanya benar". Kaos/baju kuning bukan rompi.
VEST_KEY = "rompi"
VEST_STRICT_RULE = (
    "ROMPI KESELAMATAN (Safety Vest / Hi-Vis Vest):\n"
    "   - Rompi keselamatan = pakaian luar TANPA LENGAN yang dipakai DI ATAS baju/kaos,\n"
    "     biasanya terbuka di depan (resleting/perekat) dan punya PITA REFLEKTIF\n"
    "     (garis perak/abu mengkilap) melintang di dada atau perut.\n"
    "   - Kaos, kemeja, jaket, atau seragam berwarna kuning/oranye BUKAN rompi keselamatan,\n"
    "     walaupun warnanya sama -> detected = false."
)
VEST_STRICT_QUALIFIER = (
    "   - Jika rompi ada: warna wajib ORANGE atau KUNING / LIME HI-VIS (is_valid_color = true);\n"
    "     rompi biru, hitam, merah -> is_valid_color = false."
)


def with_strict_vest(items):
    """Salinan katalog aktif dengan aturan rompi ketat (katalog produksi tidak diubah)."""
    out = []
    for item in items:
        if item.key == VEST_KEY:
            q = replace(item.qualifier, prompt_rule=VEST_STRICT_QUALIFIER) if item.qualifier else None
            item = replace(item, prompt_rule=VEST_STRICT_RULE, qualifier=q)
        out.append(item)
    return out


REASON_KEY = "alasan"
REASON_RULE = f'Isi "{REASON_KEY}" (maksimal 5 kata, apa yang terlihat) SEBELUM nilai benar/salah tiap item.'


def minimal_shape(items, smoking: bool = True, reason: bool = False) -> str:
    """Bentuk jawaban ringkas: hanya nilai yang dipakai `ppe_rules.evaluate`."""
    fields = []
    for item in items:
        f = [f'"{REASON_KEY}": "<maks 5 kata>"'] if reason else []
        f.append('"detected": true/false')
        if item.reports_color:
            f.append('"color": "<warna>"')
        if item.qualifier is not None:
            f.append(f'"{item.qualifier.key}": true/false')
        fields.append(f'"{item.key}": {{' + ", ".join(f) + "}")
    extra = f', "{SMOKING_KEY}": true/false' if smoking else ""
    return '{"items": {' + ", ".join(fields) + f'}}, "{REAL_PERSON_KEY}": true/false{extra}}}'


def build_prompts(variant: str, items) -> tuple[str, str]:
    if variant == "P0":
        return build_system_prompt(items), messages.VLM_USER_PROMPT
    if variant in ("P1", "P1N", "P3"):
        smoking, reason = variant != "P1N", variant == "P3"
        rules = ppe_rules.build_prompt_rules(items)
        extra = "\n".join(r for r, on in ((REAL_PERSON_RULE, True), (SMOKING_RULE, smoking),
                                          (REASON_RULE, reason)) if on)
        system = (f"{SHORT_HEADER}\n\n{rules}\n\n{extra}\n\n"
                  f"Bentuk JSON:\n{minimal_shape(items, smoking=smoking, reason=reason)}")
        return system, SHORT_USER
    if variant == "P2":
        rules = "\n".join(COMPACT_RULES.get(i.key, i.prompt_rule or "") for i in items)
        system = (f"{SHORT_HEADER}\n{rules}\n{REAL_PERSON_RULE}\n{SMOKING_RULE}\n"
                  f"Bentuk JSON:\n{minimal_shape(items)}")
        return system, SHORT_USER
    if variant in BIT_VARIANTS:
        keys = [k for k, _ in flag_keys(items, short=variant == "PC")]
        if variant in ("PA", "PC"):
            shape = "{" + ", ".join(f'"{k}": 0/1' for k in keys) + "}"
        else:
            shape = "[" + ", ".join(keys) + "]  (tulis sebagai larik angka 0/1, urutan persis seperti ini)"
        rule = short_bit_rule(items) if variant == "PC" else BIT_RULE
        system = (f"{SHORT_HEADER}\n\n{ppe_rules.build_prompt_rules(items)}\n\n{rule}\n\n"
                  f"Bentuk JSON:\n{shape}")
        return system, SHORT_USER
    raise ValueError(f"varian prompt tidak dikenal: {variant}")


# --- Jawaban 0/1 (uji T36a2) ---------------------------------------------------------
# PA: objek kunci bernilai 0/1; PB: larik 0/1 berurutan; PC: seperti PA dengan kunci
# syarat berbahasa Indonesia pendek (rompi_warna, sepatu_tertutup). Semua dengan skema
# JSON yang dipaksakan (structured output Ollama), jadi bentuknya dijamin sah.
BIT_VARIANTS = ("PA", "PB", "PC")
# Nama pendek syarat (hanya untuk uji PC); syarat lain memakai kunci katalog
QUALIFIER_SHORT = {"is_valid_color": "warna", "is_closed_shoes": "tertutup"}
BIT_RULE = (
    "Isi 1 = ya/terpenuhi, 0 = tidak. <item> = item dipakai (detected); "
    "<item>_<syarat> = syarat item terpenuhi (mis. rompi_is_valid_color, sepatu_is_closed_shoes); "
    f"{ppe_rules.REAL_PERSON_KEY} = 1 jika subjek orang fisik nyata."
)


def flag_keys(items, short: bool = False) -> list[tuple[str, tuple[str, str]]]:
    """Kunci datar -> (item, field) sesuai katalog aktif, plus tanda orang nyata."""
    out = []
    for item in items:
        out.append((item.key, (item.key, "detected")))
        if item.qualifier is not None:
            q = item.qualifier.key
            name = QUALIFIER_SHORT.get(q, q) if short else q
            out.append((f"{item.key}_{name}", (item.key, q)))
    out.append((ppe_rules.REAL_PERSON_KEY, ("", "")))
    return out


def short_bit_rule(items) -> str:
    """Aturan PC: arti tiap kunci syarat pendek dijelaskan dengan nama di aturan item."""
    pairs = [f"{k} = {field}" for k, (_, field) in flag_keys(items, short=True) if field not in ("detected", "")]
    return (f"Isi 1 = ya/terpenuhi, 0 = tidak. <item> = item dipakai (detected); {'; '.join(pairs)}; "
            f"{ppe_rules.REAL_PERSON_KEY} = 1 jika subjek orang fisik nyata.")


def bit_schema(variant: str, items) -> dict:
    keys = [k for k, _ in flag_keys(items, short=variant == "PC")]
    bit = {"type": "integer", "enum": [0, 1]}
    if variant in ("PA", "PC"):
        return {"type": "object", "properties": {k: bit for k in keys}, "required": keys,
                "additionalProperties": False}
    return {"type": "array", "items": bit, "minItems": len(keys), "maxItems": len(keys)}


def output_format(variant: str, items):
    return bit_schema(variant, items) if variant in BIT_VARIANTS else "json"


def smoking_flag(parsed):
    """Rokok terlihat menurut jawaban: kunci atas (prompt eksperimen) atau item larangan produksi (T58)."""
    if not isinstance(parsed, dict):
        return None
    if SMOKING_KEY in parsed:
        return parsed[SMOKING_KEY]
    item = parsed.get("items", {}).get(SMOKING_KEY)
    return item.get("detected") if isinstance(item, dict) else None


def confirm_production_smoking(client, model: str, image_b64: str, parsed: dict, row: dict):
    """Konfirmasi kedua seperti produksi (T58): rokok hanya berlaku bila kedua jawaban sepakat."""
    system, user = confirmation_prompts(ppe_rules.get_item(SMOKING_KEY))
    try:
        reply = call(client, model, system, user, image_b64)["message"]["content"]
        confirmed, seen = parse_confirmation(json.loads(reply))
    except Exception as e:
        confirmed, seen = False, f"galat: {str(e)[:60]}"
    row.update(rokok_konfirmasi=confirmed, rokok_benda=seen)
    parsed["items"][SMOKING_KEY]["detected"] = confirmed


def to_production_payload(data, variant: str, items=None) -> dict:
    """Jawaban ringkas → bentuk yang dipahami `_parse_vlm_payload` produksi."""
    if variant == "P0":
        return data
    if variant in BIT_VARIANTS:
        keys = flag_keys(items, short=variant == "PC")
        values = data if variant == "PB" else [data.get(k) for k, _ in keys]
        result: dict[str, Any] = {"items": {}}
        for (_, (item_key, field)), value in zip(keys, values):
            if item_key:
                result["items"].setdefault(item_key, {})[field] = value == 1
            elif value == 0:
                result["missing_items"] = [ppe_rules.SPOOF_MISSING_LABEL]
        return result
    payload = {"items": data.get("items", {})}
    if data.get(REAL_PERSON_KEY) is False:
        payload["missing_items"] = [ppe_rules.SPOOF_MISSING_LABEL]
    return payload


# --- Gambar ----------------------------------------------------------------------------

def encode(image_bgr, max_side: int) -> tuple[str, str]:
    """Diperkecil & dikompres seperti produksi; hasil base64 + ukuran akhir."""
    h, w = image_bgr.shape[:2]
    if max(h, w) > max_side:
        s = max_side / float(max(h, w))
        image_bgr = cv2.resize(image_bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.VLM_JPEG_QUALITY])
    return base64.b64encode(buf.tobytes()).decode(), f"{image_bgr.shape[1]}x{image_bgr.shape[0]}"


# --- Ollama ----------------------------------------------------------------------------

def ollama_root() -> str:
    base = cfg.VLM_BACKUP_BASE_URL or "http://localhost:11434/v1"
    return base[:-3] if base.rstrip("/").endswith("/v1") else base.rstrip("/")


def call(client: httpx.Client, model: str, system: str, user: str, image_b64: str,
         fmt: str | dict = "json") -> dict:
    body = {
        "model": model, "stream": False, "format": fmt, "keep_alive": "10m",
        "options": {"temperature": cfg.VLM_TEMPERATURE},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user, "images": [image_b64]}],
    }
    r = client.post(f"{ollama_root()}/api/chat", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


# --- Ringkasan -------------------------------------------------------------------------

def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def p90(xs):
    xs = sorted(x for x in xs if x is not None)
    return round(xs[min(len(xs) - 1, int(0.9 * len(xs)))], 2) if xs else None


def summarize(rows):
    out = {}
    for key in sorted({r["variant"] for r in rows}):
        rs = [r for r in rows if r["variant"] == key]
        ok = [r for r in rs if r["status"] == "ok"]
        inc = [r for r in rs if not r["label_complete"]]
        out[key] = {
            "dikirim": len(rs), "jawaban_valid": len(ok),
            "akurasi": round(sum(r["pred_complete"] == r["label_complete"] for r in ok) / len(rs), 3) if rs else None,
            # Galat server (mis. Ollama crash pada gambar tertentu) dipisah dari salah
            # jawab: masalahnya di runtime, bukan di kemampuan model/prompt.
            "galat_server": sum(r["status"] == "galat" for r in rs),
            "akurasi_tanpa_galat": round(sum(r["pred_complete"] == r["label_complete"] for r in ok) / len(ok), 3)
            if ok else None,
            "lolos_padahal_kurang": sum(r.get("pred_complete") is True for r in inc),
            "lengkap_ditolak": sum(r.get("pred_complete") is False for r in rs if r["label_complete"]),
            "rokok_true": sum(r.get("rokok") is True for r in ok),
            "rokok_awal_true": sum(r.get("rokok_awal") is True for r in ok),
            "tubuh_utuh_dikirim": sum(r.get("full_body") is True for r in rs),
            "tubuh_utuh_akurasi": round(sum(r["pred_complete"] == r["label_complete"] for r in ok if r.get("full_body"))
                                        / max(1, sum(r.get("full_body") is True for r in rs)), 3),
            "tubuh_utuh_lolos_padahal_kurang": sum(r.get("pred_complete") is True for r in inc if r.get("full_body")),
            "latensi_median_s": med(r["latency_s"] for r in ok), "latensi_p90_s": p90([r["latency_s"] for r in ok]),
            "token_input_median": med(r["prompt_tokens"] for r in ok),
            "baca_input_median_ms": med(r["prompt_ms"] for r in ok),
            "token_output_median": med(r["output_tokens"] for r in ok),
            "tulis_output_median_ms": med(r["output_ms"] for r in ok),
            "ukuran_gambar_contoh": ok[0]["image_size"] if ok else None,
            "panggilan_tidak_100_gpu": sum(r.get("gpu") != FULL_GPU for r in rs if r["status"] != "tanpa_orang"),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--prompts", default="P0,P1,P2")
    ap.add_argument("--sizes", default="640")
    ap.add_argument("--limit", type=int, default=0, help="batasi jumlah foto per kelas (0 = semua)")
    ap.add_argument("--model", default=cfg.VLM_BACKUP_MODEL or "qwen2.5vl:7b")
    ap.add_argument("--vest-strict", action="store_true", help="aturan rompi ketat (hanya di alat ini)")
    ap.add_argument("--files", default="", help="hanya foto dengan nama ini, dipisah koma (mis. no_47,no_14)")
    ap.add_argument("--dump", action="store_true", help="cetak jawaban mentah model")
    args = ap.parse_args()

    prompts = args.prompts.split(",")
    sizes = args.sizes.split(",")
    variants = [(p, s) for p in prompts for s in sizes]
    data = Path(args.data).resolve()
    files = []
    for sub, label in CLASSES.items():
        fs = sorted(f for f in (data / sub).glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
        if args.files:
            wanted = set(args.files.split(","))
            fs = [f for f in fs if f.stem in wanted]
        files += [(f, label) for f in (fs[:args.limit] if args.limit else fs)]

    ppe_rules.load_settings()
    items = ppe_rules.get_active_items()
    if args.vest_strict:
        items = with_strict_vest(items)
    detector.load()
    print(f"model {args.model} | {len(files)} foto | varian {variants} | item {[i.key for i in items]}", flush=True)

    # Potongan YOLO dihitung sekali, sebelum beban & pengukuran
    prepared = []
    for f, label in files:
        frame = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR)
        det = person_crop(frame)
        prepared.append((f, label, frame, det.crop_img if det is not None else None,
                         det.is_full_body if det is not None else None))

    sampler = GpuSampler()
    sampler.start()
    client = httpx.Client()
    # Pemanasan (tidak diukur): memuat model ke GPU
    first = next(p for p in prepared if p[3] is not None)
    call(client, args.model, *build_prompts(prompts[0], items), encode(first[3], 640)[0])
    load = CameraLoad(first[2])
    load.start()
    time.sleep(2)
    residency = ollama_residency(args.model)
    print(f"porsi GPU Ollama saat beban YOLO: {residency}", flush=True)

    rows = []
    total = len(prepared) * len(variants)
    n = 0
    # Varian di luar, foto di dalam: seperti produksi, prompt sistem yang sama
    # dikirim berturut-turut sehingga cache prompt Ollama terpakai. Diselang-seling
    # per foto, cache itu terbuang dan waktu baca input tampak lebih lambat.
    for prompt, size in variants:
        for f, label, frame, crop, full_body in prepared:
            n += 1
            suffix = "+rompi_ketat" if args.vest_strict else ""
            row = {"variant": f"{prompt}@{size}{suffix}", "file": f"{f.parent.name}/{f.name}",
                   "label_complete": label, "full_body": full_body}
            src = frame if size == FULL else crop
            if src is None:
                row["status"] = "tanpa_orang"
                rows.append(row)
                continue
            img, dims = encode(src, cfg.VLM_IMAGE_MAX_SIZE if size == FULL else int(size))
            system, user = build_prompts(prompt, items)
            start = time.time()
            resp = {}
            try:
                resp = call(client, args.model, system, user, img, output_format(prompt, items))
                raw = resp.get("message", {}).get("content", "")
                if args.dump:
                    print(f"--- {row['variant']} {row['file']}", raw, sep="\n", flush=True)
                parsed = json.loads(raw)
                row["rokok_awal"] = smoking_flag(parsed)
                if prompt == "P0" and row["rokok_awal"] is True:
                    confirm_production_smoking(client, args.model, img, parsed, row)
                res = VLMAnalyzer._parse_vlm_payload(to_production_payload(parsed, prompt, items), items)
                row.update(status="ok", pred_complete=res.is_complete, missing="; ".join(res.missing_items),
                           rokok=smoking_flag(parsed), output_chars=len(raw))
            except Exception as e:
                row.update(status="galat", error=str(e)[:160])
            row.update(
                latency_s=round(time.time() - start, 2), image_size=dims,
                # Model bisa dimuat ulang sebagian ke CPU bila aplikasi lain merebut
                # VRAM; latensi baris seperti itu tidak sebanding dengan yang lain.
                gpu=ollama_residency(args.model),
                prompt_tokens=resp.get("prompt_eval_count"),
                prompt_ms=round(resp["prompt_eval_duration"] / NS_PER_MS) if resp.get("prompt_eval_duration") else None,
                output_tokens=resp.get("eval_count"),
                output_ms=round(resp["eval_duration"] / NS_PER_MS) if resp.get("eval_duration") else None,
                load_ms=round(resp["load_duration"] / NS_PER_MS) if resp.get("load_duration") else None,
            )
            rows.append(row)
            verdict = ("BENAR" if row.get("pred_complete") == label else "SALAH") if row["status"] == "ok" else "GALAT"
            print(f"[{n}/{total}] {row['variant']:9} {row['file']}: {verdict} {row['latency_s']} dtk "
                  f"(in {row['prompt_tokens']} tok/{row['prompt_ms']} ms, out {row['output_tokens']} tok/{row['output_ms']} ms)",
                  flush=True)

    load.stop_flag.set()
    sampler.stop_flag.set()
    load.join(5)
    client.close()
    unload_ollama(args.model)

    summary = {"model": args.model, "porsi_gpu_ollama": residency,
               "vram_puncak_mb": max(sampler.samples) if sampler.samples else None,
               "item_aktif": [i.key for i in items], "varian": summarize(rows)}
    out_dir = cfg.DATA_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{time.strftime('%Y%m%d-%H%M%S')}_bench_{args.model.replace(':', '-')}"
    with open(out_dir / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)
    (out_dir / f"{stem}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nRINGKASAN " + json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    print(f"hasil: {out_dir / stem}.csv/.json", flush=True)


if __name__ == "__main__":
    main()
