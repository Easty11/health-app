"""Routine ids on the rendered routine, and one forced catalogue refresh on a title miss (11 Oct 2026).

Two incidents, one session:
  (a) `Suitcase Deadlift`, a custom made in the Hevy app, was reported unresolved and then resolved
      unchanged on retry once the operator had run the template sync by hand. `refresh_catalogue_if_stale`
      only fires past its 24h window, so a fresh-looking marker hid a stale catalogue.
  (b) Session B's update emitted (L)'s template id for BOTH `... (L)` and `... (R)`: the `## Hevy
      routines` section rendered titles only, so the only ids in view were history ids.

Gates: every rendered exercise carries `[ID: X]` (and a payload with no id renders without crashing);
a title miss forces ONE sync for that user, re-resolves, and writes; a failed or unproductive sync
falls through to the unresolved report without raising; the bound is one sync per CHAT TURN across
every block in both lanes. Sync is faked at the transport (`chat.sync_exercise_templates`); the
resolver, the store and both processors are real. No live Hevy call.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import context_builder
import hevy_templates
import models
from auth import get_current_user
from database import get_db
from encryption import encrypt
from hevy_routine_format import format_routine_compact, format_routine_full
from routers import chat


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Renderer                                                                     #
# --------------------------------------------------------------------------- #

def _set():
    return [{"type": "normal", "weight_kg": 20, "reps": 8}]


def _routine(*exercises):
    return {"id": "rt-1", "title": "Session B", "folder_id": 5,
            "updated_at": "2026-10-10T08:00:00Z", "exercises": list(exercises)}


def test_two_exercises_render_both_id_tags():
    out = "\n".join(format_routine_full(_routine(
        {"exercise_template_id": "AAA111", "title": "Bench Press", "sets": _set()},
        {"exercise_template_id": "BBB222", "title": "Suitcase Deadlift", "sets": _set()},
    ), {}))
    assert "  Bench Press [ID: AAA111]" in out
    assert "  Suitcase Deadlift [ID: BBB222]" in out


def test_the_tag_precedes_the_superset_tag_and_leaves_it_intact():
    out = "\n".join(format_routine_full(_routine(
        {"exercise_template_id": "AAA111", "title": "Row", "superset_id": 0, "sets": _set()},
    ), {}))
    assert "  Row [ID: AAA111]  [superset 0]" in out      # 0 is a real group, still rendered


def test_a_unilateral_pair_renders_distinct_ids():
    """Incident (b): (L) and (R) are separate customs. Both ids must be in view on the routine."""
    out = "\n".join(format_routine_full(_routine(
        {"exercise_template_id": "LEFT01", "title": "Half-Kneeling Press (L)", "sets": _set()},
        {"exercise_template_id": "RIGHT2", "title": "Half-Kneeling Press (R)", "sets": _set()},
    ), {}))
    assert "Half-Kneeling Press (L) [ID: LEFT01]" in out
    assert "Half-Kneeling Press (R) [ID: RIGHT2]" in out


@pytest.mark.parametrize("ex", [
    {"title": "No Id Key", "sets": _set()},
    {"exercise_template_id": None, "title": "Null Id", "sets": _set()},
    {"exercise_template_id": "", "title": "Empty Id", "sets": _set()},
])
def test_a_payload_missing_an_id_renders_without_crashing_or_a_tag(ex):
    out = "\n".join(format_routine_full(_routine(ex), {}))
    assert ex["title"] in out
    assert "[ID:" not in out


def test_the_untitled_fallback_still_never_crashes():
    out = "\n".join(format_routine_full(_routine({"sets": _set()}), {}))
    assert "Unknown exercise" in out and "[ID:" not in out


def test_the_compact_index_stays_titles_only():
    """The index must stay context-small; ids ride on the full-detail lines only."""
    out = "\n".join(format_routine_compact(_routine(
        {"exercise_template_id": "AAA111", "title": "Bench Press", "sets": _set()}), {}))
    assert "Bench Press" in out and "[ID:" not in out


def test_the_hevy_routines_section_carries_the_ids():
    data = {"routines": [_routine(
        {"exercise_template_id": "AAA111", "title": "Bench Press", "sets": _set()})],
        "folders": [{"id": 5, "title": "Block"}], "age_seconds": 0, "stale": False,
        "unavailable": False}
    out = context_builder._section_hevy_routines(data, {"label": "Base"}, {"Base": 5})
    assert "Bench Press [ID: AAA111]" in out


# --------------------------------------------------------------------------- #
# Refresh on miss                                                              #
# --------------------------------------------------------------------------- #

class _FakeHevy:
    def __init__(self, live=None):
        self.live = live
        self.created, self.updated = [], []

    async def get_routine_folders(self, page_size=10):
        return []

    async def create_routine(self, title, exercises, folder_id=None):
        self.created.append((title, exercises))
        return {"routine": {"id": "new"}}

    async def get_routine(self, routine_id):
        return {"routine": self.live}

    async def update_routine(self, routine_id, title, exercises):
        self.updated.append((routine_id, title, exercises))
        return {"routine": {"id": routine_id}}


@pytest.fixture
def user(db_session):
    db_session.add(models.User(id=1, email="refresh@test", hashed_password="x"))
    db_session.commit()
    return 1


def _template(db, tid, title):
    db.add(models.HevyExerciseTemplate(id=tid, title=title, is_custom=True, owner_user_id=1))
    db.commit()


def _install_sync(monkeypatch, db, *, adds=(), raises=None):
    """Fake the sync transport. `adds` are (id, title) customs the refresh surfaces."""
    calls: list = []

    async def fake_sync(_db, *, only_user_id=None):
        calls.append(only_user_id)
        if raises is not None:
            raise raises
        for tid, title in adds:
            _template(db, tid, title)
        return {"users_synced": 1, "users_failed": 0}

    monkeypatch.setattr(chat, "sync_exercise_templates", fake_sync)
    return calls


def _create(*titles, block_title="Session B") -> str:
    import json
    body = {"title": block_title, "exercises": [{"title": t, "sets": _set()} for t in titles]}
    return f"<hevy_create_routine>{json.dumps(body)}</hevy_create_routine>"


def _update(*titles, routine_id="rt-1") -> str:
    import json
    body = {"routine_id": routine_id, "title": "Session B",
            "exercises": [{"title": t, "sets": _set()} for t in titles]}
    return f"<hevy_update_routine>{json.dumps(body)}</hevy_update_routine>"


def test_a_miss_forces_one_sync_then_resolves_and_writes(db_session, user, monkeypatch):
    """Incident (a): the custom exists in Hevy but not in the local store. The marker is FRESH, so
    `refresh_catalogue_if_stale` would skip; the miss must force the sync regardless of it."""
    db_session.add(models.UserIntegration(
        user_id=1, provider="hevy", api_key_encrypted=encrypt("hk_test"),
        templates_synced_at=datetime.now(timezone.utc)))
    db_session.commit()
    assert hevy_templates.resolve_exercise(db_session, "Suitcase Deadlift", 1) is None
    calls = _install_sync(monkeypatch, db_session, adds=[("SUIT01", "Suitcase Deadlift")])
    fake = _FakeHevy()

    _, _, results = _run(chat._process_routine_actions(_create("Suitcase Deadlift"), fake, 1, db_session))

    assert calls == [1]                                         # exactly one sync, for this user
    assert results[0].saved is True and results[0].reason_code == "created"
    (title, exercises), = fake.created
    assert exercises[0]["exercise_template_id"] == "SUIT01"      # re-resolved after the refresh
    assert "title" not in exercises[0]


def test_an_update_miss_forces_one_sync_then_resolves_and_writes(db_session, user, monkeypatch):
    calls = _install_sync(monkeypatch, db_session, adds=[("SUIT01", "Suitcase Deadlift")])
    fake = _FakeHevy(live={"id": "rt-1", "title": "Session B", "exercises": []})

    _, _, results = _run(chat._process_routine_updates(_update("Suitcase Deadlift"), fake, 1, db_session))

    assert calls == [1]
    assert results[0].saved is True and results[0].reason_code == "updated"
    assert fake.updated[0][2][0]["exercise_template_id"] == "SUIT01"


def test_a_hit_never_syncs(db_session, user, monkeypatch):
    _template(db_session, "BENCH1", "Bench Press")
    calls = _install_sync(monkeypatch, db_session)
    fake = _FakeHevy()
    _, _, results = _run(chat._process_routine_actions(_create("Bench Press"), fake, 1, db_session))
    assert calls == [] and results[0].saved is True


def test_ids_already_in_the_block_never_sync(db_session, user, monkeypatch):
    """An update that copies ids from the routine line goes through no title resolution at all."""
    import json
    calls = _install_sync(monkeypatch, db_session)
    fake = _FakeHevy(live={"id": "rt-1", "title": "Session B", "exercises": []})
    body = {"routine_id": "rt-1", "title": "Session B",
            "exercises": [{"exercise_template_id": "LEFT01", "sets": _set()},
                          {"exercise_template_id": "RIGHT2", "sets": _set()}]}
    block = f"<hevy_update_routine>{json.dumps(body)}</hevy_update_routine>"
    _, _, results = _run(chat._process_routine_updates(block, fake, 1, db_session))
    assert calls == [] and results[0].saved is True
    assert [e["exercise_template_id"] for e in fake.updated[0][2]] == ["LEFT01", "RIGHT2"]


def test_a_still_missing_title_after_a_good_sync_is_reported_unresolved(db_session, user, monkeypatch):
    """The sync worked but the title is genuinely absent: today's unresolved report, nothing written,
    and resolution stayed EXACT (a near-title the refresh surfaced is a candidate, never adopted)."""
    calls = _install_sync(monkeypatch, db_session, adds=[("NEAR01", "Suitcase Deadlifts")])
    fake = _FakeHevy()
    _, _, results = _run(chat._process_routine_actions(_create("Suitcase Deadlift"), fake, 1, db_session))
    assert calls == [1]
    assert results[0].saved is False and results[0].reason_code == "unresolved_exercise"
    assert "Suitcase Deadlift" in results[0].reason
    assert fake.created == []


def test_a_failing_sync_falls_through_to_the_unresolved_report_without_raising(db_session, user, monkeypatch):
    calls = _install_sync(monkeypatch, db_session, raises=RuntimeError("hevy down"))
    fake = _FakeHevy()
    _, _, results = _run(chat._process_routine_actions(_create("Suitcase Deadlift"), fake, 1, db_session))
    assert calls == [1]
    assert results[0].saved is False and results[0].reason_code == "unresolved_exercise"
    assert fake.created == []


def test_a_sync_that_reports_failure_without_raising_is_the_same(db_session, user, monkeypatch):
    """`sync_exercise_templates` itself never raises (#77): it returns users_failed instead."""
    calls: list = []

    async def failing(_db, *, only_user_id=None):
        calls.append(only_user_id)
        return {"users_synced": 0, "users_attempted": 1, "users_failed": 1}

    monkeypatch.setattr(chat, "sync_exercise_templates", failing)
    _, _, results = _run(chat._process_routine_updates(
        _update("Suitcase Deadlift"), _FakeHevy(live={"id": "rt-1", "exercises": []}), 1, db_session))
    assert calls == [1]
    assert results[0].saved is False and results[0].reason_code == "unresolved_exercise"


def test_two_unresolved_blocks_in_one_reply_sync_once(db_session, user, monkeypatch):
    calls = _install_sync(monkeypatch, db_session)                # refresh surfaces nothing
    fake = _FakeHevy()
    reply = _create("Ghost One", block_title="A") + _create("Ghost Two", block_title="B")
    _, _, results = _run(chat._process_routine_actions(reply, fake, 1, db_session))
    assert len(results) == 2 and all(r.reason_code == "unresolved_exercise" for r in results)
    assert calls == [1]                                          # one sync for the whole turn


def test_the_bound_spans_both_lanes_when_the_turn_shares_one_refresh(db_session, user, monkeypatch):
    calls = _install_sync(monkeypatch, db_session)
    turn = chat._TurnCatalogueRefresh()
    fake = _FakeHevy(live={"id": "rt-1", "exercises": []})
    _, _, created = _run(chat._process_routine_actions(
        _create("Ghost One"), fake, 1, db_session, refresh=turn))
    _, _, updated = _run(chat._process_routine_updates(
        _update("Ghost Two"), fake, 1, db_session, refresh=turn))
    assert created[0].reason_code == "unresolved_exercise"
    assert updated[0].reason_code == "unresolved_exercise"
    assert calls == [1]


def test_a_later_block_resolves_off_the_refresh_an_earlier_block_paid_for(db_session, user, monkeypatch):
    """Block A's miss forces the sync, which surfaces both customs. Block B then hits on its FIRST
    pass, so the spent allowance costs it nothing."""
    calls = _install_sync(monkeypatch, db_session,
                          adds=[("SUIT01", "Suitcase Deadlift"), ("CARRY1", "Farmer Carry")])
    fake = _FakeHevy()
    reply = _create("Suitcase Deadlift", block_title="A") + _create("Farmer Carry", block_title="B")
    _, _, results = _run(chat._process_routine_actions(reply, fake, 1, db_session))
    assert [r.saved for r in results] == [True, True]
    assert calls == [1]


def test_one_block_with_a_hit_and_a_miss_keeps_the_hit(db_session, user, monkeypatch):
    """The second pass only revisits exercises still missing an id: the hit is not re-resolved."""
    _template(db_session, "BENCH1", "Bench Press")
    calls = _install_sync(monkeypatch, db_session, adds=[("SUIT01", "Suitcase Deadlift")])
    fake = _FakeHevy()
    _, _, results = _run(chat._process_routine_actions(
        _create("Bench Press", "Suitcase Deadlift"), fake, 1, db_session))
    assert results[0].saved is True and calls == [1]
    assert [e["exercise_template_id"] for e in fake.created[0][1]] == ["BENCH1", "SUIT01"]


def test_a_miss_never_mints_a_custom(db_session, user, monkeypatch):
    """No auto-minting on a miss: the exercise-creation primitive is never reached from the
    routine lane."""
    _install_sync(monkeypatch, db_session)

    async def boom(*a, **k):
        raise AssertionError("a routine title miss must not mint a custom")

    monkeypatch.setattr(chat, "create_and_resolve", boom)
    _, _, results = _run(chat._process_routine_actions(
        _create("Ghost One"), _FakeHevy(), 1, db_session))
    assert results[0].reason_code == "unresolved_exercise"


# --------------------------------------------------------------------------- #
# Endpoint wiring: ONE allowance per turn, handed to both lanes                #
# --------------------------------------------------------------------------- #

def test_the_endpoint_hands_both_lanes_the_same_turn_refresh(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = models.User(email="wiring@test", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    app = FastAPI()
    app.include_router(chat.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u

    class _Msgs:
        def create(self, **kw):
            return SimpleNamespace(content=[SimpleNamespace(text="Draft.")])

    fake_client = SimpleNamespace(messages=_Msgs())
    monkeypatch.setattr(chat.anthropic, "Anthropic", lambda api_key=None: fake_client)

    seen: dict = {}

    async def spy_actions(reply, hevy_client, user_id, db, **kw):
        seen["create"] = kw.get("refresh")
        return reply, [], []

    async def spy_updates(reply, hevy_client, user_id, db, **kw):
        seen["update"] = kw.get("refresh")
        return reply, [], []

    monkeypatch.setattr(chat, "_process_routine_actions", spy_actions)
    monkeypatch.setattr(chat, "_process_routine_updates", spy_updates)

    r = TestClient(app).post("/chat", json={"message": "hi", "conversation_history": []})
    assert r.status_code == 200, r.text
    assert isinstance(seen["create"], chat._TurnCatalogueRefresh)
    assert seen["create"] is seen["update"]                     # one object, not one per lane
