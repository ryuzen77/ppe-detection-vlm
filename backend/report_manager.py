import logging
import sqlite3
import threading
import json
import time
import os
import csv
import io
from pathlib import Path
from typing import Optional, List, Dict
import cv2
import numpy as np

from . import ppe_rules
from .config import cfg
from . import messages

logger = logging.getLogger(__name__)

# Label sumber keputusan VLM cadangan (lihat VLMEngine.label)
BACKUP_SOURCE_PREFIX = "VLM_CADANGAN:"

# Jalur data diatur lewat DATA_DIR di config, di luar direktori kode
DB_PATH = cfg.DB_PATH
SNAPSHOTS_DIR = cfg.SNAPSHOTS_DIR

# Versi skema, disimpan di `PRAGMA user_version`.
#   0 — skema awal: sebelas kolom tetap untuk helm, rompi, celana, dan sepatu
#   1 — hasil per item disimpan generik di `items_json`, mengikuti `ppe_rules`
SCHEMA_VERSION = 1

_CREATE_TABLE_V1 = """
    CREATE TABLE {name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        track_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        date_str TEXT NOT NULL,
        time_str TEXT NOT NULL,
        is_complete INTEGER NOT NULL,
        items_json TEXT NOT NULL DEFAULT '{{}}',
        missing_items TEXT,
        notes TEXT,
        inference_source TEXT,
        inference_time_ms REAL,
        snapshot_filename TEXT
    )
"""

_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_timestamp ON worker_inspections(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_is_complete ON worker_inspections(is_complete)",
)


def _legacy_row_to_items(row: sqlite3.Row) -> dict:
    """Mengemas kolom per item skema versi 0 ke bentuk `items_json`.

    Pemetaan ini sengaja ditulis tetap: ia menggambarkan skema lama yang sudah
    tidak akan berubah, bukan katalog APD yang berlaku sekarang.
    """
    return {
        "helm": {
            "detected": bool(row["helm_detected"]),
            "description": row["helm_desc"] or "",
        },
        "rompi": {
            "detected": bool(row["rompi_detected"]),
            "color": row["rompi_color"] or "",
            "is_valid_color": bool(row["rompi_valid"]),
            "description": row["rompi_desc"] or "",
        },
        "celana": {
            "detected": bool(row["celana_detected"]),
            "description": row["celana_desc"] or "",
        },
        "sepatu": {
            "detected": bool(row["sepatu_detected"]),
            "is_closed_shoes": bool(row["sepatu_closed"]),
            "description": row["sepatu_desc"] or "",
        },
    }


def _parse_json(text: Optional[str], default):
    try:
        return json.loads(text) if text else default
    except Exception:
        return default


class ReportManager:
    """Manages SQLite database storage for worker inspection records,
    JPEG snapshot image archiving, compliance statistics, and CSV exports."""

    def __init__(self, db_path: Path = DB_PATH, snapshots_dir: Path = SNAPSHOTS_DIR):
        # Hanya mencatat jalur. Folder dan migrasi skema dikerjakan open(),
        # supaya mengimpor modul ini tidak menyentuh disk.
        self.db_path = Path(db_path)
        self.snapshots_dir = Path(snapshots_dir)
        self._opened = False
        self._open_lock = threading.Lock()

    def open(self) -> "ReportManager":
        """Menyiapkan folder dan membawa skema ke versi terkini. Idempoten.

        Dipanggil saat startup; akses pertama juga memanggilnya, jadi pemanggil
        yang lupa tidak mendapati tabel yang belum ada.
        """
        with self._open_lock:
            if not self._opened:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.snapshots_dir.mkdir(parents=True, exist_ok=True)
                self._init_db()
                self._opened = True
        return self

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=cfg.DB_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_connection(self) -> sqlite3.Connection:
        if not self._opened:
            self.open()
        return self._connect()

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._migrate(conn)
        finally:
            conn.close()

    def _migrate(self, conn: sqlite3.Connection):
        """Membawa database ke `SCHEMA_VERSION` dalam satu transaksi.

        Bila salah satu langkah gagal, seluruh perubahan dibatalkan dan database
        tetap pada versi lamanya — tidak ada keadaan setengah jadi.
        """
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database {self.db_path} berversi skema {version}, lebih baru dari "
                f"yang dikenali kode ini ({SCHEMA_VERSION}). Perbarui aplikasi."
            )

        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'worker_inspections'"
        ).fetchone() is not None

        if has_table:
            self._backup_before_migration(version)

        # Transaksi dikendalikan manual: modul sqlite3 tidak membungkus DDL
        # dalam transaksi secara otomatis.
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        try:
            if not has_table:
                conn.execute(_CREATE_TABLE_V1.format(name="worker_inspections"))
            else:
                self._migrate_v0_to_v1(conn)
            for sql in _CREATE_INDEXES:
                conn.execute(sql)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _backup_before_migration(self, version: int):
        """Salinan utuh database sebelum migrasi, di samping berkas aslinya."""
        backup_path = self.db_path.with_name(f"{self.db_path.stem}.v{version}.bak")
        if backup_path.exists():
            return
        src = self._connect()
        dst = sqlite3.connect(str(backup_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        logger.info(f"Cadangan sebelum migrasi skema: {backup_path.name}")

    def _migrate_v0_to_v1(self, conn: sqlite3.Connection):
        """Sebelas kolom per item → satu kolom `items_json`. Seluruh baris dipertahankan."""
        old_seq = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'worker_inspections'"
        ).fetchone()

        conn.execute(_CREATE_TABLE_V1.format(name="worker_inspections_v1"))
        rows = conn.execute("SELECT * FROM worker_inspections ORDER BY id ASC").fetchall()
        conn.executemany(
            """
            INSERT INTO worker_inspections_v1 (
                id, track_id, timestamp, date_str, time_str, is_complete,
                items_json, missing_items, notes, inference_source,
                inference_time_ms, snapshot_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"], row["track_id"], row["timestamp"], row["date_str"],
                    row["time_str"], row["is_complete"],
                    json.dumps(_legacy_row_to_items(row), ensure_ascii=False),
                    row["missing_items"], row["notes"], row["inference_source"],
                    row["inference_time_ms"], row["snapshot_filename"],
                )
                for row in rows
            ],
        )
        conn.execute("DROP TABLE worker_inspections")
        conn.execute("ALTER TABLE worker_inspections_v1 RENAME TO worker_inspections")

        # Pertahankan penghitung AUTOINCREMENT agar id baris yang pernah dihapus
        # tidak dipakai ulang.
        if old_seq is not None:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'worker_inspections'",
                (old_seq[0],),
            )
        logger.info(f"Migrasi skema v0 -> v1: {len(rows)} baris dipindahkan.")

    def save_inspection(
        self,
        track_id: int,
        is_complete: bool,
        items: Dict[str, dict],
        missing_items: List[str],
        notes: str,
        inference_source: str,
        inference_time_ms: float,
        crop_img: Optional[np.ndarray] = None
    ) -> dict:
        """Saves inspection snapshot to disk and inserts record into SQLite.

        `items` berisi hasil per item APD, dikunci `PPEItem.key`.
        """
        now = time.localtime()
        iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", now)
        date_str = time.strftime("%Y-%m-%d", now)
        time_str = time.strftime("%H:%M:%S", now)
        file_time_slug = time.strftime("%Y%m%d_%H%M%S", now)

        snapshot_filename = ""
        if crop_img is not None and crop_img.size > 0:
            snapshot_filename = f"worker_{track_id}_{file_time_slug}.jpg"
            save_path = self.snapshots_dir / snapshot_filename
            try:
                cv2.imwrite(str(save_path), crop_img, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.SNAPSHOT_JPEG_QUALITY])
            except Exception as e:
                logger.error(f"Error saving snapshot image: {e}")
                snapshot_filename = ""

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO worker_inspections (
                    track_id, timestamp, date_str, time_str, is_complete,
                    items_json, missing_items, notes, inference_source,
                    inference_time_ms, snapshot_filename
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                track_id,
                iso_timestamp,
                date_str,
                time_str,
                1 if is_complete else 0,
                json.dumps(items, ensure_ascii=False),
                json.dumps(missing_items, ensure_ascii=False),
                notes,
                inference_source,
                inference_time_ms,
                snapshot_filename
            ))
            record_id = cursor.lastrowid
            conn.commit()

        return {
            "id": record_id,
            "track_id": track_id,
            "timestamp": iso_timestamp,
            "time_str": time_str,
            "is_complete": is_complete,
            "missing_items": missing_items,
            "snapshot_filename": snapshot_filename,
            "inference_source": inference_source,
            "inference_time_ms": inference_time_ms
        }

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict:
        rec = dict(row)
        rec["is_complete"] = bool(rec["is_complete"])
        rec["missing_items"] = _parse_json(rec["missing_items"], [])
        rec["items"] = _parse_json(rec.pop("items_json"), {})
        return rec

    def get_reports(self, limit: int = 50, offset: int = 0, status_filter: str = "all", date_filter: Optional[str] = None) -> dict:
        """Retrieves paginated inspection records with summary statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Global statistics
            cursor.execute("SELECT COUNT(*) as total FROM worker_inspections")
            total_count = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) as complete_count FROM worker_inspections WHERE is_complete = 1")
            complete_count = cursor.fetchone()["complete_count"]

            violation_count = total_count - complete_count
            compliance_rate = round((complete_count / total_count * 100.0), 1) if total_count > 0 else 100.0

            # Keputusan oleh VLM cadangan (utama gagal/terputus), T27
            cursor.execute("SELECT COUNT(*) AS n FROM worker_inspections WHERE inference_source LIKE ?",
                           (f"{BACKUP_SOURCE_PREFIX}%",))
            backup_count = cursor.fetchone()["n"]

            # Filter query
            conditions = []
            params = []
            if status_filter == "complete":
                conditions.append("is_complete = 1")
            elif status_filter == "incomplete":
                conditions.append("is_complete = 0")

            if date_filter:
                conditions.append("date_str = ?")
                params.append(date_filter)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            cursor.execute(f"""
                SELECT COUNT(*) as filtered_total FROM worker_inspections {where_clause}
            """, params)
            filtered_total = cursor.fetchone()["filtered_total"]

            query = f"""
                SELECT * FROM worker_inspections
                {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
            query_params = list(params) + [limit, offset]
            cursor.execute(query, query_params)
            records = [self._row_to_record(row) for row in cursor.fetchall()]

            return {
                "total_all": total_count,
                "complete_count": complete_count,
                "violation_count": violation_count,
                "compliance_rate": compliance_rate,
                "backup_count": backup_count,
                "filtered_total": filtered_total,
                "page_records": records
            }

    @staticmethod
    def _item_csv_text(item: ppe_rules.PPEItem, result: Optional[dict]) -> str:
        """Isi sel CSV satu item APD, diturunkan dari definisinya."""
        if result is None:
            # Item yang ditambahkan ke katalog setelah baris ini tercatat
            return messages.CSV_ITEM_NOT_ASSESSED
        if item.is_satisfied(result):
            color = result.get("color", "") if item.reports_color else ""
            return messages.CSV_ITEM_OK_COLOR.format(color=color) if color else messages.CSV_ITEM_OK
        if result.get("detected", False) and item.qualifier is not None:
            return item.qualifier.fail_label.upper()
        return item.fail_label.upper()

    def export_csv_text(self) -> str:
        """Exports all inspection records to a standard CSV string for HSE/K3 audit.

        Kolom per item APD dibangkitkan dari katalog `ppe_rules`.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        items = ppe_rules.get_items()

        writer.writerow(
            messages.CSV_HEADER_LEADING
            + [item.label for item in items]
            + messages.CSV_HEADER_TRAILING
        )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM worker_inspections ORDER BY id ASC")
            rows = cursor.fetchall()

            for i, row in enumerate(rows, start=1):
                missing_list = _parse_json(row["missing_items"], [])
                results = _parse_json(row["items_json"], {})
                status_str = messages.CSV_STATUS_COMPLETE if row["is_complete"] else messages.CSV_STATUS_INCOMPLETE

                writer.writerow(
                    [i, row["date_str"], row["time_str"], messages.CSV_WORKER_ID.format(track_id=row["track_id"]), status_str]
                    + [self._item_csv_text(item, results.get(item.key)) for item in items]
                    + ["; ".join(missing_list) if missing_list else messages.CSV_EMPTY,
                       row["inference_source"], row["inference_time_ms"],
                       row["notes"], row["snapshot_filename"]]
                )

        return output.getvalue()

    def get_snapshot_path(self, filename: str) -> Optional[Path]:
        """Resolves snapshot image path safely to avoid path traversal."""
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            return None
        safe_name = os.path.basename(filename)
        path = (self.snapshots_dir / safe_name).resolve()
        snapshots_root = self.snapshots_dir.resolve()
        try:
            if path.is_relative_to(snapshots_root) and path.exists() and path.is_file():
                return path
        except AttributeError:
            if str(path).startswith(str(snapshots_root)) and path.exists() and path.is_file():
                return path
        return None

    def _delete_photos(self, filenames: list[str]) -> tuple[int, int]:
        deleted_count = 0
        reclaimed_bytes = 0
        for fname in filenames:
            if not fname:
                continue
            path = self.get_snapshot_path(fname)
            if path:
                try:
                    reclaimed_bytes += path.stat().st_size
                    path.unlink()
                    deleted_count += 1
                except OSError:
                    pass
        return deleted_count, reclaimed_bytes

    def cleanup_old_data(self):
        """Pembersihan data sesuai kebijakan retensi (T20)."""
        now = time.time()
        deleted_photos = 0
        deleted_audits = 0
        reclaimed_bytes = 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Hapus audit (dan fotonya) yang melewati batas RETENTION_AUDIT_DAYS
                if cfg.RETENTION_AUDIT_DAYS > 0:
                    audit_cutoff = now - (cfg.RETENTION_AUDIT_DAYS * 86400)
                    audit_cutoff_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(audit_cutoff))
                    
                    cursor.execute("SELECT snapshot_filename FROM worker_inspections WHERE timestamp < ? AND snapshot_filename != ''", (audit_cutoff_str,))
                    audit_photos = [row["snapshot_filename"] for row in cursor.fetchall()]
                    
                    cursor.execute("DELETE FROM worker_inspections WHERE timestamp < ?", (audit_cutoff_str,))
                    deleted_audits += cursor.rowcount
                    conn.commit()
                    
                    d_count, r_bytes = self._delete_photos(audit_photos)
                    deleted_photos += d_count
                    reclaimed_bytes += r_bytes

                # 2. Hapus foto yang melewati batas RETENTION_PHOTO_DAYS
                if cfg.RETENTION_PHOTO_DAYS > 0:
                    photo_cutoff = now - (cfg.RETENTION_PHOTO_DAYS * 86400)
                    photo_cutoff_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(photo_cutoff))
                    
                    cursor.execute("SELECT snapshot_filename FROM worker_inspections WHERE timestamp < ? AND snapshot_filename != ''", (photo_cutoff_str,))
                    old_photos = [row["snapshot_filename"] for row in cursor.fetchall()]
                    
                    cursor.execute("UPDATE worker_inspections SET snapshot_filename = '' WHERE timestamp < ? AND snapshot_filename != ''", (photo_cutoff_str,))
                    conn.commit()
                    
                    d_count, r_bytes = self._delete_photos(old_photos)
                    deleted_photos += d_count
                    reclaimed_bytes += r_bytes

                # 3. Pengaman ukuran folder
                if cfg.RETENTION_MAX_PHOTO_GB > 0:
                    max_bytes = cfg.RETENTION_MAX_PHOTO_GB * 1024 * 1024 * 1024
                    photos = []
                    total_size = 0
                    for p in self.snapshots_dir.glob("*.jpg"):
                        try:
                            st = p.stat()
                            photos.append((st.st_mtime, p))
                            total_size += st.st_size
                        except OSError:
                            pass
                    
                    if total_size > max_bytes:
                        photos.sort(key=lambda x: x[0])  # oldest first
                        bytes_to_free = total_size - max_bytes
                        to_delete_names = []
                        for mtime, p in photos:
                            if bytes_to_free <= 0:
                                break
                            try:
                                size = p.stat().st_size
                                to_delete_names.append(p.name)
                                bytes_to_free -= size
                            except OSError:
                                pass
                        
                        # Update DB first, then delete files
                        for fname in to_delete_names:
                            cursor.execute("UPDATE worker_inspections SET snapshot_filename = '' WHERE snapshot_filename = ?", (fname,))
                        conn.commit()
                        
                        d_count, r_bytes = self._delete_photos(to_delete_names)
                        deleted_photos += d_count
                        reclaimed_bytes += r_bytes

            if deleted_photos > 0 or deleted_audits > 0:
                logger.info(f"Retensi data: menghapus {deleted_audits} audit dan {deleted_photos} foto "
                            f"(membebaskan {reclaimed_bytes / (1024*1024):.1f} MB).")
        except Exception as e:
            logger.error(f"Gagal membersihkan data tua: {e}")

report_mgr = ReportManager()
