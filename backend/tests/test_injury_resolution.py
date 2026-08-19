"""Injury resolution — the write end of a loop that could only be opened (#222/#223).

An injury entry could be CREATED and SUPERSEDED-BY-KEY, but not RESOLVED. The
consequence was live, not hypothetical: `gather_active_injuries` kept returning
healed injuries and `is_contraindicated` kept suppressing regions the user had
recovered in, with no surface listing them so the operator could see what to retire.

The load-bearing gate is `test_a_suppressed_region_becomes_selectable_after_resolve`:
a SPECIFIC region asserted contraindicated before and selectable after, with no other
input changed. Asserting only that the injury list shrank would pass even if the
suppression never lifted.

The GUARD gates are the other half and matter as much: nothing auto-resolves. A
passing `resolve_by` date, a soreness series at the exit condition, and a live
`review` flag must each leave `active` untouched — an injury constraint that lifts
itself with no operator in the loop is a safety failure (#72 stays surfacing-only).
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import injury_trajectory
import models
from auth import get_current_user
from database import get_db
from engine import selection, taxonomy
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


def _injury(db, user_id, *, key="hamstring_right", body_part="hamstring",
            side="right", value=None, active=True, **kw):
    """An injury row shaped the way `gather_active_injuries` reads it."""
    val = value if value is not None else {
        "body_part": body_part,
        "side": side,
        "signal_type": "mechanical",
        "restrictions": ["no end-range stretching"],
    }
    row = models.UserKnowledgeEntry(
        user_id=user_id, type="injury", key=key, value=val,
        source="chat", added_at=date.today(), active=active, **kw,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# The acute-hamstring block set, straight from the engine. Pinned as a
# precondition rather than hardcoded, so a taxonomy edit fails loudly here
# instead of quietly making the load-bearing gate vacuous.
SUPPRESSED_BY_HAMSTRING = "single_leg_hop"


# ── step 1: the read surface ─────────────────────────────────────────────────

def test_injuries_endpoint_returns_only_active_injuries(db_session):
    u = _user(db_session, "inj-a@example.com")
    _injury(db_session, u.id, key="hamstring_right")
    _injury(db_session, u.id, key="ankle_left", body_part="ankle", side="left")
    _injury(db_session, u.id, key="old_calf", body_part="calf", active=False)
    # A non-injury entry must not leak through the injury surface.
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="schedule_item", key="weekly_split",
        value={"split": "upper/lower"}, source="chat", added_at=date.today(), active=True,
    ))
    db_session.commit()

    body = _client(db_session, u).get("/knowledge/injuries").json()
    assert {r["key"] for r in body} == {"hamstring_right", "ankle_left"}
    assert {r["type"] for r in body} == {"injury"}


def test_include_resolved_returns_inactive_rows_too(db_session):
    u = _user(db_session, "inj-b@example.com")
    _injury(db_session, u.id, key="live_one")
    _injury(db_session, u.id, key="dead_one", active=False)

    c = _client(db_session, u)
    assert {r["key"] for r in c.get("/knowledge/injuries").json()} == {"live_one"}
    assert {r["key"] for r in c.get(
        "/knowledge/injuries", params={"include_resolved": "true"}
    ).json()} == {"live_one", "dead_one"}


def test_injuries_endpoint_never_returns_another_users_rows(db_session):
    """Cross-user isolation, asserted with two fixture users on BOTH arms — the
    default and `include_resolved=true`, since the history arm widens the filter
    and is where a dropped `user_id` would show up."""
    mine = _user(db_session, "mine@example.com")
    theirs = _user(db_session, "theirs@example.com")
    _injury(db_session, mine.id, key="my_hamstring")
    _injury(db_session, theirs.id, key="their_hamstring")
    _injury(db_session, theirs.id, key="their_old_ankle", active=False)

    c = _client(db_session, mine)
    for params in ({}, {"include_resolved": "true"}):
        keys = {r["key"] for r in c.get("/knowledge/injuries", params=params).json()}
        assert keys == {"my_hamstring"}, f"leak with params={params}: {keys}"


def test_the_trajectory_block_is_returned_unmodified(db_session):
    """#72's trajectory rides inside `value`; this surface reads, never reinterprets."""
    u = _user(db_session, "inj-traj@example.com")
    traj = {
        "shape": "resolving_by",
        "declared_on": "2026-07-01",
        "resolve_by": "2026-09-01",
        "review_when": {"metric": "soreness", "op": "<=", "threshold": 1,
                        "sustained_days": 3},
    }
    _injury(db_session, u.id, value={
        "body_part": "hamstring", "side": "right",
        "signal_type": "mechanical", "restrictions": [], "trajectory": traj,
    })
    row = _client(db_session, u).get("/knowledge/injuries").json()[0]
    assert row["value"]["trajectory"] == traj


def test_the_read_surface_distinguishes_superseded_from_resolved(db_session):
    """Both terminal states read `active=False`; only supersession names a successor.
    Without `superseded_by` on the schema the history arm could not tell them apart."""
    u = _user(db_session, "inj-sup@example.com")
    first = _injury(db_session, u.id, key="hamstring_right")
    second = _injury(db_session, u.id, key="hamstring_right_v2")
    first.superseded_by = second.id
    first.active = False
    db_session.commit()

    rows = {r["id"]: r for r in _client(db_session, u).get(
        "/knowledge/injuries", params={"include_resolved": "true"}).json()}
    assert rows[first.id]["superseded_by"] == second.id
    assert rows[second.id]["superseded_by"] is None


def test_no_injuries_is_an_empty_list_not_an_error(db_session):
    u = _user(db_session, "inj-empty@example.com")
    r = _client(db_session, u).get("/knowledge/injuries")
    assert r.status_code == 200
    assert r.json() == []


# ── step 2: the resolution write ─────────────────────────────────────────────

RESOLVE_BODY = {
    "resolved_on": "2026-08-19",
    "basis": "asymptomatic 3 weeks, full-speed running with no reaction",
    "resolved_by": "user",
}


def _resolve(client, entry_id, **overrides):
    return client.post(f"/knowledge/injuries/{entry_id}/resolve",
                       json={**RESOLVE_BODY, **overrides})


def test_resolve_deactivates_and_stamps_the_resolution(db_session):
    u = _user(db_session, "res-a@example.com")
    row = _injury(db_session, u.id)
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
    """The `JSON`-column trap: the column is not a `MutableDict`, so an in-place
    `value["resolution"] = ...` is invisible to the unit of work and silently
    dropped at commit. Read the row back from a FRESH query with the identity map
    expired — asserting on the response body alone would pass either way."""
    u = _user(db_session, "res-persist@example.com")
    row = _injury(db_session, u.id)
    _resolve(_client(db_session, u), row.id)

    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.active is False
    assert fresh.value["resolution"]["resolved_by"] == "user"
    # The original content survives — resolution ADDS, it does not replace.
    assert fresh.value["body_part"] == "hamstring"
    assert fresh.value["restrictions"] == ["no end-range stretching"]


def test_resolution_leaves_superseded_by_null(db_session):
    """Resolution is not supersession: there is no successor. The two terminal
    states must stay distinguishable in the ledger."""
    u = _user(db_session, "res-sup@example.com")
    row = _injury(db_session, u.id)
    assert _resolve(_client(db_session, u), row.id).json()["superseded_by"] is None
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.superseded_by is None


def test_superseded_and_resolved_are_distinguishable(db_session):
    """Both read `active=False`; only one names a successor, and only one carries a
    `resolution` block. Asserted side by side so a later collapse of the two states
    fails here rather than looking like a simplification."""
    u = _user(db_session, "res-vs-sup@example.com")
    superseded = _injury(db_session, u.id, key="shared_key")
    resolved = _injury(db_session, u.id, key="other_key")
    successor = _injury(db_session, u.id, key="shared_key_v2")
    superseded.superseded_by = successor.id
    superseded.active = False
    db_session.commit()
    _resolve(_client(db_session, u), resolved.id)

    db_session.expire_all()
    sup = db_session.query(models.UserKnowledgeEntry).filter_by(id=superseded.id).one()
    res = db_session.query(models.UserKnowledgeEntry).filter_by(id=resolved.id).one()
    assert (sup.active, res.active) == (False, False)
    assert sup.superseded_by == successor.id
    assert res.superseded_by is None
    assert "resolution" not in (sup.value or {})
    assert "resolution" in res.value


def test_the_row_is_retained_and_visible_in_history(db_session):
    """Never delete. The resolved row still exists and carries its resolution."""
    u = _user(db_session, "res-hist@example.com")
    row = _injury(db_session, u.id)
    c = _client(db_session, u)
    _resolve(c, row.id)

    assert c.get("/knowledge/injuries").json() == []
    history = c.get("/knowledge/injuries", params={"include_resolved": "true"}).json()
    assert [h["id"] for h in history] == [row.id]
    assert history[0]["value"]["resolution"]["basis"] == RESOLVE_BODY["basis"]


def test_resolved_on_defaults_to_today_when_omitted(db_session):
    u = _user(db_session, "res-today@example.com")
    row = _injury(db_session, u.id)
    r = _client(db_session, u).post(
        f"/knowledge/injuries/{row.id}/resolve",
        json={"basis": "healed", "resolved_by": "clinician"},
    )
    assert r.status_code == 200
    assert r.json()["value"]["resolution"]["resolved_on"] == str(date.today())


# ── refusals ─────────────────────────────────────────────────────────────────

def test_resolving_twice_is_409_and_writes_nothing(db_session):
    u = _user(db_session, "res-409@example.com")
    row = _injury(db_session, u.id)
    c = _client(db_session, u)
    assert _resolve(c, row.id).status_code == 200

    second = _resolve(c, row.id, basis="a different basis that must not land")
    assert second.status_code == 409
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.value["resolution"]["basis"] == RESOLVE_BODY["basis"]


def test_resolving_another_users_entry_is_404_and_writes_nothing(db_session):
    mine = _user(db_session, "res-mine@example.com")
    theirs = _user(db_session, "res-theirs@example.com")
    victim = _injury(db_session, theirs.id, key="their_hamstring")

    r = _resolve(_client(db_session, mine), victim.id)
    assert r.status_code == 404
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=victim.id).one()
    assert fresh.active is True
    assert "resolution" not in (fresh.value or {})


def test_a_non_injury_entry_cannot_be_resolved_through_this_route(db_session):
    """The route is scoped to `type='injury'`, so it cannot retire a schedule_item."""
    u = _user(db_session, "res-type@example.com")
    item = models.UserKnowledgeEntry(
        user_id=u.id, type="schedule_item", key="weekly_split",
        value={"split": "upper/lower"}, source="chat", added_at=date.today(), active=True,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    assert _resolve(_client(db_session, u), item.id).status_code == 404
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=item.id).one()
    assert fresh.active is True


def test_a_missing_entry_is_404(db_session):
    u = _user(db_session, "res-missing@example.com")
    assert _resolve(_client(db_session, u), 999999).status_code == 404


@pytest.mark.parametrize("bad", ["physio", "", "USER", "system", "app"])
def test_an_unrecognised_resolved_by_is_422(db_session, bad):
    u = _user(db_session, "res-by@example.com")
    row = _injury(db_session, u.id)
    r = _resolve(_client(db_session, u), row.id, resolved_by=bad)
    assert r.status_code == 422
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.active is True


@pytest.mark.parametrize("good", ["user", "clinician"])
def test_the_two_recognised_resolved_by_values_are_accepted(db_session, good):
    """Negative control for the refusal battery above — a validator that refused
    everything would pass every 422 assertion and report green."""
    u = _user(db_session, "res-ok@example.com")
    row = _injury(db_session, u.id)
    assert _resolve(_client(db_session, u), row.id, resolved_by=good).status_code == 200


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_basis_is_422(db_session, blank):
    """A resolution with no stated grounds is what later reads as an accident."""
    u = _user(db_session, "res-basis@example.com")
    row = _injury(db_session, u.id)
    assert _resolve(_client(db_session, u), row.id, basis=blank).status_code == 422
    db_session.expire_all()
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.active is True


# ── the load-bearing gate: suppression actually lifts ────────────────────────

def _blocked(db, user_id, region_key, side):
    """The real path: ledger -> gather_active_injuries -> is_contraindicated."""
    region = taxonomy.by_key(region_key)
    assert region is not None, f"{region_key} does not resolve in the taxonomy"
    blocked, _reason = selection.is_contraindicated(
        region, side,
        profile_hard_stops=None,
        active_injuries=selection.gather_active_injuries(db, user_id),
    )
    return blocked


def test_a_suppressed_region_becomes_selectable_after_resolve(db_session):
    """THE gate. A SPECIFIC region asserted contraindicated before and selectable
    after, with no other input changed — no profile, no capability state, no
    taxonomy edit, only the resolve call in between.

    Asserting merely that the injury list shrank would pass even if the suppression
    never lifted, which is the failure this exists to catch.
    """
    u = _user(db_session, "gate@example.com")
    row = _injury(db_session, u.id, body_part="hamstring", side="right")

    # Precondition — the block is real, and it is THIS injury doing it.
    assert _blocked(db_session, u.id, SUPPRESSED_BY_HAMSTRING, taxonomy.SIDE_RIGHT) is True
    assert len(selection.gather_active_injuries(db_session, u.id)) == 1

    r = _resolve(_client(db_session, u), row.id)
    assert r.status_code == 200

    assert _blocked(db_session, u.id, SUPPRESSED_BY_HAMSTRING, taxonomy.SIDE_RIGHT) is False
    assert selection.gather_active_injuries(db_session, u.id) == []


def test_the_resolved_injury_leaves_the_probe_queue_filter(db_session):
    """The same lift, one layer out: the region re-enters the computed probe queue.
    `compute_probe_queue` is what `/engine/next` actually consumes, so this is the
    consequence the user sees."""
    u = _user(db_session, "gate-queue@example.com")
    row = _injury(db_session, u.id, body_part="hamstring", side="right")

    def queued():
        return {
            (c["region_key"], c["side"])
            for c in selection.compute_probe_queue(
                db_session, u.id, profile=None, loaded_region_keys=set())
        }

    target = (SUPPRESSED_BY_HAMSTRING, taxonomy.SIDE_RIGHT)
    before = queued()
    assert target not in before

    _resolve(_client(db_session, u), row.id)
    after = queued()
    assert target in after
    # The lift is SCOPED: resolving one injury adds back its blocked regions and
    # changes nothing else.
    assert before < after


def test_resolving_one_injury_does_not_lift_another(db_session):
    """Two live injuries, one resolved. The survivor's block must hold — a resolve
    that cleared the whole ledger would pass the single-injury gate above."""
    u = _user(db_session, "gate-two@example.com")
    hamstring = _injury(db_session, u.id, key="hamstring_right",
                        body_part="hamstring", side="right")
    _injury(db_session, u.id, key="shoulder_left", body_part="shoulder", side="left")

    assert _blocked(db_session, u.id, "vertical_push", taxonomy.SIDE_BILATERAL) is True
    _resolve(_client(db_session, u), hamstring.id)

    assert _blocked(db_session, u.id, SUPPRESSED_BY_HAMSTRING, taxonomy.SIDE_RIGHT) is False
    assert _blocked(db_session, u.id, "vertical_push", taxonomy.SIDE_BILATERAL) is True
    assert [i["body_part"] for i in selection.gather_active_injuries(db_session, u.id)] == ["shoulder"]


# ── GUARD: nothing auto-resolves ─────────────────────────────────────────────

def _record(db, user_id, on, key, soreness):
    db.add(models.DailyRecord(user_id=user_id, date=on, soreness={key: soreness}))
    db.commit()


TRAJECTORY = {
    "shape": "resolving_by",
    "declared_on": "2026-07-01",
    "resolve_by": "2026-08-01",
    "review_when": {"metric": "soreness", "op": "<=", "threshold": 1,
                    "sustained_days": 3},
}


def _injury_with_trajectory(db, user_id):
    return _injury(db, user_id, value={
        "body_part": "hamstring", "side": "right",
        "signal_type": "mechanical", "restrictions": ["no end-range stretching"],
        "trajectory": TRAJECTORY,
    })


def test_a_passed_resolve_by_date_does_not_deactivate_anything(db_session):
    """GUARD. `resolve_by` is 2026-08-01 and today is well past it. The divergence
    flag fires — and the entry stays ACTIVE and the region stays suppressed. A
    constraint that lifted itself on a date would invert #72 with no operator in
    the loop."""
    u = _user(db_session, "guard-date@example.com")
    row = _injury_with_trajectory(db_session, u.id)
    _record(db_session, u.id, date(2026, 7, 20), "hamstring_right", 3)
    _record(db_session, u.id, date(2026, 8, 10), "hamstring_right", 3)

    flags = injury_trajectory.evaluate(u.id, db_session, today=date(2026, 8, 19))
    assert flags["divergences"] == [{
        "key": "hamstring_right",
        "label": "hamstring right",
        "message": ("expected resolved by 2026-08-01, still symptomatic "
                    "(soreness 3) — revisit"),
    }], "precondition: the divergence flag fires, with its exact message pinned"

    db_session.expire_all()
    assert db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one().active is True
    assert _blocked(db_session, u.id, SUPPRESSED_BY_HAMSTRING, taxonomy.SIDE_RIGHT) is True


def test_a_live_review_flag_does_not_deactivate_anything(db_session):
    """GUARD. Soreness sits at the declared exit condition for the full sustained
    window, so `evaluate()` raises a review flag — the strongest possible "this looks
    resolved" signal the system produces. It still must not resolve anything."""
    u = _user(db_session, "guard-review@example.com")
    row = _injury_with_trajectory(db_session, u.id)
    for d in (date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12)):
        _record(db_session, u.id, d, "hamstring_right", 1)

    flags = injury_trajectory.evaluate(u.id, db_session, today=date(2026, 8, 12))
    assert len(flags["reviews"]) == 1, "precondition: the review flag fires"
    assert "review the restriction" in flags["reviews"][0]["message"]

    db_session.expire_all()
    assert db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one().active is True
    assert _blocked(db_session, u.id, SUPPRESSED_BY_HAMSTRING, taxonomy.SIDE_RIGHT) is True
    assert len(selection.gather_active_injuries(db_session, u.id)) == 1


def test_expire_stale_still_needs_a_predicted_date_and_is_not_resolution(db_session):
    """GUARD. `expire_stale` is the pre-existing date-driven path and is untouched:
    it flips only rows whose `expires_at` was predicted at creation, and it writes no
    `resolution` block — so an expired row is still distinguishable from a resolved
    one. An injury with no `expires_at` is left alone."""
    u = _user(db_session, "guard-expire@example.com")
    dated = _injury(db_session, u.id, key="dated", expires_at=date(2026, 1, 1))
    undated = _injury(db_session, u.id, key="undated")

    assert knowledge_router.expire_stale_entries(u.id, db_session) == 1
    db_session.expire_all()
    d = db_session.query(models.UserKnowledgeEntry).filter_by(id=dated.id).one()
    ud = db_session.query(models.UserKnowledgeEntry).filter_by(id=undated.id).one()
    assert d.active is False
    assert "resolution" not in (d.value or {})
    assert ud.active is True


def test_trajectory_flags_are_unchanged_for_an_unresolved_injury(db_session):
    """Trajectory semantics must not move. Both flags pinned EXACTLY for a fixture
    whose injury is untouched by this change — a drift in `evaluate()` fails here
    rather than being absorbed as noise."""
    u = _user(db_session, "guard-semantics@example.com")
    _injury_with_trajectory(db_session, u.id)
    _record(db_session, u.id, date(2026, 8, 10), "hamstring_right", 1)
    _record(db_session, u.id, date(2026, 8, 11), "hamstring_right", 1)
    _record(db_session, u.id, date(2026, 8, 12), "hamstring_right", 1)

    flags = injury_trajectory.evaluate(u.id, db_session, today=date(2026, 8, 19))
    assert flags == {
        # No divergence: `resolving_by` only diverges while the last reading is
        # still >1, and this series sits at 1 — the injury DID resolve by its
        # declared date, which is exactly why the review arm is the one that fires.
        # (Pinned after the first draft asserted a divergence here and the source
        # refused it — the expectation was wrong, not the code.)
        "divergences": [],
        "reviews": [{
            "key": "hamstring_right",
            "label": "hamstring right",
            "message": ("review trigger: soreness <= 1 sustained 3d — "
                        "looks resolved, review the restriction"),
        }],
    }


def test_a_resolved_injury_drops_out_of_trajectory_evaluation(db_session):
    """`evaluate()` reads active rows, so a resolved injury stops being flagged —
    consequence of the resolve, not a change to trajectory semantics."""
    u = _user(db_session, "guard-post@example.com")
    row = _injury_with_trajectory(db_session, u.id)
    _record(db_session, u.id, date(2026, 8, 10), "hamstring_right", 3)
    _record(db_session, u.id, date(2026, 8, 18), "hamstring_right", 3)

    before = injury_trajectory.evaluate(u.id, db_session, today=date(2026, 8, 19))
    assert before["divergences"], "precondition: it was being flagged"

    _resolve(_client(db_session, u), row.id)
    after = injury_trajectory.evaluate(u.id, db_session, today=date(2026, 8, 19))
    assert after == {"divergences": [], "reviews": []}


def test_no_module_outside_the_endpoint_writes_active_false_on_an_injury(db_session):
    """GUARD, structural. `injury_trajectory` must stay surfacing-only: it may not
    assign `active` at all. Asserted against the source so a later edit that adds a
    write cannot pass by simply not being exercised by a test."""
    import inspect
    import re

    src = inspect.getsource(injury_trajectory)
    writes = re.findall(r"\.active\s*=(?!=)", src)
    assert writes == [], f"injury_trajectory must not assign .active — found {writes}"
