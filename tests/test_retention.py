import time
import os
import pytest

from backend.config import cfg
from backend.report_manager import ReportManager

@pytest.fixture
def temp_retention_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    reports_dir = data_dir / "reports"
    snapshots_dir = reports_dir / "snapshots"
    db_path = reports_dir / "audit.db"
    
    monkeypatch.setattr(cfg, "DATA_DIR", data_dir)
    monkeypatch.setattr(cfg, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(cfg, "SNAPSHOTS_DIR", snapshots_dir)
    monkeypatch.setattr(cfg, "DB_PATH", db_path)
    
    # 1 day for photo, 2 days for audit, max photo size 1 KB
    monkeypatch.setattr(cfg, "RETENTION_PHOTO_DAYS", 1)
    monkeypatch.setattr(cfg, "RETENTION_AUDIT_DAYS", 2)
    monkeypatch.setattr(cfg, "RETENTION_MAX_PHOTO_GB", 1 / (1024 * 1024))  # 1 KB = 1024 bytes
    
    mgr = ReportManager(db_path, snapshots_dir)
    mgr.open()
    yield mgr
    mgr._opened = False


def test_cleanup_old_data_time(temp_retention_env):
    mgr = temp_retention_env
    conn = mgr._get_connection()
    
    now = time.time()
    day = 86400
    
    # Insert dummy data directly to db
    def insert(track_id, timestamp_offset, has_photo):
        t = now + timestamp_offset
        ts_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))
        fname = f"photo_{track_id}.jpg" if has_photo else ""
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO worker_inspections (
                track_id, timestamp, date_str, time_str, is_complete,
                items_json, missing_items, notes, inference_source,
                inference_time_ms, snapshot_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (track_id, ts_str, "2026-01-01", "12:00", 1, '{}', '[]', '', 'VLM', 1.0, fname))
        conn.commit()
        
        if has_photo:
            p = mgr.snapshots_dir / fname
            p.write_bytes(b"x" * 10)  # 10 bytes file
            # Change mtime so it matches offset if we wanted to sort by mtime, 
            # but db timestamp is what matters for time-based retention
            os.utime(p, (t, t))
    
    # Case 1: Fresh audit (0 days). Should be kept entirely.
    insert(1, 0, True)
    
    # Case 2: Photo old (1.5 days), Audit fresh (< 2 days). Photo deleted, Audit kept without photo.
    insert(2, -1.5 * day, True)
    
    # Case 3: Audit old (3 days). Audit deleted, Photo deleted.
    insert(3, -3.0 * day, True)
    
    # Run cleanup
    mgr.cleanup_old_data()
    
    cursor = conn.cursor()
    cursor.execute("SELECT track_id, snapshot_filename FROM worker_inspections ORDER BY track_id")
    rows = cursor.fetchall()
    
    assert len(rows) == 2, "Audit 3 should be deleted"
    
    # track 1
    assert rows[0]["track_id"] == 1
    assert rows[0]["snapshot_filename"] == "photo_1.jpg"
    assert (mgr.snapshots_dir / "photo_1.jpg").exists()
    
    # track 2
    assert rows[1]["track_id"] == 2
    assert rows[1]["snapshot_filename"] == "", "Snapshot filename should be cleared in DB"
    assert not (mgr.snapshots_dir / "photo_2.jpg").exists(), "Photo should be deleted from disk"
    
    # track 3 photo should be gone
    assert not (mgr.snapshots_dir / "photo_3.jpg").exists()


def test_cleanup_max_size(temp_retention_env):
    mgr = temp_retention_env
    conn = mgr._get_connection()
    now = time.time()
    
    # We set max photo size to 1 KB (1024 bytes)
    # Let's create 3 photos, each 500 bytes. Total = 1500 bytes (over limit).
    # The oldest should be deleted.
    
    def insert(track_id, timestamp_offset):
        t = now + timestamp_offset
        ts_str = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))
        fname = f"photo_{track_id}.jpg"
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO worker_inspections (
                track_id, timestamp, date_str, time_str, is_complete,
                items_json, missing_items, notes, inference_source,
                inference_time_ms, snapshot_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (track_id, ts_str, "2026-01-01", "12:00", 1, '{}', '[]', '', 'VLM', 1.0, fname))
        conn.commit()
        
        p = mgr.snapshots_dir / fname
        p.write_bytes(b"x" * 500)
        os.utime(p, (t, t))
    
    # All photos are fresh enough to not be deleted by time (< 1 day)
    insert(1, -0.5 * 86400) # Oldest
    insert(2, -0.2 * 86400) # Middle
    insert(3, -0.1 * 86400) # Newest
    
    mgr.cleanup_old_data()
    
    # Only photo 1 should be deleted (500 bytes). Remaining = 1000 <= 1024
    assert not (mgr.snapshots_dir / "photo_1.jpg").exists()
    assert (mgr.snapshots_dir / "photo_2.jpg").exists()
    assert (mgr.snapshots_dir / "photo_3.jpg").exists()
    
    cursor = conn.cursor()
    cursor.execute("SELECT track_id, snapshot_filename FROM worker_inspections ORDER BY track_id")
    rows = cursor.fetchall()
    
    assert rows[0]["track_id"] == 1
    assert rows[0]["snapshot_filename"] == ""
    
    assert rows[1]["track_id"] == 2
    assert rows[1]["snapshot_filename"] == "photo_2.jpg"
    
    assert rows[2]["track_id"] == 3
    assert rows[2]["snapshot_filename"] == "photo_3.jpg"
