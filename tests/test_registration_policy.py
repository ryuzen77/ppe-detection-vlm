"""Akses T83 diuji dengan wajah/gambar sintetis, tanpa VLM cloud atau kamera."""

# ruff: noqa: F811
import csv
import io
import sqlite3
import threading
import time
from datetime import date, timedelta
from types import SimpleNamespace
from statistics import median
from time import perf_counter

import numpy as np
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from backend import face_identity, messages, registration_policy, runtime_settings
from backend.api import routes_registration, routes_reports
from backend.api.deps import require_session
from backend.app import app
from backend.auth import SessionUser
from backend.config import cfg
from backend.notifier import notifier
from backend.report_manager import ReportManager, SCHEMA_VERSION
from backend.report_manager import HELD_COUNT_SQL, RECOGNITION_SQL
from backend.state_manager import TrackState
from test_lifecycle import _balasan, _det, _wait_for, gerbang, vlm  # noqa: F401

PATH = "/api/config/registration-policy"
KNOWN = face_identity.Identity(face_identity.RECOGNIZED, 9, "Pekerja Uji", "UJI-009", 0.9)
UNKNOWN = face_identity.Identity(face_identity.UNKNOWN)


class Identifier:
    def __init__(self, replies, ready=True):
        self.replies, self.available, self.calls = list(replies), ready, []
        self.store = SimpleNamespace(face_ready=self.ready)

    def ready(self):
        return self.available

    def check_ready(self):
        return self.ready()

    def mark_unavailable(self):
        self.available = False

    def identify(self, crops, session_id=0):
        self.calls.append([crop.copy() for crop in crops])
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            self.available = False
            raise reply
        return reply


@pytest.fixture
def policy_env(tmp_path, monkeypatch):
    import backend.state_manager as sm

    monkeypatch.setattr(runtime_settings, "SETTINGS_PATH", tmp_path / "settings.json")
    policy = registration_policy.RegistrationPolicy()
    monkeypatch.setattr(registration_policy, "policy", policy)
    manager = ReportManager(tmp_path / "audit.db", tmp_path / "snapshots").open()
    for module in (sm, routes_registration, routes_reports):
        monkeypatch.setattr(module, "report_mgr", manager)
    fake = Identifier([UNKNOWN])
    monkeypatch.setattr(face_identity, "identifier", fake)
    monkeypatch.setattr(cfg, "FACE_RETRY_SECONDS", 0.25)
    return SimpleNamespace(policy=policy, manager=manager, identifier=fake, client=TestClient(app))


def start_inspection(manager):
    for _ in range(cfg.STABLE_FRAMES_REQUIRED):
        manager.update_frame_detections([_det(True)])


def wait_decision(manager):
    assert _wait_for(lambda: manager.session is not None and manager.session.state == TrackState.ANALYZED)
    return manager.get_telemetry()["active_track"]


def test_disabled_keeps_old_green_without_retry(policy_env, gerbang, vlm):
    start_inspection(gerbang)
    active = wait_decision(gerbang)
    assert active["decision"] == "granted" and active["hold_reason"] is None
    assert active["face_retry_s"] is None and notifier.current_state == "GREEN"
    assert vlm.calls == 1 and len(policy_env.identifier.calls) == 1
    assert policy_env.manager.get_reports()["held_count"] == 0


@pytest.mark.parametrize("ready", [True, False])
def test_missing_ppe_always_red(policy_env, gerbang, vlm, ready):
    policy_env.policy.save(True)
    policy_env.identifier.available = ready
    vlm.reply = _balasan(rompi=True)
    start_inspection(gerbang)
    active = wait_decision(gerbang)
    assert active["decision"] == "denied" and active["hold_reason"] is None
    assert active["face_retry_s"] is None and notifier.current_state == "RED"
    assert vlm.calls == 1


def test_new_frames_retry_recognized_without_second_vlm(policy_env, gerbang, vlm):
    policy_env.policy.save(True)
    policy_env.identifier.replies = [UNKNOWN, KNOWN]
    start_inspection(gerbang)
    assert _wait_for(lambda: gerbang.session is not None and gerbang.session.face_retry)
    active = gerbang.get_telemetry()["active_track"]
    assert active["decision"] is None and 0 <= active["face_retry_s"] <= cfg.FACE_RETRY_SECONDS
    for shade in range(cfg.FACE_VOTE_FRAMES):
        gerbang.update_frame_detections([_det(True, crop_img=np.full((40, 40, 3), shade, np.uint8))])
    active = wait_decision(gerbang)
    assert active["decision"] == "granted" and active["identity"]["employee_no"] == KNOWN.employee_no
    assert notifier.current_state == "GREEN" and vlm.calls == 1
    assert len(policy_env.identifier.calls) == 2
    assert [int(crop[0, 0, 0]) for crop in policy_env.identifier.calls[1]] == list(range(cfg.FACE_VOTE_FRAMES))
    row = policy_env.manager.get_reports()["page_records"][0]
    assert row["fr_status"] == "recognized" and row["gate_hold"] is None


def test_retry_exhausted_yellow_audit_and_compliance(policy_env, gerbang, vlm):
    policy_env.policy.save(True)
    start_inspection(gerbang)
    active = wait_decision(gerbang)
    assert active["decision"] == "held" and active["hold_reason"] == "unregistered"
    assert active["face_retry_s"] is None and notifier.current_state == "YELLOW"
    page = policy_env.manager.get_reports(status_filter="held")
    assert page["held_count"] == page["complete_count"] == page["filtered_total"] == 1
    assert page["compliance_rate"] == 100 and page["violation_count"] == 0
    assert page["page_records"][0]["gate_hold"] == "unregistered"
    assert page["page_records"][0]["is_complete"] is True
    assert gerbang.get_telemetry()["history"][0]["gate_hold"] == "unregistered"
    for _ in range(10):
        gerbang.update_frame_detections([_det(True)])
    assert vlm.calls == 1 and notifier.current_state == "YELLOW"
    assert policy_env.client.get("/api/reports?status=held").json()["filtered_total"] == 1


@pytest.mark.parametrize("error", [None, RuntimeError("engine tiruan gagal")])
def test_unavailable_fr_holds_instead_of_green(policy_env, gerbang, error):
    policy_env.policy.save(True)
    if error is None:
        policy_env.identifier.available = False
    else:
        policy_env.identifier.replies = [error]
    start_inspection(gerbang)
    active = wait_decision(gerbang)
    assert active["hold_reason"] == "fr_unavailable" and active["decision"] == "held"
    assert notifier.current_state == "YELLOW" and notifier.message == messages.REGISTRATION_FR_UNAVAILABLE
    assert gerbang.get_telemetry()["registration_policy"] == {"enabled": True, "fr_ready": False}
    assert policy_env.manager.get_reports()["page_records"][0]["gate_hold"] == "fr_unavailable"


def test_policy_rejects_unready_and_unconfirmed(policy_env):
    policy_env.identifier.available = False
    response = policy_env.client.post(PATH, json={"require_registered": True, "confirm_low_recognition": True})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "fr_not_ready"
    policy_env.identifier.available = True
    response = policy_env.client.post(PATH, json={"require_registered": True})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "low_recognition_needs_confirmation"
    assert policy_env.policy.enabled is False


def test_policy_save_reload_and_security_event(policy_env, security_events):
    response = policy_env.client.post(PATH, json={"require_registered": True, "confirm_low_recognition": True})
    assert response.status_code == 200 and response.json()["require_registered"] is True
    assert registration_policy.RegistrationPolicy().enabled is True
    assert security_events[-1]["event"] == registration_policy.POLICY_CHANGED
    assert security_events[-1]["actor"] == "admin-uji" and security_events[-1]["time"]
    policy_env.identifier.available = False
    assert policy_env.client.post(PATH, json={"require_registered": False}).status_code == 200
    assert registration_policy.RegistrationPolicy().enabled is False


def test_admin_only_both_policy_routes(policy_env):
    async def operator(request: Request):
        return SessionUser("operator-uji", "operator")

    app.dependency_overrides[require_session] = operator
    assert policy_env.client.get(PATH).status_code == 403
    assert policy_env.client.post(PATH, json={"require_registered": False}).status_code == 403


def audit(manager, status=None, held=None):
    return manager.save_inspection(1, True, {}, [], "", "tiruan", 0, identity={"status": status}, gate_hold=held)


def test_recognition_window_null_unknown_and_boundary(policy_env):
    manager = policy_env.manager
    assert manager.recognition_rate(7)["rate"] is None
    for status in ("recognized", "unknown", None, "disabled"):
        audit(manager, status)
    with manager._get_connection() as conn:
        conn.execute(
            "UPDATE worker_inspections SET date_str = ? WHERE id = 1", ((date.today() - timedelta(days=6)).isoformat(),)
        )
    status = policy_env.client.get(PATH).json()
    assert status["recognition"] == {"rate": 0.25, "recognized": 1, "passes": 4, "days": 7, "threshold": 0.95}
    with manager._get_connection() as conn:
        conn.execute(
            "UPDATE worker_inspections SET date_str = ? WHERE id = 1", ((date.today() - timedelta(days=7)).isoformat(),)
        )
    assert manager.recognition_rate(7)["rate"] == 0


def test_migration_v3_preserves_old_apd(policy_env, tmp_path):
    path = tmp_path / "old.db"
    old = ReportManager(path, tmp_path / "old_snap").open()
    audit(old, "recognized")
    with sqlite3.connect(path) as conn:
        conn.execute("DROP INDEX idx_gate_hold")
        conn.execute("ALTER TABLE worker_inspections DROP COLUMN gate_hold")
        conn.execute("PRAGMA user_version = 3")
    migrated = ReportManager(path, tmp_path / "old_snap").open()
    page = migrated.get_reports()
    assert page["page_records"][0]["gate_hold"] is None
    assert page["complete_count"] == 1 and page["held_count"] == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert path.with_name("old.v3.bak").exists()


def test_csv_adds_hold_without_changing_apd(policy_env):
    for held in (None, "unregistered", "fr_unavailable"):
        audit(policy_env.manager, "unknown", held)
    response = policy_env.client.get("/api/reports/export")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0][-1] == messages.CSV_HEADER_GATE_HOLD
    assert [row[-1] for row in rows[1:]] == [messages.CSV_EMPTY, *messages.CSV_GATE_HOLD_LABELS.values()]
    assert "unregistered" not in response.text and "fr_unavailable" not in response.text
    assert [row[4] for row in rows[1:]] == [
        messages.CSV_STATUS_COMPLETE,
        messages.CSV_STATUS_HELD,
        messages.CSV_STATUS_HELD,
    ]


def test_engine_failure_is_cached_unavailable(monkeypatch):
    identifier = face_identity.FaceIdentifier(
        engine=SimpleNamespace(subject_embeddings=lambda _: (_ for _ in ()).throw(RuntimeError("engine tiruan")))
    )
    monkeypatch.setattr(identifier, "_store_override", SimpleNamespace(face_ready=lambda: True))
    monkeypatch.setattr(identifier, "gallery", lambda: None)
    assert identifier.check_ready() is False
    assert identifier.ready() is False


def test_known_face_grants_immediately(policy_env, gerbang, vlm):
    policy_env.policy.save(True)
    policy_env.identifier.replies = [KNOWN]
    start_inspection(gerbang)
    active = wait_decision(gerbang)
    assert active["decision"] == "granted" and active["face_retry_s"] is None
    assert len(policy_env.identifier.calls) == vlm.calls == 1


def test_old_green_memory_cannot_bypass_enabled_policy(policy_env, gerbang, vlm):
    start_inspection(gerbang)
    wait_decision(gerbang)
    gerbang.update_frame_detections([])
    time.sleep(cfg.STANDBY_RESET_DELAY_SECONDS + 0.05)
    gerbang.update_frame_detections([])
    policy_env.policy.save(True)
    start_inspection(gerbang)
    assert wait_decision(gerbang)["decision"] == "held"
    assert vlm.calls == 2


@pytest.mark.parametrize("error", [RuntimeError("FR tiruan gagal saat ulang"), TimeoutError("engine tiruan timeout")])
def test_error_during_retry_holds_without_repeating_vlm(policy_env, gerbang, vlm, error):
    policy_env.policy.save(True)
    policy_env.identifier.replies = [UNKNOWN, error]
    start_inspection(gerbang)
    assert _wait_for(lambda: gerbang.session is not None and gerbang.session.face_retry)
    for _ in range(cfg.FACE_VOTE_FRAMES):
        gerbang.update_frame_detections([_det(True)])
    assert wait_decision(gerbang)["hold_reason"] == "fr_unavailable"
    assert vlm.calls == 1 and policy_env.manager.get_reports()["total_all"] == 1


@pytest.mark.parametrize("engine_timeout", [False, True], ids=["retry_window_exhausted", "engine_timeout"])
def test_late_fr_after_timeout_cannot_change_held_identity(policy_env, gerbang, vlm, monkeypatch, engine_timeout):
    if engine_timeout:
        monkeypatch.setattr(cfg, "FACE_RETRY_SECONDS", 2.0)
        monkeypatch.setattr(cfg, "FACE_IDENTIFY_TIMEOUT_SECONDS", 0.1)
    policy_env.policy.save(True)
    release, started = threading.Event(), threading.Event()
    original = policy_env.identifier.identify

    def identify(crops, session_id=0):
        if policy_env.identifier.calls:
            started.set()
            release.wait(2)
            return KNOWN
        return original(crops, session_id)

    monkeypatch.setattr(policy_env.identifier, "identify", identify)
    start_inspection(gerbang)
    assert _wait_for(lambda: gerbang.session is not None and gerbang.session.face_retry)
    for _ in range(cfg.FACE_VOTE_FRAMES):
        gerbang.update_frame_detections([_det(True)])
    assert started.wait(1)
    try:
        active = wait_decision(gerbang)
        assert active["hold_reason"] == ("fr_unavailable" if engine_timeout else "unregistered")
        assert registration_policy.fr_ready() is not engine_timeout
    finally:
        release.set()
        gerbang.fr_executor.submit(lambda: None).result(timeout=2)
    assert gerbang.get_telemetry()["active_track"] == active
    assert active["decision"] == "held" and vlm.calls == 1
    assert registration_policy.fr_ready() is not engine_timeout


def test_camera_fault_during_retry_cannot_grant(policy_env, gerbang, vlm):
    policy_env.policy.save(True)
    start_inspection(gerbang)
    assert _wait_for(lambda: gerbang.session is not None and gerbang.session.face_retry)
    try:
        gerbang.set_camera_fault("lost")
        assert _wait_for(lambda: policy_env.manager.get_reports()["total_all"] == 1)
        assert gerbang.get_telemetry()["active_track"] is None
        assert notifier.current_state == "YELLOW" and vlm.calls == 1
    finally:
        gerbang.set_camera_fault(None)


def test_above_threshold_needs_no_confirmation(policy_env):
    audit(policy_env.manager, "recognized")
    response = policy_env.client.post(PATH, json={"require_registered": True})
    assert response.status_code == 200 and response.json()["recognition"]["rate"] == 1


def test_save_failure_keeps_policy_disabled(policy_env, monkeypatch):
    monkeypatch.setattr(runtime_settings, "update", lambda *args: False)
    response = policy_env.client.post(PATH, json={"require_registered": True, "confirm_low_recognition": True})
    assert response.status_code == 500 and policy_env.policy.enabled is False


def test_both_vlm_fail_still_wait_without_audit(policy_env, gerbang, vlm):
    policy_env.policy.save(True)
    vlm.error = RuntimeError("VLM tiruan tidak tersedia")
    start_inspection(gerbang)
    assert _wait_for(lambda: gerbang.session is not None and gerbang.session.state == TrackState.WAITING_SYSTEM)
    active = gerbang.get_telemetry()["active_track"]
    assert active["decision"] is None and active["hold_reason"] is None
    assert active["vlm_result"] is None and notifier.current_state == "YELLOW"
    assert policy_env.manager.get_reports()["total_all"] == 0


@pytest.mark.parametrize("size", [100, 100_000])
def test_audit_indexes_and_timing(policy_env, size):
    manager = policy_env.manager
    day = date.today().isoformat()
    with manager._get_connection() as conn:
        conn.executemany(
            "INSERT INTO worker_inspections (track_id,timestamp,date_str,time_str,is_complete,fr_status,gate_hold) "
            "VALUES (1,?,?, '08:00:00',1,?,?)",
            ((day, day, "recognized" if i % 2 else "unknown", None if i % 2 else "unregistered") for i in range(size)),
        )
        plan = conn.execute("EXPLAIN QUERY PLAN " + RECOGNITION_SQL, ("recognized", day, day)).fetchall()
        held_plan = conn.execute("EXPLAIN QUERY PLAN " + HELD_COUNT_SQL).fetchall()
    assert "idx_date_str" in str([tuple(row) for row in plan])
    assert "idx_gate_hold" in str([tuple(row) for row in held_plan])
    result = manager.recognition_rate(cfg.FR_RATE_WINDOW_DAYS)
    elapsed = []
    for _ in range(5):
        start = perf_counter()
        result = manager.recognition_rate(cfg.FR_RATE_WINDOW_DAYS)
        elapsed.append((perf_counter() - start) * 1000)
    assert result["passes"] == size and result["rate"] == 0.5
    print(
        f"T83 audit {size}: median {median(elapsed):.3f} ms; plan={[tuple(row) for row in plan]}; held={[tuple(row) for row in held_plan]}"
    )


@pytest.mark.parametrize("size", [100, 100_000])
def test_inspection_policy_timing(policy_env, gerbang, size):
    from backend.vlm_analyzer import InspectionResult

    policy_env.policy.save(True)
    result = InspectionResult(is_complete=True)
    identity, held = gerbang._resolve_registration(1, result, KNOWN)
    elapsed = []
    for _ in range(5):
        start = perf_counter()
        for _ in range(size):
            identity, held = gerbang._resolve_registration(1, result, KNOWN)
        elapsed.append((perf_counter() - start) * 1_000_000 / size)
    assert identity == KNOWN and held is None
    print(f"T83 inspection {size}: median {median(elapsed):.3f} us/inspection (FR tiruan, tanpa VLM/I/O)")


@pytest.mark.parametrize("people", [1, 20])
def test_retry_frame_path_timing(policy_env, gerbang, people):
    from backend.state_manager import GateSession

    session = GateSession(42, time.time())
    session.state, session.face_retry = TrackState.ANALYZING, True
    gerbang.session = session
    detections = [_det(True, track_id=42 + index) for index in range(people)]
    elapsed = []
    for _ in range(5):
        start = perf_counter()
        for _ in range(200):
            gerbang.update_frame_detections(detections)
        elapsed.append((perf_counter() - start) * 1000 / 200)
    assert len(session.face_frames) == cfg.FACE_VOTE_FRAMES
    print(f"T83 retry frame {people} people: median {median(elapsed):.3f} ms/frame (crop sintetis)")


def test_retry_continues_on_new_batches_until_recognized(policy_env, gerbang, vlm, monkeypatch):
    monkeypatch.setattr(cfg, "FACE_RETRY_SECONDS", 2.0)
    policy_env.policy.save(True)
    policy_env.identifier.replies = [UNKNOWN, UNKNOWN, KNOWN]
    start_inspection(gerbang)
    assert _wait_for(lambda: gerbang.session is not None and gerbang.session.face_retry)
    for shade in (10, 20):
        for _ in range(cfg.FACE_VOTE_FRAMES):
            gerbang.update_frame_detections([_det(True, crop_img=np.full((40, 40, 3), shade, np.uint8))])
        assert _wait_for(lambda: len(policy_env.identifier.calls) >= shade // 10 + 1)
    assert wait_decision(gerbang)["decision"] == "granted" and vlm.calls == 1
    assert [int(batch[0][0, 0, 0]) for batch in policy_env.identifier.calls[1:]] == [10, 20]
