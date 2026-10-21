"""Riwayat inspeksi, foto bukti, dan ekspor CSV audit."""
import time
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from .. import messages
from ..report_manager import report_mgr
from ..api_monitor import api_monitor
from .deps import require_admin

router = APIRouter()


# --- WORKER REPORT & AUDIT ENDPOINTS ---

def _checked_dates(*values: Optional[str]):
    """Tanggal dari klien wajib YYYY-MM-DD: nilai lain ditolak 400, bukan diam-diam kosong."""
    try:
        for value in values:
            if value:
                date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=messages.API_REPORT_DATE_INVALID)


def _attendance_date(value: Optional[str]) -> str:
    _checked_dates(value)
    if not value:
        return date.today().isoformat()
    if date.fromisoformat(value).isoformat() != value:
        raise HTTPException(status_code=400, detail=messages.API_REPORT_DATE_INVALID)
    return value


@router.get("/api/reports/attendance", dependencies=[Depends(require_admin)])
def get_attendance(date: Optional[str] = None, department: Optional[str] = None,
                   company: Optional[str] = None):
    return report_mgr.get_attendance(_attendance_date(date), department, company)


@router.get("/api/reports/attendance/export", dependencies=[Depends(require_admin)])
def export_attendance_csv(date: Optional[str] = None, department: Optional[str] = None,
                          company: Optional[str] = None):
    day = _attendance_date(date)
    report = report_mgr.get_attendance(day, department, company)
    filename = messages.ATTENDANCE_CSV_FILENAME.format(date=day)
    return StreamingResponse(report_mgr.iter_attendance_csv(report), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}",
                                      "Cache-Control": "no-store"})


@router.get("/api/reports")
async def get_worker_reports(limit: int = 50, offset: int = 0, status: str = "all", date: Optional[str] = None,
                             date_from: Optional[str] = Query(None, alias="from"),
                             date_to: Optional[str] = Query(None, alias="to"),
                             worker_id: Optional[int] = None,
                             department: Optional[str] = None,
                             company: Optional[str] = None):
    """Returns paginated worker inspection records with global compliance statistics."""
    _checked_dates(date, date_from, date_to)
    data = report_mgr.get_reports(
        limit=limit,
        offset=offset,
        status_filter=status,
        date_filter=date,
        date_from=date_from,
        date_to=date_to,
        worker_id=worker_id,
        department=department,
        company=company,
    )
    # Gangguan (utama & cadangan gagal) sengaja tidak masuk audit — tidak ada
    # keputusan — jadi hitungannya berasal dari pemantau VLM sejak server menyala.
    data["system_outages"] = api_monitor.get_status()["no_decisions"]
    return data

@router.get("/api/reports/snapshots/{filename}")
async def get_worker_snapshot(filename: str):
    """Serves an inspection snapshot crop image for a specific worker."""
    path = report_mgr.get_snapshot_path(filename)
    if path and path.exists():
        return FileResponse(str(path), media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"error": messages.API_SNAPSHOT_NOT_FOUND})

@router.get("/api/reports/summary")
async def get_report_summary(period: str = "day", date: Optional[str] = None,
                             worker_id: Optional[int] = None,
                             department: Optional[str] = None,
                             company: Optional[str] = None):
    """Ringkasan harian/mingguan/bulanan untuk grafik Laporan (kontrak T49, filter T79)."""
    _checked_dates(date)
    try:
        return report_mgr.get_summary(
            period,
            date,
            worker_id=worker_id,
            department=department,
            company=company,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/reports/export")
async def export_worker_reports_csv(date_from: Optional[str] = Query(None, alias="from"),
                                    date_to: Optional[str] = Query(None, alias="to"),
                                    worker_id: Optional[int] = None,
                                    department: Optional[str] = None,
                                    company: Optional[str] = None):
    """Generates and downloads a CSV audit report for HSE/K3 compliance (rentang & filter opsional, T79)."""
    _checked_dates(date_from, date_to)
    suffix = "_".join(v for v in (date_from, date_to) if v) or time.strftime("%Y-%m-%d")
    filename = messages.REPORT_CSV_FILENAME.format(suffix=suffix)
    return StreamingResponse(
        report_mgr.iter_csv_chunks(
            date_from=date_from,
            date_to=date_to,
            worker_id=worker_id,
            department=department,
            company=company,
        ),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )
