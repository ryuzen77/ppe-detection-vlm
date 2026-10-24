"""Agregasi kehadiran dari snapshot audit dan daftar pekerja aktif yang hanya dibaca."""

import sqlite3
from typing import Optional
from . import worker_store
from .face_identity import RECOGNIZED


_ATTENDANCE_SEEN_SQL = """
    WITH daily AS (
        SELECT worker_id, employee_no, worker_name AS name, department, company, time_str,
               is_complete, ROW_NUMBER() OVER worker_day AS latest,
               MIN(time_str) OVER worker_day AS first_seen,
               COUNT(*) OVER worker_day AS passes,
               SUM(is_complete = 1 AND gate_hold IS NULL) OVER worker_day AS passed,
               SUM(is_complete = 0) OVER worker_day AS rejected
        FROM worker_inspections WHERE date_str = ? AND fr_status = ?
        WINDOW worker_day AS (PARTITION BY worker_id ORDER BY time_str DESC, id DESC
                              ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
    )
    SELECT worker_id, employee_no, name, department, company, first_seen,
           time_str AS last_seen, passes, passed, rejected,
           is_complete AS last_complete
    FROM daily WHERE latest = 1 ORDER BY first_seen, worker_id
"""

_ATTENDANCE_UNKNOWN_SQL = """
    SELECT COUNT(*) AS passes, COALESCE(SUM(is_complete = 1 AND gate_hold IS NULL), 0) AS passed,
           COALESCE(SUM(is_complete = 0), 0) AS rejected
    FROM worker_inspections WHERE date_str = ? AND fr_status IS NOT ?
"""


def _attendance_matches(row: dict, department: Optional[str], company: Optional[str]) -> bool:
    return (not department or row["department"] == department) and (not company or row["company"] == company)


def _attendance_totals(seen: list[dict], unknown: dict, active_workers: int, seen_workers: int) -> dict:
    """Mutu pengenalan dihitung atas seluruh gerbang; jumlah pekerja mengikuti filter daftar."""
    recognized = sum(row["passes"] for row in seen)
    passes = recognized + unknown["passes"]
    return {
        "passes": passes,
        "recognized": recognized,
        "recognition_rate": recognized / passes if passes else None,
        "active_workers": active_workers,
        "seen_workers": seen_workers,
    }


def _attendance_unknown(conn: sqlite3.Connection, date_str: str) -> dict:
    return dict(conn.execute(_ATTENDANCE_UNKNOWN_SQL, (date_str, RECOGNIZED)).fetchone())


def read_seen(conn: sqlite3.Connection, date_str: str):
    return [dict(row) for row in conn.execute(_ATTENDANCE_SEEN_SQL, (date_str, RECOGNIZED))]


def get_attendance(date_str: str, seen: list[dict], unknown: dict, department=None, company=None):
    seen_ids = {row["worker_id"] for row in seen}
    for row in seen:
        row["last_complete"] = bool(row["last_complete"])
    active = [
        row for row in worker_store.store.active_attendance_workers() if _attendance_matches(row, department, company)
    ]
    filtered_seen = [row for row in seen if _attendance_matches(row, department, company)]
    return {
        "date": date_str,
        "seen": filtered_seen,
        "not_seen": [row for row in active if row["worker_id"] not in seen_ids],
        "unknown": unknown,
        "totals": _attendance_totals(seen, unknown, len(active), len(filtered_seen)),
    }
