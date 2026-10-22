"""`get_exercise_catalogue` (Q27 tag pass, STEP 3b): the MCP read of the Hevy exercise catalogue with its tag state.

READ-ONLY and visibility-scoped. The tag state is `selection.classify_coverage` (the one definition the audit
uses); the visibility predicate is `hevy_templates._visible_to`. Network is faked at the two refresh doors.
"""
import asyncio
from datetime import datetime, timezone

import pytest

import mcp_server
import models
from engine import selection

from test_capability_observations import _FORBIDDEN_VERDICT
from test_series_exercise import _user

DEFAULT_ID = "C469EA70"
CUSTOM_ID = "238ebf2c-d96c-4673-abe0-f7a0ec887867"
NOPAT_ID = "d17b9661-e174-4f73-bd82-9e7025a34e2c"
UNTAGGED_ID = "11111111-aaaa-bbbb-cccc-000000000001"
SIDED_ID = "bb1aa298-c18a-4702-b4c8-1b8dc97b28a8"
OTHER_ID = "99999999-aaaa-bbbb-cccc-000000000009"


def _tmpl(db, tid, title, *, owner=None, laterality=None, adjudicated=False):
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=owner is not None, owner_user_id=owner, laterality=laterality,
        adjudicated_at=datetime.now(timezone.utc) if adjudicated else None))
    db.commit()


def _tag(db, tid, region, role="primary", side=None):
    db.add(models.ExerciseRegionTag(hevy_exercise_template_id=tid, region_key=region, role=role, side=side))
    db.commit()


@pytest.fixture
def world(db_session, monkeypatch):
    """User 1 and user 2; a default, three of user 1's customs (tagged / no-pattern / untagged), a sided
    custom, and a custom owned by user 2. Refresh doors faked and recorded."""
    u1, u2 = _user(db_session, "cat1@example.com"), _user(db_session, "cat2@example.com")
    _tmpl(db_session, DEFAULT_ID, "Hip Abduction (Cable)")
    _tmpl(db_session, CUSTOM_ID, "Copenhagen Adductor Plank Hip Lift", owner=u1.id, laterality="bilateral")
    _tmpl(db_session, NOPAT_ID, "Tibialis Raise", owner=u1.id, adjudicated=True)
    _tmpl(db_session, UNTAGGED_ID, "Brand New Thing", owner=u1.id)
    _tmpl(db_session, SIDED_ID, "Kneeling Leg Curl (L)", owner=u1.id, laterality="unilateral")
    _tmpl(db_session, OTHER_ID, "Other Persons Custom", owner=u2.id)
    _tag(db_session, DEFAULT_ID, "hip_abduction")
    _tag(db_session, CUSTOM_ID, "hip_adduction")
    _tag(db_session, CUSTOM_ID, "anti_lateral_flexion", role="secondary")
    _tag(db_session, SIDED_ID, "knee_flexion", side="left")

    calls = []

    async def fake_stale(db, user_id):
        calls.append(("stale", user_id))
        return None

    async def fake_force(db, *, only_user_id=None):
        calls.append(("force", only_user_id))
        return {}

    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    u1_id = u1.id
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u1_id)
    monkeypatch.setattr(mcp_server, "refresh_catalogue_if_stale", fake_stale)
    monkeypatch.setattr(mcp_server, "sync_exercise_templates", fake_force)
    return {"db": db_session, "u1_id": u1.id, "u2_id": u2.id, "calls": calls, "mp": monkeypatch}


def _raw(query=None):
    return asyncio.run(mcp_server.get_exercise_catalogue(query))


def _call(query=None):
    """The tool's text without the `as_of` stamp every tool carries."""
    head, _, body = _raw(query).partition(chr(10) * 2)
    assert head.startswith("as_of: ")
    return body


def _line(out, tid):
    return next(l for l in out.splitlines() if l.startswith(tid + " | "))


def test_a_custom_and_a_default_are_visible_and_another_users_custom_is_not(world):
    out = _call()
    assert _line(out, DEFAULT_ID).split(" | ")[2] == "default"
    assert _line(out, CUSTOM_ID).split(" | ")[2] == "custom"
    assert "Other Persons Custom" not in out and OTHER_ID not in out
    # and the other user sees their own custom, not user 1's
    world["mp"].setattr(mcp_server, "_current_user_id", lambda: world["u2_id"])
    other = _call()
    assert OTHER_ID in other and CUSTOM_ID not in other and DEFAULT_ID in other


def test_the_substring_filter_is_case_insensitive_and_narrows(world):
    everything = _call()
    narrowed = _call("cOpEnHaGeN")
    assert CUSTOM_ID in narrowed and DEFAULT_ID not in narrowed and NOPAT_ID not in narrowed
    assert narrowed.count(" | ") < everything.count(" | ")
    assert "contains 'cOpEnHaGeN'" in narrowed.splitlines()[0]
    assert _call("   ") == everything                          # a blank query is no filter


def test_a_wildcard_character_in_the_query_is_literal(world):
    _tmpl(world["db"], "22222222-aaaa-bbbb-cccc-000000000002", "100% Effort_Test", owner=world["u1_id"])
    assert "100% Effort_Test" in _call("100%")
    assert "100% Effort_Test" in _call("effort_t")
    assert DEFAULT_ID not in _call("%")                      # '%' is a character, not 'match everything'
    assert DEFAULT_ID not in _call("_")


def test_tag_state_and_declared_side_match_the_seeded_rows(world):
    out = _call()
    assert _line(out, DEFAULT_ID).endswith("TAGGED hip_abduction(primary)")
    custom = _line(out, CUSTOM_ID)
    assert "laterality bilateral" in custom
    assert custom.endswith("TAGGED anti_lateral_flexion(secondary), hip_adduction(primary)")
    assert _line(out, NOPAT_ID).endswith("NO-PATTERN") and "side" not in _line(out, NOPAT_ID)
    assert _line(out, UNTAGGED_ID).endswith("UNTAGGED") and "laterality unset" in _line(out, UNTAGGED_ID)
    assert _line(out, SIDED_ID).endswith("TAGGED knee_flexion(primary) | side left")
    assert "side" not in _line(out, DEFAULT_ID) and "side" not in _line(out, CUSTOM_ID)


def test_the_state_is_the_one_the_audit_uses(world):
    _, classes = selection.classify_coverage(world["db"], {DEFAULT_ID, CUSTOM_ID, NOPAT_ID, UNTAGGED_ID, SIDED_ID})
    word = {"tagged": "TAGGED", "adjudicated_no_pattern": "NO-PATTERN", "untagged": "UNTAGGED"}
    out = _call()
    for tid, cls in classes.items():
        assert word[cls] in _line(out, tid), (tid, cls)


def test_the_catalogue_is_refreshed_first_by_the_staleness_door(world):
    _call()
    assert world["calls"] == [("stale", world["u1_id"])]        # a hit does not force a sync


def test_a_miss_forces_one_refresh_and_finds_a_template_made_since(world, monkeypatch):
    async def force_adds(db, *, only_user_id=None):
        world["calls"].append(("force", only_user_id))
        _tmpl(db, "33333333-aaaa-bbbb-cccc-000000000003", "Made Minutes Ago", owner=only_user_id)
        return {}
    monkeypatch.setattr(mcp_server, "sync_exercise_templates", force_adds)
    out = _call("minutes ago")
    assert "33333333-aaaa-bbbb-cccc-000000000003" in out and "UNTAGGED" in out
    assert world["calls"] == [("stale", world["u1_id"]), ("force", world["u1_id"])]


def test_a_miss_that_stays_a_miss_forces_exactly_once_and_says_so(world):
    out = _call("no such exercise")
    assert out.startswith("No exercise templates visible to you whose title contains 'no such exercise'")
    assert [c[0] for c in world["calls"]] == ["stale", "force"]


def test_a_failing_forced_refresh_does_not_fail_the_read(world, monkeypatch):
    async def boom(db, *, only_user_id=None):
        raise RuntimeError("hevy down")
    monkeypatch.setattr(mcp_server, "sync_exercise_templates", boom)
    assert _call("no such exercise").startswith("No exercise templates visible")
    assert DEFAULT_ID in _call()                                  # and the local store still reads


def test_the_read_writes_nothing_and_states_no_verdict(world):
    db = world["db"]
    before = (db.query(models.HevyExerciseTemplate).count(), db.query(models.ExerciseRegionTag).count(),
              db.query(models.HevyExerciseTemplate).filter(models.HevyExerciseTemplate.adjudicated_at.isnot(None)).count())
    out = _call() + _call("hip") + _call("zzz")
    db.rollback()
    after = (db.query(models.HevyExerciseTemplate).count(), db.query(models.ExerciseRegionTag).count(),
             db.query(models.HevyExerciseTemplate).filter(models.HevyExerciseTemplate.adjudicated_at.isnot(None)).count())
    assert before == after
    hit = _FORBIDDEN_VERDICT.search(out)
    assert hit is None, hit.group(0)


def test_the_tool_is_registered_with_one_optional_query_parameter():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    schema = tools["get_exercise_catalogue"].inputSchema
    assert set(schema["properties"]) == {"query"} and not schema.get("required")
