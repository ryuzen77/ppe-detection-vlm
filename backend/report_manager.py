import sqlite3
import json
import time
import os
import csv
import io
from pathlib import Path
from typing import Optional, List, Dict, Any
import cv2
import numpy as np

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
SNAPSHOTS_DIR = REPORTS_DIR / "snapshots"
DB_PATH = REPORTS_DIR / "audit.db"

class ReportManager:
    """Manages SQLite database storage for worker inspection records,
    JPEG snapshot image archiving, compliance statistics, and CSV exports."""

    def __init__(self):
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS worker_inspections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    date_str TEXT NOT NULL,
                    time_str TEXT NOT NULL,
                    is_complete INTEGER NOT NULL,
                    helm_detected INTEGER NOT NULL,
                    helm_desc TEXT,
                    rompi_detected INTEGER NOT NULL,
                    rompi_color TEXT,
                    rompi_valid INTEGER NOT NULL,
                    rompi_desc TEXT,
                    celana_detected INTEGER NOT NULL,
                    celana_desc TEXT,
                    sepatu_detected INTEGER NOT NULL,
                    sepatu_closed INTEGER NOT NULL,
                    sepatu_desc TEXT,
                    missing_items TEXT,
                    notes TEXT,
                    inference_source TEXT,
                    inference_time_ms REAL,
                    snapshot_filename TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON worker_inspections(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_complete ON worker_inspections(is_complete)")
            conn.commit()

    def save_inspection(
        self,
        track_id: int,
        is_complete: bool,
        helm_data: dict,
        rompi_data: dict,
        celana_data: dict,
        sepatu_data: dict,
        missing_items: List[str],
        notes: str,
        inference_source: str,
        inference_time_ms: float,
        crop_img: Optional[np.ndarray] = None
    ) -> dict:
        """Saves inspection snapshot to disk and inserts record into SQLite."""
        now = time.localtime()
        iso_timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", now)
        date_str = time.strftime("%Y-%m-%d", now)
        time_str = time.strftime("%H:%M:%S", now)
        file_time_slug = time.strftime("%Y%m%d_%H%M%S", now)

        snapshot_filename = ""
        if crop_img is not None and crop_img.size > 0:
            snapshot_filename = f"worker_{track_id}_{file_time_slug}.jpg"
            save_path = SNAPSHOTS_DIR / snapshot_filename
            try:
                # Save compressed snapshot JPEG (~30-50 KB)
                cv2.imwrite(str(save_path), crop_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            except Exception as e:
                print(f"[ReportManager] Error saving snapshot image: {e}")
                snapshot_filename = ""

        missing_json = json.dumps(missing_items, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO worker_inspections (
                    track_id, timestamp, date_str, time_str, is_complete,
                    helm_detected, helm_desc,
                    rompi_detected, rompi_color, rompi_valid, rompi_desc,
                    celana_detected, celana_desc,
                    sepatu_detected, sepatu_closed, sepatu_desc,
                    missing_items, notes, inference_source, inference_time_ms,
                    snapshot_filename
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                track_id,
                iso_timestamp,
                date_str,
                time_str,
                1 if is_complete else 0,
                1 if helm_data.get("detected", False) else 0,
                helm_data.get("description", ""),
                1 if rompi_data.get("detected", False) else 0,
                rompi_data.get("color", ""),
                1 if rompi_data.get("is_valid_color", False) else 0,
                rompi_data.get("description", ""),
                1 if celana_data.get("detected", False) else 0,
                celana_data.get("description", ""),
                1 if sepatu_data.get("detected", False) else 0,
                1 if sepatu_data.get("is_closed_shoes", False) else 0,
                sepatu_data.get("description", ""),
                missing_json,
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

    def get_reports(self, limit: int = 50, offset: int = 0, status_filter: str = "all") -> dict:
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

            # Filter query
            where_clause = ""
            params = []
            if status_filter == "complete":
                where_clause = "WHERE is_complete = 1"
            elif status_filter == "incomplete":
                where_clause = "WHERE is_complete = 0"

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
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()

            records = []
            for row in rows:
                rec = dict(row)
                rec["is_complete"] = bool(rec["is_complete"])
                rec["helm_detected"] = bool(rec["helm_detected"])
                rec["rompi_detected"] = bool(rec["rompi_detected"])
                rec["rompi_valid"] = bool(rec["rompi_valid"])
                rec["celana_detected"] = bool(rec["celana_detected"])
                rec["sepatu_detected"] = bool(rec["sepatu_detected"])
                rec["sepatu_closed"] = bool(rec["sepatu_closed"])
                try:
                    rec["missing_items"] = json.loads(rec["missing_items"]) if rec["missing_items"] else []
                except Exception:
                    rec["missing_items"] = []
                records.append(rec)

            return {
                "total_all": total_count,
                "complete_count": complete_count,
                "violation_count": violation_count,
                "compliance_rate": compliance_rate,
                "filtered_total": filtered_total,
                "page_records": records
            }

    def export_csv_text(self) -> str:
        """Exports all inspection records to a standard CSV string for HSE/K3 audit."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header standard
        writer.writerow([
            "No",
            "Tanggal",
            "Waktu",
            "ID Pekerja",
            "Status Kelulusan",
            "Helm",
            "Rompi",
            "Celana Panjang",
            "Sepatu Tertutup",
            "Item Kurang / Pelanggaran",
            "Sumber Analisis",
            "Waktu Proses (ms)",
            "Catatan",
            "Nama File Snapshot"
        ])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM worker_inspections ORDER BY id ASC")
            rows = cursor.fetchall()

            for i, row in enumerate(rows, start=1):
                missing_list = []
                try:
                    missing_list = json.loads(row["missing_items"]) if row["missing_items"] else []
                except Exception:
                    pass

                status_str = "LENGKAP (Akses Diizinkan)" if row["is_complete"] else "TIDAK LENGKAP (Ditolak)"
                helm_str = "OK" if row["helm_detected"] else "TIDAK ADA"
                rompi_str = f"OK ({row['rompi_color']})" if row["rompi_valid"] else "TIDAK SAH / TIDAK ADA"
                celana_str = "OK" if row["celana_detected"] else "CELANA PENDEK"
                sepatu_str = "OK" if row["sepatu_closed"] else "SANDAL / TERBUKA"

                writer.writerow([
                    i,
                    row["date_str"],
                    row["time_str"],
                    f"Pekerja #{row['track_id']}",
                    status_str,
                    helm_str,
                    rompi_str,
                    celana_str,
                    sepatu_str,
                    "; ".join(missing_list) if missing_list else "-",
                    row["inference_source"],
                    row["inference_time_ms"],
                    row["notes"],
                    row["snapshot_filename"]
                ])

        return output.getvalue()

    def get_snapshot_path(self, filename: str) -> Optional[Path]:
        """Resolves snapshot image path safely to avoid path traversal."""
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            return None
        safe_name = os.path.basename(filename)
        path = (SNAPSHOTS_DIR / safe_name).resolve()
        snapshots_root = SNAPSHOTS_DIR.resolve()
        try:
            if path.is_relative_to(snapshots_root) and path.exists() and path.is_file():
                return path
        except AttributeError:
            if str(path).startswith(str(snapshots_root)) and path.exists() and path.is_file():
                return path
        return None

report_mgr = ReportManager()
