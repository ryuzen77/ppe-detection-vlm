import logging
import sqlite3
import threading
import json
import time
import os
import csv
import io
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Optional, List, Dict
import cv2
import numpy as np

from . import ppe_rules
from . import report_summary
from .config import cfg
from . import messages
from . import worker_store
from .face_identity import RECOGNIZED
from .disk_guard import BYTES_PER_GB

logger = logging.getLogger(__name__)

# Label sumber keputusan VLM cadangan (lihat VLMEngine.label)
BACKUP_SOURCE_PREFIX = "VLM_CADANGAN:"

# Retensi (T20): umur data dihitung dalam hari
SECONDS_PER_DAY = 24 * 60 * 60
BYTES_PER_MB = 1024 ** 2

# Akhiran foto bukti yang sedang ditulis (lihat _write_snapshot)
SNAPSHOT_TMP_SUFFIX = ".tmp"
CSV_BOM = "\ufeff"  # Excel mengenali UTF-8 lewat penanda di awal berkas, termasuk ekspor kosong.

# Filter tanggal dikerjakan sebelum window: hanya audit hari terpilih yang diurutkan.
_ATTENDANCE_SEEN_SQL = """
    WITH daily AS (
        SELECT worker_id, employee_no, worker_name AS name, department, company, time_str,
               is_complete, ROW_NUMBER() OVER worker_day AS latest,
               MIN(time_str) OVER worker_day AS first_seen,
               COUNT(*) OVER worker_day AS passes,
               SUM(is_complete) OVER worker_day AS passed
        FROM worker_inspections WHERE date_str = ? AND fr_status = ?
        WINDOW worker_day AS (PARTITION BY worker_id ORDER BY time_str DESC, id DESC
                              ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    )
    SELECT worker_id, employee_no, name, department, company, first_seen,
           time_str AS last_seen, passes, passed, passes - passed AS rejected,
           is_complete AS last_complete
    FROM daily WHERE latest = 1 ORDER BY first_seen, worker_id
"""
_ATTENDANCE_UNKNOWN_SQL = """
    SELECT COUNT(*) AS passes, COALESCE(SUM(is_complete), 0) AS passed,
           COUNT(*) - COALESCE(SUM(is_complete), 0) AS rejected
    FROM worker_inspections WHERE date_str = ? AND fr_status IS NOT ?
"""
_ATTENDANCE_COUNT_FIELDS = ("first_seen", "last_seen", "passes", "passed", "rejected")
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _attendance_matches(row: dict, department: Optional[str], company: Optional[str]) -> bool:
    return (not department or row["department"] == department) and (not company or row["company"] == company)


def _attendance_totals(seen: list[dict], unknown: dict, active_workers: int, seen_workers: int) -> dict:
    """Mutu pengenalan dihitung atas seluruh gerbang; jumlah pekerja mengikuti filter daftar."""
    recognized = sum(row["passes"] for row in seen)
    passes = recognized + unknown["passes"]
    return {"passes": passes, "recognized": recognized,
            "recognition_rate": recognized / passes if passes else None,
            "active_workers": active_workers, "seen_workers": seen_workers}


def _attendance_csv_cell(value):
    """Nama bebas tetap teks ketika CSV dibuka di spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value

# Jalur data diatur lewat DATA_DIR di config, di luar direktori kode
DB_PATH = cfg.DB_PATH
SNAPSHOTS_DIR = cfg.SNAPSHOTS_DIR

# Versi skema, disimpan di `PRAGMA user_version`.
#   0 — skema awal: sebelas kolom tetap untuk helm, rompi, celana, dan sepatu
#   1 — hasil per item disimpan generik di `items_json`, mengikuti `ppe_rules`
#   2 — identitas pekerja dari pengenalan wajah (T34c1); kolom boleh kosong (audit lama &
#       gerbang tanpa FR). Nama & nomor pegawai disalin saat inspeksi: audit adalah catatan
#       siapa yang lewat SAAT ITU, dan tetap terbaca setelah data wajah pekerja dihapus retensi.
#   3 — snapshot divisi (department) & kontraktor (company) (T79); riwayat audit tetap benar
#       walau pekerja berpindah divisi kelak. Baris audit lama tetap NULL.
SCHEMA_VERSION = 3

_V2_COLUMNS = (
    ("worker_id", "INTEGER"),
    ("employee_no", "TEXT"),
    ("worker_name", "TEXT"),
    ("fr_status", "TEXT"),
    ("fr_score", "REAL"),
)

_V3_COLUMNS = (
    ("department", "TEXT"),
    ("company", "TEXT"),
)

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

# Kolom yang diisi saat audit baru ditulis (id & default diisi SQLite)
_INSPECTION_COLUMNS = (
    "track_id", "timestamp", "date_str", "time_str", "is_complete", "items_json",
    "missing_items", "notes", "inference_source", "inference_time_ms", "snapshot_filename",
    *(name for name, _ in _V2_COLUMNS),
    *(name for name, _ in _V3_COLUMNS),
)
_INSERT_INSPECTION = (
    f"INSERT INTO worker_inspections ({', '.join(_INSPECTION_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_INSPECTION_COLUMNS))})"
)

def _identity_values(identity: Optional[dict]) -> tuple:
    """Nilai kolom v2 & v3 dari hasil pengenalan wajah; None = tanpa FR."""
    who = identity or {}
    keys = {
        "worker_id": "worker_id",
        "employee_no": "employee_no",
        "worker_name": "name",
        "fr_status": "status",
        "fr_score": "score",
        "department": "department",
        "company": "company",
    }
    return tuple(who.get(keys[column]) for column, _ in (*_V2_COLUMNS, *_V3_COLUMNS))


_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_timestamp ON worker_inspections(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_is_complete ON worker_inspections(is_complete)",
    # Filter & ringkasan per rentang tanggal (T49); tanpa ini laporan bulanan memindai seluruh tabel
    "CREATE INDEX IF NOT EXISTS idx_date_str ON worker_inspections(date_str)",
    # Laporan & filter per pekerja (T34)
    "CREATE INDEX IF NOT EXISTS idx_worker_id ON worker_inspections(worker_id)",
)


def _range_clause(date_from: Optional[str], date_to: Optional[str]) -> tuple[list[str], list]:
    """Syarat SQL rentang tanggal inklusif (T49); sisi yang kosong tidak membatasi."""
    conditions, params = [], []
    if date_from:
        conditions.append("date_str >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("date_str <= ?")
        params.append(date_to)
    return conditions, params


def _filter_clause(
    status_filter: str = "all",
    date_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    worker_id: Optional[int] = None,
    department: Optional[str] = None,
    company: Optional[str] = None,
) -> tuple[list[str], list]:
    """Syarat SQL gabungan untuk filter audit (T79)."""
    conditions, params = [], []
    if status_filter == "complete":
        conditions.append("is_complete = 1")
    elif status_filter == "incomplete":
        conditions.append("is_complete = 0")
    if date_filter:
        conditions.append("date_str = ?")
        params.append(date_filter)
    range_conditions, range_params = _range_clause(date_from, date_to)
    conditions += range_conditions
    params += range_params
    if worker_id is not None:
        conditions.append("worker_id = ?")
        params.append(worker_id)
    if department and department.strip():
        conditions.append("department = ?")
        params.append(department.strip())
    if company and company.strip():
        conditions.append("company = ?")
        params.append(company.strip())
    return conditions, params


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
        partial = list(self.snapshots_dir.glob(f"*{SNAPSHOT_TMP_SUFFIX}"))
        for p in partial:
            try:
                p.unlink()
            except OSError:
                pass
        if partial:
            logger.warning(messages.SNAPSHOT_TMP_REMOVED.format(count=len(partial)))

    def _write_snapshot(self, path: Path, image: np.ndarray) -> bool:
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

    def _connect(self, check_same_thread: bool = True) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=cfg.DB_TIMEOUT_SECONDS, check_same_thread=check_same_thread)
        conn.row_factory = sqlite3.Row
        # Per koneksi: dulu hanya disetel (NORMAL) di koneksi inisialisasi yang
        # langsung ditutup, jadi tidak pernah berlaku untuk penulisan audit (T37)
        conn.execute(f"PRAGMA synchronous = {cfg.AUDIT_DB_SYNCHRONOUS};")
        return conn

    def _get_connection(self) -> sqlite3.Connection:
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
    def _ensure_indexes(conn: sqlite3.Connection):
        """Indeks dipastikan ada setiap kali DB dibuka, bukan hanya saat migrasi skema:
        indeks baru (mis. idx_date_str, T49) tidak pernah dibuat di database yang
        skemanya sudah terbaru (temuan 06-10). IF NOT EXISTS = aman diulang."""
        for sql in _CREATE_INDEXES:
            conn.execute(sql)
        conn.commit()

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
                self._migrate_v1_to_v2(conn, existing=False)
                self._migrate_v2_to_v3(conn, existing=False)
            else:
                if version == 0:
                    self._migrate_v0_to_v1(conn)
                    self._migrate_v1_to_v2(conn, existing=True)
                    self._migrate_v2_to_v3(conn, existing=True)
                elif version == 1:
                    self._migrate_v1_to_v2(conn, existing=True)
                    self._migrate_v2_to_v3(conn, existing=True)
                elif version == 2:
                    self._migrate_v2_to_v3(conn, existing=True)
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

    @staticmethod
    def _migrate_v1_to_v2(conn: sqlite3.Connection, existing: bool):
        """Kolom identitas pekerja (T34c1). Baris lama tetap, kolom barunya kosong.
        Database baru juga melewati langkah ini (tabel v1 + kolom v2), tanpa log migrasi."""
        for name, sql_type in _V2_COLUMNS:
            conn.execute(f"ALTER TABLE worker_inspections ADD COLUMN {name} {sql_type}")
        if existing:
            logger.info("Migrasi skema v1 -> v2: kolom identitas pekerja ditambahkan.")

    @staticmethod
    def _migrate_v2_to_v3(conn: sqlite3.Connection, existing: bool):
        """Kolom snapshot department & company (T79). Baris lama tetap, kolom barunya kosong.
        Database baru juga melewati langkah ini (tabel v1 + kolom v2 + kolom v3), tanpa log migrasi."""
        for name, sql_type in _V3_COLUMNS:
            conn.execute(f"ALTER TABLE worker_inspections ADD COLUMN {name} {sql_type}")
        if existing:
            logger.info("Migrasi skema v2 -> v3: kolom snapshot department & company ditambahkan.")

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
    ) -> dict:
        """Saves inspection snapshot to disk and inserts record into SQLite.

        `items` berisi hasil per item APD, dikunci `PPEItem.key`. `identity` (T34c1): hasil
        pengenalan wajah `{worker_id, employee_no, name, status, score}`; None = tanpa FR.
        """
        now = time.localtime()
        iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", now)
        time_str = time.strftime("%H:%M:%S", now)
        snapshot_filename = self._save_snapshot(track_id, crop_img, now)
        record_id = self._insert_inspection((
            track_id,
            iso_timestamp,
            time.strftime("%Y-%m-%d", now),
            time_str,
            1 if is_complete else 0,
            json.dumps(items, ensure_ascii=False),
            json.dumps(missing_items, ensure_ascii=False),
            notes,
            inference_source,
            inference_time_ms,
            snapshot_filename,
            *_identity_values(identity),
        ))
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

    def _save_snapshot(self, track_id: int, crop_img: Optional[np.ndarray], now: time.struct_time) -> str:
        """Nama foto bukti yang tertulis; kosong bila tanpa potongan atau gagal ditulis."""
        if crop_img is None or crop_img.size == 0:
            return ""
        name = self._reserve_snapshot_name(f"worker_{track_id}_{time.strftime('%Y%m%d_%H%M%S', now)}")
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
            n = 1
            while True:
                name = f"{stem}.jpg" if n == 1 else f"{stem}_{n}.jpg"
                if name not in self._snapshots_in_progress and not (self.snapshots_dir / name).exists():
                    self._snapshots_in_progress.add(name)
                    return name
                n += 1

    def _insert_inspection(self, values: tuple) -> int:
        """Satu baris audit (urutan nilai = `_INSPECTION_COLUMNS`); mengembalikan id-nya."""
        with self._get_connection() as conn:
            record_id = conn.execute(_INSERT_INSPECTION, values).lastrowid
            conn.commit()
        assert record_id is not None, "INSERT selalu mengisi lastrowid"
        return record_id

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> dict:
        rec = dict(row)
        rec["is_complete"] = bool(rec["is_complete"])
        rec["missing_items"] = _parse_json(rec["missing_items"], [])
        rec["items"] = _parse_json(rec.pop("items_json"), {})
        return rec

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

            # Filter query (T79)
            conditions, params = _filter_clause(
                status_filter=status_filter,
                date_filter=date_filter,
                date_from=date_from,
                date_to=date_to,
                worker_id=worker_id,
                department=department,
                company=company,
            )
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
        start, end = report_summary.period_range(period, report_summary.parse_date(anchor, date.today()))
        conditions = ["date_str BETWEEN ? AND ?"]
        params: list = [start.isoformat(), end.isoformat()]
        if worker_id is not None:
            conditions.append("worker_id = ?")
            params.append(worker_id)
        if department and department.strip():
            conditions.append("department = ?")
            params.append(department.strip())
        if company and company.strip():
            conditions.append("company = ?")
            params.append(company.strip())
        where = f"WHERE {' AND '.join(conditions)}"
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT date_str, time_str, is_complete, missing_items FROM worker_inspections {where}",
                params,
            ).fetchall()
        audit = [report_summary.AuditRow(r["date_str"], r["time_str"], bool(r["is_complete"]), r["missing_items"])
                 for r in rows]
        return report_summary.summarize(period, start, end, audit)

    @staticmethod
    def _csv_text(rows: list[list]) -> str:
        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        return buffer.getvalue()

    def get_attendance(self, date_str: str, department: Optional[str] = None,
                       company: Optional[str] = None) -> dict:
        """Informasi lintasan harian, bukan absensi. Identitas audit tidak diambil dari galeri terkini."""
        with closing(self._get_connection()) as conn, conn:
            conn.execute("BEGIN")
            seen = [dict(row) for row in conn.execute(_ATTENDANCE_SEEN_SQL, (date_str, RECOGNIZED))]
            unknown = self._attendance_unknown(conn, date_str)
        seen_ids = {row["worker_id"] for row in seen}
        for row in seen:
            row["last_complete"] = bool(row["last_complete"])
        active = [row for row in worker_store.store.active_attendance_workers()
                  if _attendance_matches(row, department, company)]
        filtered_seen = [row for row in seen if _attendance_matches(row, department, company)]
        return {"date": date_str, "seen": filtered_seen,
                "not_seen": [row for row in active if row["worker_id"] not in seen_ids],
                "unknown": unknown, "totals": _attendance_totals(seen, unknown, len(active), len(filtered_seen))}

    @staticmethod
    def _attendance_unknown(conn: sqlite3.Connection, date_str: str) -> dict:
        return dict(conn.execute(_ATTENDANCE_UNKNOWN_SQL, (date_str, RECOGNIZED)).fetchone())

    @staticmethod
    def _attendance_csv_row(number: int, row: dict, seen: bool) -> list:
        status = messages.ATTENDANCE_SEEN if seen else messages.ATTENDANCE_NOT_SEEN
        counts = [row[key] for key in _ATTENDANCE_COUNT_FIELDS] if seen else [""] * len(_ATTENDANCE_COUNT_FIELDS)
        values = [number, row["employee_no"], row["name"], row["department"], row["company"], status, *counts]
        return [_attendance_csv_cell(value) for value in values]

    def iter_attendance_csv(self, report: dict):
        """Gunakan laporan yang sama dengan JSON agar isi dan ringkasan ekspor tetap konsisten."""
        yield CSV_BOM + self._csv_text([[messages.ATTENDANCE_CSV_NOTE], messages.ATTENDANCE_CSV_HEADER])
        number = 0
        for section in ("seen", "not_seen"):
            for row in report[section]:
                number += 1
                yield self._csv_text([self._attendance_csv_row(number, row, section == "seen")])
        unknown = report["unknown"]
        yield self._csv_text([["", "", "", "", "", messages.ATTENDANCE_UNKNOWN, "", "",
                              unknown["passes"], unknown["passed"], unknown["rejected"]]])

    def _csv_row(self, number: int, row, items) -> list:
        missing_list = _parse_json(row["missing_items"], [])
        results = _parse_json(row["items_json"], {})
        status_str = messages.CSV_STATUS_COMPLETE if row["is_complete"] else messages.CSV_STATUS_INCOMPLETE
        return ([number, row["date_str"], row["time_str"], messages.CSV_WORKER_ID.format(track_id=row["track_id"]), status_str,
                 self._worker_csv_text(row),
                 row["department"] or messages.CSV_EMPTY,
                 row["company"] or messages.CSV_EMPTY]
                + [self._item_csv_text(item, results.get(item.key)) for item in items]
                + ["; ".join(missing_list) if missing_list else messages.CSV_EMPTY,
                   row["inference_source"], row["inference_time_ms"], row["notes"], row["snapshot_filename"]])

    @staticmethod
    def _worker_csv_text(row) -> str:
        """Nama dari pengenalan wajah (T34c1); kosong untuk audit lama / gerbang tanpa FR."""
        if row["worker_name"]:
            return messages.CSV_FACE_RECOGNIZED.format(name=row["worker_name"], employee_no=row["employee_no"])
        return messages.CSV_FACE_UNKNOWN if row["fr_status"] == "unknown" else messages.CSV_EMPTY

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
        header = messages.CSV_HEADER_LEADING + [
            messages.CSV_HEADER_WORKER_NAME,
            messages.CSV_HEADER_DEPARTMENT,
            messages.CSV_HEADER_COMPANY,
        ]
        yield CSV_BOM + self._csv_text([header + [item.label for item in items] + messages.CSV_HEADER_TRAILING])
        conditions, params = _filter_clause(
            date_from=date_from,
            date_to=date_to,
            worker_id=worker_id,
            department=department,
            company=company,
        )
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        number = 0
        if not self._opened:
            self.open()
        conn = self._connect(check_same_thread=False)
        try:
            cursor = conn.execute(f"SELECT * FROM worker_inspections {where} ORDER BY id ASC", params)
            while batch := cursor.fetchmany(cfg.CSV_EXPORT_BATCH_ROWS):
                rows = [self._csv_row(number + i, row, items) for i, row in enumerate(batch, start=1)]
                number += len(batch)
                yield self._csv_text(rows)
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
        return "".join(self.iter_csv_chunks(
            date_from=date_from,
            date_to=date_to,
            worker_id=worker_id,
            department=department,
            company=company,
        ))

    def get_last_seen_batch(self, worker_ids: list[int]) -> dict[int, dict]:
        """Pemeriksaan terakhir per worker_id (T79). Mengembalikan {worker_id: {"at": timestamp, "is_complete": bool}}."""
        if not worker_ids:
            return {}
        marks = ",".join("?" * len(worker_ids))
        query = (
            f"SELECT worker_id, timestamp, is_complete FROM worker_inspections "
            f"WHERE id IN (SELECT MAX(id) FROM worker_inspections WHERE worker_id IN ({marks}) GROUP BY worker_id)"
        )
        with self._get_connection() as conn:
            rows = conn.execute(query, worker_ids).fetchall()
        return {r["worker_id"]: {"at": r["timestamp"], "is_complete": bool(r["is_complete"])} for r in rows}

    def get_last_seen(self, worker_id: int) -> Optional[dict]:
        res = self.get_last_seen_batch([worker_id])
        return res.get(worker_id)

    def get_worker_inspections(self, worker_id: int, limit: int = 50, before: Optional[int] = None) -> dict:
        """Riwayat inspeksi pekerja berhalaman urut terbaru (T79). Memakai idx_worker_id."""
        limit = max(1, min(limit, 100))
        conditions = ["worker_id = ?"]
        params: list = [worker_id]
        if before is not None:
            conditions.append("id < ?")
            params.append(before)
        where = f"WHERE {' AND '.join(conditions)}"
        query = (
            f"SELECT id, timestamp, is_complete, missing_items, fr_score, snapshot_filename "
            f"FROM worker_inspections {where} ORDER BY id DESC LIMIT ?"
        )
        params.append(limit + 1)
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        has_next = len(rows) > limit
        selected_rows = rows[:limit] if has_next else rows
        items = [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "is_complete": bool(r["is_complete"]),
                "missing_items": _parse_json(r["missing_items"], []),
                "fr_score": r["fr_score"],
                "snapshot_filename": r["snapshot_filename"],
            }
            for r in selected_rows
        ]
        next_before = selected_rows[-1]["id"] if has_next and selected_rows else None
        return {"items": items, "next_before": next_before}

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
        """Pembersihan data sesuai kebijakan retensi (T20).

        Urutan tetap: audit kedaluwarsa (beserta fotonya) → foto kedaluwarsa →
        pengaman ukuran folder. Basis data diperbarui dulu baru berkas dihapus,
        jadi audit tidak pernah menunjuk foto yang sudah tidak ada.
        """
        now = time.time()
        try:
            with self._get_connection() as conn:
                steps = (self._expire_audits(conn, now), self._expire_photos(conn, now),
                         self._enforce_photo_quota(conn))
            deleted_audits, deleted_photos, reclaimed_bytes = (sum(column) for column in zip(*steps))
            if deleted_photos > 0 or deleted_audits > 0:
                logger.info(f"Retensi data: menghapus {deleted_audits} audit dan {deleted_photos} foto "
                            f"(membebaskan {reclaimed_bytes / BYTES_PER_MB:.1f} MB).")
        except Exception as e:
            logger.error(f"Gagal membersihkan data tua: {e}")

    @staticmethod
    def _cutoff(now: float, days: int) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - days * SECONDS_PER_DAY))

    @staticmethod
    def _photos_before(conn: sqlite3.Connection, cutoff: str) -> list[str]:
        rows = conn.execute("SELECT snapshot_filename FROM worker_inspections "
                            "WHERE timestamp < ? AND snapshot_filename != ''", (cutoff,))
        return [row["snapshot_filename"] for row in rows.fetchall()]

    def _expire_audits(self, conn: sqlite3.Connection, now: float) -> tuple[int, int, int]:
        """Audit lebih tua dari RETENTION_AUDIT_DAYS dihapus beserta fotonya. (audit, foto, byte)."""
        if cfg.RETENTION_AUDIT_DAYS <= 0:
            return 0, 0, 0
        cutoff = self._cutoff(now, cfg.RETENTION_AUDIT_DAYS)
        photos = self._photos_before(conn, cutoff)
        deleted = conn.execute("DELETE FROM worker_inspections WHERE timestamp < ?", (cutoff,)).rowcount
        conn.commit()
        return (deleted, *self._delete_photos(photos))

    def _expire_photos(self, conn: sqlite3.Connection, now: float) -> tuple[int, int, int]:
        """Foto lebih tua dari RETENTION_PHOTO_DAYS dihapus; baris auditnya tetap."""
        if cfg.RETENTION_PHOTO_DAYS <= 0:
            return 0, 0, 0
        cutoff = self._cutoff(now, cfg.RETENTION_PHOTO_DAYS)
        photos = self._photos_before(conn, cutoff)
        conn.execute("UPDATE worker_inspections SET snapshot_filename = '' "
                     "WHERE timestamp < ? AND snapshot_filename != ''", (cutoff,))
        conn.commit()
        return (0, *self._delete_photos(photos))

    def _enforce_photo_quota(self, conn: sqlite3.Connection) -> tuple[int, int, int]:
        """Folder foto melebihi RETENTION_MAX_PHOTO_GB: foto terlama (mtime) dihapus, termasuk yatim."""
        if cfg.RETENTION_MAX_PHOTO_GB <= 0:
            return 0, 0, 0
        names = self._oldest_photos_over(cfg.RETENTION_MAX_PHOTO_GB * BYTES_PER_GB)
        if not names:
            return 0, 0, 0
        for fname in names:
            conn.execute("UPDATE worker_inspections SET snapshot_filename = '' WHERE snapshot_filename = ?", (fname,))
        conn.commit()
        return (0, *self._delete_photos(names))

    def _oldest_photos_over(self, max_bytes: float) -> list[str]:
        """Nama foto terlama yang harus dihapus supaya total ukuran folder <= max_bytes."""
        photos = []
        for path in self.snapshots_dir.glob("*.jpg"):
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

report_mgr = ReportManager()
