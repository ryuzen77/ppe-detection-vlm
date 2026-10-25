"""Berkas foto bukti; reservasi nama dan lock dimiliki ReportManager."""

import logging
import os
import time
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
from ..config import cfg
from .. import messages

logger = logging.getLogger(__name__)


def snapshot_stem(track_id, now):
    return f"worker_{track_id}_{time.strftime('%Y%m%d_%H%M%S', now)}"


SNAPSHOT_TMP_SUFFIX = ".tmp"


def _remove_partial_snapshots(snapshots_dir: Path):
    """Foto sementara yang tertinggal karena listrik padam/crash saat ditulis."""
    partial = list(snapshots_dir.glob(f"*{SNAPSHOT_TMP_SUFFIX}"))
    for p in partial:
        try:
            p.unlink()
        except OSError:
            pass
    if partial:
        logger.warning(messages.SNAPSHOT_TMP_REMOVED.format(count=len(partial)))


def _write_snapshot(path: Path, image: np.ndarray) -> bool:
    """Menulis JPEG secara atomik: berkas sementara di-fsync lalu diganti nama.

    Listrik padam di tengah penulisan tidak meninggalkan foto rusak dengan
    nama final, dan kegagalan (mis. disk penuh) terdeteksi. Dulu hasil
    cv2.imwrite tidak diperiksa, sehingga audit bisa merujuk foto yang
    tidak pernah tertulis.
    """
    tmp = path.with_name(path.name + SNAPSHOT_TMP_SUFFIX)
    try:
        ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.SNAPSHOT_JPEG_QUALITY])
        if not ok:
            raise ValueError("cv2.imencode gagal")
        with open(tmp, "wb") as f:
            f.write(buf.tobytes())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.error(messages.SNAPSHOT_WRITE_FAILED.format(name=path.name, error=e))
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _reserve_snapshot_name(snapshots_dir: Path, in_progress: set[str], stem: str) -> str:
    """`<stem>.jpg`, atau `<stem>_2.jpg`, `_3`, ... bila nama itu sudah ada / sedang ditulis.

    T64: ID pelacak + detik saja bisa kembar (dua inspeksi di detik yang sama) dan foto
    pertama tertimpa, sehingga bukti audit menunjuk orang yang salah.
    """
    n = 1
    while True:
        name = f"{stem}.jpg" if n == 1 else f"{stem}_{n}.jpg"
        if name not in in_progress and not (snapshots_dir / name).exists():
            in_progress.add(name)
            return name
        n += 1


def get_snapshot_path(snapshots_dir: Path, filename: str) -> Optional[Path]:
    """Resolves snapshot image path safely to avoid path traversal."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return None
    safe_name = os.path.basename(filename)
    path = (snapshots_dir / safe_name).resolve()
    snapshots_root = snapshots_dir.resolve()
    try:
        if path.is_relative_to(snapshots_root) and path.exists() and path.is_file():
            return path
    except AttributeError:
        if str(path).startswith(str(snapshots_root)) and path.exists() and path.is_file():
            return path
    return None


def _delete_photos(snapshots_dir: Path, filenames: list[str]) -> tuple[int, int]:
    deleted_count = 0
    reclaimed_bytes = 0
    for fname in filenames:
        if not fname:
            continue
        path = get_snapshot_path(snapshots_dir, fname)
        if path:
            try:
                reclaimed_bytes += path.stat().st_size
                path.unlink()
                deleted_count += 1
            except OSError:
                pass
    return deleted_count, reclaimed_bytes
