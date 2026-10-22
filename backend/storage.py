"""Menyiapkan direktori data dan memindahkan data dari tata letak lama.

Sebelum T12, audit, foto bukti, dan pilihan operator tersimpan di dalam
`backend/`. Pemindahan berjalan sekali, otomatis, saat server pertama kali
dijalankan dengan tata letak baru. Berkas yang sudah ada di tujuan tidak pernah
ditimpa: data lama yang bentrok dibiarkan di tempatnya dan dilaporkan.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

LEGACY_DIR = Path(__file__).resolve().parent


def _move(src: Path, dst: Path, moved: list, skipped: list):
    if not src.exists():
        return
    if dst.exists():
        skipped.append(src)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    moved.append(dst)


def _remove_if_empty(path: Path):
    try:
        path.rmdir()
    except OSError:
        pass  # Tidak ada, atau masih berisi berkas yang bentrok


def migrate_legacy_data(cfg) -> tuple[list, list]:
    """Memindahkan data dari `backend/` ke `cfg.DATA_DIR`. Mengembalikan (dipindah, dilewati)."""
    moved, skipped = [], []
    if cfg.DATA_DIR == LEGACY_DIR:
        return moved, skipped

    legacy_reports = LEGACY_DIR / "reports"

    # Basis data dipindah bersama berkas WAL-nya. Tanpa -wal, transaksi yang
    # belum di-checkpoint hilang; karena itu ketiganya hanya dipindah bila
    # basis data tujuan belum ada.
    legacy_db = legacy_reports / cfg.DB_PATH.name
    if legacy_db.exists():
        if cfg.DB_PATH.exists():
            skipped.append(legacy_db)
        else:
            for suffix in ("", "-wal", "-shm"):
                _move(
                    legacy_db.with_name(legacy_db.name + suffix),
                    cfg.DB_PATH.with_name(cfg.DB_PATH.name + suffix),
                    moved,
                    skipped,
                )

    # Cadangan sebelum migrasi skema (audit.v0.bak, ...)
    if legacy_reports.is_dir():
        for backup in sorted(legacy_reports.glob(f"{cfg.DB_PATH.stem}.v*.bak")):
            _move(backup, cfg.REPORTS_DIR / backup.name, moved, skipped)

    legacy_snapshots = legacy_reports / "snapshots"
    if legacy_snapshots.is_dir():
        for photo in sorted(legacy_snapshots.iterdir()):
            if photo.is_file():
                _move(photo, cfg.SNAPSHOTS_DIR / photo.name, moved, skipped)

    _move(LEGACY_DIR / cfg.CAMERA_STATE_PATH.name, cfg.CAMERA_STATE_PATH, moved, skipped)
    _move(LEGACY_DIR / cfg.RUNTIME_SETTINGS_PATH.name, cfg.RUNTIME_SETTINGS_PATH, moved, skipped)

    _remove_if_empty(legacy_snapshots)
    _remove_if_empty(legacy_reports)
    return moved, skipped


def prepare_data_dir(cfg):
    """Membuat struktur direktori data dan menjalankan pemindahan data lama."""
    cfg.SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    moved, skipped = migrate_legacy_data(cfg)
    if moved:
        logger.info(f"{len(moved)} berkas data dipindah dari {LEGACY_DIR} ke {cfg.DATA_DIR}")
    for path in skipped:
        logger.warning(
            f"{path} tidak dipindah karena tujuan sudah berisi "
            f"berkas bernama sama. Periksa dan gabungkan secara manual."
        )
