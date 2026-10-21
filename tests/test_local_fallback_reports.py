"""T72: audit darurat dihitung terpisah, termasuk lewat rute HTTP laporan."""

import sqlite3
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from backend.report_manager import BACKUP_SOURCE_PREFIX, ReportManager
from backend.vlm_selection import LOCAL_FALLBACK_SOURCE_PREFIX


@pytest.fixture
def manager(tmp_path):
    return ReportManager(db_path=tmp_path / "audit.db", snapshots_dir=tmp_path / "snapshots").open()


def _insert_rows(manager, sources):
    with sqlite3.connect(manager.db_path) as conn:
        conn.executemany(
            """INSERT INTO worker_inspections
            (track_id, timestamp, date_str, time_str, is_complete, inference_source)
            VALUES (1, '2026-10-21T08:00:00', '2026-10-21', '08:00:00', 1, ?)""",
            ((source,) for source in sources),
        )


def test_reports_http_separates_emergency_backup_and_primary(manager, monkeypatch):
    from backend.api import routes_reports
    from backend.app import app

    _insert_rows(
        manager,
        (
            "VLM_LIVE:gemini/model-uji",
            f"{BACKUP_SOURCE_PREFIX}ollama/model-uji",
            f"{LOCAL_FALLBACK_SOURCE_PREFIX}ollama/model-uji",
            f"{LOCAL_FALLBACK_SOURCE_PREFIX}ollama/model-uji",
            None,
            "label-lama",
            "VLMXDARURAT:ollama/model-uji",
            "VLMXCADANGAN:ollama/model-uji",
        ),
    )
    monkeypatch.setattr(routes_reports, "report_mgr", manager)
    response = TestClient(app).get("/api/reports")
    assert response.status_code == 200
    report = response.json()
    assert report["total_all"] == 8 and report["local_fallback_count"] == 2 and report["backup_count"] == 1


def test_empty_reports_have_zero_local_fallback_count(manager):
    report = manager.get_reports()
    assert report["local_fallback_count"] == report["backup_count"] == 0


def test_source_index_is_added_to_existing_database(manager):
    with sqlite3.connect(manager.db_path) as conn:
        conn.execute("DROP INDEX idx_inference_source")
    ReportManager(db_path=manager.db_path, snapshots_dir=manager.snapshots_dir).open()
    with sqlite3.connect(manager.db_path) as conn:
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(worker_inspections)")}
    assert "idx_inference_source" in indexes


@pytest.mark.parametrize("count", [100, 100_000])
def test_global_source_count_performance_and_query_plan(manager, count):
    _insert_rows(manager, [f"{LOCAL_FALLBACK_SOURCE_PREFIX}ollama/model-uji"] * count)
    queries = []
    original_connect = manager._get_connection

    def connect():
        conn = original_connect()
        conn.set_trace_callback(queries.append)
        return conn

    manager._get_connection = connect
    start = perf_counter()
    result = manager.get_reports(limit=0)
    elapsed_ms = (perf_counter() - start) * 1000
    query = next(query for query in queries if "AS local_fallback_count" in query)
    with sqlite3.connect(manager.db_path) as conn:
        plan = conn.execute(f"EXPLAIN QUERY PLAN {query}").fetchall()
    assert result["local_fallback_count"] == count and result["backup_count"] == 0
    assert sum("AS local_fallback_count" in query for query in queries) == 1
    assert any("USING COVERING INDEX idx_inference_source" in row[3] for row in plan)
    print(f"SOURCE_COUNTS rows={count} elapsed_ms={elapsed_ms:.3f} plan={plan}")
