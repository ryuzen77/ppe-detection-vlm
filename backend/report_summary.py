"""Ringkasan laporan harian / mingguan / bulanan (T49). Logika murni, tanpa I/O.

`report_manager` mengambil baris audit dalam rentang tanggal; modul ini membagi
rentang, mengisi batang grafik (termasuk yang nol, supaya sumbu waktu UI tidak
bolong), dan menghitung item APD yang paling sering kurang.
"""
import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional

from . import messages, ppe_rules

PERIOD_DAY, PERIOD_WEEK, PERIOD_MONTH = "day", "week", "month"
PERIODS = (PERIOD_DAY, PERIOD_WEEK, PERIOD_MONTH)
HOURS_PER_DAY = 24
DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class AuditRow:
    date_str: str          # YYYY-MM-DD (waktu lokal server)
    time_str: str          # HH:MM:SS
    is_complete: bool
    missing_items: str     # JSON daftar missing_label


def parse_date(value: Optional[str], today: date) -> date:
    """Kosong = hari ini; format salah -> ValueError (API membalas 400)."""
    return date.fromisoformat(value) if value else today


def period_range(period: str, anchor: date) -> tuple[date, date]:
    """Rentang inklusif. Minggu = Senin-Minggu."""
    if period == PERIOD_DAY:
        return anchor, anchor
    if period == PERIOD_WEEK:
        monday = anchor - timedelta(days=anchor.weekday())
        return monday, monday + timedelta(days=DAYS_PER_WEEK - 1)
    if period == PERIOD_MONTH:
        last = calendar.monthrange(anchor.year, anchor.month)[1]
        return anchor.replace(day=1), anchor.replace(day=last)
    raise ValueError(messages.API_REPORT_PERIOD_INVALID.format(periods=", ".join(PERIODS)))


def _empty_buckets(period: str, start: date, end: date) -> dict[str, dict]:
    if period == PERIOD_DAY:
        return {f"{h:02d}": {"start": f"{h:02d}:00", "label": f"{h:02d}", "passed": 0, "rejected": 0}
                for h in range(HOURS_PER_DAY)}
    buckets = {}
    day = start
    while day <= end:
        label = messages.WEEKDAY_SHORT[day.weekday()] if period == PERIOD_WEEK else str(day.day)
        buckets[day.isoformat()] = {"start": day.isoformat(), "label": label, "passed": 0, "rejected": 0}
        day += timedelta(days=1)
    return buckets


def _bucket_key(period: str, row: AuditRow) -> str:
    return row.time_str[:2] if period == PERIOD_DAY else row.date_str


def _missing_labels(raw: str) -> list[str]:
    try:
        labels = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(label) for label in labels] if isinstance(labels, list) else []


def _missing_ranking(rows: Iterable[AuditRow]) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        for label in _missing_labels(row.missing_items):
            counts[label] = counts.get(label, 0) + 1
    ranking = []
    for label, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        item = ppe_rules.get_item_by_missing_label(label)
        ranking.append({"key": item.key if item else None, "label": label, "count": count})
    return ranking


def summarize(period: str, start: date, end: date, rows: list[AuditRow]) -> dict:
    """Bentuk JSON sesuai kontrak T49 di docs/RENCANA.md."""
    buckets = _empty_buckets(period, start, end)
    for row in rows:
        bucket = buckets.get(_bucket_key(period, row))
        if bucket is not None:
            bucket["passed" if row.is_complete else "rejected"] += 1
    passed = sum(b["passed"] for b in buckets.values())
    total = passed + sum(b["rejected"] for b in buckets.values())
    return {
        "period": period,
        "range": {"from": start.isoformat(), "to": end.isoformat()},
        "totals": {"total": total, "passed": passed, "rejected": total - passed,
                   "compliance_rate": round(passed / total * 100, 1) if total else None},
        "buckets": list(buckets.values()),
        "missing_items": _missing_ranking(r for r in rows if not r.is_complete),
    }
