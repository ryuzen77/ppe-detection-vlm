"""Suara nama pekerja saat lolos (T34d): "APD lengkap. Silakan masuk, Pak/Bu <nama panggilan>."

- Satu MP3 utuh per pekerja (lebih alami daripada menyambung dua berkas), dibuat SEKALI saat
  pendaftaran/ubah profil, diputar offline di gerbang.
- Mesin suara = gTTS (keputusan pengguna 19-10, opsi A): kalimat dikirim ke layanan suara
  Google. Yang dikirim HANYA sapaan + nama panggilan — bukan nama lengkap, nomor pegawai, atau
  wajah — dan tercatat di formulir persetujuan. Setiap pembuatan dicatat di security log.
- Gagal (tanpa internet, layanan menolak) = pekerja tetap terdaftar, saat lolos suara umum
  dipakai; tidak pernah menghambat pendaftaran atau gerbang.
- MP3 = data pribadi: di DATA_DIR (bukan aset rilis) dan dihapus bersama data wajah.
"""

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import messages, security_log
from .config import cfg
from .generate_audio import TTS_LANG
from .worker_store import Worker

logger = logging.getLogger(__name__)

PROVIDER = "gtts"
# Pembuatan suara di thread sendiri: jawaban API pendaftaran tidak menunggu jaringan
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Voice_Worker")


def voice_path(worker_id: int) -> Path:
    return cfg.VOICE_DIR / f"worker_{worker_id}.mp3"


def voice_ready(worker_id: int) -> bool:
    return voice_path(worker_id).is_file()


def voice_text(worker: Worker) -> Optional[str]:
    """Kalimat yang diucapkan; None bila sapaan atau nama panggilan belum ada (pekerja lama)."""
    if not worker.salutation or not worker.nickname:
        return None
    return messages.VOICE_PASS_NAMED.format(salutation=worker.salutation, nickname=worker.nickname)


def _gtts_save(text: str, target: Path) -> None:
    from gtts import gTTS

    gTTS(text=text, lang=TTS_LANG, slow=False, timeout=cfg.VOICE_TTS_TIMEOUT_SECONDS).save(str(target))


def synthesize(worker: Worker, save: Optional[Callable[[str, Path], None]] = None) -> bool:
    """Buat (atau ganti) MP3 nama pekerja. Ditulis ke berkas sementara lalu dipindah, supaya
    gerbang tidak pernah memutar berkas setengah jadi. Tidak pernah melempar galat.
    `save` dicari saat dipanggil (bukan nilai bawaan argumen) supaya tes bisa menggantinya
    tanpa pernah menghubungi layanan suara sungguhan."""
    save = save or _gtts_save
    text = voice_text(worker)
    if text is None:
        delete([worker.id])
        return False
    target = voice_path(worker.id)
    partial = target.with_suffix(".part")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        save(text, partial)
        partial.replace(target)
    except Exception as e:
        partial.unlink(missing_ok=True)
        logger.warning(messages.LOG_VOICE_FAILED.format(worker_id=worker.id, error=e))
        security_log.record(security_log.WORKER_VOICE_CREATED, worker_id=worker.id, provider=PROVIDER, ok=False)
        return False
    logger.info(messages.LOG_VOICE_CREATED.format(worker_id=worker.id))
    security_log.record(security_log.WORKER_VOICE_CREATED, worker_id=worker.id, provider=PROVIDER, ok=True)
    return True


def request(worker: Worker) -> Future:
    """Pembuatan suara di latar; pemanggil (API) tidak menunggu jaringan."""
    return _executor.submit(synthesize, worker)


def delete(worker_ids: Iterable[int]) -> int:
    """Hapus MP3 nama (hak hapus & retensi). Jumlah berkas yang dihapus."""
    removed = 0
    for worker_id in worker_ids:
        path = voice_path(worker_id)
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def pass_voice(worker_id: Optional[int]) -> Optional[Path]:
    """Berkas suara untuk keputusan lolos pekerja yang dikenali; None = suara umum."""
    if worker_id is None:
        return None
    path = voice_path(worker_id)
    return path if path.is_file() else None
