"""Penyusunan CSV; koneksi streaming diberikan dan ditutup oleh fasad."""

import csv
import io
import sqlite3
from typing import Optional
from . import messages, ppe_rules
from .config import cfg
from .audit_queries import _parse_json


CSV_BOM = "\ufeff"  # Excel mengenali UTF-8 lewat penanda di awal berkas, termasuk ekspor kosong.

_ATTENDANCE_COUNT_FIELDS = ("first_seen", "last_seen", "passes", "passed", "rejected")

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def _attendance_csv_cell(value):
    """Nama bebas tetap teks ketika CSV dibuka di spreadsheet."""
    if isinstance(value, str) and value.lstrip().startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


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


def _csv_text(rows: list[list]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


def _attendance_csv_row(number: int, row: dict, seen: bool) -> list:
    status = messages.ATTENDANCE_SEEN if seen else messages.ATTENDANCE_NOT_SEEN
    counts = [row[key] for key in _ATTENDANCE_COUNT_FIELDS] if seen else [""] * len(_ATTENDANCE_COUNT_FIELDS)
    values = [number, row["employee_no"], row["name"], row["department"], row["company"], status, *counts]
    return [_attendance_csv_cell(value) for value in values]


def iter_attendance_csv(report: dict):
    """Gunakan laporan yang sama dengan JSON agar isi dan ringkasan ekspor tetap konsisten."""
    yield CSV_BOM + _csv_text([[messages.ATTENDANCE_CSV_NOTE], messages.ATTENDANCE_CSV_HEADER])
    number = 0
    for section in ("seen", "not_seen"):
        for row in report[section]:
            number += 1
            yield _csv_text([_attendance_csv_row(number, row, section == "seen")])
    unknown = report["unknown"]
    yield _csv_text(
        [
            [
                "",
                "",
                "",
                "",
                "",
                messages.ATTENDANCE_UNKNOWN,
                "",
                "",
                unknown["passes"],
                unknown["passed"],
                unknown["rejected"],
            ]
        ]
    )


def _csv_row(number: int, row, items) -> list:
    missing_list = _parse_json(row["missing_items"], [])
    results = _parse_json(row["items_json"], {})
    status_str = messages.CSV_STATUS_COMPLETE if row["is_complete"] else messages.CSV_STATUS_INCOMPLETE
    if row["gate_hold"] is not None:
        status_str = messages.CSV_STATUS_HELD
    return (
        [
            number,
            row["date_str"],
            row["time_str"],
            messages.CSV_WORKER_ID.format(track_id=row["track_id"]),
            status_str,
            _worker_csv_text(row),
            row["department"] or messages.CSV_EMPTY,
            row["company"] or messages.CSV_EMPTY,
        ]
        + [_item_csv_text(item, results.get(item.key)) for item in items]
        + [
            "; ".join(missing_list) if missing_list else messages.CSV_EMPTY,
            row["inference_source"],
            row["inference_time_ms"],
            row["notes"],
            row["snapshot_filename"],
            messages.CSV_GATE_HOLD_LABELS.get(row["gate_hold"], messages.CSV_EMPTY),
        ]
    )


def _worker_csv_text(row) -> str:
    """Nama dari pengenalan wajah (T34c1); kosong untuk audit lama / gerbang tanpa FR."""
    if row["worker_name"]:
        return messages.CSV_FACE_RECOGNIZED.format(name=row["worker_name"], employee_no=row["employee_no"])
    return messages.CSV_FACE_UNKNOWN if row["fr_status"] == "unknown" else messages.CSV_EMPTY


def csv_header(items) -> str:
    header = messages.CSV_HEADER_LEADING + [
        messages.CSV_HEADER_WORKER_NAME,
        messages.CSV_HEADER_DEPARTMENT,
        messages.CSV_HEADER_COMPANY,
    ]
    return CSV_BOM + _csv_text(
        [header + [item.label for item in items] + (messages.CSV_HEADER_TRAILING + [messages.CSV_HEADER_GATE_HOLD])]
    )


def iter_csv_chunks(conn: sqlite3.Connection, items, conditions, params):
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    number = 0
    cursor = conn.execute(f"SELECT * FROM worker_inspections {where} ORDER BY id ASC", params)
    while batch := cursor.fetchmany(cfg.CSV_EXPORT_BATCH_ROWS):
        rows = [_csv_row(number + i, row, items) for i, row in enumerate(batch, start=1)]
        number += len(batch)
        yield _csv_text(rows)
