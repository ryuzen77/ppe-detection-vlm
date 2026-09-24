"""Riwayat inspeksi, foto bukti, dan ekspor CSV audit."""
import time

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import messages
from ..report_manager import report_mgr
from ..api_monitor import api_monitor

router = APIRouter()


# --- WORKER REPORT & AUDIT ENDPOINTS ---

@router.get("/api/reports")
async def get_worker_reports(limit: int = 50, offset: int = 0, status: str = "all", date: str = None):
    """Returns paginated worker inspection records with global compliance statistics."""
    data = report_mgr.get_reports(limit=limit, offset=offset, status_filter=status, date_filter=date)
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

@router.get("/api/reports/export")
async def export_worker_reports_csv():
    """Generates and downloads a CSV audit report for HSE/K3 compliance."""
    csv_data = report_mgr.export_csv_text()
    today_str = time.strftime("%Y-%m-%d")
    filename = f"laporan_inspeksi_apd_{today_str}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )
