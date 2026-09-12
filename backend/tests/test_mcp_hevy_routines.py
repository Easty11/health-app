"""Hevy routine read-back MCP tools — `search_hevy_routines` + `get_hevy_routine`.

Mirrors `test_hevy_summary_enrichment`'s harness: the Hevy client is faked (no
live API), the tools build their own `HevyClient`, open their own `SessionLocal`,
and resolve the user via `_current_user_id`, so all three are monkeypatched. The
stored key is a real Fernet token so the tools' own `decrypt` runs unmocked
(auth/decrypt path exercised end-to-end, as the workout tool's tests do).

Coverage:
  * list returns compact live data (title/id/folder/exercise titles + count) and
    NO per-set detail;
  * list paginates (page < page_count) and concatenates;
  * full-by-id returns the complete config INCLUDING superset grouping, rest,
    notes, and every set;
  * exercise names render as titles, with a store fallback when the live payload
    omits a title (VERIFY 4);
  * empty (no routines) and bad-id (404) are handled cleanly, not as a crash;
  * not-connected returns a clear message.
"""
import asyncio

import httpx
import pytest

import mcp_server
import models
from encryption import encrypt

USER = 42

# Two routines to exercise pagination (one per page) and the compact list shape.
ROUTINE_LIST_P1 = {
    "id": "rt-push-1",
    "title": "Push Day",
    "folder_id": 5,
    "exercises": [
        {"exercise_template_id": "BENCH01", "title": "Bench Press (Barbell)",
         "sets": [{"type": "normal", "weight_kg": 80, "reps": 5}]},
        {"exercise_template_id": "FLY01", "title": "Cable Fly",
         "sets": [{"type": "normal", "weight_kg": 15, "reps": 12}]},
    ],
}
ROUTINE_LIST_P2 = {
    "id": "rt-pull-2",
    "title": "Pull Day",
    "folder_id": None,
    "exercises": [
        {"exercise_template_id": "ROW01", "title": "Barbell Row",
         "sets": [{"type": "normal", "weight_kg": 70, "reps": 8}]},
    ],
}

# One routine in full, exercising superset grouping (two exercises share
# superset_id 0 — a valid id that is falsy, so it also guards the `is not None`
# check), rest, multi-line notes, warmup labelling, and RPE.
ROUTINE_FULL = {
    "id": "rt-push-1",
    "title": "Push Day",
    "folder_id": 5,
    "notes": "Chest focus - superset the fly",
    "exercises": [
        {"exercise_template_id": "BENCH01", "title": "Bench Press (Barbell)",
         "superset_id": 0, "rest_seconds": 120,
         "notes": "Left side\nWatch shoulder",
         "sets": [
             {"type": "warmup", "weight_kg": 40, "reps": 10},
             {"type": "normal", "weight_kg": 80, "reps": 5, "rpe": 8.5},
         ]},
        {"exercise_template_id": "FLY01", "title": "Cable Fly",
         "superset_id": 0, "rest_seconds": 60, "notes": "",
         "sets": [{"type": "normal", "weight_kg": 15, "reps": 12}]},
        {"exercise_template_id": "TRI01", "title": "Tricep Pushdown",
         "superset_id": None, "rest_seconds": 90, "notes": "",
         "sets": [{"type": "normal", "weight_kg": 30, "reps": 15}]},
    ],
}


class _FakeHevyClient:
    """Configurable fake: `pages` drives get_routines, `by_id` drives get_routine.
    A routine_id absent from `by_id` raises a 404 like the real connector's `_check`."""

    pages: dict[int, dict] = {}
    by_id: dict[str, dict] = {}

    def __init__(self, api_key):
        self.api_key = api_key

    async def get_routines(self, page=1, page_size=10):
        return self.pages.get(page, {"routines": [], "page_count": max(self.pages, default=1)})

    async def get_routine(self, routine_id):
        if routine_id not in self.by_id:
            request = httpx.Request("GET", f"https://api.hevyapp.com/v1/routines/{routine_id}")
            response = httpx.Response(404, request=request, text="not found")
            raise httpx.HTTPStatusError("404", request=request, response=response)
        return self.by_id[routine_id]


def _install(monkeypatch, db_session, *, pages=None, by_id=None, connect=True,
             templates=None):
    db_session.add(models.User(id=USER, email=f"u{USER}@test", hashed_password="x"))
    db_session.flush()
    if connect:
        db_session.add(models.UserIntegration(
            user_id=USER, provider="hevy", api_key_encrypted=encrypt("fake-key"),
        ))
    for tid, title in (templates or {}).items():
        db_session.add(models.HevyExerciseTemplate(id=tid, title=title, is_custom=False))
    db_session.commit()

    _FakeHevyClient.pages = pages or {}
    _FakeHevyClient.by_id = by_id or {}

    monkeypatch.setattr(mcp_server, "HevyClient", _FakeHevyClient)
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: USER)


# ---------- search_hevy_routines ----------

def test_search_lists_routines_compactly(monkeypatch, db_session):
    _install(monkeypatch, db_session, pages={1: {"routines": [ROUTINE_LIST_P1], "page_count": 1}})
    out = asyncio.run(mcp_server.search_hevy_routines())
    assert "Push Day" in out
    assert "id: rt-push-1" in out
    assert "folder: 5" in out
    assert "2 exercise(s): Bench Press (Barbell), Cable Fly" in out


def test_search_omits_set_detail(monkeypatch, db_session):
    """The compact list must stay context-small — no per-set rendering."""
    _install(monkeypatch, db_session, pages={1: {"routines": [ROUTINE_LIST_P1], "page_count": 1}})
    out = asyncio.run(mcp_server.search_hevy_routines())
    assert "Set 1" not in out
    assert "80kg" not in out


def test_search_paginates_and_concatenates(monkeypatch, db_session):
    _install(monkeypatch, db_session, pages={
        1: {"routines": [ROUTINE_LIST_P1], "page_count": 2},
        2: {"routines": [ROUTINE_LIST_P2], "page_count": 2},
    })
    out = asyncio.run(mcp_server.search_hevy_routines())
    assert "Push Day" in out
    assert "Pull Day" in out
    assert "Hevy routines (2)" in out
    assert "folder: none" in out  # P2 has folder_id None


def test_search_empty(monkeypatch, db_session):
    _install(monkeypatch, db_session, pages={1: {"routines": [], "page_count": 1}})
    out = asyncio.run(mcp_server.search_hevy_routines())
    assert "No routines found in Hevy." in out


def test_search_not_connected(monkeypatch, db_session):
    _install(monkeypatch, db_session, connect=False)
    out = asyncio.run(mcp_server.search_hevy_routines())
    assert "Hevy integration not connected" in out


# ---------- get_hevy_routine ----------

def test_full_returns_complete_config_with_supersets(monkeypatch, db_session):
    _install(monkeypatch, db_session, by_id={"rt-push-1": ROUTINE_FULL})
    out = asyncio.run(mcp_server.get_hevy_routine("rt-push-1"))
    # Header + routine notes
    assert "## Push Day  (id: rt-push-1, folder: 5)" in out
    assert "Chest focus - superset the fly" in out
    # Superset grouping surfaced (0 is a valid, falsy id)
    assert out.count("[superset 0]") == 2
    assert "[superset" not in out.split("Tricep Pushdown")[1]  # the None-superset ex has no tag
    # Rest, multi-line notes, per-set detail incl. warmup label + RPE
    assert "rest: 120s" in out
    assert "note: Left side" in out
    assert "note: Watch shoulder" in out
    assert "[warmup]" in out
    assert "RPE 8.5" in out
    assert "80kg × 5" in out


def test_full_renders_titles_not_uuids(monkeypatch, db_session):
    _install(monkeypatch, db_session, by_id={"rt-push-1": ROUTINE_FULL})
    out = asyncio.run(mcp_server.get_hevy_routine("rt-push-1"))
    assert "Bench Press (Barbell)" in out
    assert "BENCH01" not in out  # the id must not leak when a title is present


def test_full_title_fallback_from_store(monkeypatch, db_session):
    """When the live payload omits a title, resolve it from the template store."""
    routine = {
        "id": "rt-x", "title": "Legs", "folder_id": None,
        "exercises": [
            {"exercise_template_id": "STORE01", "superset_id": None,
             "rest_seconds": 90, "sets": [{"type": "normal", "reps": 10}]},
        ],
    }
    _install(monkeypatch, db_session, by_id={"rt-x": routine},
             templates={"STORE01": "Back Squat"})
    out = asyncio.run(mcp_server.get_hevy_routine("rt-x"))
    assert "Back Squat" in out
    assert "STORE01" not in out


def test_full_bad_id(monkeypatch, db_session):
    _install(monkeypatch, db_session, by_id={"rt-push-1": ROUTINE_FULL})
    out = asyncio.run(mcp_server.get_hevy_routine("does-not-exist"))
    assert "No routine found with id 'does-not-exist'." in out


def test_full_tolerates_routine_wrapper(monkeypatch, db_session):
    """Hevy wraps the single-routine GET as {"routine": {...}} — unwrap it."""
    _install(monkeypatch, db_session, by_id={"rt-push-1": {"routine": ROUTINE_FULL}})
    out = asyncio.run(mcp_server.get_hevy_routine("rt-push-1"))
    assert "## Push Day  (id: rt-push-1, folder: 5)" in out


def test_full_not_connected(monkeypatch, db_session):
    _install(monkeypatch, db_session, connect=False, by_id={"rt-push-1": ROUTINE_FULL})
    out = asyncio.run(mcp_server.get_hevy_routine("rt-push-1"))
    assert "Hevy integration not connected" in out


# ---------- as_of stamp (mirrors the workout tool) ----------

def test_output_carries_as_of_stamp(monkeypatch, db_session):
    _install(monkeypatch, db_session, pages={1: {"routines": [ROUTINE_LIST_P1], "page_count": 1}})
    out = asyncio.run(mcp_server.search_hevy_routines())
    assert out.splitlines()[0].startswith("as_of: ")
