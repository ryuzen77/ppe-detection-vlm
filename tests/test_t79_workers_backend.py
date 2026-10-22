"""Tes komprehensif kontrak T79 (T79a backend halaman Pekerja).

Mencakup:
1. Hak admin (403 untuk non-admin pada semua endpoint baru).
2. CRUD organisasi (departments & companies), validasi nama, proteksi builtin dan in_use.
3. Penomoran pegawai otomatis, pengabaian format lain, deteksi bentrok, dan PATCH employee_no.
4. Riwayat pemeriksaan pekerja berhalaman dan EXPLAIN QUERY PLAN kueri riwayat (idx_worker_id).
5. Migrasi skema lama workers.db dan audit.db (v2 -> v3).
6. Snapshot department & company pada audit, filter laporan, ringkasan, dan CSV export.
"""

import sqlite3
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend import face_crypto, messages, worker_store
from backend.api.deps import require_session
from backend.app import app
from backend.auth import SessionUser
from backend.config import cfg
from backend.report_manager import ReportManager


@pytest.fixture
def store(tmp_path, monkeypatch):
    db_file = tmp_path / "workers.db"
    repository = worker_store.SqliteWorkerStore(db_file, key=face_crypto.generate_key())
    monkeypatch.setattr(worker_store, "store", repository)
    return repository


@pytest.fixture
def rep_mgr(tmp_path, monkeypatch):
    mgr = ReportManager()
    mgr.db_path = tmp_path / "audit.db"
    mgr.snapshots_dir = tmp_path / "snapshots"
    mgr.snapshots_dir.mkdir(parents=True, exist_ok=True)
    mgr._opened = False
    mgr.open()
    monkeypatch.setattr("backend.api.routes_workers.report_mgr", mgr)
    monkeypatch.setattr("backend.api.routes_reports.report_mgr", mgr)
    monkeypatch.setattr("backend.state_manager.report_mgr", mgr)
    return mgr


@pytest.fixture
def client():
    return TestClient(app)


# --- 1. Hak Admin (403 untuk non-admin) ---


def test_endpoint_baru_403_untuk_non_admin(client, store, rep_mgr):
    async def operator_user(request: Request) -> SessionUser:
        user = SessionUser("operator-uji", "operator")
        request.state.user = user
        return user

    app.dependency_overrides[require_session] = operator_user
    try:
        endpoints = [
            ("get", "/api/org/departments"),
            ("post", "/api/org/departments"),
            ("patch", "/api/org/departments/1"),
            ("delete", "/api/org/departments/1"),
            ("get", "/api/org/companies"),
            ("post", "/api/org/companies"),
            ("patch", "/api/org/companies/1"),
            ("delete", "/api/org/companies/1"),
            ("get", "/api/workers/next-employee-no"),
            ("get", "/api/workers/1/inspections"),
        ]
        for method, path in endpoints:
            r = getattr(client, method)(path)
            assert r.status_code == 403, (
                f"Endpoint {method.upper()} {path} seharusnya 403 untuk non-admin, dapat {r.status_code}"
            )
    finally:
        app.dependency_overrides.pop(require_session, None)


# --- 2. Organisasi CRUD & Proteksi ---


def test_organisasi_crud_dan_proteksi(client, store):
    # GET awal: departments kosong, companies berisi bawaan "Internal" dengan builtin=True
    deps = client.get("/api/org/departments").json()
    assert deps == []
    comps = client.get("/api/org/companies").json()
    assert len(comps) == 1
    assert comps[0]["name"] == cfg.WORKER_DEFAULT_COMPANY
    assert comps[0]["builtin"] is True

    # POST departemen baru
    r_dep = client.post("/api/org/departments", json={"name": "Logistik"})
    assert r_dep.status_code == 201
    dep_data = r_dep.json()
    dep_id = dep_data["id"]
    assert dep_data["name"] == "Logistik"
    assert dep_data["workers"] == 0

    # Duplikat nama -> 409
    r_dup = client.post("/api/org/departments", json={"name": "logistik"})
    assert r_dup.status_code == 409
    assert r_dup.json()["detail"]["code"] == "name_taken"

    # Nama kosong atau lebih dari max -> 400
    r_empty = client.post("/api/org/departments", json={"name": "   "})
    assert r_empty.status_code == 400
    assert r_empty.json()["detail"]["code"] == "invalid_name"

    r_long = client.post("/api/org/departments", json={"name": "X" * (cfg.ORG_NAME_MAX_LENGTH + 1)})
    assert r_long.status_code == 400
    assert r_long.json()["detail"]["code"] == "invalid_name"

    # PATCH nama
    r_patch = client.patch(f"/api/org/departments/{dep_id}", json={"name": "Supply Chain"})
    assert r_patch.status_code == 200
    assert r_patch.json()["name"] == "Supply Chain"

    # POST kontraktor / company baru
    r_comp = client.post("/api/org/companies", json={"name": "PT Maju Jaya"})
    assert r_comp.status_code == 201
    comp_id = r_comp.json()["id"]

    # Buat pekerja dengan divisi & kontraktor tersebut
    r_worker = client.post(
        "/api/workers",
        json={
            "employee_no": "P-0010",
            "name": "Siti Aminah",
            "consent": True,
            "nickname": "Siti",
            "gender": "female",
            "department_id": dep_id,
            "company_id": comp_id,
        },
    )
    assert r_worker.status_code == 201
    worker_id = r_worker.json()["id"]

    # Jumlah worker dan builtin terhitung di GET /api/org
    deps = client.get("/api/org/departments").json()
    assert deps[0]["workers"] == 1
    assert deps[0]["builtin"] is False

    comps_after = client.get("/api/org/companies").json()
    maju_jaya = next(c for c in comps_after if c["id"] == comp_id)
    assert maju_jaya["builtin"] is False

    # DELETE divisi yang sedang dipakai pekerja -> 409 in_use
    r_del_dep = client.delete(f"/api/org/departments/{dep_id}")
    assert r_del_dep.status_code == 409
    assert r_del_dep.json()["detail"]["code"] == "in_use"

    # PATCH perusahaan bawaan "Internal" -> 409 builtin
    internal_id = comps[0]["id"]
    r_patch_builtin = client.patch(f"/api/org/companies/{internal_id}", json={"name": "Nama Baru"})
    assert r_patch_builtin.status_code == 409
    assert r_patch_builtin.json()["detail"]["code"] == "builtin"

    # DELETE perusahaan bawaan "Internal" -> 409 builtin
    r_del_internal = client.delete(f"/api/org/companies/{internal_id}")
    assert r_del_internal.status_code == 409
    assert r_del_internal.json()["detail"]["code"] == "builtin"

    # Lepas divisi pekerja lewat PATCH workers, lalu hapus divisi
    client.patch(f"/api/workers/{worker_id}", json={"department_id": None})
    r_del_dep_ok = client.delete(f"/api/org/departments/{dep_id}")
    assert r_del_dep_ok.status_code == 204

    # Divisi sudah terhapus -> 404
    assert client.patch(f"/api/org/departments/{dep_id}", json={"name": "Baru"}).status_code == 404


def test_buka_ulang_store_tidak_duplikasi_perusahaan_bawaan(tmp_path):
    db_file = tmp_path / "workers_reopen.db"
    key = face_crypto.generate_key()
    s1 = worker_store.SqliteWorkerStore(path=db_file, key=key)
    comps1 = s1.list_org("companies")
    assert len(comps1) == 1
    assert comps1[0]["builtin"] is True
    assert comps1[0]["name"] == cfg.WORKER_DEFAULT_COMPANY

    # Buka store kedua kali pada berkas database yang sama
    s2 = worker_store.SqliteWorkerStore(path=db_file, key=key)
    comps2 = s2.list_org("companies")
    assert len(comps2) == 1
    assert comps2[0]["builtin"] is True
    assert comps2[0]["id"] == comps1[0]["id"]


def test_patch_gender_saja_meminta_suara_ulang(client, store, monkeypatch):
    suara_diminta = []
    monkeypatch.setattr("backend.worker_voice.request", lambda w: suara_diminta.append(w))
    r = client.post(
        "/api/workers",
        json={"name": "Joko", "consent": True, "nickname": "Joko", "gender": "male"},
    )
    assert r.status_code == 201
    wid = r.json()["id"]
    assert len(suara_diminta) == 1
    assert suara_diminta[-1].salutation == "Pak"

    # PATCH gender saja dari male ke female
    r_patch = client.patch(f"/api/workers/{wid}", json={"gender": "female"})
    assert r_patch.status_code == 200
    assert r_patch.json()["gender"] == "female"
    assert r_patch.json()["salutation"] == "Bu"
    assert len(suara_diminta) == 2
    assert suara_diminta[-1].salutation == "Bu"


# --- 3. Nomor Pegawai Otomatis & Relasi Pekerja ---


def test_nomor_pegawai_otomatis_dan_pembaharuan(client, store):
    # Preview next-employee-no saat awal
    r_next = client.get("/api/workers/next-employee-no").json()
    assert r_next["employee_no"] == "P-0001"

    # POST dengan employee_no kosong -> otomatis P-0001
    r_w1 = client.post(
        "/api/workers",
        json={"name": "Ahmad", "consent": True, "nickname": "Ahmad", "gender": "male"},
    )
    assert r_w1.status_code == 201
    w1 = r_w1.json()
    assert w1["employee_no"] == "P-0001"
    assert w1["company"]["name"] == cfg.WORKER_DEFAULT_COMPANY
    assert w1["department"] is None

    # Next employee-no naik jadi P-0002
    assert client.get("/api/workers/next-employee-no").json()["employee_no"] == "P-0002"

    # Daftarkan pekerja dengan nomor format lain (mis. manual HR)
    r_hr = client.post(
        "/api/workers",
        json={"employee_no": "HR-9999", "name": "Bambang", "consent": True, "nickname": "Bambang", "gender": "male"},
    )
    assert r_hr.status_code == 201
    # Format lain diabaikan dalam penomoran otomatis
    assert client.get("/api/workers/next-employee-no").json()["employee_no"] == "P-0002"

    # POST pekerja berikutnya tanpa nomor -> mendapat P-0002
    r_w2 = client.post(
        "/api/workers",
        json={"name": "Cahyo", "consent": True, "nickname": "Cahyo", "gender": "male"},
    )
    assert r_w2.json()["employee_no"] == "P-0002"

    # PATCH employee_no w1 ke nomor berbeda (T84: terkunci) -> 409 employee_no_locked
    r_patch_no = client.patch(f"/api/workers/{w1['id']}", json={"employee_no": "P-0088", "nickname": "Ahmad Ganti"})
    assert r_patch_no.status_code == 409
    assert r_patch_no.json()["detail"]["code"] == "employee_no_locked"
    # Pastikan data tidak berubah (nickname tetap Ahmad, employee_no tetap P-0001)
    w1_check = client.get("/api/workers").json()["workers"]
    assert next(w for w in w1_check if w["id"] == w1["id"])["nickname"] == "Ahmad"
    assert next(w for w in w1_check if w["id"] == w1["id"])["employee_no"] == "P-0001"

    # PATCH employee_no dengan nomor yang sama (case insensitive) -> 200 diabaikan
    r_same_no = client.patch(f"/api/workers/{w1['id']}", json={"employee_no": "p-0001", "nickname": "Ahmad Baru"})
    assert r_same_no.status_code == 200
    assert r_same_no.json()["employee_no"] == "P-0001"
    assert r_same_no.json()["nickname"] == "Ahmad Baru"

    # PATCH tanpa employee_no -> 200 tetap jalan
    r_no_emp = client.patch(f"/api/workers/{w1['id']}", json={"nickname": "Ahmad Final"})
    assert r_no_emp.status_code == 200
    assert r_no_emp.json()["nickname"] == "Ahmad Final"

    # Coba daftarkan pekerja dengan id departemen fiktif -> 400 invalid_department
    r_bad_dep = client.post(
        "/api/workers",
        json={"name": "Dedi", "consent": True, "nickname": "Dedi", "gender": "male", "department_id": 9999},
    )
    assert r_bad_dep.status_code == 400
    assert r_bad_dep.json()["detail"]["code"] == "invalid_department"


def test_pencarian_dan_filter_pekerja(client, store):
    # Buat 2 pekerja
    client.post(
        "/api/workers",
        json={"employee_no": "P-0010", "name": "Budi Santoso", "consent": True, "nickname": "Budi", "gender": "male"},
    )
    w2 = client.post(
        "/api/workers",
        json={"employee_no": "P-0020", "name": "Dewi Sartika", "consent": True, "nickname": "Dewi", "gender": "female"},
    ).json()
    # Nonaktifkan w2
    client.post(f"/api/workers/{w2['id']}/deactivate")

    # Cari q=sartika
    res_q = client.get("/api/workers?q=sartika").json()["workers"]
    assert len(res_q) == 1
    assert res_q[0]["name"] == "Dewi Sartika"

    # Cari q=P-0010
    res_no = client.get("/api/workers?q=p-0010").json()["workers"]
    assert len(res_no) == 1
    assert res_no[0]["name"] == "Budi Santoso"

    # Filter active=true
    res_act = client.get("/api/workers?active=true").json()["workers"]
    assert len(res_act) == 1
    assert res_act[0]["name"] == "Budi Santoso"

    # Filter active=false
    res_inact = client.get("/api/workers?active=false").json()["workers"]
    assert len(res_inact) == 1
    assert res_inact[0]["name"] == "Dewi Sartika"


# --- 4. Riwayat Berhalaman & EXPLAIN QUERY PLAN ---


def test_riwayat_berhalaman_dan_explain_query_plan(client, store, rep_mgr):
    w = client.post(
        "/api/workers",
        json={"employee_no": "P-0001", "name": "Eko", "consent": True, "nickname": "Eko", "gender": "male"},
    ).json()
    wid = w["id"]

    # Simpan 5 inspeksi untuk pekerja ini
    for i in range(1, 6):
        rep_mgr.save_inspection(
            track_id=1,
            is_complete=True,
            items={},
            missing_items=[],
            notes=f"Inspeksi {i}",
            inference_source="VLM_LIVE:mock",
            inference_time_ms=100.0,
            identity={"worker_id": wid, "employee_no": "P-0001", "name": "Eko", "status": "recognized", "score": 0.95},
        )

    # Ambil halaman 1 (limit=2)
    p1 = client.get(f"/api/workers/{wid}/inspections?limit=2").json()
    assert len(p1["items"]) == 2
    assert p1["next_before"] is not None
    # Urut terbaru (id lebih besar dulu)
    assert p1["items"][0]["id"] > p1["items"][1]["id"]

    # Ambil halaman 2
    p2 = client.get(f"/api/workers/{wid}/inspections?limit=2&before={p1['next_before']}").json()
    assert len(p2["items"]) == 2
    assert p2["items"][0]["id"] < p1["items"][1]["id"]
    assert p2["next_before"] is not None

    # Ambil halaman 3
    p3 = client.get(f"/api/workers/{wid}/inspections?limit=2&before={p2['next_before']}").json()
    assert len(p3["items"]) == 1
    assert p3["next_before"] is None

    # EXPLAIN QUERY PLAN kueri riwayat
    with rep_mgr._get_connection() as conn:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT id, timestamp, is_complete, missing_items, fr_score, snapshot_filename "
            "FROM worker_inspections WHERE worker_id = ? AND id < ? ORDER BY id DESC LIMIT ?",
            (wid, 999, 10),
        ).fetchall()
        plan_str = " ".join(r["detail"] for r in plan)
        assert "idx_worker_id" in plan_str or "USING INDEX" in plan_str, f"Query plan harus memakai indeks: {plan_str}"


# --- 5. Migrasi Skema Lama workers.db & audit.db ---


def test_migrasi_workers_db_dari_skema_lama(tmp_path):
    old_db = tmp_path / "old_workers.db"
    conn = sqlite3.connect(old_db)
    # Skema lama tanpa tabel departments/companies dan tanpa kolom department_id/company_id di workers
    conn.executescript("""
        CREATE TABLE workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_no TEXT NOT NULL COLLATE NOCASE UNIQUE,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            consent_at TEXT NOT NULL,
            consent_by TEXT NOT NULL,
            consent_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            deactivated_at TEXT,
            nickname TEXT NOT NULL DEFAULT '',
            gender TEXT NOT NULL DEFAULT 'male',
            face_deleted_at TEXT
        );
        CREATE TABLE face_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
            condition TEXT NOT NULL,
            model_version TEXT NOT NULL,
            dim INTEGER NOT NULL,
            nonce BLOB NOT NULL,
            ciphertext BLOB NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );
        INSERT INTO workers (id, employee_no, name, active, consent_at, consent_by, consent_version, created_at, created_by, nickname, gender)
        VALUES (1, 'P-0001', 'Pekerja Lama', 1, '2026-01-01', 'admin', '1.0', '2026-01-01', 'admin', 'Lama', 'male');
    """)
    conn.close()

    # Buka dengan SqliteWorkerStore baru
    store = worker_store.SqliteWorkerStore(old_db, key=face_crypto.generate_key())
    w = store.get(1)
    assert w.name == "Pekerja Lama"
    assert w.department is None
    assert w.company is not None
    assert w.company.name == cfg.WORKER_DEFAULT_COMPANY


def test_migrasi_audit_db_dari_skema_v2(tmp_path):
    old_audit = tmp_path / "old_audit.db"
    conn = sqlite3.connect(old_audit)
    # Skema v2 (dengan kolom worker_id dst tapi tanpa department & company)
    conn.executescript("""
        CREATE TABLE worker_inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            date_str TEXT NOT NULL,
            time_str TEXT NOT NULL,
            is_complete INTEGER NOT NULL,
            items_json TEXT NOT NULL DEFAULT '{}',
            missing_items TEXT,
            notes TEXT,
            inference_source TEXT,
            inference_time_ms REAL,
            snapshot_filename TEXT,
            worker_id INTEGER,
            employee_no TEXT,
            worker_name TEXT,
            fr_status TEXT,
            fr_score REAL
        );
        PRAGMA user_version = 2;
        INSERT INTO worker_inspections (id, track_id, timestamp, date_str, time_str, is_complete, worker_id, worker_name)
        VALUES (1, 1, '2026-01-01T10:00:00', '2026-01-01', '10:00:00', 1, 1, 'Pekerja Lama');
    """)
    conn.close()

    mgr = ReportManager()
    mgr.db_path = old_audit
    mgr.snapshots_dir = tmp_path / "snaps"
    mgr.snapshots_dir.mkdir(parents=True, exist_ok=True)
    mgr._opened = False
    mgr.open()

    with mgr._get_connection() as c:
        version = c.execute("PRAGMA user_version").fetchone()[0]
        assert version == 3
        row = c.execute("SELECT worker_name, department, company FROM worker_inspections WHERE id = 1").fetchone()
        assert row["worker_name"] == "Pekerja Lama"
        assert row["department"] is None
        assert row["company"] is None


# --- 6. Snapshot & Filter Laporan ---


def test_laporan_snapshot_dan_filter(client, store, rep_mgr):
    # Buat divisi dan kontraktor
    dep = client.post("/api/org/departments", json={"name": "Konstruksi"}).json()
    comp = client.post("/api/org/companies", json={"name": "PT Kontraktor A"}).json()

    # Simpan inspeksi dengan snapshot organisasi
    rep_mgr.save_inspection(
        track_id=1,
        is_complete=True,
        items={},
        missing_items=[],
        notes="Inspeksi Sukses",
        inference_source="VLM_LIVE:mock",
        inference_time_ms=100.0,
        identity={
            "worker_id": 10,
            "employee_no": "P-0010",
            "name": "Fajar",
            "status": "recognized",
            "score": 0.92,
            "department": dep["name"],
            "company": comp["name"],
        },
    )

    # Simpan inspeksi kedua tanpa organisasi (pekerja tak dikenal)
    rep_mgr.save_inspection(
        track_id=2,
        is_complete=False,
        items={},
        missing_items=["Helm Keselamatan"],
        notes="Tak Dikenal",
        inference_source="VLM_LIVE:mock",
        inference_time_ms=120.0,
        identity={"status": "unknown"},
    )

    # Filter reports by worker_id
    r_w = client.get("/api/reports?worker_id=10").json()
    assert len(r_w["page_records"]) == 1
    assert r_w["page_records"][0]["department"] == "Konstruksi"
    assert r_w["page_records"][0]["company"] == "PT Kontraktor A"

    # Filter reports by department
    r_dep = client.get("/api/reports?department=Konstruksi").json()
    assert len(r_dep["page_records"]) == 1

    # Filter reports by company
    r_comp = client.get("/api/reports?company=PT Kontraktor A").json()
    assert len(r_comp["page_records"]) == 1

    # Filter summary
    summary = client.get("/api/reports/summary?period=day&department=Konstruksi").json()
    assert summary["totals"]["total"] == 1
    assert summary["totals"]["passed"] == 1

    # Export CSV dengan filter & pastikan kolom header dan nilainya ada
    csv_text = rep_mgr.export_csv_text(department="Konstruksi")
    assert messages.CSV_HEADER_DEPARTMENT in csv_text
    assert messages.CSV_HEADER_COMPANY in csv_text
    assert "Konstruksi" in csv_text
    assert "PT Kontraktor A" in csv_text
