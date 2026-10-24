"""Pemilihan dan SQL retensi; commit dan penghapusan setelahnya dikendalikan fasad."""

import sqlite3
import time
from pathlib import Path
from .config import cfg


SECONDS_PER_DAY = 24 * 60 * 60

BYTES_PER_MB = 1024**2


def _cutoff(now: float, days: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - days * SECONDS_PER_DAY))


def _photos_before(conn: sqlite3.Connection, cutoff: str) -> list[str]:
    rows = conn.execute(
        "SELECT snapshot_filename FROM worker_inspections WHERE timestamp < ? AND snapshot_filename != ''",
        (cutoff,),
    )
    return [row["snapshot_filename"] for row in rows.fetchall()]


def _expire_audits(conn: sqlite3.Connection, now: float) -> tuple[int, list[str]]:
    """Hapus audit kedaluwarsa; kembalikan jumlah dan nama foto untuk dihapus fasad setelah commit."""
    cutoff = _cutoff(now, cfg.RETENTION_AUDIT_DAYS)
    photos = _photos_before(conn, cutoff)
    deleted = conn.execute("DELETE FROM worker_inspections WHERE timestamp < ?", (cutoff,)).rowcount
    return deleted, photos


def _expire_photos(conn: sqlite3.Connection, now: float) -> list[str]:
    """Kosongkan referensi foto kedaluwarsa; fasad menghapus berkasnya setelah commit."""
    cutoff = _cutoff(now, cfg.RETENTION_PHOTO_DAYS)
    photos = _photos_before(conn, cutoff)
    conn.execute(
        "UPDATE worker_inspections SET snapshot_filename = '' WHERE timestamp < ? AND snapshot_filename != ''",
        (cutoff,),
    )
    return photos


def _oldest_photos_over(snapshots_dir: Path, max_bytes: float) -> list[str]:
    """Nama foto terlama yang harus dihapus supaya total ukuran folder <= max_bytes."""
    photos = []
    for path in snapshots_dir.glob("*.jpg"):
        try:
            st = path.stat()
        except OSError:
            continue
        photos.append((st.st_mtime, st.st_size, path.name))
    excess = sum(size for _, size, _ in photos) - max_bytes
    names = []
    for _, size, name in sorted(photos, key=lambda photo: photo[0]):
        if excess <= 0:
            break
        names.append(name)
        excess -= size
    return names


def clear_photo_names(conn: sqlite3.Connection, names: list[str]):
    for fname in names:
        conn.execute("UPDATE worker_inspections SET snapshot_filename = '' WHERE snapshot_filename = ?", (fname,))
