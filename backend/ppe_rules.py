"""Definisi item APD — satu-satunya sumber kebenaran.

Sebelum berkas ini ada, keempat item APD bukan data melainkan struktur kode:
nama dan sifatnya tertanam di model Pydantic, prompt VLM, heuristik lokal,
sebelas kolom SQLite, rantai if/elif pemutar audio, nama berkas MP3, dan elemen
DOM ber-ID tetap. Memasang sistem di lokasi dengan APD berbeda berarti menyunting
sembilan berkas sekaligus memigrasi database.

Semua bagian itu kini membaca definisi di sini. Menambah, menghapus, atau
mengubah item APD dilakukan dengan menyunting `PPE_ITEMS` saja.

Catatan pembagian tugas: SUSUNAN item ditentukan saat deploy lewat berkas ini,
sedangkan item mana yang AKTIF dapat diubah operator dari dashboard saat sistem
berjalan (lihat `get_active_items` dan `set_active`). Item yang dimatikan tidak
diperiksa sama sekali: tidak masuk prompt VLM, checklist, maupun keputusan gerbang.
"""

import logging
import threading
from dataclasses import dataclass, replace
from typing import Optional

from . import runtime_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Qualifier:
    """Syarat tambahan di luar sekadar 'terdeteksi'.

    Sebagian APD tidak cukup hanya ada — rompi harus berwarna hi-vis, sepatu
    harus tertutup. Dulu kedua syarat ini diistimewakan lewat field khusus di
    model (`is_valid_color`, `is_closed_shoes`); di sini keduanya jadi bentuk
    umum yang sama sehingga item baru bisa punya syaratnya sendiri.
    """

    key: str            # Nama field pada hasil VLM, mis. "is_valid_color"
    prompt_rule: str    # Kalimat syarat untuk prompt VLM
    fail_label: str     # Teks lencana UI ketika item ada tetapi syarat tidak terpenuhi


@dataclass(frozen=True)
class PPEItem:
    """Satu item APD beserta seluruh sifat yang dibutuhkan lintas modul."""

    key: str                    # Pengenal internal; dipakai sebagai kunci JSON, DB, dan DOM
    label: str                  # Nama yang dibaca operator
    icon: str                   # Emoji untuk lencana dashboard lama (dihapus bersama UI lama)
    icon_name: str              # Nama ikon garis untuk UI baru (mis. "hard-hat"); kunci ke registri ikon frontend
    missing_label: str          # Nama yang masuk ke daftar `missing_items`
    audio_missing: str          # Nama berkas MP3 (tanpa ekstensi) saat item tidak lengkap
    audio_missing_text: str     # Kalimat TTS untuk berkas tersebut (dipakai generate_audio.py)
    prompt_rule: str            # Aturan penilaian untuk prompt VLM
    ok_label: str               # Teks lencana saat lolos
    fail_label: str             # Teks lencana saat tidak terdeteksi
    short_label: str = ""       # Nama ringkas untuk lencana sempit; kosong = pakai `label`
    reports_color: bool = False # Warna item relevan untuk penilaian dan ditampilkan ke operator
    required_default: bool = True  # Aktif secara bawaan; operator dapat mengubahnya
    qualifier: Optional[Qualifier] = None

    def to_public_dict(self) -> dict:
        """Bentuk item untuk frontend lewat `GET /api/ppe-rules`.

        Hanya sifat tampilan dan penilaian; teks prompt dan audio tetap di server.
        """
        return {
            "key": self.key,
            "label": self.label,
            "short_label": self.short_label or self.label,
            "icon": self.icon,
            "icon_name": self.icon_name,
            "ok_label": self.ok_label,
            "fail_label": self.fail_label,
            "reports_color": self.reports_color,
            "required": self.required_default,
            "qualifier": (
                {"key": self.qualifier.key, "fail_label": self.qualifier.fail_label}
                if self.qualifier is not None else None
            ),
        }

    def is_satisfied(self, result: dict) -> bool:
        """Apakah hasil pemeriksaan satu item memenuhi syarat.

        `result` adalah dict berisi minimal `detected`, ditambah field qualifier
        bila item ini punya syarat tambahan.
        """
        if not result.get("detected", False):
            return False
        if self.qualifier is not None:
            return bool(result.get(self.qualifier.key, False))
        return True


# ---------------------------------------------------------------------------
# Katalog APD
#
# Nilai-nilai di bawah menyalin persis perilaku yang berlaku sebelum berkas ini
# dibuat, supaya pemindahan ke definisi terpusat tidak mengubah hasil inspeksi.
# ---------------------------------------------------------------------------

PPE_ITEMS: list[PPEItem] = [
    PPEItem(
        key="helm",
        label="Helm Keselamatan",
        short_label="Helm",
        icon="🪖",
        icon_name="hard-hat",
        missing_label="Helm Keselamatan",
        audio_missing="kurang_helm",
        audio_missing_text="Helm belum dipakai. Akses ditolak.",
        ok_label="Terpasang",
        fail_label="Tidak Ada",
        # T48 (keputusan pengguna 05-10): yang dinilai helm DIPAKAI, bukan dipakai
        # sempurna. Helm di atas rambut lebat (apd_10) sempat ditolak.
        prompt_rule=(
            "HELM KESELAMATAN (Safety Helmet / Hard Hat):\n"
            "   - Wajib memakai helm keselamatan proyek/industri DI KEPALA.\n"
            "   - WARNA BEBAS (putih, kuning, merah, biru, orange, dll semuanya sah dan diizinkan).\n"
            "   - Tetap sah walau rambut tebal/panjang terlihat di bawahnya, posisinya agak miring,\n"
            "     atau tali dagu tidak terlihat.\n"
            "   - Topi kain biasa, topi baseball, atau kupluk BUKAN helm keselamatan;\n"
            "     helm yang dipegang atau digantung (tidak di kepala) = tidak dipakai."
        ),
    ),
    PPEItem(
        key="rompi",
        label="Rompi Keselamatan",
        short_label="Rompi",
        reports_color=True,
        icon="🦺",
        icon_name="safety-vest",
        missing_label="Rompi Keselamatan Orange/Kuning",
        audio_missing="kurang_rompi",
        audio_missing_text="Rompi keselamatan belum sesuai. Akses ditolak.",
        ok_label="Terpasang",
        fail_label="Tidak Ada",
        # Bentuk dinilai terpisah dari warna: di uji T35 baju/kaos kuning (termasuk
        # motif hitam-kuning) dikira rompi karena aturan lama hanya menekankan warna.
        prompt_rule=(
            "ROMPI KESELAMATAN (Safety Vest / Hi-Vis Vest):\n"
            "   - Rompi keselamatan = pakaian luar TANPA LENGAN yang dipakai DI ATAS baju/kaos,\n"
            "     biasanya terbuka di depan (resleting/perekat) dan punya PITA REFLEKTIF\n"
            "     (garis perak/abu mengkilap) melintang di dada atau perut.\n"
            "   - Kaos, kemeja, jaket, atau seragam berwarna kuning/oranye BUKAN rompi keselamatan,\n"
            "     walaupun warnanya sama -> detected = false."
        ),
        qualifier=Qualifier(
            key="is_valid_color",
            prompt_rule=(
                # Warna hi-vis disebut satu per satu: di validasi T36a rompi hijau
                # stabilo ditulis model "green" lalu dinilai tidak sah.
                "   - Jika rompi ada, nilai warnanya: ORANYE, KUNING, atau HIJAU STABILO / LIME / NEON\n"
                "     (hi-vis) -> is_valid_color = true; rompi biru, hitam, merah, abu-abu, atau hijau tua\n"
                "     -> is_valid_color = false."
            ),
            fail_label="Bukan Hi-Vis",
        ),
    ),
    PPEItem(
        key="celana",
        label="Celana Panjang",
        short_label="Celana",
        icon="👖",
        icon_name="trousers",
        missing_label="Celana Panjang",
        audio_missing="kurang_celana",
        audio_missing_text="Celana panjang belum dipakai. Akses ditolak.",
        ok_label="Panjang",
        fail_label="Pendek",
        prompt_rule=(
            "CELANA PANJANG:\n"
            "   - Wajib memakai celana panjang (jeans, celana kerja, celana kain, cargo).\n"
            "   - Celana pendek atau celana selutut TIDAK DIIZINKAN."
        ),
    ),
    PPEItem(
        key="sepatu",
        label="Sepatu Tertutup",
        short_label="Sepatu",
        icon="👞",
        icon_name="sport-shoe",
        missing_label="Sepatu Tertutup",
        audio_missing="kurang_sepatu",
        audio_missing_text="Sepatu tertutup belum dipakai. Akses ditolak.",
        ok_label="Tertutup",
        fail_label="Terbuka/Sandal",
        # T48: jenis, warna, dan merek tidak dinilai; yang penting kaki tertutup
        # (apd_4 bersepatu tertutup sempat ditolak).
        prompt_rule=(
            "SEPATU TERTUTUP:\n"
            "   - Wajib alas kaki tertutup yang menutupi jari dan punggung kaki: safety boots,\n"
            "     sepatu kerja, sepatu kets/sneaker, sepatu kulit. Jenis, warna, dan merek bebas.\n"
            "   - Tetap sah walau sebagian sepatu tertutup ujung celana, asalkan bentuk sepatunya terlihat."
        ),
        qualifier=Qualifier(
            key="is_closed_shoes",
            prompt_rule=(
                "   - Sandal, selop, sandal jepit, atau telanjang kaki TIDAK DIIZINKAN "
                "(is_closed_shoes = false)."
            ),
            fail_label="Terbuka/Sandal",
        ),
    ),
    # Dua item di bawah umum di lokasi kerja tertentu, tetapi tidak di semua
    # lokasi; karena itu mati secara bawaan dan dinyalakan operator bila perlu.
    # Keduanya belum punya pemeriksa heuristik lokal, jadi di mode offline
    # hasilnya "tidak dapat diperiksa" dan gerbang tetap tertutup.
    PPEItem(
        key="kacamata",
        label="Kacamata Safety",
        short_label="Kacamata",
        icon="🥽",
        icon_name="rectangle-goggles",
        missing_label="Kacamata Safety",
        audio_missing="kurang_kacamata",
        audio_missing_text="Kacamata safety belum dipakai. Akses ditolak.",
        ok_label="Terpasang",
        fail_label="Tidak Ada",
        required_default=False,
        prompt_rule=(
            "KACAMATA SAFETY (Safety Glasses / Goggles):\n"
            "   - Wajib memakai kacamata pelindung atau goggles di depan mata.\n"
            "   - Kacamata baca/minus biasa tanpa pelindung samping, atau kacamata "
            "yang dinaikkan ke dahi, TIDAK DIHITUNG."
        ),
    ),
    PPEItem(
        key="sarung_tangan",
        label="Sarung Tangan",
        short_label="Sarung Tangan",
        icon="🧤",
        icon_name="hand",
        missing_label="Sarung Tangan",
        audio_missing="kurang_sarung_tangan",
        audio_missing_text="Sarung tangan belum dipakai. Akses ditolak.",
        ok_label="Terpasang",
        fail_label="Tidak Ada",
        required_default=False,
        prompt_rule=(
            "SARUNG TANGAN KERJA (Work Gloves):\n"
            "   - Wajib memakai sarung tangan kerja di KEDUA tangan.\n"
            "   - Bila salah satu tangan terlihat tanpa sarung tangan, atau kedua "
            "tangan tidak terlihat sama sekali, anggap TIDAK terdeteksi."
        ),
    ),
]


# Aturan tingkat sistem, bukan milik satu item. Dipisah supaya prompt tetap bisa
# dirakit dari katalog tanpa kehilangan pemeriksaan anti-spoofing.
# Kunci jawaban VLM untuk anti-spoofing: false = subjek bukan orang fisik nyata.
REAL_PERSON_KEY = "orang_nyata"

ANTI_SPOOF_RULE = (
    "VALIDASI ORANG NYATA (Anti-Spoofing):\n"
    "   - Subjek wajib merupakan orang fisik nyata yang sedang berdiri untuk diinspeksi.\n"
    "   - Jika gambar hanyalah foto yang ditampilkan di layar smartphone/laptop atau "
    f"cetakan kertas yang diarahkan ke kamera, isi {REAL_PERSON_KEY} = false."
)

SPOOF_MISSING_LABEL = "Bukan Orang Fisik Nyata (Terdeteksi Foto/Layar)"


# ---------------------------------------------------------------------------
# Akses katalog
# ---------------------------------------------------------------------------

def get_items() -> list[PPEItem]:
    """Seluruh item di katalog, aktif maupun tidak, dengan status aktif terkini.

    Dipakai untuk hal yang harus mengenal semua item: laporan, ekspor CSV,
    pembangkit audio, dan daftar checkbox di dashboard.
    """
    return apply_required_overrides(_active_overrides)


def get_active_items() -> list[PPEItem]:
    """Item yang sedang diperiksa — dasar prompt VLM, engine lokal, dan gerbang."""
    return [item for item in get_items() if item.required_default]


def get_item_by_missing_label(label: str) -> Optional[PPEItem]:
    """Item yang `missing_label`-nya persis `label`, atau None.

    `missing_items` pada hasil inspeksi selalu dihitung oleh `evaluate()`, jadi
    labelnya bisa dipetakan balik ke item tanpa menebak lewat substring.
    """
    for item in PPE_ITEMS:
        if item.missing_label == label:
            return item
    return None


def get_item(key: str) -> Optional[PPEItem]:
    """Satu item berdasarkan kuncinya, atau None bila tidak dikenal."""
    for item in PPE_ITEMS:
        if item.key == key:
            return item
    return None


def item_keys() -> list[str]:
    """Urutan kunci item, dipakai untuk kolom laporan dan urutan lencana."""
    return [item.key for item in PPE_ITEMS]


def apply_required_overrides(overrides: dict) -> list[PPEItem]:
    """Katalog dengan status wajib ditimpa pilihan operator.

    Dipakai oleh pengaturan runtime: susunan item tetap dari berkas ini, hanya
    kolom `required_default` yang boleh berubah. Kunci yang tidak dikenal
    diabaikan agar berkas pengaturan lama tidak merusak sistem.
    """
    if not overrides:
        return list(PPE_ITEMS)
    return [
        replace(item, required_default=bool(overrides[item.key]))
        if item.key in overrides else item
        for item in PPE_ITEMS
    ]


# ---------------------------------------------------------------------------
# Status aktif dari operator
# ---------------------------------------------------------------------------

_SETTINGS_KEY = "ppe_active"
_settings_lock = threading.Lock()


def _load_active_overrides() -> dict:
    """Pilihan tersimpan, hanya untuk kunci yang masih ada di katalog."""
    stored = runtime_settings.load().get(_SETTINGS_KEY, {})
    if not isinstance(stored, dict):
        return {}
    known = {item.key for item in PPE_ITEMS}
    overrides = {k: bool(v) for k, v in stored.items() if k in known}
    # Berkas yang mematikan semua item akan membuka gerbang untuk siapa pun;
    # lebih aman kembali ke bawaan katalog.
    if overrides and not any(
        overrides.get(item.key, item.required_default) for item in PPE_ITEMS
    ):
        logger.warning("Pengaturan tersimpan mematikan semua item APD; memakai bawaan katalog.")
        return {}
    return overrides


# Kosong (= bawaan katalog) sampai load_settings() dipanggil saat startup, supaya
# mengimpor modul ini tidak membaca disk sebelum DATA_DIR siap.
_active_overrides: dict = {}


def load_settings():
    """Memuat pilihan item aktif dari runtime_settings.json."""
    global _active_overrides
    with _settings_lock:
        _active_overrides = _load_active_overrides()


def set_active(changes: dict) -> list[PPEItem]:
    """Menghidupkan/mematikan item, lalu menyimpannya agar bertahan setelah restart.

    `changes` berisi {kunci_item: bool}. Menolak kunci yang tidak dikenal dan
    kombinasi yang mematikan semua item — tanpa satu pun item aktif, setiap
    pekerja akan dinyatakan lengkap.
    """
    global _active_overrides
    known = {item.key for item in PPE_ITEMS}
    unknown = [k for k in changes if k not in known]
    if unknown:
        raise ValueError(f"Item APD tidak dikenal: {', '.join(unknown)}")

    with _settings_lock:
        merged = {**_active_overrides, **{k: bool(v) for k, v in changes.items()}}
        if not any(merged.get(item.key, item.required_default) for item in PPE_ITEMS):
            raise ValueError("Minimal satu item APD harus tetap aktif.")
        _active_overrides = merged
        runtime_settings.update(_SETTINGS_KEY, merged)
    return get_items()


# ---------------------------------------------------------------------------
# Perakitan prompt VLM
# ---------------------------------------------------------------------------

def build_prompt_rules(items: Optional[list[PPEItem]] = None) -> str:
    """Bagian aturan penilaian pada prompt, dinomori sesuai urutan katalog."""
    items = items if items is not None else get_active_items()
    blok = [f"0. {ANTI_SPOOF_RULE}"]

    for nomor, item in enumerate(items, start=1):
        teks = item.prompt_rule
        if item.qualifier is not None:
            teks = f"{teks}\n{item.qualifier.prompt_rule}"
        blok.append(f"{nomor}. {teks}")

    return "\n\n".join(blok)


def build_json_shape(items: Optional[list[PPEItem]] = None) -> str:
    """Bentuk JSON ringkas yang diminta dari VLM, diturunkan dari katalog.

    Hanya nilai yang dipakai `evaluate` (plus warna untuk ditampilkan dan tanda
    anti-spoofing). Deskripsi bebas, `is_complete`, `missing_items`, dan `notes`
    sengaja tidak diminta: kesimpulan dihitung sistem, dan menulis teks bebas
    membuat VLM lokal ~2x lebih lambat (T35: 7,8 -> 3,6 dtk) tanpa menambah akurasi.
    """
    items = items if items is not None else get_active_items()
    fields = []
    for item in items:
        field = ['"detected": true/false']
        if item.reports_color:
            field.append('"color": "<warna>"')
        if item.qualifier is not None:
            field.append(f'"{item.qualifier.key}": true/false')
        fields.append(f'"{item.key}": {{' + ", ".join(field) + "}")
    return '{"items": {' + ", ".join(fields) + f'}}, "{REAL_PERSON_KEY}": true/false}}'



def evaluate(results: dict, items: Optional[list[PPEItem]] = None) -> tuple[bool, list[str]]:
    """Menghitung kelengkapan dari hasil per item.

    Mengembalikan (is_complete, missing_items). Hanya item aktif yang
    menentukan kelulusan.
    """
    items = items if items is not None else get_active_items()
    missing = []
    for item in items:
        if not item.required_default:
            continue
        if not item.is_satisfied(results.get(item.key, {})):
            missing.append(item.missing_label)
    return (len(missing) == 0), missing
