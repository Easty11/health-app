"""get_hevy_workouts summary parity (DECISIONS_LOG #68).

The summarizer used to read the set-type field as `set_type` (a dead no-op — the
raw field is `type`), skip all-warmup exercises, and render only weight×reps /
BW×reps sets — dropping per-set RPE, exercise notes, workout description, warmup
labels, and duration/distance-only movements. These faked-payload tests assert
the six restored behaviours end-to-end through the real tool.

The Hevy client is faked (no live API); get_hevy_workouts builds its own
HevyClient, opens its own SessionLocal, and resolves the user via
`_current_user_id`, so all three are monkeypatched. The stored key is a real
Fernet token so the tool's own `decrypt` runs unmocked.
"""
import asyncio

import pytest

import mcp_server
import models
from encryption import encrypt

USER = 42

# One workout exercising every restored behaviour. start_time is recent-relative
# only in that the test calls the tool with a very wide `days` window.
WORKOUT = {
    "title": "Lower Strength",
    "description": "Deload week - keep RPE capped",   # (7) workout description
    "start_time": "2026-07-10T08:17:58+00:00",
    "end_time": "2026-07-10T09:20:00+00:00",
    "exercises": [
        {
            "title": "Back Squat",
            "exercise_template_id": "SQ01",
            # (3) multi-line note: L/R tag on line 1, observation on line 2
            "notes": "Left side\nFelt a twinge in hip",
            "sets": [
                # (1) warmup — deliberately HEAVIER than the working sets so that
                # e1RM excluding it (116.7) differs from including it (140.0);
                # (2) half-point RPE.
                {"type": "warmup", "weight_kg": 120, "reps": 5, "rpe": 6},
                {"type": "normal", "weight_kg": 100, "reps": 5, "rpe": 8.5},
                {"type": "normal", "weight_kg": 100, "reps": 5, "rpe": 9},
            ],
        },
        {
            "title": "Plank",
            "exercise_template_id": "PL01",
            "notes": "",
            # (4) duration-only set
            "sets": [{"type": "normal", "duration_seconds": 60}],
        },
        {
            "title": "Sled Drag",
            "exercise_template_id": "SL01",
            "notes": "",
            # (5) distance-only set (no weight, no reps)
            "sets": [{"type": "normal", "distance_meters": 100}],
        },
        {
            "title": "Band Pull-Apart",
            "exercise_template_id": "BP01",
            "notes": "",
            # (6) all-warmup exercise — must still render, no e1RM
            "sets": [
                {"type": "warmup", "reps": 20},
                {"type": "warmup", "reps": 20},
            ],
        },
    ],
}


def _install(monkeypatch, db_session, workout=WORKOUT):
    db_session.add(models.UserIntegration(
        user_id=USER, provider="hevy", api_key_encrypted=encrypt("fake-key"),
    ))
    db_session.commit()

    class FakeHevyClient:
        def __init__(self, api_key):
            self.api_key = api_key

        async def get_workouts(self, page=1, page_size=10):
            # Page 1 carries the workout; page 2 is empty to terminate the loop.
            if page == 1:
                return {"workouts": [workout], "page_count": 1}
            return {"workouts": [], "page_count": 1}

    monkeypatch.setattr(mcp_server, "HevyClient", FakeHevyClient)
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: USER)


def _run(monkeypatch, db_session, workout=WORKOUT):
    _install(monkeypatch, db_session, workout)
    # Wide window so the fixed 2026-07-10 workout is always inside it.
    return asyncio.run(mcp_server.get_hevy_workouts(days=36500))


# ---------- (1) warmup rendered + labelled, excluded from e1RM ----------
def test_warmup_rendered_and_labelled(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    assert "[warmup]" in out                       # rendered AND labelled
    assert "120kg × 5" in out                       # the warmup set is not dropped


def test_warmup_excluded_from_e1rm(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    # Working sets only: _epley_1rm(100, 5) = 116.7. Including the heavier warmup
    # would give 140.0 — its absence proves the exclusion.
    assert "e1RM≈116.7kg" in out
    assert "140.0" not in out


# ---------- (2) per-set RPE incl. half-points ----------
def test_rpe_rendered_including_half_points(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    assert "RPE 8.5" in out
    assert "RPE 9" in out


# ---------- (3) multi-line note preserved (both lines) ----------
def test_multiline_note_preserved(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    assert "Left side" in out
    assert "Felt a twinge in hip" in out


# ---------- (4) duration-only set rendered, not blank ----------
def test_duration_only_set_rendered(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    assert "1m 00s" in out


# ---------- (5) distance-only set rendered, not blank ----------
def test_distance_only_set_rendered(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    assert "100m" in out


# ---------- (6) all-warmup exercise not skipped ----------
def test_all_warmup_exercise_not_skipped(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    assert "Band Pull-Apart" in out


# ---------- (7) workout description shown when present ----------
def test_description_shown_when_present(monkeypatch, db_session):
    out = _run(monkeypatch, db_session)
    assert "Deload week - keep RPE capped" in out


def test_description_absent_when_empty(monkeypatch, db_session):
    workout = {**WORKOUT, "description": ""}
    out = _run(monkeypatch, db_session, workout)
    assert "Description:" not in out
