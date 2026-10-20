"""Tes kontrak T84: Nomor pegawai terkunci setelah dibuat (T84a backend).

Persyaratan Kontrak T84:
1. POST /api/workers tidak berubah (nomor otomatis jika kosong, atau validasi nomor manual).
2. PATCH /api/workers/{id} dengan nomor berbeda (case-insensitive) -> 409 employee_no_locked,
   data pekerja (termasuk kolom lain di request yang sama) tidak berubah.
3. PATCH /api/workers/{id} dengan nomor sama (case-insensitive) -> 200 diabaikan, kolom lain tersimpan.
4. PATCH /api/workers/{id} tanpa employee_no -> 200 normal.
"""

import pytest
from fastapi.testclient import TestClient

from backend import face_crypto, messages, worker_store
from backend.app import app


@pytest.fixture
def store(tmp_path, monkeypatch):
    db_file = tmp_path / "workers_t84.db"
    repository = worker_store.SqliteWorkerStore(db_file, key=face_crypto.generate_key())
    monkeypatch.setattr(worker_store, "store", repository)
    return repository


@pytest.fixture
def client():
    return TestClient(app)


def test_post_workers_tidak_berubah(client, store):
    # Kosong -> otomatis dibuat
    r1 = client.post(
        "/api/workers",
        json={"name": "Asep Sunandar", "consent": True, "nickname": "Asep", "gender": "male"},
    )
    assert r1.status_code == 201
    assert r1.json()["employee_no"] == "P-0001"

    # Diisi manual HR -> sesuai yang diisi
    r2 = client.post(
        "/api/workers",
        json={
            "employee_no": "HR-9999",
            "name": "Bambang Pamungkas",
            "consent": True,
            "nickname": "Bambang",
            "gender": "male",
        },
    )
    assert r2.status_code == 201
    assert r2.json()["employee_no"] == "HR-9999"


def test_patch_nomor_berbeda_ditolak_409_dan_data_tidak_berubah(client, store):
    r_create = client.post(
        "/api/workers",
        json={
            "employee_no": "EMP-001",
            "name": "Cecep Rahman",
            "consent": True,
            "nickname": "Cecep",
            "gender": "male",
        },
    )
    assert r_create.status_code == 201
    worker_id = r_create.json()["id"]

    # Coba ubah nomor ke EMP-002 bersamaan dengan mengubah nickname & gender
    r_patch = client.patch(
        f"/api/workers/{worker_id}",
        json={"employee_no": "EMP-002", "nickname": "Cecep Ganti", "gender": "female"},
    )
    assert r_patch.status_code == 409
    err = r_patch.json()["detail"]
    assert err["code"] == "employee_no_locked"
    assert err["message"] == messages.WORKER_EMPLOYEE_NO_LOCKED

    # Pastikan data pekerja TIDAK berubah sama sekali
    worker = store.get(worker_id)
    assert worker.employee_no == "EMP-001"
    assert worker.nickname == "Cecep"
    assert worker.gender == "male"


def test_patch_nomor_sama_diterima_200_dan_kolom_lain_terupdate(client, store):
    r_create = client.post(
        "/api/workers",
        json={
            "employee_no": "EMP-005",
            "name": "Dadang Subur",
            "consent": True,
            "nickname": "Dadang",
            "gender": "male",
        },
    )
    worker_id = r_create.json()["id"]

    # Nomor sama persis -> 200, kolom lain berhasil diubah
    r_same = client.patch(
        f"/api/workers/{worker_id}",
        json={"employee_no": "EMP-005", "nickname": "Dadang Update"},
    )
    assert r_same.status_code == 200
    assert r_same.json()["employee_no"] == "EMP-005"
    assert r_same.json()["nickname"] == "Dadang Update"

    # Nomor sama tetapi beda huruf besar/kecil (case insensitive) -> 200 diabaikan
    r_case = client.patch(
        f"/api/workers/{worker_id}",
        json={"employee_no": "emp-005", "nickname": "Dadang Final"},
    )
    assert r_case.status_code == 200
    assert r_case.json()["employee_no"] == "EMP-005"
    assert r_case.json()["nickname"] == "Dadang Final"


def test_patch_tanpa_nomor_tetap_jalan(client, store):
    r_create = client.post(
        "/api/workers",
        json={
            "employee_no": "EMP-009",
            "name": "Endang Suryana",
            "consent": True,
            "nickname": "Endang",
            "gender": "male",
        },
    )
    worker_id = r_create.json()["id"]

    # PATCH tanpa menyebut employee_no
    r_patch = client.patch(
        f"/api/workers/{worker_id}",
        json={"nickname": "Endang Keren"},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["employee_no"] == "EMP-009"
    assert r_patch.json()["nickname"] == "Endang Keren"
