"""Katalog penyedia VLM & daftar model tervalidasi (T39b) — satu sumber, seperti katalog APD.

`.env` cukup memilih penyedia + model + key; sisanya (alamat bawaan, model
bawaan, lokal/cloud, cara mematikan mode berpikir) diambil dari profil.

Akurasi tiap model berbeda dan peka terhadap prompt, jadi pasangan penyedia +
model dicatat di VALIDATIONS setelah diuji dengan foto berlabel
(`tools/bench_vlm.py` / `tools/eval_vlm.py`). Model yang belum tervalidasi
tetap boleh dipakai (keputusan pengguna: peringatan saja), tetapi ditandai di
log dan Pengaturan. Modul ini sengaja tidak mengimpor apa pun dari backend,
karena `config.py` memakainya.
"""
from dataclasses import dataclass
from typing import Optional

OFFICIAL = "official"          # pernah diuji di gerbang ini
EXPERIMENTAL = "experimental"  # adaptor tersedia, belum pernah diuji di sini

API_GEMINI = "gemini"
API_OPENAI_COMPATIBLE = "openai_compatible"
API_ANTHROPIC = "anthropic"

# Tingkat "berpikir" umum (VLM_THINKING); profil menerjemahkannya ke parameter penyedia
THINKING_LEVELS = ("off", "low", "medium", "high")


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    api: str
    is_local: bool
    support: str
    base_url: str = ""
    default_model: str = ""
    # Tingkat umum -> nilai parameter penyedia; None = penyedia tidak bisa diatur
    thinking: Optional[dict] = None
    data_location: str = ""
    # Nama variabel .env yang menyimpan API key penyedia ini (T28). Key hanya ada
    # di .env; dashboard memilih penyedia, tidak pernah menerima key.
    key_env: str = ""
    # Nama tampilan di Pengaturan admin (bukan UI operator)
    label: str = ""


PROFILES = {p.name: p for p in (
    # Gemini 3 tidak bisa mematikan berpikir sepenuhnya; "minimal" terukur ~1,4 dtk
    # vs ~5 dtk bawaan dengan jawaban APD yang sama (T23).
    ProviderProfile("gemini", API_GEMINI, is_local=False, support=OFFICIAL,
                    default_model="gemini-3.5-flash-lite",
                    thinking={"off": "minimal", "low": "low", "medium": "medium", "high": "high"},
                    data_location="Google Cloud (global)", key_env="GEMINI_API_KEY", label="Google Gemini"),
    # T26: satu-satunya model lokal yang tidak meloloskan APD kurang
    ProviderProfile("ollama", API_OPENAI_COMPATIBLE, is_local=True, support=OFFICIAL,
                    base_url="http://localhost:11434/v1", default_model="qwen2.5vl:7b",
                    data_location="mesin ini", label="Ollama (lokal)"),
    # vLLM tidak punya port bawaan yang aman: 8000 dipakai server ini sendiri
    ProviderProfile("vllm", API_OPENAI_COMPATIBLE, is_local=True, support=EXPERIMENTAL,
                    data_location="mesin ini", label="vLLM (lokal)"),
    ProviderProfile("openai", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://api.openai.com/v1", data_location="OpenAI (AS)",
                    key_env="OPENAI_API_KEY", label="OpenAI"),
    ProviderProfile("openrouter", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://openrouter.ai/api/v1", data_location="OpenRouter + penyedia model",
                    key_env="OPENROUTER_API_KEY", label="OpenRouter"),
    # Region internasional; akun Tiongkok daratan memakai dashscope.aliyuncs.com
    ProviderProfile("qwen", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                    data_location="Alibaba Cloud", key_env="DASHSCOPE_API_KEY", label="Qwen (Alibaba DashScope)"),
    # Hanya model yang menerima gambar (mis. deepseek-flash)
    ProviderProfile("deepseek", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://api.deepseek.com", data_location="DeepSeek (Tiongkok)",
                    key_env="DEEPSEEK_API_KEY", label="DeepSeek"),
    # T28: region internasional; akun Tiongkok daratan memakai api.moonshot.cn. Gambar
    # dikirim sebagai data URI base64 (URL gambar jarak jauh tidak diterima). Model
    # bawaan sengaja kosong: diisi admin saat uji, tidak ditebak.
    ProviderProfile("kimi", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    base_url="https://api.moonshot.ai/v1", data_location="Moonshot AI",
                    key_env="MOONSHOT_API_KEY", label="Kimi (Moonshot)"),
    # T28: Claude lewat Messages API (adaptor sendiri). Model bawaan kosong: dipilih admin.
    ProviderProfile("anthropic", API_ANTHROPIC, is_local=False, support=EXPERIMENTAL,
                    base_url="https://api.anthropic.com", data_location="Anthropic (AS)",
                    key_env="ANTHROPIC_API_KEY", label="Claude (Anthropic)"),
    # Alamat wajib dari VLM_BASE_URL; key hanya lewat VLM_API_KEY / VLM_BACKUP_API_KEY
    ProviderProfile("openai-compatible", API_OPENAI_COMPATIBLE, is_local=False, support=EXPERIMENTAL,
                    label="Server OpenAI-compatible"),
)}


@dataclass(frozen=True)
class ModelValidation:
    """Hasil uji foto berlabel. `missed` = pekerja APD kurang yang diloloskan (harus 0)."""
    provider: str
    model: str
    prompt_version: str
    date: str
    photos: int
    missed: int
    false_rejects: Optional[int]       # None = tidak tercatat
    median_seconds: Optional[float]    # None = tidak tercatat
    complete: bool          # False = uji sebagian (mis. 10 foto tersulit)
    note: str = ""


VALIDATIONS = (
    # T86 Gemini (21-10; gambar tubuh + perbesaran KEPALA saja — panel tangan dibatalkan karena helm yang
    # dipegang & kaos kuning ikut diperbesar lalu dikira dipakai oleh model lokal). Pengguna meminta 10 foto
    # tersulit: no_16 (helm dipegang), no_47 (kaos kuning), no_34 (tangan bernoda semen), apd_10, apd_4,
    # apd_19, no_23, no_35, no_45 → 9/9 benar (median 2,35 dtk), tanpa rokok palsu; + foto bukti gerbang
    # baris 121 (rokok di mulut, lolos sebelum T86) lewat analyze_person + konfirmasi → ditolak rokok.
    # VLM lokal TIDAK memakai panel (vlm_selection.uses_zoom): prompt & gambarnya isi T58 persis.
    ModelValidation("gemini", "gemini-3.5-flash-lite", "T86", "2026-10-21", photos=10, missed=0, false_rejects=0,
                    median_seconds=2.35, complete=False,
                    note="T86: no_16, no_47, no_34, apd_10, apd_4, apd_19, no_23, no_35, no_45 + bukti gerbang "
                         "(rokok di mulut); data/eval 20261021-101715"),
    # T58 Gemini (izin pengguna 14-10: total 5 foto, jaga RPM): 5/5 benar — apd_10 & apd_4 (salah
    # tolak model lokal) lolos, no_34 (tangan bernoda semen) tidak dianggap rokok. Tanpa konfirmasi
    # kedua (eval_vlm memanggil VLM langsung). Median ~1,75 dtk.
    # Tambahan sore 14-10 (izin pengguna: maks. 5 foto): apd_19, apd_7, no_35 (sepatu kurang),
    # no_40 (hanya helm kurang), no_45 (foto/layar) → 5/5 benar; Gemini sedang lambat
    # (median 5,5 dtk, 4/5 > batas produksi 4 dtk → di gerbang beralih ke cadangan). Gabungan 10 foto.
    ModelValidation("gemini", "gemini-3.5-flash-lite", "T58", "2026-10-14", photos=10, missed=0, false_rejects=0,
                    median_seconds=3.45, complete=False,
                    note="T58: apd_1, apd_10, apd_4, apd_19, apd_7, no_1, no_34, no_35, no_40, no_45; "
                         "data/eval 20261014-070915, -171309"),
    # T58 (prompt T48 + larangan rokok + konfirmasi kedua), 84 foto: 0 lolos; salah tolak apd_10;
    # galat apd_19 & no_23 (sama dgn sebelumnya); rokok palsu no_34 (tangan bernoda semen)
    # dibatalkan konfirmasi. Setelah galat no_23 Ollama memuat ulang model 26% di CPU (T38):
    # foto 43-48 benar tetapi ~27 dtk; sisa 36 foto diulang dengan model dimuat bersih.
    ModelValidation("ollama", "qwen2.5vl:7b", "T58", "2026-10-14", photos=84, missed=0, false_rejects=1,
                    median_seconds=3.7, complete=True,
                    note="RTX 4060 Laptop, beban YOLO; log bench_t58c (foto 1-48) + data/eval 20261014-000630"),
    # T48 (prompt helm/sepatu dilonggarkan): 10 foto, sama dengan sebelum pelonggaran
    # (apd_10 & apd_4 tetap salah tolak). Hasil 84 foto prompt T36a: 0/58 lolos, 2/26 salah tolak.
    ModelValidation("ollama", "qwen2.5vl:7b", "T48", "2026-10-05", photos=10, missed=0, false_rejects=2,
                    median_seconds=5.7, complete=False,
                    note="T48 10 foto (data/eval/20261005-171212); prompt T36a sebelumnya 84 foto 0 lolos"),
    # T48 (helm/sepatu dilonggarkan): 2 foto lengkap yang ditolak model lokal + 10 foto
    # yang kurangnya hanya helm/sepatu (paling berisiko lolos bila aturan longgar).
    ModelValidation("gemini", "gemini-3.5-flash-lite", "T48", "2026-10-05", photos=12, missed=0, false_rejects=0,
                    median_seconds=2.21, complete=False,
                    note="T48: apd_10, apd_4 + 10 foto kurang helm/sepatu; data/eval 20261005-172017, -172428"),
    # Free tier tidak cukup untuk 84 foto sekaligus (keputusan pengguna 05-10): diuji bertahap,
    # 10 foto per sesi dengan jeda 4 dtk (15 RPM). Satu jawaban 4,08 dtk > batas 4 dtk.
    ModelValidation("gemini", "gemini-3.5-flash-lite", "T36a", "2026-10-05", photos=20, missed=0, false_rejects=0,
                    median_seconds=2.17, complete=False,
                    note="20 foto berbeda (T39a 10 tersulit + 05-10 10 acak tubuh utuh), 10 lengkap/10 kurang; "
                         "data/eval 20260927-232352, -233047, 20261005-170311"),
    # T26 (prompt lama): lebih cepat, tetapi meloloskan pekerja ber-APD kurang
    ModelValidation("ollama", "qwen2.5vl:3b", "T26", "2026-09-24", photos=84, missed=11, false_rejects=None,
                    median_seconds=None, complete=True, note="T26: lolos 11/58 APD kurang, akurasi 83%"),
)

# Status validasi sepasang penyedia + model untuk prompt yang berlaku
VALIDATED = "validated"
PARTIAL = "partial"
OUTDATED = "outdated"          # tervalidasi untuk prompt lama
UNSAFE = "unsafe"              # pernah meloloskan APD kurang
UNVALIDATED = "unvalidated"


def get_profile(name: str) -> Optional[ProviderProfile]:
    return PROFILES.get((name or "").strip().lower())


def default_model(name: str) -> str:
    profile = get_profile(name)
    return profile.default_model if profile else ""


def is_local(name: str) -> bool:
    profile = get_profile(name)
    return bool(profile and profile.is_local)


def find_validation(provider: str, model: str, prompt_version: str = "") -> Optional[ModelValidation]:
    """Catatan untuk versi prompt itu; bila tidak ada, catatan terbaru model tersebut."""
    key = ((provider or "").strip().lower(), (model or "").strip())
    records = [v for v in VALIDATIONS if (v.provider, v.model) == key]
    exact = [v for v in records if v.prompt_version == prompt_version]
    return (exact or sorted(records, key=lambda v: v.date, reverse=True) or [None])[0]


def validation_status(provider: str, model: str, prompt_version: str) -> str:
    # Pernah meloloskan APD kurang di versi prompt mana pun = tidak aman
    key = ((provider or "").strip().lower(), (model or "").strip())
    if any((v.provider, v.model) == key and v.missed > 0 for v in VALIDATIONS):
        return UNSAFE
    v = find_validation(provider, model, prompt_version)
    if v is None:
        return UNVALIDATED
    if v.prompt_version != prompt_version:
        return OUTDATED
    return VALIDATED if v.complete else PARTIAL


def thinking_value(name: str, level: str) -> Optional[str]:
    """Nilai parameter berpikir penyedia; None = tidak dikirim (penyedia tidak mendukungnya)."""
    profile = get_profile(name)
    if profile is None or profile.thinking is None:
        return None
    return profile.thinking.get(level)
