"""Coach reads + updates Hevy routines (#314).

G1 render + shared-formatter identity; G2 fetch-failure/stale isolated; G3 update happy /
stale-refused / unknown-id-refused / rpe-stripped / diff reported (§18: the stale guard rests on
the pre-write refetch — skip it and the stale-write test can't refuse); G4 no MCP tool name in
any rendered prompt section; the double-footer guard (one reply → one write per block, one
footer); phase-folder-on-create.
"""
import asyncio

import pytest

import context_builder
import hevy_routine_cache
import hevy_routine_format
import mcp_server
from routers.chat import (
    _compose_response,
    _process_knowledge_updates,
    _process_routine_actions,
    _process_routine_updates,
    _strip_footer_echo,
)


def _run(coro):
    # asyncio.run makes a fresh loop per call — robust in the full suite, where a shared
    # get_event_loop() can be closed by an earlier test.
    return asyncio.run(coro)


# --------------------------- fakes --------------------------- #

class _FakeHevy:
    def __init__(self, routine=None, folders=None, routines=None):
        self._routine = routine
        self._folders = folders or []
        self._routines = routines or []
        self.updated = []          # (routine_id, title, exercises)
        self.created_folders = []  # titles
        self.get_routine_calls = 0

    async def get_routine(self, routine_id):
        self.get_routine_calls += 1
        if self._routine is None:
            import httpx
            raise httpx.HTTPStatusError("404", request=None, response=None)
        return {"routine": self._routine}

    async def update_routine(self, routine_id, title, exercises):
        # mirror the real connector: strip rpe via the shared builder
        from connectors.hevy import _validate_routine_exercises
        built = _validate_routine_exercises(exercises)
        self.updated.append((routine_id, title, built))
        return {"routine": {"id": routine_id}}

    async def get_routine_folders(self, page_size=10):
        return self._folders

    async def create_routine_folder(self, title):
        self.created_folders.append(title)
        return {"routine_folder": {"id": 999, "title": title}}

    async def get_all_routines(self, page_size=10):
        return self._routines


_ROUTINE = {
    "id": "rt-1", "title": "Push", "folder_id": 5, "updated_at": "2026-09-19T08:00:00Z",
    "exercises": [
        {"exercise_template_id": "A", "title": "Bench", "sets": [{"type": "normal", "weight_kg": 60, "reps": 8}]},
        {"exercise_template_id": "B", "title": "Fly", "sets": [{"type": "normal", "weight_kg": 15, "reps": 12}]},
    ],
}


# --------------------------- G1: render + shared formatter --------------------------- #

def test_shared_formatter_is_one_renderer_two_callers():
    assert mcp_server.format_routine_compact is hevy_routine_format.format_routine_compact
    assert mcp_server.format_routine_full is hevy_routine_format.format_routine_full
    assert context_builder.format_routine_full is hevy_routine_format.format_routine_full


def test_section_renders_index_and_declared_full_working_set():
    data = {"routines": [_ROUTINE], "folders": [{"id": 5, "title": "Block 2"}],
            "age_seconds": 0, "stale": False, "unavailable": False}
    out = context_builder._section_hevy_routines(data, {"label": "Base"}, {"Base": 5})
    assert "### All routines (1) — index" in out
    assert "declared for phase 'Base'" in out
    assert "Bench" in out and "60kg × 8" in out           # full detail present


def test_section_fallback_folder_says_so_when_undeclared():
    data = {"routines": [_ROUTINE], "folders": [{"id": 5, "title": "Block 2"}],
            "age_seconds": 0, "stale": False, "unavailable": False}
    out = context_builder._section_hevy_routines(data, {"label": "Base"}, None)
    assert "FALLBACK" in out and "most-recently-used" in out


def test_section_omitted_when_no_hevy():
    assert context_builder._section_hevy_routines(None, None, None) == ""


# --------------------------- G2: fetch failure / stale isolated --------------------------- #

def test_section_unavailable_never_crashes():
    out = context_builder._section_hevy_routines(
        {"routines": [], "folders": [], "unavailable": True}, None, None)
    assert "unavailable" in out.lower()


def test_section_marks_stale_copy_with_age():
    data = {"routines": [_ROUTINE], "folders": [], "age_seconds": 420, "stale": True, "unavailable": False}
    out = context_builder._section_hevy_routines(data, None, None)
    assert "Cached copy ~7 min old" in out


def test_cache_serves_stale_on_fetch_error_else_unavailable():
    class _Boom:
        async def get_all_routines(self, page_size=10): raise RuntimeError("down")
        async def get_routine_folders(self, page_size=10): return []
    hevy_routine_cache.invalidate(1)
    # nothing cached → unavailable
    r = _run(hevy_routine_cache.get_routines_cached(_Boom(), 1))
    assert r["unavailable"] is True
    # seed a good copy, then a later failing fetch (ttl expired) serves it stale
    good = _FakeHevy(routines=[_ROUTINE], folders=[{"id": 5, "title": "B2"}])
    r2 = _run(hevy_routine_cache.get_routines_cached(good, 1, now=1000.0))
    assert r2["unavailable"] is False and r2["routines"]
    r3 = _run(hevy_routine_cache.get_routines_cached(_Boom(), 1, now=2000.0))  # ttl expired → fetch fails
    assert r3["stale"] is True and r3["routines"] and r3["age_seconds"] == 1000


# --------------------------- G3: update path --------------------------- #

def test_update_happy_path_reports_diff_and_sends_no_folder(db_session):
    fake = _FakeHevy(routine=dict(_ROUTINE))
    block = (
        '<hevy_update_routine>{"routine_id":"rt-1","title":"Push","updated_at":'
        '"2026-09-19T08:00:00Z","exercises":['
        '{"exercise_template_id":"A","sets":[{"type":"normal","weight_kg":65,"reps":8,"rpe":8}]}]}'
        "</hevy_update_routine>"
    )
    cleaned, actions, results = _run(_process_routine_updates(block, fake, 1, db_session))
    assert len(results) == 1 and results[0].saved is True
    assert fake.updated, "update_routine was called"
    rid, title, built = fake.updated[0]
    assert rid == "rt-1"
    # rpe stripped by the shared builder; Fly (B) removed → diff names it
    assert "rpe" not in built[0]["sets"][0]
    assert "removed" in results[0].reason and "Fly" in results[0].reason
    assert "changed sets" in results[0].reason  # Bench weight 60→65


def test_update_refused_when_stale(db_session):
    """Block's updated_at differs from the live refetch → refuse, do not write. §18: this refusal
    depends on the pre-write get_routine refetch; skip that and there is no live value to compare,
    so a stale write would go through and this test would fail."""
    live = dict(_ROUTINE); live["updated_at"] = "2026-09-20T09:00:00Z"  # changed upstream
    fake = _FakeHevy(routine=live)
    block = (
        '<hevy_update_routine>{"routine_id":"rt-1","title":"Push","updated_at":'
        '"2026-09-19T08:00:00Z","exercises":[{"exercise_template_id":"A","sets":[]}]}'
        "</hevy_update_routine>"
    )
    _, _, results = _run(_process_routine_updates(block, fake, 1, db_session))
    assert results[0].saved is False and results[0].reason_code == "stale"
    assert not fake.updated, "no write on a stale routine"
    assert fake.get_routine_calls == 1, "the refetch must run (the stale guard rests on it)"


def test_update_unknown_id_refused_nothing_written(db_session):
    fake = _FakeHevy(routine=None)  # get_routine raises → not found
    block = '<hevy_update_routine>{"routine_id":"nope","exercises":[]}</hevy_update_routine>'
    _, _, results = _run(_process_routine_updates(block, fake, 1, db_session))
    assert results[0].saved is False and results[0].reason_code == "not_found"
    assert not fake.updated


def test_update_needs_a_routine_id(db_session):
    fake = _FakeHevy(routine=dict(_ROUTINE))
    block = '<hevy_update_routine>{"exercises":[]}</hevy_update_routine>'
    _, _, results = _run(_process_routine_updates(block, fake, 1, db_session))
    assert results[0].saved is False and results[0].reason_code == "invalid_shape"
    assert not fake.updated


# --------------------------- phase-folder on create --------------------------- #

def test_create_uses_declared_phase_folder(db_session):
    fake = _FakeHevy(routines=[])
    # capture create_routine
    created = {}
    async def _create(title, exercises, folder_id=None):
        created["folder_id"] = folder_id
        return {"routine": {"id": "new"}}
    fake.create_routine = _create
    block = ('<hevy_create_routine>{"title":"New","exercises":['
             '{"exercise_template_id":"A","sets":[{"type":"normal","reps":5}]}]}</hevy_create_routine>')
    _run(_process_routine_actions(block, fake, 1, db_session,
                                  phase_label="Base", phase_folders={"Base": 7}))
    assert created["folder_id"] == 7   # placed in the declared folder, no block folder given


def test_create_makes_phase_folder_when_none_declared(db_session):
    fake = _FakeHevy(routines=[], folders=[])  # no folder named after the phase
    created = {}
    async def _create(title, exercises, folder_id=None):
        created["folder_id"] = folder_id
        return {"routine": {"id": "new"}}
    fake.create_routine = _create
    block = ('<hevy_create_routine>{"title":"New","exercises":['
             '{"exercise_template_id":"A","sets":[{"type":"normal","reps":5}]}]}</hevy_create_routine>')
    _run(_process_routine_actions(block, fake, 1, db_session,
                                  phase_label="Base", phase_folders=None))
    assert fake.created_folders == ["Base"]   # created a phase-named folder
    assert created["folder_id"] == 999        # and placed the routine in it


# --------------------------- G4: no MCP tool name in the prompt --------------------------- #

_MCP_TOOL_NAMES = [
    "search_hevy_routines", "get_hevy_routine", "get_recovery_metrics", "get_checkin_history",
    "get_training_sessions", "get_hevy_workouts", "get_readiness_snapshot", "get_training_load",
    "get_lab_results",
]


def test_no_mcp_tool_name_appears_in_any_rendered_prompt_section():
    sections = [
        context_builder._section_user_profile(None),
        context_builder._section_routine_creation(["hevy"]),
        context_builder._section_exercise_creation(["hevy"]),
        context_builder._section_knowledge_update(),
        context_builder._section_onboarding_interview(),
    ]
    blob = "\n".join(sections)
    for name in _MCP_TOOL_NAMES:
        assert name not in blob, f"MCP tool name {name!r} leaked into a rendered prompt section"


# --------------------------- double-footer guard (ruling 5) --------------------------- #

def _kn_block(key, activity, day):
    import json
    payload = {"type": "schedule_item", "key": key, "value": {
        "activity": activity, "days": [day], "hard": False, "expected_load": "light",
        "time_of_day": "morning", "same_day_training": False, "duration_weeks": None,
        "season_end": None}}
    return f"<knowledge_update>{json.dumps(payload)}</knowledge_update>"


def test_one_reply_one_write_per_block_and_exactly_one_footer(db_session):
    import models
    u = models.User(email="footer314@x.io", hashed_password="x")
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    # three distinct, non-clashing schedule_item rewrites in one reply, PLUS a model footer echo
    # (the tally, #314) AND a model echo of a PER-ENTRY action line (#316 carry-over).
    reply = ("Done.\n" + _kn_block("mon_a", "gym A", "monday") + _kn_block("tue_b", "gym B", "tuesday")
             + _kn_block("wed_c", "gym C", "wednesday")
             + "\n✓ Schedule entry saved: mon_a\n✓ 3 saved")
    cleaned, actions, results = _process_knowledge_updates(reply, u.id, db_session)
    assert len(results) == 3 and all(r.saved for r in results)   # exactly one write per block

    class _DummyClient: pass
    final, _ = _compose_response(
        client=_DummyClient(), model="m", user_message="x", reply=cleaned,
        all_actions=actions, write_results=results)
    assert final.count("✓ 3 saved") == 1     # tally echo stripped, one authoritative footer
    # #316: every per-entry action line appears EXACTLY once — the model's echo of "mon_a" is
    # stripped before the authoritative `actions_taken` are appended.
    for key in ("mon_a", "tue_b", "wed_c"):
        assert final.count(f"✓ Schedule entry saved: {key}") == 1


def test_strip_footer_echo_strips_per_entry_action_echoes(db_session):
    # #316: per-entry action lines the MODEL wrote are stripped too (they duplicated in prod);
    # ordinary prose — including a ✓ bullet that is NOT an action line — is kept.
    txt = ("✓ Schedule entry saved: mon_a\n"
           "✗ Injury entry NOT saved: knee — day clash\n"
           "✓ Routine 'Push Day' created in Hevy — folder Base\n"
           "✓ 3 saved\n"
           "✓ Your deadlift is looking strong this week\n"     # prose, no action phrase → kept
           "keep me")
    out = _strip_footer_echo(txt)
    assert "✓ Schedule entry saved: mon_a" not in out
    assert "NOT saved: knee" not in out
    assert "created in Hevy" not in out
    assert "✓ 3 saved" not in out
    assert "✓ Your deadlift is looking strong this week" in out   # prose survives
    assert "keep me" in out
