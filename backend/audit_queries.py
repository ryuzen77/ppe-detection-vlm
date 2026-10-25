"""Kueri audit atas koneksi yang diberikan fasad, tanpa membuka koneksi sendiri."""

import json
import sqlite3
from datetime import date
from typing import Optional
from . import report_summary
from .face_identity import RECOGNIZED
from .vlm_selection import LOCAL_FALLBACK_SOURCE_PREFIX


BACKUP_SOURCE_PREFIX = "VLM_CADANGAN:"

RECOGNITION_SQL = (
    "SELECT COUNT(*) AS passes, COALESCE(SUM(fr_status = ?), 0) AS recognized "
    "FROM worker_inspections WHERE date_str BETWEEN ? AND ?"
)

HELD_COUNT_SQL = "SELECT COUNT(*) FROM worker_inspections WHERE gate_hold IS NOT NULL"


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
        conditions.append("is_complete = 1 AND gate_hold IS NULL")
    elif status_filter == "incomplete":
        conditions.append("is_complete = 0")
    elif status_filter == "held":
        conditions.append("gate_hold IS NOT NULL")
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


def _parse_json(text: Optional[str], default):
    try:
        return json.loads(text) if text else default
    except Exception:
        return default


def _row_to_record(row: sqlite3.Row) -> dict:
    rec = dict(row)
    rec["is_complete"] = bool(rec["is_complete"])
    rec["missing_items"] = _parse_json(rec["missing_items"], [])
    rec["items"] = _parse_json(rec.pop("items_json"), {})
    return rec


def _decision_counts(conn: sqlite3.Connection, conditions: list[str], params: list) -> dict:
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    held_select = ", COUNT(gate_hold) AS held_count" if conditions else ""
    row = conn.execute(
        "SELECT COALESCE(SUM(instr(inference_source, ?) = 1), 0) AS backup_count, "
        "COALESCE(SUM(instr(inference_source, ?) = 1), 0) AS local_fallback_count "
        f"{held_select} FROM worker_inspections {where}",
        [BACKUP_SOURCE_PREFIX, LOCAL_FALLBACK_SOURCE_PREFIX, *params],
    ).fetchone()
    counts = dict(row)
    if not conditions:
        counts["held_count"] = conn.execute(HELD_COUNT_SQL).fetchone()[0]
    return counts


def get_reports(
    conn: sqlite3.Connection,
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
    cursor = conn.cursor()

    # Global statistics
    cursor.execute("SELECT COUNT(*) as total FROM worker_inspections")
    total_count = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as complete_count FROM worker_inspections WHERE is_complete = 1")
    complete_count = cursor.fetchone()["complete_count"]

    violation_count = total_count - complete_count
    compliance_rate = round((complete_count / total_count * 100.0), 1) if total_count > 0 else 100.0

    # Filter query (T79)
    conditions, params = _filter_clause(
        date_filter=date_filter,
        date_from=date_from,
        date_to=date_to,
        worker_id=worker_id,
        department=department,
        company=company,
    )
    source_counts = _decision_counts(conn, conditions, params)
    status_conditions, status_params = _filter_clause(status_filter=status_filter)
    conditions, params = status_conditions + conditions, status_params + params
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor.execute(
        f"""
                SELECT COUNT(*) as filtered_total FROM worker_inspections {where_clause}
            """,
        params,
    )
    filtered_total = cursor.fetchone()["filtered_total"]

    query = f"""
                SELECT * FROM worker_inspections
                {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
    query_params = list(params) + [limit, offset]
    cursor.execute(query, query_params)
    records = [_row_to_record(row) for row in cursor.fetchall()]

    return {
        "total_all": total_count,
        "complete_count": complete_count,
        "violation_count": violation_count,
        "compliance_rate": compliance_rate,
        **source_counts,
        "filtered_total": filtered_total,
        "page_records": records,
    }


def get_last_seen_batch(conn: sqlite3.Connection, worker_ids: list[int]) -> dict[int, dict]:
    """Pemeriksaan terakhir per worker_id (T79). Mengembalikan {worker_id: {"at": timestamp, "is_complete": bool}}."""
    if not worker_ids:
        return {}
    marks = ",".join("?" * len(worker_ids))
    query = (
        f"SELECT worker_id, timestamp, is_complete FROM worker_inspections "
        f"WHERE id IN (SELECT MAX(id) FROM worker_inspections WHERE worker_id IN ({marks}) GROUP BY worker_id)"
    )
    rows = conn.execute(query, worker_ids).fetchall()
    return {r["worker_id"]: {"at": r["timestamp"], "is_complete": bool(r["is_complete"])} for r in rows}


def get_worker_inspections(
    conn: sqlite3.Connection, worker_id: int, limit: int = 50, before: Optional[int] = None
) -> dict:
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


def summary_query(period, anchor=None, worker_id=None, department=None, company=None):
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
    return start, end, where, params


def summary_rows(conn: sqlite3.Connection, where: str, params: list):
    rows = conn.execute(
        f"SELECT date_str, time_str, is_complete, missing_items, gate_hold FROM worker_inspections {where}",
        params,
    ).fetchall()
    return rows


def summarize_rows(period, start, end, rows):
    audit = [
        report_summary.AuditRow(
            r["date_str"], r["time_str"], bool(r["is_complete"]), r["missing_items"], r["gate_hold"]
        )
        for r in rows
    ]
    return report_summary.summarize(period, start, end, audit)


def recognition_counts(conn: sqlite3.Connection, start, end):
    return conn.execute(RECOGNITION_SQL, (RECOGNIZED, start.isoformat(), end.isoformat())).fetchone()
