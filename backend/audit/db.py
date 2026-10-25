"""Pabrik koneksi dan SQL migrasi audit; fasad mengendalikan transaksi serta umur koneksi."""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional
from ..config import cfg

logger = logging.getLogger(__name__)


def inspection_time():
    return time.localtime()


# Versi PRAGMA user_version: v0 kolom APD tetap; v1 items_json; v2 identitas;
# v3 snapshot divisi/perusahaan; v4 gate_hold terpisah dari kelengkapan APD.
SCHEMA_VERSION = 4

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

# Urutan nilai saat audit ditulis; id dan nilai bawaan diisi SQLite.
_INSPECTION_COLUMNS = (
    "track_id",
    "timestamp",
    "date_str",
    "time_str",
    "is_complete",
    "items_json",
    "missing_items",
    "notes",
    "inference_source",
    "inference_time_ms",
    "snapshot_filename",
    *(name for name, _ in _V2_COLUMNS),
    *(name for name, _ in _V3_COLUMNS),
    "gate_hold",
)

_INSERT_INSPECTION = (
    f"INSERT INTO worker_inspections ({', '.join(_INSPECTION_COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(_INSPECTION_COLUMNS))})"
)

_CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_timestamp ON worker_inspections(timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_is_complete ON worker_inspections(is_complete)",
    # Filter & ringkasan per rentang tanggal (T49); tanpa ini laporan bulanan memindai seluruh tabel
    "CREATE INDEX IF NOT EXISTS idx_date_str ON worker_inspections(date_str)",
    # Laporan & filter per pekerja (T34)
    "CREATE INDEX IF NOT EXISTS idx_worker_id ON worker_inspections(worker_id)",
    # T72: hitungan global cadangan/darurat cukup membaca indeks kecil, bukan seluruh audit.
    "CREATE INDEX IF NOT EXISTS idx_inference_source ON worker_inspections(inference_source)",
    "CREATE INDEX IF NOT EXISTS idx_gate_hold ON worker_inspections(gate_hold) WHERE gate_hold IS NOT NULL",
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


def connect(db_path: Path, check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=cfg.DB_TIMEOUT_SECONDS, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    # Per koneksi: dulu hanya disetel (NORMAL) di koneksi inisialisasi yang
    # langsung ditutup, jadi tidak pernah berlaku untuk penulisan audit (T37)
    conn.execute(f"PRAGMA synchronous = {cfg.AUDIT_DB_SYNCHRONOUS};")
    return conn


def backup_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))


def _ensure_indexes(conn: sqlite3.Connection):
    """Indeks dipastikan ada setiap kali DB dibuka, bukan hanya saat migrasi skema:
    indeks baru (mis. idx_date_str, T49) tidak pernah dibuat di database yang
    skemanya sudah terbaru (temuan 06-10). IF NOT EXISTS = aman diulang."""
    for sql in _CREATE_INDEXES:
        conn.execute(sql)


def _upgrade_schema(conn: sqlite3.Connection, version: int, has_table: bool):
    if not has_table:
        conn.execute(_CREATE_TABLE_V1.format(name="worker_inspections"))
        version = 0
    elif version == 0:
        _migrate_v0_to_v1(conn)
    if version < 2:
        _migrate_v1_to_v2(conn, existing=has_table)
    if version < 3:
        _migrate_v2_to_v3(conn, existing=has_table)
    conn.execute("ALTER TABLE worker_inspections ADD COLUMN gate_hold TEXT NULL")


def _migrate_v0_to_v1(conn: sqlite3.Connection):
    """Sebelas kolom per item → satu kolom `items_json`. Seluruh baris dipertahankan."""
    old_seq = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'worker_inspections'").fetchone()

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
                row["id"],
                row["track_id"],
                row["timestamp"],
                row["date_str"],
                row["time_str"],
                row["is_complete"],
                json.dumps(_legacy_row_to_items(row), ensure_ascii=False),
                row["missing_items"],
                row["notes"],
                row["inference_source"],
                row["inference_time_ms"],
                row["snapshot_filename"],
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


def _migrate_v1_to_v2(conn: sqlite3.Connection, existing: bool):
    """Kolom identitas pekerja (T34c1). Baris lama tetap, kolom barunya kosong.
    Database baru juga melewati langkah ini (tabel v1 + kolom v2), tanpa log migrasi."""
    for name, sql_type in _V2_COLUMNS:
        conn.execute(f"ALTER TABLE worker_inspections ADD COLUMN {name} {sql_type}")
    if existing:
        logger.info("Migrasi skema v1 -> v2: kolom identitas pekerja ditambahkan.")


def _migrate_v2_to_v3(conn: sqlite3.Connection, existing: bool):
    """Kolom snapshot department & company (T79). Baris lama tetap, kolom barunya kosong.
    Database baru juga melewati langkah ini (tabel v1 + kolom v2 + kolom v3), tanpa log migrasi."""
    for name, sql_type in _V3_COLUMNS:
        conn.execute(f"ALTER TABLE worker_inspections ADD COLUMN {name} {sql_type}")
    if existing:
        logger.info("Migrasi skema v2 -> v3: kolom snapshot department & company ditambahkan.")


def insert_inspection(conn: sqlite3.Connection, values: tuple):
    return conn.execute(_INSERT_INSPECTION, values).lastrowid
