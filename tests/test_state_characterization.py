"""Karakterisasi state machine gerbang `StateManager.update_frame_detections` (T42b).

Sebelum fungsi ±100 baris itu dipecah, perilaku kode lama untuk ribuan frame
acak (orang masuk/keluar, tubuh terpotong, melangkah, VLM menjawab lengkap/kurang/
gangguan/galat dengan jeda beberapa frame, potongan gambar kosong) direkam di
`golden/state_manager.json`, termasuk isi baris audit & riwayat (T42e).
Refaktor tidak boleh mengubahnya.

Bila perilaku SENGAJA diubah, bangkitkan ulang acuannya:
    python tests/test_state_characterization.py --regenerate
"""
import json
import sys
import time as real_time
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOLDEN = Path(__file__).resolve().parent / "golden" / "state_manager.json"
SCENARIOS, FRAMES, FPS = 18, 1200, 15
VLM_DELAY_FRAMES = 4
SLOW_VLM_DELAY_FRAMES = 3 * FPS   # > jeda jalur kosong: hasil tiba setelah sesi berakhir (T42e)
CFG_OVERRIDES = {"STANDBY_RESET_DELAY_SECONDS": 1.5, "READY_HOLD_SECONDS": 1.0, "STABLE_FRAMES_REQUIRED": 3,
                 "VLM_SYSTEM_RETRY_SECONDS": 2.0, "DECIDED_TRACK_MEMORY_SECONDS": 10.0}


class _World:
    """Jam, suara, VLM, dan audit tiruan yang dipasang ke modul state_manager."""

    def __init__(self, sm_module, monkeypatch, first_reply: int = 0, delay_frames: int = VLM_DELAY_FRAMES):
        from backend.vlm_analyzer import InspectionResult
        self.delay = delay_frames / FPS
        self.now, self.sounds, self.pending, self.vlm_calls, self.audits = 1000.0, [], [], 0, []
        clock = types.SimpleNamespace(time=lambda: self.now, strftime=real_time.strftime)
        monkeypatch.setattr(sm_module, "time", clock)
        ap = sm_module.audio_player
        monkeypatch.setattr(ap, "play", lambda name, *a, **k: self.sounds.append(name))
        monkeypatch.setattr(ap, "play_step_back", lambda clip_type="": self.sounds.append(f"mundur:{clip_type}"))
        monkeypatch.setattr(ap, "play_result", lambda is_complete, missing_items=None:
                            self.sounds.append(f"hasil:{is_complete}:{','.join(missing_items or [])}"))
        monkeypatch.setattr(sm_module.report_mgr, "save_inspection", self._save)
        replies = [InspectionResult(is_complete=True, inference_source="VLM_LIVE:x"),
                   InspectionResult(is_complete=False, missing_items=["Helm Keselamatan"], inference_source="VLM_LIVE:x"),
                   InspectionResult(is_system_unavailable=True), None]

        def analyze(crop):
            self.vlm_calls += 1
            reply = replies[(self.vlm_calls - 1 + first_reply) % len(replies)]
            if reply is None:
                raise RuntimeError("galat VLM tiruan")
            return reply
        monkeypatch.setattr(sm_module.vlm_analyzer, "analyze_person", analyze)

    def _save(self, crop_img, **fields):
        self.audits.append(dict(fields, crop_shape=list(crop_img.shape)))
        return {"snapshot_filename": f"bukti-{len(self.audits)}.jpg"}

    def submit(self, fn, *args):
        self.pending.append((self.now + self.delay, fn, args))

    def run_due(self):
        due = [p for p in self.pending if p[0] <= self.now]
        self.pending = [p for p in self.pending if p[0] > self.now]
        for _, fn, args in due:
            fn(*args)


def _people(rng, frame_i, state):
    """0-2 orang; subjek melangkah lalu berhenti, kadang terpotong/menyamping/keluar jalur."""
    from backend import messages
    from backend.detector import DetectionResult
    p_leave = 0.004 if state["seed"] % 3 == 2 else 0.04    # seed%3==2: lama di jalur (>12 dtk terpotong)
    if state["present"] and rng.random() < p_leave:         # pekerja pergi 2-4 dtk (> jeda jalur kosong)
        state["present"], state["away"] = False, int(rng.integers(2 * FPS, 4 * FPS))
    elif not state["present"]:
        state["away"] -= 1
        if state["away"] <= 0:                                 # datang: biasanya orang baru
            state["present"], state["y"], state["walking"] = True, 300.0, True
            # Skenario seed%3==1: pekerja yang sama sering kembali (menguji ingatan keputusan lolos)
            state["tid"] += 1 if rng.random() < (0.2 if state["seed"] % 3 == 1 else 0.8) else 0
    out = []
    if state["present"]:
        # Keadaan bertahan beberapa saat sebelum berubah, seperti orang sungguhan
        # Skenario seed%3==2: tubuh lama terpotong (menguji batas suara mundur per sesi)
        p_full = 0.003 if state["seed"] % 3 == 2 else 0.015
        for key, p_flip in (("walking", 0.04), ("full", p_full), ("facing", 0.015)):
            if rng.random() < p_flip:
                state[key] = not state[key]
        state["y"] += 6.0 if state["walking"] else float(rng.normal(0, 1))
        full, facing = state["full"], state["facing"]
        kp = [[0, 0, 0.9]] * 17 if facing else [[0, 0, 0.9]] * 5 + [[0, 0, 0.1]] * 2 + [[0, 0, 0.9]] * 10
        y = state["y"]
        crop = (rng.integers(0, 255, (24, 12, 3))).astype(np.uint8)
        if state["seed"] % 4 == 3 and rng.random() < 0.3:   # potongan gagal dibuat (T42e)
            crop = None
        out.append(DetectionResult(track_id=state["tid"], bbox=[400, int(y - 250), 500, int(y + 250)], is_full_body=full,
                                   reason=messages.POSE_OK if full else messages.POSE_FEET_CLIPPED,
                                   is_inside_corridor=rng.random() > 0.05, keypoints=kp, crop_img=crop, conf=0.9,
                                   clip_type="OPTIMAL" if full else "FEET_CLIPPED"))
    if rng.random() < 0.1:   # orang lain lewat, kadang di dalam jalur
        out.append(DetectionResult(track_id=99, bbox=[100, 50, 160, 400], is_full_body=True, reason=messages.POSE_OK,
                                   is_inside_corridor=rng.random() < 0.3, keypoints=None, crop_img=None, conf=0.8))
    return out


def run_scenarios(monkeypatch):
    import backend.state_manager as sm
    from backend.config import cfg
    from backend.notifier import notifier
    for k, v in CFG_OVERRIDES.items():
        monkeypatch.setattr(cfg, k, v)
    out = []
    for seed in range(SCENARIOS):
        world = _World(sm, monkeypatch, first_reply=seed,
                       delay_frames=SLOW_VLM_DELAY_FRAMES if seed % 6 == 4 else VLM_DELAY_FRAMES)
        mgr = sm.StateManager()
        monkeypatch.setattr(mgr, "executor", types.SimpleNamespace(submit=world.submit))
        notifier.set_idle()
        rng, state = np.random.default_rng(seed), {"present": True, "tid": 1, "y": 300.0, "walking": True,
                                                  "full": seed % 3 != 2, "facing": True, "seed": seed}
        base = sm.GateSession._counter
        for i in range(FRAMES):
            world.now += 1 / FPS
            world.sounds.clear()
            audits, history = len(world.audits), len(mgr.inspection_history)
            mgr.update_frame_detections(_people(rng, i, state))
            world.run_due()
            s = mgr.session
            newest = None
            if len(mgr.inspection_history) != history:   # riwayat baru tanpa jam dinding
                newest = {k: v for k, v in mgr.inspection_history[0].items() if k != "timestamp"}
            out.append([seed, i, None if s is None else s.session_id - base, None if s is None else s.state,
                        None if s is None else s.track_id, None if s is None else s.stable_frames,
                        notifier.current_state, list(world.sounds), world.vlm_calls, len(mgr.inspection_history),
                        world.audits[audits:], newest,
                        None if s is None or s.vlm_result is None else s.vlm_result.model_dump()])
    return out


def test_state_machine_tidak_berubah(monkeypatch, catalog_defaults):
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = json.loads(json.dumps(run_scenarios(monkeypatch)))
    diffs = [i for i, (a, e) in enumerate(zip(actual, expected)) if a != e]
    assert len(actual) == len(expected) and not diffs, f"{len(diffs)} frame berubah, mis. {[actual[i] for i in diffs[:2]]}"


def test_acuan_mencakup_semua_keadaan():
    rows = json.loads(GOLDEN.read_text(encoding="utf-8"))
    states = {r[3] for r in rows}
    assert {"STEP_BACK_WARNING", "STABILIZING", "ANALYZING", "ANALYZED", "WAITING_SYSTEM", None} <= states, states
    assert {"GREEN", "RED", "OFF"} <= {r[6] for r in rows}
    # T42e: baris audit, hasil terlambat (sesi sudah berakhir), sesi diulang setelah galat
    # VLM / potongan kosong (ANALYZING → mundur ke awal, sesi sama, tanpa audit)
    assert any(r[10] for r in rows) and any(r[11] for r in rows)
    assert any(r[10] and r[3] != "ANALYZED" for r in rows), "hasil terlambat tidak terekam"
    retried = [(a, b) for a, b in zip(rows, rows[1:]) if a[0] == b[0] and a[2] == b[2]
               and a[3] == "ANALYZING" and b[3] in ("INITIAL", "STABILIZING") and not b[10]]
    assert {a[8] == b[8] for a, b in retried} == {True, False}, "galat VLM & potongan kosong harus sama-sama terekam"

if __name__ == "__main__" and "--regenerate" in sys.argv:
    import conftest  # noqa: F401
    import pytest
    from backend import ppe_rules
    mp = pytest.MonkeyPatch()
    mp.setattr(ppe_rules, "_active_overrides", {})   # sama dengan fixture catalog_defaults
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(run_scenarios(mp)), encoding="utf-8")
    mp.undo()
    print(f"acuan ditulis: {GOLDEN}")
