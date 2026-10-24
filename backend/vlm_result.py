"""Hasil inspeksi dan penguraian jawaban VLM, tanpa mesin atau perangkat."""

from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import ppe_rules


class ItemResult(BaseModel):
    """Hasil pemeriksaan satu item APD.

    Bentuknya sengaja longgar: syarat tambahan seperti `is_valid_color` (rompi)
    atau `is_closed_shoes` (sepatu) masuk sebagai field ekstra sesuai definisi
    di `ppe_rules`, bukan sebagai kelas khusus per item. Dengan begitu item APD
    baru tidak memerlukan kelas model baru.
    """

    model_config = ConfigDict(extra="allow")

    detected: bool = Field(default=False, description="Apakah item terdeteksi dipakai")
    color: str = Field(default="", description="Warna item bila relevan")
    description: str = Field(default="", description="Keterangan singkat item")

    @model_validator(mode="before")
    @classmethod
    def _null_means_not_given(cls, data):
        """`null` dari VLM = nilai tidak diisi, jadi nilai bawaan yang berlaku.

        Gemini menjawab `"color": null` untuk orang tanpa rompi (T39a). Tanpa ini
        seluruh jawaban gagal divalidasi, dianggap kegagalan VLM utama, dilempar ke
        cadangan, dan dua kali berturut-turut membuat pemutus sirkuit menganggap
        utama mati. Syarat (qualifier) yang null dianggap tidak terpenuhi.
        """
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class InspectionResult(BaseModel):
    """Hasil inspeksi APD lengkap, dikunci pada katalog `ppe_rules`."""

    items: dict[str, ItemResult] = Field(default_factory=dict, description="Hasil per item APD, dikunci nama item")
    is_complete: bool = Field(default=False, description="True jika seluruh item wajib terpenuhi")
    missing_items: List[str] = Field(default_factory=list, description="Nama APD yang belum memenuhi syarat")
    notes: str = Field(default="", description="Ringkasan hasil inspeksi dalam Bahasa Indonesia")
    inference_source: str = Field(
        default="",
        description="Sumber keputusan: VLM_LIVE:<penyedia>/<model> (utama) atau VLM_CADANGAN:<penyedia>/<model>",
    )
    inference_time_ms: float = Field(default=0.0, description="Durasi inspeksi dalam milidetik")
    decided_by: str = Field(default="", description="VLM yang memutuskan: 'utama' atau 'cadangan'")
    is_system_unavailable: bool = Field(
        default=False,
        description="True jika utama dan cadangan sama-sama gagal: TIDAK ada keputusan, pekerja diminta menunggu",
    )

    def item(self, key: str) -> ItemResult:
        """Hasil satu item; item yang tidak dinilai dianggap tidak terdeteksi."""
        return self.items.get(key) or ItemResult()


APDInspectionResult = InspectionResult

_SPOOF_MARKER = "bukan orang fisik"


def _is_spoof_rejection(missing_items) -> bool:
    """Apakah model menolak subjek sebagai foto/layar, dengan ejaan apa pun."""
    return any(isinstance(m, str) and _SPOOF_MARKER in m.casefold() for m in (missing_items or []))


def _parse_vlm_payload(data: dict, aktif=None) -> InspectionResult:
    """Mengubah balasan JSON VLM menjadi hasil yang dikunci pada katalog.

    Keputusan kelengkapan dihitung ulang dari `ppe_rules`, bukan diambil
    mentah dari balasan model: dengan begitu aturan wajib/opsional yang
    berlaku di sistem selalu yang menentukan, bukan tafsir model.

    Penolakan tingkat sistem dari model — terutama anti-spoofing — tetap
    dihormati karena tidak berasal dari katalog item.
    """
    mentah = data.get("items")
    if not isinstance(mentah, dict):
        # Balasan bentuk lama (item di tingkat teratas) tetap diterima
        mentah = {k: data.get(k) for k in ppe_rules.item_keys() if isinstance(data.get(k), dict)}

    aktif = aktif if aktif is not None else ppe_rules.get_active_items()
    items = {}
    for item in aktif:
        nilai = mentah.get(item.key)
        items[item.key] = (
            ItemResult(**nilai) if isinstance(nilai, dict) else ItemResult(description="Tidak dinilai oleh VLM")
        )

    is_complete, missing = ppe_rules.evaluate({k: v.model_dump() for k, v in items.items()}, aktif)

    # Satu-satunya penolakan dari teks bebas model yang dihormati adalah
    # anti-spoofing: aturan itu ada di prompt tetapi bukan item katalog, jadi
    # tidak bisa dihitung ulang dari `items`. Nama item di `missing_items`
    # sengaja diabaikan — sistem menghitungnya sendiri dari `items` — karena
    # model menulisnya dengan ejaan yang berubah-ubah ("Helm keselamatan" vs
    # "Helm Keselamatan") sehingga pencocokan teks menghasilkan duplikat, dan
    # menyebut item yang sedang dimatikan tidak boleh menolak pekerja.
    # Bentuk sekarang: `orang_nyata` = false. Penanda lama di `missing_items`
    # tetap dihormati (balasan penyedia dengan prompt lama / uji lama).
    if data.get(ppe_rules.REAL_PERSON_KEY) is False or _is_spoof_rejection(data.get("missing_items")):
        missing = [ppe_rules.SPOOF_MISSING_LABEL] + missing
        is_complete = False

    return InspectionResult(
        items=items,
        is_complete=is_complete,
        missing_items=missing,
        notes=str(data.get("notes", "")),
    )
