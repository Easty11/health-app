"""Injury clearance sweep — `GET /knowledge/injuries/{id}/sweep` (surfacing-only).

The ledger is the only authority on injury state; every other store holding the injury is a
copy. Resolving the ledger row retires the authority, but chat context reads the free-text
`user_knowledge` store UNFILTERED every turn, so a copy there keeps re-imposing the constraint.
The load-bearing gate is the NEGATIVE CONTROL: a planted `user_knowledge` line the ledger reads
cannot see (resolved → absent from the active list) is found by the sweep.

The guard half matters as much: the sweep never writes. Every store is byte-identical after it.
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import hevy_routine_cache
import injury_sweep
import models
from auth import get_current_user
from database import get_db
from routers import knowledge as knowledge_router

HAMSTRING = {
    "body_part": "hamstring",
    "side": "right",
    "signal_type": "mechanical",
    "restrictions": ["striding", "sprinting", "static end-range hamstring stretching"],
    "detail": "Right proximal semimembranosus rupture.",
}


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _entry(db, user_id, *, type_="injury", key="injury_hamstring_right", value=None,
           notes=None, source="chat", active=True):
    row = models.UserKnowledgeEntry(
        user_id=user_id, type=type_, key=key, value=value if value is not None else HAMSTRING,
        notes=notes, source=source, active=active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _uk(db, user_id, category, content):
    row = models.UserKnowledge(user_id=user_id, category=category, content=content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _hevy(db, user_id, routines):
    """Connect Hevy and warm the routine cache, so the sweep reads it without a network call."""
    from encryption import encrypt
    db.add(models.UserIntegration(user_id=user_id, provider="hevy",
                                  api_key_encrypted=encrypt("test-key")))
    db.commit()
    hevy_routine_cache._CACHE[user_id] = (time.monotonic(), {"routines": routines, "folders": []})


@pytest.fixture(autouse=True)
def _clear_cache():
    hevy_routine_cache._CACHE.clear()
    yield
    hevy_routine_cache._CACHE.clear()


INJURY_HISTORY = "\n".join([
    "Right hamstring (semimembranosus) tear — no sprinting",   # 0 — same side
    "Left hamstring tight after footy",                         # 1 — opposite side
    "Pes anserine sore on the left",                            # 2 — no match
    "Hamstring feels fine on long runs",                        # 3 — no side
])


@pytest.fixture
def world(db_session):
    """A RESOLVED right-hamstring injury with copies in every app-reachable store."""
    u = _user(db_session, "sweep@example.com")
    inj = _entry(db_session, u.id)
    c = _client(db_session, u)
    r = c.post(f"/knowledge/injuries/{inj.id}/resolve", json={
        "resolved_on": "2026-09-27", "basis": "cleared", "resolved_by": "user"})
    assert r.status_code == 200, r.text

    history = _uk(db_session, u.id, "Injury History", INJURY_HISTORY)
    background = _uk(db_session, u.id, "Training Background", "Strides on Tuesdays\nLikes rowing")
    sched = _entry(db_session, u.id, type_="schedule_item", key="football",
                   value={"activity": "football", "days": ["saturday"], "hard": True},
                   notes="no sprinting until hamstring clears")
    pref = _entry(db_session, u.id, type_="preference", key="warmup",
                  value={"text": "Nordic curls for the hamstring first"}, source="api")
    _hevy(db_session, u.id, [{
        "id": "rt-1", "title": "Lower A", "notes": "Skip strides this block",
        "exercises": [{"title": "Nordic Curl", "notes": "Right hamstring: stop at 7 RPE"},
                      {"title": "Squat", "notes": "Brace"}],
    }])
    return {"user": u, "client": c, "inj": inj, "history": history,
            "background": background, "sched": sched, "pref": pref}


def _sweep(world, **params):
    r = world["client"].get(f"/knowledge/injuries/{world['inj'].id}/sweep", params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ── G1: hits from each reachable store ──────────────────────────────────────

def test_resolved_injury_returns_hits_from_every_reachable_store(world):
    body = _sweep(world)
    assert body["active"] is False
    assert {s["store"]: s["status"] for s in body["stores"]} == {
        "user_knowledge": "searched", "user_knowledge_entries": "searched",
        "hevy_routines": "searched"}
    by_store = {}
    for h in body["hits"]:
        by_store.setdefault(h["store"], []).append(h)
    assert set(by_store) == {"user_knowledge", "user_knowledge_entries", "hevy_routines"}
    assert all(s["hits"] == len(by_store[s["store"]]) for s in body["stores"])


def test_free_text_hits_are_per_line_with_edit_never_delete(world):
    hits = [h for h in _sweep(world)["hits"] if h["row_id"] == world["history"].id
            and h["store"] == "user_knowledge"]
    assert sorted(h["line_index"] for h in hits) == [0, 1, 3]     # line 2 (pes anserine) not hit
    assert {h["action"] for h in hits} == {"edit"}
    assert {h["action_route"] for h in hits} == {f"PUT /knowledge/{world['history'].id}"}
    assert {h["reaches_context"] for h in hits} == {"yes"}
    # Restriction words are stemmed: "striding" finds "Strides".
    bg = [h for h in _sweep(world)["hits"] if h["row_id"] == world["background"].id
          and h["store"] == "user_knowledge"]
    assert [h["line_index"] for h in bg] == [0]


def test_opposite_side_is_flagged_not_dropped_and_no_side_is_unflagged(world):
    hits = {h["line_index"]: h for h in _sweep(world)["hits"]
            if h["store"] == "user_knowledge" and h["row_id"] == world["history"].id}
    assert hits[0]["opposite_side"] is False and hits[0]["sides_mentioned"] == ["right"]
    assert hits[1]["opposite_side"] is True and hits[1]["sides_mentioned"] == ["left"]
    assert hits[3]["opposite_side"] is False and hits[3]["sides_mentioned"] == []


def test_structured_entries_carry_their_existing_action(world):
    hits = [h for h in _sweep(world)["hits"] if h["store"] == "user_knowledge_entries"]
    sched = [h for h in hits if h["row_id"] == world["sched"].id]
    pref = [h for h in hits if h["row_id"] == world["pref"].id]
    assert sched and {h["action"] for h in sched} == {"resolve"}
    assert sched[0]["action_route"] == f"POST /knowledge/schedule/{world['sched'].id}/resolve"
    assert sched[0]["reaches_context"] == "yes"          # notes on a source=chat schedule_item
    assert pref and pref[0]["action"] == "none" and pref[0]["action_route"] is None
    assert pref[0]["reaches_context"] == "unverified"
    # The ledger itself is the authority, never a copy.
    assert not any(h["row_id"] == world["inj"].id for h in hits)


def test_hevy_routine_and_exercise_notes_are_searched_via_the_cache(world):
    hits = [h for h in _sweep(world)["hits"] if h["store"] == "hevy_routines"]
    assert {h["location"] for h in hits} == {
        "routine 'Lower A' · notes", "routine 'Lower A' · Nordic Curl · notes"}
    assert {h["action"] for h in hits} == {"none"}
    assert {h["reaches_context"] for h in hits} == {"conditional"}


def test_operator_terms_are_added_case_insensitively(world):
    assert not any("rowing" in h["snippet"] for h in _sweep(world)["hits"])
    body = _sweep(world, terms="ROWING, ")
    assert "rowing" in body["terms"]
    assert any(h["snippet"] == "Likes rowing" for h in body["hits"])


def test_manual_checklist_is_always_present_and_last(world, db_session):
    body = _sweep(world)
    assert list(body)[-1] == "manual_checklist"
    stores = [c["store"] for c in body["manual_checklist"]]
    for required in ("project_knowledge_files", "claude_memory", "browser_chat_history"):
        assert required in stores
    # Also with zero hits.
    u = _user(db_session, "sweep-empty@example.com")
    inj = _entry(db_session, u.id)
    r = _client(db_session, u).get(f"/knowledge/injuries/{inj.id}/sweep").json()
    assert r["hits"] == [] and [c["store"] for c in r["manual_checklist"]] == stores


def test_hevy_not_connected_is_reported_not_an_error(db_session):
    u = _user(db_session, "sweep-nohevy@example.com")
    inj = _entry(db_session, u.id)
    body = _client(db_session, u).get(f"/knowledge/injuries/{inj.id}/sweep").json()
    assert {s["store"]: s["status"] for s in body["stores"]}["hevy_routines"] == "not_connected"


# ── G1: 404 scope ────────────────────────────────────────────────────────────

def test_non_injury_id_is_404(world):
    r = world["client"].get(f"/knowledge/injuries/{world['sched'].id}/sweep")
    assert r.status_code == 404


def test_other_users_injury_and_unknown_id_are_404(world, db_session):
    other = _user(db_session, "sweep-other@example.com")
    theirs = _entry(db_session, other.id)
    assert world["client"].get(f"/knowledge/injuries/{theirs.id}/sweep").status_code == 404
    assert world["client"].get("/knowledge/injuries/999999/sweep").status_code == 404


# ── G1: negative control — the sweep finds what the ledger alone misses ─────

def test_sweep_finds_a_planted_copy_the_ledger_reads_cannot_see(world):
    c = world["client"]
    planted = "PLANTED: hamstring — no sprinting, ever"
    row = _uk(c.app.dependency_overrides[get_db](), world["user"].id, "Constraints", planted)

    # The ledger's active read no longer holds the injury at all …
    assert c.get("/knowledge/injuries").json() == []
    # … and no ledger row, resolved or not, carries the planted text.
    ledger = c.get("/knowledge/injuries", params={"include_resolved": "true"}).json()
    assert planted not in repr(ledger)
    # The sweep finds it.
    hits = [h for h in _sweep(world)["hits"] if h["store"] == "user_knowledge"
            and h["row_id"] == row.id]
    assert [h["snippet"] for h in hits] == [planted]


# ── guard: read-only, and the resolve contract is untouched ─────────────────

def _snapshot(db, user_id):
    db.expire_all()
    uk = [(r.id, r.category, r.content) for r in
          db.query(models.UserKnowledge).filter_by(user_id=user_id).order_by(models.UserKnowledge.id)]
    ents = [(r.id, r.type, r.key, r.value, r.notes, r.active, r.superseded_by) for r in
            db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id)
            .order_by(models.UserKnowledgeEntry.id)]
    return uk, ents


def test_sweep_never_writes(world, db_session):
    before = _snapshot(db_session, world["user"].id)
    _sweep(world)
    _sweep(world, terms="footy")
    assert _snapshot(db_session, world["user"].id) == before


def test_resolve_route_contract_is_untouched():
    routes = {(r.path, tuple(sorted(r.methods))): r for r in knowledge_router.router.routes}
    resolve = routes[("/knowledge/injuries/{entry_id}/resolve", ("POST",))]
    assert resolve.response_model is knowledge_router.KnowledgeEntryOut
    sweep = routes[("/knowledge/injuries/{entry_id}/sweep", ("GET",))]
    assert sweep.response_model is knowledge_router.InjurySweepOut


# ── unit: term derivation ────────────────────────────────────────────────────

def test_terms_derive_from_body_part_key_and_restriction_words():
    e = models.UserKnowledgeEntry(type="injury", key="injury_hamstring_right", value=HAMSTRING)
    terms = injury_sweep.derive_terms(e, ["Semimembranosus"])
    assert terms == ["hamstring", "strid", "sprint", "stretch", "semimembranosus"]
    # Generic restriction words and side words never become terms on their own.
    for t in ("static", "range", "right", "injury", "end"):
        assert t not in terms
