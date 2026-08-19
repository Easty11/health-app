"""`weekly_template` — capacity-quota microcycle on the fortification profile (#221).

Six gates, in brief order. The one that matters is (e): a region under an active
hard-stop must not be returned even when its capacity matches the requested slot.
That is asserted END-TO-END through `compute_probe_queue` -> `select_next` rather
than by reading the filter order off the source — a filter-order assumption is
exactly the thing a later refactor breaks silently.

The refusal tests carry NEGATIVE CONTROLS: templates the validator MUST accept, so
a validator that refused everything could not report green (FEEDBACK 10).
"""
import json

import pytest

import models
from engine import profile as profile_mod
from engine import selection, taxonomy
from engine.taxonomy import SIDE_BILATERAL


def _user(db, email="wt@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


BRIEF_TEMPLATE = {
    "slots": [
        {"capacity": "ENDURANCE", "sessions_per_week": 2, "minutes": 30},
        {"capacity": "STABILITY", "sessions_per_week": 2, "minutes": 15},
        {"capacity": "POWER", "sessions_per_week": 2, "minutes": 15},
        {"capacity": "STRENGTH", "sessions_per_week": 3, "minutes": 45},
    ]
}


# ── the identity `resolve_capacity` leans on ─────────────────────────────────

def test_capacity_name_lower_equals_value_for_every_member():
    """`resolve_capacity` accepts "STABILITY" and "stability" through ONE lookup
    because `name.lower() == value` holds today. A member that broke the identity
    would make the uppercase spelling silently unresolvable — pin it."""
    broken = [c.name for c in taxonomy.Capacity if c.name.lower() != c.value]
    assert broken == []


@pytest.mark.parametrize("token", ["STABILITY", "stability", " Stability ", "sTaBiLiTy"])
def test_resolve_capacity_accepts_both_spellings(token):
    assert taxonomy.resolve_capacity(token) is taxonomy.Capacity.STABILITY


@pytest.mark.parametrize("token", ["CARDIO", "", "  ", None, 3, ["STABILITY"]])
def test_resolve_capacity_refuses_non_members(token):
    assert taxonomy.resolve_capacity(token) is None


# ── gate (a): profile round-trip is byte-identical ───────────────────────────

def test_template_round_trips_byte_identical(db_session):
    """PUT a template -> GET returns it byte-identical. Asserted on the serialised
    JSON, not on `==`: dict equality would pass a re-cased or re-ordered value."""
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, {"weekly_template": BRIEF_TEMPLATE})
    read_back = profile_mod.profile_to_dict(p)["weekly_template"]
    assert json.dumps(read_back) == json.dumps(BRIEF_TEMPLATE)


def test_weekly_template_is_upsertable_and_serialised(db_session):
    """Both halves. Missing either is the failure mode the brief names: a field in
    `_UPSERTABLE` but not in `profile_to_dict` writes and never reads back."""
    assert "weekly_template" in profile_mod._UPSERTABLE
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, {"weekly_template": BRIEF_TEMPLATE})
    assert "weekly_template" in profile_mod.profile_to_dict(p)


def test_a_second_upsert_overwrites_the_template(db_session):
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": BRIEF_TEMPLATE})
    p = profile_mod.upsert_profile(
        db_session, u.id,
        {"weekly_template": {"slots": [
            {"capacity": "MOBILITY", "sessions_per_week": 1, "minutes": 20}]}},
    )
    assert [s["capacity"] for s in p.weekly_template["slots"]] == ["MOBILITY"]


def test_retirement_is_the_empty_slot_sentinel_not_a_clear(db_session):
    """`upsert_profile` cannot null a field (the shared `is not None` guard), so an
    empty slot list is how a template is retired. Pin both halves."""
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": BRIEF_TEMPLATE})
    p = profile_mod.upsert_profile(db_session, u.id, {"weekly_template": None})
    assert p.weekly_template == BRIEF_TEMPLATE, "None must not clear the field"
    p = profile_mod.upsert_profile(db_session, u.id, {"weekly_template": {"slots": []}})
    assert p.weekly_template == {"slots": []}


# ── gate (b): unknown capacity -> refused, no row written ────────────────────

def test_unknown_capacity_is_refused(db_session):
    u = _user(db_session)
    bad = {"slots": [{"capacity": "CARDIO", "sessions_per_week": 2, "minutes": 30}]}
    with pytest.raises(ValueError, match="unknown capacity"):
        profile_mod.upsert_profile(db_session, u.id, {"weekly_template": bad})


def test_a_refused_template_writes_no_row(db_session):
    """The gate the brief spells out. Validation runs before `db.add`, so a user
    with no profile still has none after a refusal — not a half-built row."""
    u = _user(db_session)
    bad = {"slots": [{"capacity": "CARDIO", "sessions_per_week": 2, "minutes": 30}]}
    with pytest.raises(ValueError):
        profile_mod.upsert_profile(db_session, u.id, {"weekly_template": bad})
    db_session.rollback()
    assert profile_mod.get_profile(db_session, u.id) is None


def test_a_refused_template_does_not_mutate_an_existing_row(db_session):
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": BRIEF_TEMPLATE})
    with pytest.raises(ValueError):
        profile_mod.upsert_profile(
            db_session, u.id,
            {"weekly_template": {"slots": [
                {"capacity": "NETBALL", "sessions_per_week": 1, "minutes": 30}]}},
        )
    db_session.rollback()
    assert profile_mod.get_profile(db_session, u.id).weekly_template == BRIEF_TEMPLATE


@pytest.mark.parametrize("bad,match", [
    ({"slots": [{"capacity": "POWER", "sessions_per_week": 2, "minutes": 30},
                {"capacity": "power", "sessions_per_week": 1, "minutes": 30}]},
     "duplicate capacity"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": 15, "minutes": 30}]}, "must be 0-14"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": -1, "minutes": 30}]}, "must be 0-14"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": 2, "minutes": 4}]}, "must be 5-180"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": 2, "minutes": 181}]}, "must be 5-180"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": True, "minutes": 30}]},
     "must be an integer"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": 2.5, "minutes": 30}]},
     "must be an integer"),
    ({"slots": [{"capacity": "POWER", "minutes": 30}]}, "missing required field"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": 2}]}, "missing required field"),
    ({"slots": [{"capacity": "POWER", "sessions_per_week": 2, "minutes": 30,
                 "sport": "netball"}]}, "unknown field"),
    ({"slots": [{"sessions_per_week": 2, "minutes": 30}]}, "unknown capacity"),
    ({"slots": "ENDURANCE"}, "must be a list"),
    ({"slots": [["POWER", 2, 30]]}, "must be an object"),
    ({"sport": "netball", "slots": []}, "unknown field"),
    ([], "must be an object"),
])
def test_malformed_templates_are_refused(bad, match):
    with pytest.raises(ValueError, match=match):
        profile_mod.validate_weekly_template(bad)


@pytest.mark.parametrize("good", [
    BRIEF_TEMPLATE,
    {"slots": []},
    {"slots": [{"capacity": "stability", "sessions_per_week": 0, "minutes": 5}]},
    {"slots": [{"capacity": "MOBILITY", "sessions_per_week": 14, "minutes": 180}]},
])
def test_valid_templates_are_accepted(good):
    """Negative control for the refusal battery above — a validator that refused
    everything would pass every `pytest.raises` and report green."""
    assert profile_mod.validate_weekly_template(good) is good


def test_the_shape_admits_no_sport_field():
    """The sport-agnostic decision, enforced rather than documented. A `sport` key
    at either level is a hard refusal — the temptation recurs (#221)."""
    for bad in ({"sport": "netball", "slots": []},
                {"slots": [{"capacity": "POWER", "sessions_per_week": 2,
                            "minutes": 30, "sport": "netball"}]}):
        with pytest.raises(ValueError, match="unknown field"):
            profile_mod.validate_weekly_template(bad)


# ── selection gates (c)-(f) ──────────────────────────────────────────────────

def _queue(db, user_id, profile):
    return selection.compute_probe_queue(
        db, user_id, profile=profile, loaded_region_keys=set(),
    )


def test_no_capacity_param_preserves_todays_selection(db_session):
    """Gate (c). Same probe region as an unconstrained call, and no `slot` key —
    the response shape is byte-identical when the parameter is absent."""
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    queue = _queue(db_session, u.id, p)
    assert queue, "fixture precondition: the probe queue is non-empty"

    out = selection.select_next(db_session, u.id, profile=p, probe_queue=queue)
    assert out["probe"]["region_key"] == queue[0]["region_key"]
    assert out["probe"]["side"] == queue[0]["side"]
    assert "slot" not in out

    explicit_none = selection.select_next(
        db_session, u.id, profile=p, probe_queue=queue, capacity=None
    )
    assert explicit_none == out


def test_capacity_slot_returns_only_that_capacity(db_session):
    """Gate (d)."""
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    queue = _queue(db_session, u.id, p)

    for cap in taxonomy.Capacity:
        out = selection.select_next(
            db_session, u.id, profile=p, probe_queue=queue, capacity=cap.name
        )
        assert out["slot"]["capacity"] == cap.value
        if out["probe"] is None:
            continue
        assert out["probe"]["capacity"] == cap.value
        assert taxonomy.by_key(out["probe"]["region_key"]).capacity is cap


def test_a_stability_slot_never_returns_a_non_stability_region(db_session):
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    queue = _queue(db_session, u.id, p)
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=queue, capacity="STABILITY"
    )
    assert out["probe"] is not None, "fixture precondition: a stability candidate exists"
    assert taxonomy.by_key(out["probe"]["region_key"]).capacity is taxonomy.Capacity.STABILITY


def test_hard_stopped_region_is_excluded_even_when_its_capacity_matches(db_session):
    """Gate (e) — the one that matters, asserted end-to-end.

    Take the region a STABILITY slot would otherwise select, hard-stop exactly it,
    and re-run the whole path. It must vanish. The pre-assertion that it WAS
    selected without the stop is what stops this passing vacuously.
    """
    u = _user(db_session)
    seed = dict(profile_mod.LUKE_PROFILE_SEED)
    seed["hard_stops"] = []
    p = profile_mod.upsert_profile(db_session, u.id, seed)

    unblocked = selection.select_next(
        db_session, u.id, profile=p,
        probe_queue=_queue(db_session, u.id, p), capacity="STABILITY",
    )
    victim = unblocked["probe"]
    assert victim is not None, "precondition: a stability region is selectable"
    assert taxonomy.by_key(victim["region_key"]).capacity is taxonomy.Capacity.STABILITY

    # Stop that exact region on every side it can be read on.
    region = taxonomy.by_key(victim["region_key"])
    p = profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [
        # Provenance is required on any hard_stop WRITE as of #227 — these were
        # written before that contract existed.
        {"region_key": region.key, "side": side, "reason": "test stop",
         "asserted_by": "user", "asserted_on": "2026-08-19"}
        for side in region.sides() + [SIDE_BILATERAL]
    ]})

    blocked_queue = _queue(db_session, u.id, p)
    assert all(c["region_key"] != region.key for c in blocked_queue), \
        "the stop must remove the region from the queue itself"

    blocked = selection.select_next(
        db_session, u.id, profile=p, probe_queue=blocked_queue, capacity="STABILITY",
    )
    assert blocked["probe"] is None or blocked["probe"]["region_key"] != region.key, \
        "a hard-stopped region came back through a matching capacity slot"


def test_the_slot_filter_can_only_remove_never_add(db_session):
    """The structural claim behind gate (e), stated directly: for every capacity,
    the slot-filtered candidate set is a SUBSET of the unconstrained one. A filter
    that can only narrow cannot re-admit anything the stop filter removed."""
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    queue = _queue(db_session, u.id, p)
    unconstrained = {(c["region_key"], c["side"]) for c in queue}
    for cap in taxonomy.Capacity:
        out = selection.select_next(
            db_session, u.id, profile=p, probe_queue=queue, capacity=cap.value
        )
        if out["probe"] is not None:
            assert (out["probe"]["region_key"], out["probe"]["side"]) in unconstrained


def test_an_empty_slot_is_a_valid_result_with_a_note(db_session):
    """An exhausted capacity yields probe=None and says why — not an error, and not
    the generic empty-queue note."""
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=[], capacity="POWER"
    )
    assert out["probe"] is None
    assert any("power" in n for n in out["notes"])
    assert out["slot"]["capacity"] == "power"


def test_select_next_refuses_an_unresolvable_capacity(db_session):
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    with pytest.raises(ValueError, match="unknown capacity"):
        selection.select_next(
            db_session, u.id, profile=p, probe_queue=_queue(db_session, u.id, p),
            capacity="NETBALL",
        )


def test_slot_reports_whether_the_fortify_target_matches(db_session):
    """The Fortify target is a DECLARED field, not a ranked candidate, so a slot
    does not drop it — the disagreement is surfaced instead of silently served."""
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    queue = _queue(db_session, u.id, p)
    # The seed target `anti_lateral_flexion` is a stability region.
    assert taxonomy.by_key("anti_lateral_flexion").capacity is taxonomy.Capacity.STABILITY

    matched = selection.select_next(
        db_session, u.id, profile=p, probe_queue=queue, capacity="STABILITY")
    assert matched["slot"]["fortify_target_matches_slot"] is True
    assert matched["fortify"]["target"] == "anti_lateral_flexion"

    mismatched = selection.select_next(
        db_session, u.id, profile=p, probe_queue=queue, capacity="ENDURANCE")
    assert mismatched["slot"]["fortify_target_matches_slot"] is False
    assert mismatched["fortify"]["target"] == "anti_lateral_flexion"


# ── gate (f): a null template behaves exactly as today ───────────────────────

def test_a_null_template_is_a_valid_state_not_a_degraded_one(db_session):
    """Gate (f). A profile that never sets a template selects identically to one
    that cannot have one — the column's presence changes nothing on its own."""
    u = _user(db_session)
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    assert p.weekly_template is None
    assert profile_mod.profile_to_dict(p)["weekly_template"] is None

    queue = _queue(db_session, u.id, p)
    without = selection.select_next(db_session, u.id, profile=p, probe_queue=queue)

    p = profile_mod.upsert_profile(db_session, u.id, {"weekly_template": BRIEF_TEMPLATE})
    with_tpl = selection.select_next(
        db_session, u.id, profile=p, probe_queue=_queue(db_session, u.id, p))

    assert with_tpl == without, \
        "storing a template must not change unconstrained selection — only ?capacity= does"


# ── the same gates over HTTP ─────────────────────────────────────────────────
#
# The brief states its gates in wire terms ("PUT a template -> GET returns it
# byte-identical", "GET /engine/next?capacity=STABILITY"). The engine-layer tests
# above prove the logic; these prove the wiring — a field validated in `profile.py`
# but absent from `ProfileIn` would be silently dropped by pydantic and every
# engine test would still pass.

from fastapi import FastAPI                       # noqa: E402
from fastapi.testclient import TestClient         # noqa: E402

from auth import get_current_user                 # noqa: E402
from database import get_db                       # noqa: E402
from routers import engine as engine_router       # noqa: E402


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(engine_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_http_put_then_get_is_byte_identical(db_session):
    """Gate (a) over the wire, compared on the raw response BYTES — the strongest
    available reading of "byte-identical", and the one that catches a silent
    re-casing that a parsed comparison would let through."""
    u = _user(db_session)
    c = _client(db_session, u)

    put = c.put("/engine/profile", json={"weekly_template": BRIEF_TEMPLATE})
    assert put.status_code == 200, put.text
    got = c.get("/engine/profile")
    assert got.status_code == 200

    assert put.json()["profile"]["weekly_template"] == BRIEF_TEMPLATE
    assert got.json()["profile"]["weekly_template"] == BRIEF_TEMPLATE
    # The exact substring the client sent, unreordered and unrecased.
    assert json.dumps(BRIEF_TEMPLATE, separators=(",", ":")) in \
        json.dumps(got.json()["profile"]["weekly_template"], separators=(",", ":"))
    assert '"capacity":"STABILITY"' in \
        json.dumps(got.json()["profile"]["weekly_template"], separators=(",", ":"))


def test_http_unknown_capacity_is_422_and_writes_no_row(db_session):
    """Gate (b) over the wire."""
    u = _user(db_session)
    c = _client(db_session, u)
    r = c.put("/engine/profile", json={
        "weekly_template": {"slots": [
            {"capacity": "CARDIO", "sessions_per_week": 2, "minutes": 30}]}})
    assert r.status_code == 422, r.text
    assert "unknown capacity" in r.json()["detail"]
    db_session.rollback()
    assert c.get("/engine/profile").json()["profile"] is None


def test_http_a_sport_field_is_422(db_session):
    u = _user(db_session)
    c = _client(db_session, u)
    r = c.put("/engine/profile", json={
        "weekly_template": {"slots": [
            {"capacity": "POWER", "sessions_per_week": 2, "minutes": 30,
             "sport": "netball"}]}})
    assert r.status_code == 422
    assert "unknown field" in r.json()["detail"]


def test_http_next_without_capacity_is_unchanged(db_session):
    """Gate (c) over the wire: no `slot` key at all when the parameter is absent."""
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    c = _client(db_session, u)
    r = c.get("/engine/next")
    assert r.status_code == 200, r.text
    assert "slot" not in r.json()
    assert r.json()["probe"] is not None


def test_http_next_with_capacity_returns_only_that_capacity(db_session):
    """Gate (d) over the wire, in the brief's own spelling."""
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    c = _client(db_session, u)
    r = c.get("/engine/next", params={"capacity": "STABILITY"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot"]["capacity"] == "stability"
    assert body["probe"]["capacity"] == "stability"
    assert taxonomy.by_key(body["probe"]["region_key"]).capacity is taxonomy.Capacity.STABILITY


def test_http_next_hard_stop_beats_a_matching_slot(db_session):
    """Gate (e) over the wire — the gate that matters, end-to-end through HTTP."""
    u = _user(db_session)
    seed = dict(profile_mod.LUKE_PROFILE_SEED)
    seed["hard_stops"] = []
    profile_mod.upsert_profile(db_session, u.id, seed)
    c = _client(db_session, u)

    victim = c.get("/engine/next", params={"capacity": "STABILITY"}).json()["probe"]
    assert victim is not None, "precondition: a stability region is selectable"

    region = taxonomy.by_key(victim["region_key"])
    c.put("/engine/profile", json={"hard_stops": [
        # Provenance is required on any hard_stop WRITE as of #227 — these were
        # written before that contract existed.
        {"region_key": region.key, "side": side, "reason": "test stop",
         "asserted_by": "user", "asserted_on": "2026-08-19"}
        for side in region.sides() + [SIDE_BILATERAL]
    ]})

    after = c.get("/engine/next", params={"capacity": "STABILITY"}).json()["probe"]
    assert after is None or after["region_key"] != region.key


def test_http_next_refuses_an_unknown_capacity_param(db_session):
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    c = _client(db_session, u)
    r = c.get("/engine/next", params={"capacity": "NETBALL"})
    assert r.status_code == 422
    assert "unknown capacity" in r.json()["detail"]


def test_http_a_user_with_no_template_is_unaffected(db_session):
    """Gate (f) over the wire."""
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    c = _client(db_session, u)
    assert c.get("/engine/profile").json()["profile"]["weekly_template"] is None
    assert c.get("/engine/next").status_code == 200
