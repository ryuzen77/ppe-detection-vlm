"""Fasad audit: koneksi, transaksi, lock dan urutan tulis tetap dikendalikan di sini."""

import json
import logging
import threading
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from time import struct_time
from typing import Optional, List, Dict
from sqlite3 import Connection
import numpy as np
from . import audit_db, snapshot_store, audit_queries, audit_export, attendance, retention
from . import ppe_rules
from .config import cfg
from .disk_guard import BYTES_PER_GB
from .audit_db import SCHEMA_VERSION as SCHEMA_VERSION
from .audit_queries import (
    BACKUP_SOURCE_PREFIX as BACKUP_SOURCE_PREFIX,
    RECOGNITION_SQL as RECOGNITION_SQL,
    HELD_COUNT_SQL as HELD_COUNT_SQL,
)
from .audit_export import CSV_BOM as CSV_BOM
from .snapshot_store import SNAPSHOT_TMP_SUFFIX as SNAPSHOT_TMP_SUFFIX
from .retention import SECONDS_PER_DAY as SECONDS_PER_DAY, BYTES_PER_MB

logger = logging.getLogger(__name__)
DB_PATH = cfg.DB_PATH
SNAPSHOTS_DIR = cfg.SNAPSHOTS_DIR


class ReportManager:
    """Manages SQLite database storage for worker inspection records,
    JPEG snapshot image archiving, compliance statistics, and CSV exports.
    """

    def __init__(self, db_path: Path = DB_PATH, snapshots_dir: Path = SNAPSHOTS_DIR):
        # Hanya mencatat jalur. Folder dan migrasi skema dikerjakan open(),
        # supaya mengimpor modul ini tidak menyentuh disk.
        self.db_path = Path(db_path)
        self.snapshots_dir = Path(snapshots_dir)
        self._opened = False
        self._open_lock = threading.Lock()
        # Nama foto yang sedang ditulis thread VLM lain (T64): dipesan di bawah lock
        # supaya dua inspeksi paralel tidak memilih nama yang sama.
        self._snapshot_lock = threading.Lock()
        self._snapshots_in_progress: set[str] = set()

    def open(self) -> "ReportManager":
        """Menyiapkan folder dan membawa skema ke versi terkini. Idempoten.

        Dipanggil saat startup; akses pertama juga memanggilnya, jadi pemanggil
        yang lupa tidak mendapati tabel yang belum ada.
        """
        with self._open_lock:
            if not self._opened:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.snapshots_dir.mkdir(parents=True, exist_ok=True)
                self._remove_partial_snapshots()
                self._init_db()
                self._opened = True
        return self

    def _remove_partial_snapshots(self):
        """Foto sementara yang tertinggal karena listrik padam/crash saat ditulis."""
        snapshot_store._remove_partial_snapshots(self.snapshots_dir)

    def _write_snapshot(self, path: Path, image: np.ndarray) -> bool:
        """Menulis JPEG secara atomik: berkas sementara di-fsync lalu diganti nama.

        Listrik padam di tengah penulisan tidak meninggalkan foto rusak dengan
        nama final, dan kegagalan (mis. disk penuh) terdeteksi. Dulu hasil
        cv2.imwrite tidak diperiksa, sehingga audit bisa merujuk foto yang
        tidak pernah tertulis.
        """
        return snapshot_store._write_snapshot(path, image)

    def _connect(self, check_same_thread: bool = True) -> Connection:
        return audit_db.connect(self.db_path, check_same_thread=check_same_thread)

    def _get_connection(self) -> Connection:
        if not self._opened:
            self.open()
        return self._connect()

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            self._migrate(conn)
            self._ensure_indexes(conn)
        finally:
            conn.close()

    @staticmethod
    def _ensure_indexes(conn: Connection):
        """Indeks dipastikan ada setiap kali DB dibuka, bukan hanya saat migrasi skema:
        indeks baru (mis. idx_date_str, T49) tidak pernah dibuat di database yang
        skemanya sudah terbaru (temuan 06-10). IF NOT EXISTS = aman diulang.
        """
        audit_db._ensure_indexes(conn)
        conn.commit()

    def _migrate(self, conn: Connection):
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

        has_table = (
            conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'worker_inspections'").fetchone()
            is not None
        )

        if has_table:
            self._backup_before_migration(version)

        # Transaksi dikendalikan manual: modul sqlite3 tidak membungkus DDL
        # dalam transaksi secara otomatis.
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        try:
            self._upgrade_schema(conn, version, has_table)
            for sql in audit_db._CREATE_INDEXES:
                conn.execute(sql)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _upgrade_schema(self, conn: Connection, version: int, has_table: bool):
        audit_db._upgrade_schema(conn, version, has_table)

    def _backup_before_migration(self, version: int):
        """Salinan utuh database sebelum migrasi, di samping berkas aslinya."""
        backup_path = self.db_path.with_name(f"{self.db_path.stem}.v{version}.bak")
        if backup_path.exists():
            return
        src = self._connect()
        dst = audit_db.backup_connection(backup_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        logger.info(f"Cadangan sebelum migrasi skema: {backup_path.name}")

    def save_inspection(
        self,
        track_id: int,
        is_complete: bool,
        items: Dict[str, dict],
        missing_items: List[str],
        notes: str,
        inference_source: str,
        inference_time_ms: float,
        crop_img: Optional[np.ndarray] = None,
        identity: Optional[dict] = None,
        gate_hold: Optional[str] = None,
    ) -> dict:
        """Saves inspection snapshot to disk and inserts record into SQLite.

        `items` berisi hasil per item APD, dikunci `PPEItem.key`. `identity` (T34c1): hasil
        pengenalan wajah `{worker_id, employee_no, name, status, score}`; None = tanpa FR.
        """
        now = audit_db.inspection_time()
        iso_timestamp = audit_db.time.strftime("%Y-%m-%dT%H:%M:%S", now)
        time_str = audit_db.time.strftime("%H:%M:%S", now)
        snapshot_filename = self._save_snapshot(track_id, crop_img, now)
        record_id = self._insert_inspection(
            (
                track_id,
                iso_timestamp,
                audit_db.time.strftime("%Y-%m-%d", now),
                time_str,
                1 if is_complete else 0,
                json.dumps(items, ensure_ascii=False),
                json.dumps(missing_items, ensure_ascii=False),
                notes,
                inference_source,
                inference_time_ms,
                snapshot_filename,
                *audit_db._identity_values(identity),
                gate_hold,
            )
        )
        return {
            "id": record_id,
            "gate_hold": gate_hold,
            "track_id": track_id,
            "timestamp": iso_timestamp,
            "time_str": time_str,
            "is_complete": is_complete,
            "missing_items": missing_items,
            "snapshot_filename": snapshot_filename,
            "inference_source": inference_source,
            "inference_time_ms": inference_time_ms,
        }

    def _save_snapshot(self, track_id: int, crop_img: Optional[np.ndarray], now: struct_time) -> str:
        """Nama foto bukti yang tertulis; kosong bila tanpa potongan atau gagal ditulis."""
        if crop_img is None or crop_img.size == 0:
            return ""
        name = self._reserve_snapshot_name(snapshot_store.snapshot_stem(track_id, now))
        try:
            return name if self._write_snapshot(self.snapshots_dir / name, crop_img) else ""
        finally:
            with self._snapshot_lock:
                self._snapshots_in_progress.discard(name)

    def _reserve_snapshot_name(self, stem: str) -> str:
        """`<stem>.jpg`, atau `<stem>_2.jpg`, `_3`, ... bila nama itu sudah ada / sedang ditulis.

        T64: ID pelacak + detik saja bisa kembar (dua inspeksi di detik yang sama) dan foto
        pertama tertimpa, sehingga bukti audit menunjuk orang yang salah.
        """
        with self._snapshot_lock:
            return snapshot_store._reserve_snapshot_name(self.snapshots_dir, self._snapshots_in_progress, stem)

    def _insert_inspection(self, values: tuple) -> int:
        """Satu baris audit (urutan nilai = `_INSPECTION_COLUMNS`); mengembalikan id-nya."""
        with self._get_connection() as conn:
            record_id = audit_db.insert_inspection(conn, values)
            conn.commit()
        assert record_id is not None, "INSERT selalu mengisi lastrowid"
        return record_id

    def recognition_rate(self, days: int, today: Optional[date] = None) -> dict:
        end = today or date.today()
        start = end - timedelta(days=max(1, days) - 1)
        with self._get_connection() as conn:
            row = audit_queries.recognition_counts(conn, start, end)
        passes, recognized = row["passes"], row["recognized"]
        return {
            "rate": recognized / passes if passes else None,
            "recognized": recognized,
            "passes": passes,
            "days": days,
            "threshold": cfg.FR_REQUIRED_RATE,
        }

    def get_reports(
        self,
        limit: int = 50,
        offset: int = 0,
        status_filter: str = "all",
        date_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        worker_id: Optional[int] = None,
        department: Optional[str] = None,
        company: Optional[str] = None,
    ) -> dict:
        """Retrieves paginated inspection records with summary statistics."""
        with self._get_connection() as conn:
            return audit_queries.get_reports(
                conn, limit, offset, status_filter, date_filter, date_from, date_to, worker_id, department, company
            )

    @staticmethod
    def _decision_counts(conn: Connection, conditions: list[str], params: list) -> dict:
        return audit_queries._decision_counts(conn, conditions, params)

    def get_summary(
        self,
        period: str,
        anchor: Optional[str] = None,
        worker_id: Optional[int] = None,
        department: Optional[str] = None,
        company: Optional[str] = None,
    ) -> dict:
        """Ringkasan harian/mingguan/bulanan untuk grafik Laporan (kontrak T49, filter T79).

        ValueError untuk periode/tanggal tidak sah (API membalas 400).
        """
        start, end, where, params = audit_queries.summary_query(period, anchor, worker_id, department, company)
        with self._get_connection() as conn:
            rows = audit_queries.summary_rows(conn, where, params)
        return audit_queries.summarize_rows(period, start, end, rows)

    def get_attendance(self, date_str: str, department: Optional[str] = None, company: Optional[str] = None) -> dict:
        """Informasi lintasan harian, bukan absensi. Identitas audit tidak diambil dari galeri terkini."""
        with closing(self._get_connection()) as conn, conn:
            conn.execute("BEGIN")
            seen = attendance.read_seen(conn, date_str)
            unknown = self._attendance_unknown(conn, date_str)
        return attendance.get_attendance(date_str, seen, unknown, department, company)

    @staticmethod
    def _attendance_unknown(conn: Connection, date_str: str) -> dict:
        return attendance._attendance_unknown(conn, date_str)

    def iter_attendance_csv(self, report: dict):
        """Gunakan laporan yang sama dengan JSON agar isi dan ringkasan ekspor tetap konsisten."""
        yield from audit_export.iter_attendance_csv(report)

    def iter_csv_chunks(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        worker_id: Optional[int] = None,
        department: Optional[str] = None,
        company: Optional[str] = None,
    ):
        """CSV audit HSE/K3 per potongan CSV_EXPORT_BATCH_ROWS baris (T43, filter T79).

        Dulu seluruh berkas dibangun di RAM (terukur 16,8 MB untuk 100 rb baris);
        kini dikirim bertahap, jadi memori tetap kecil berapa pun rentangnya.
        Kolom per item APD dibangkitkan dari katalog `ppe_rules`.
        """
        items = ppe_rules.get_items()
        yield audit_export.csv_header(items)
        conditions, params = audit_queries._filter_clause(
            date_from=date_from, date_to=date_to, worker_id=worker_id, department=department, company=company
        )
        if not self._opened:
            self.open()
        conn = self._connect(check_same_thread=False)
        try:
            yield from audit_export.iter_csv_chunks(conn, items, conditions, params)
        finally:
            conn.close()

    def export_csv_text(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        worker_id: Optional[int] = None,
        department: Optional[str] = None,
        company: Optional[str] = None,
    ) -> str:
        """Seluruh CSV sebagai satu teks (alat & tes); API memakai iter_csv_chunks."""
        return "".join(
            self.iter_csv_chunks(
                date_from=date_from,
                date_to=date_to,
                worker_id=worker_id,
                department=department,
                company=company,
            )
        )

    def get_last_seen_batch(self, worker_ids: list[int]) -> dict[int, dict]:
        """Pemeriksaan terakhir per worker_id (T79). Mengembalikan {worker_id: {"at": timestamp, "is_complete": bool}}."""
        if not worker_ids:
            return {}
        with self._get_connection() as conn:
            return audit_queries.get_last_seen_batch(conn, worker_ids)

    def get_last_seen(self, worker_id: int) -> Optional[dict]:
        res = self.get_last_seen_batch([worker_id])
        return res.get(worker_id)

    def get_worker_inspections(self, worker_id: int, limit: int = 50, before: Optional[int] = None) -> dict:
        """Riwayat inspeksi pekerja berhalaman urut terbaru (T79). Memakai idx_worker_id."""
        with self._get_connection() as conn:
            return audit_queries.get_worker_inspections(conn, worker_id, limit, before)

    def get_snapshot_path(self, filename: str) -> Optional[Path]:
        """Resolves snapshot image path safely to avoid path traversal."""
        return snapshot_store.get_snapshot_path(self.snapshots_dir, filename)

    def _delete_photos(self, filenames: list[str]) -> tuple[int, int]:
        return snapshot_store._delete_photos(self.snapshots_dir, filenames)

    def cleanup_old_data(self):
        """Pembersihan data sesuai kebijakan retensi (T20).

        Urutan tetap: audit kedaluwarsa (beserta fotonya) → foto kedaluwarsa →
        pengaman ukuran folder. Basis data diperbarui dulu baru berkas dihapus,
        jadi audit tidak pernah menunjuk foto yang sudah tidak ada.
        """
        now = retention.time.time()
        try:
            with self._get_connection() as conn:
                steps = (
                    self._expire_audits(conn, now),
                    self._expire_photos(conn, now),
                    self._enforce_photo_quota(conn),
                )
            deleted_audits, deleted_photos, reclaimed_bytes = (sum(column) for column in zip(*steps))
            if deleted_photos > 0 or deleted_audits > 0:
                logger.info(
                    f"Retensi data: menghapus {deleted_audits} audit dan {deleted_photos} foto "
                    f"(membebaskan {reclaimed_bytes / BYTES_PER_MB:.1f} MB)."
                )
        except Exception as e:
            logger.error(f"Gagal membersihkan data tua: {e}")

    def _expire_audits(self, conn: Connection, now: float) -> tuple[int, int, int]:
        """Audit lebih tua dari RETENTION_AUDIT_DAYS dihapus beserta fotonya. (audit, foto, byte)."""
        if cfg.RETENTION_AUDIT_DAYS <= 0:
            return 0, 0, 0
        deleted, photos = retention._expire_audits(conn, now)
        conn.commit()
        return (deleted, *self._delete_photos(photos))

    def _expire_photos(self, conn: Connection, now: float) -> tuple[int, int, int]:
        """Foto lebih tua dari RETENTION_PHOTO_DAYS dihapus; baris auditnya tetap."""
        if cfg.RETENTION_PHOTO_DAYS <= 0:
            return 0, 0, 0
        photos = retention._expire_photos(conn, now)
        conn.commit()
        return (0, *self._delete_photos(photos))

    def _enforce_photo_quota(self, conn: Connection) -> tuple[int, int, int]:
        """Folder foto melebihi RETENTION_MAX_PHOTO_GB: foto terlama (mtime) dihapus, termasuk yatim."""
        if cfg.RETENTION_MAX_PHOTO_GB <= 0:
            return 0, 0, 0
        names = self._oldest_photos_over(cfg.RETENTION_MAX_PHOTO_GB * BYTES_PER_GB)
        if not names:
            return 0, 0, 0
        retention.clear_photo_names(conn, names)
        conn.commit()
        return (0, *self._delete_photos(names))

    def _oldest_photos_over(self, max_bytes: float) -> list[str]:
        """Nama foto terlama yang harus dihapus supaya total ukuran folder <= max_bytes."""
        return retention._oldest_photos_over(self.snapshots_dir, max_bytes)


report_mgr = ReportManager()
