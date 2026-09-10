"""schedule_item resolution — retiring a commitment as "no longer true" (#222 extended).

A `schedule_item` could be CREATED and SUPERSEDED (by key, by `supersedes`, or by the
day-overlap path), and it could be EXPIRED by `expire-stale` when a predicted
`expires_at` passed. Neither is the same act as an operator declaring a live
commitment retired with stated grounds and no successor — the season ended, the user
left the team. That third act is what `POST /knowledge/schedule/{id}/resolve` adds,
mirroring the injury resolve route (`test_injury_resolution.py`) and sharing its body
(`_resolve_entry`).

The load-bearing gates here are the CROSS-TYPE 404 (an injury id through the schedule
route retires nothing) and the FRESH-QUERY read of the resolution block (the plain-JSON
column trap), which is what keeps this route honestly parallel to the injury one.
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from load_metrics import _local_day  # AEST "today" — the clock the resolve path uses (Q137)
from routers import knowledge as knowledge_router


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


def _schedule_item(db, user_id, *, key="rugby_seniors", value=None, active=True, **kw):
    """A conforming schedule_item row. ORM construction is deliberately unvalidated
    (the backfill path), but a realistic value keeps the GET /schedule read honest."""
    val = value if value is not None else {
        "activity": "Rugby Training — Seniors",
        "days": ["tuesday"],
        "sessions_per_week": None,
        "hard": True,
        "expected_load": "moderate",
        "time_of_day": "evening",
        "same_day_training": True,
        "duration_weeks": None,
        "season_end": "2026-09-05",
        "supersedes": None,
    }
    row = models.UserKnowledgeEntry(
        user_id=user_id, type="schedule_item", key=key, value=val,
        source="chat", added_at=date.today(), active=active, **kw,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _injury(db, user_id, *, key="hamstring_right", active=True):
    row = models.UserKnowledgeEntry(
        user_id=user_id, type="injury", key=key,
        value={"body_part": "hamstring", "side": "right",
               "signal_type": "mechanical", "restrictions": []},
        source="chat", added_at=date.today(), active=active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


RESOLVE_BODY = {
    "resolved_on": "2026-08-19",
    "basis": "season finished 2026-09-05, no longer training with the club",
    "resolved_by": "user",
}


def _resolve(client, entry_id, **overrides):
    return client.post(f"/knowledge/schedule/{entry_id}/resolve",
                       json={**RESOLVE_BODY, **overrides})


# ── the resolution write ─────────────────────────────────────────────────────

def test_resolve_deactivates_and_stamps_the_resolution(db_session):
    u = _user(db_session, "sched-res-a@example.com")
    row = _schedule_item(db_session, u.id)
    r = _resolve(_client(db_session, u), row.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["value"]["resolution"] == {
        "resolved_on": "2026-08-19",
        "basis": RESOLVE_BODY["basis"],
        "resolved_by": "user",
    }


def test_the_resolution_block_actually_persists(db_session):
    """The plain-`JSON`-column trap, same as the injury route: an in-place mutation is
    invisible to the unit of work. Read the row back from a FRESH query with the
    identity map expired — the response body alone would pass either way."""
    u = _user(db_session, "sched-res-persist@example.com")
    row = _schedule_item(db_session, u.id)
    _resolve(_client(db_session, u), row.id)

    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.active is False
    assert fresh.value["resolution"]["resolved_by"] == "user"
    # The original content survives — resolution ADDS, it does not replace.
    assert fresh.value["activity"] == "Rugby Training — Seniors"
    assert fresh.value["days"] == ["tuesday"]


def test_resolution_leaves_superseded_by_null(db_session):
    """Resolution is not supersession: there is no successor."""
    u = _user(db_session, "sched-res-sup@example.com")
    row = _schedule_item(db_session, u.id)
    assert _resolve(_client(db_session, u), row.id).json()["superseded_by"] is None
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.superseded_by is None


def test_resolved_on_defaults_to_today_when_omitted(db_session):
    u = _user(db_session, "sched-res-today@example.com")
    row = _schedule_item(db_session, u.id)
    r = _client(db_session, u).post(
        f"/knowledge/schedule/{row.id}/resolve",
        json={"basis": "no longer at this club", "resolved_by": "clinician"},
    )
    assert r.status_code == 200
    # `resolved_on` defaults to `_local_day()` (AEST) in the resolve path; anchor
    # the expectation on that same clock, not the runner's UTC `date.today()` (Q137).
    assert r.json()["value"]["resolution"]["resolved_on"] == str(_local_day())


def test_a_resolved_schedule_item_drops_out_of_get_schedule(db_session):
    """`GET /knowledge/schedule` is active-only, so a resolved commitment leaves it —
    the consequence the calendar view sees. The row itself is retained."""
    u = _user(db_session, "sched-res-get@example.com")
    row = _schedule_item(db_session, u.id, key="rugby")
    other = _schedule_item(db_session, u.id, key="swim",
                           value={"activity": "Swim", "days": ["thursday"],
                                  "hard": False, "expected_load": "light",
                                  "time_of_day": "morning", "same_day_training": False,
                                  "duration_weeks": None, "season_end": None})
    c = _client(db_session, u)
    assert {r["id"] for r in c.get("/knowledge/schedule").json()} == {row.id, other.id}

    _resolve(c, row.id)
    remaining = c.get("/knowledge/schedule").json()
    assert {r["id"] for r in remaining} == {other.id}

    # Retained in history, resolution block intact.
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.active is False
    assert fresh.value["resolution"]["basis"] == RESOLVE_BODY["basis"]


# ── refusals ─────────────────────────────────────────────────────────────────

def test_resolving_twice_is_409_and_writes_nothing(db_session):
    u = _user(db_session, "sched-res-409@example.com")
    row = _schedule_item(db_session, u.id)
    c = _client(db_session, u)
    assert _resolve(c, row.id).status_code == 200

    second = _resolve(c, row.id, basis="a different basis that must not land")
    assert second.status_code == 409
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.value["resolution"]["basis"] == RESOLVE_BODY["basis"]


def test_an_injury_id_through_the_schedule_route_is_404_and_writes_nothing(db_session):
    """THE cross-type gate. The route is scoped to `type='schedule_item'`, so an
    injury id is a 404 that retires nothing — the same 404-leak defence the injury
    route carries in reverse. This is why the routes stay per-type."""
    u = _user(db_session, "sched-res-cross@example.com")
    inj = _injury(db_session, u.id)

    r = _resolve(_client(db_session, u), inj.id)
    assert r.status_code == 404
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=inj.id).one()
    assert fresh.active is True
    assert "resolution" not in (fresh.value or {})


def test_resolving_another_users_entry_is_404_and_writes_nothing(db_session):
    mine = _user(db_session, "sched-res-mine@example.com")
    theirs = _user(db_session, "sched-res-theirs@example.com")
    victim = _schedule_item(db_session, theirs.id, key="their_rugby")

    r = _resolve(_client(db_session, mine), victim.id)
    assert r.status_code == 404
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=victim.id).one()
    assert fresh.active is True
    assert "resolution" not in (fresh.value or {})


def test_a_missing_entry_is_404(db_session):
    u = _user(db_session, "sched-res-missing@example.com")
    assert _resolve(_client(db_session, u), 999999).status_code == 404


@pytest.mark.parametrize("bad", ["physio", "", "USER", "system", "app"])
def test_an_unrecognised_resolved_by_is_422(db_session, bad):
    u = _user(db_session, "sched-res-by@example.com")
    row = _schedule_item(db_session, u.id)
    r = _resolve(_client(db_session, u), row.id, resolved_by=bad)
    assert r.status_code == 422
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.active is True


@pytest.mark.parametrize("good", ["user", "clinician"])
def test_the_two_recognised_resolved_by_values_are_accepted(db_session, good):
    """Negative control for the refusal battery — a validator that refused everything
    would pass every 422 assertion and report green."""
    u = _user(db_session, "sched-res-ok@example.com")
    row = _schedule_item(db_session, u.id)
    assert _resolve(_client(db_session, u), row.id, resolved_by=good).status_code == 200


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_basis_is_422(db_session, blank):
    """A resolution with no stated grounds is what later reads as an accident."""
    u = _user(db_session, "sched-res-basis@example.com")
    row = _schedule_item(db_session, u.id)
    assert _resolve(_client(db_session, u), row.id, basis=blank).status_code == 422
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.active is True
