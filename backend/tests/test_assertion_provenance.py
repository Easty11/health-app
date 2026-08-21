"""Assertion provenance on profile entries (#227/#228).

`hard_stops` and `live_signals` recorded WHAT was asserted but not who asserted it,
on what basis, or when. Two consequences, and the second is the real one:
attribution (a user statement and an engine inference occupied the same JSON key by
occupying none), and retirement (an entry asserted for a transient signal had no
recorded basis, so a hard stop nobody remembers setting is indistinguishable from
one that still applies).

Two gates carry the weight, and neither is about the happy path:

  * the REGRESSION gate — provenance is metadata and must not alter selection. The
    same fixture must return the same region before and after, asserted by running
    BOTH shapes through the real path in one test rather than trusting that added
    keys are inert.
  * the GUARD — nothing auto-expires. A `review_on` in the past must still block.
    A hard stop that quietly stops applying because a date passed is the exact
    inversion of what this brief is for.
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import models
from auth import get_current_user
from database import get_db
from engine import profile as profile_mod
from engine import selection, taxonomy
from routers import engine as engine_router


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(engine_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


PROV = {"asserted_by": "user", "asserted_on": "2026-08-19"}

STOP_WITH_PROV = {
    "region_key": "single_leg_hop", "side": "right", "reason": "post-op precaution",
    "asserted_by": "clinician",
    "asserted_on": "2026-08-01",
    "basis": "surgeon's 12-week loading restriction, written on the discharge note",
    "review_on": "2026-11-01",
}

# The same stop as it would have been written before provenance existed.
STOP_LEGACY = {
    "region_key": "single_leg_hop", "side": "right", "reason": "post-op precaution",
}


def _blocked(region_key, side, hard_stops):
    """The real path: `is_contraindicated` with no injuries, only profile stops."""
    region = taxonomy.by_key(region_key)
    assert region is not None, f"{region_key} does not resolve in the taxonomy"
    blocked, _reason = selection.is_contraindicated(
        region, side, profile_hard_stops=hard_stops, active_injuries=[],
    )
    return blocked


# ── the vocabulary ───────────────────────────────────────────────────────────

def test_asserted_by_is_a_closed_three_tier_set():
    assert profile_mod.ASSERTED_BY_VALUES == ("user", "engine", "clinician")


def test_the_authority_vocabulary_agrees_with_the_resolution_store():
    """`asserted_by` (this store) and `resolved_by` (#222's injury resolution) are
    the same AUTHORITY axis and must not drift into different words for one idea.

    They differ by exactly one member, and the difference is principled rather than
    accidental: `engine` can ASSERT (a probe response is an inference the engine
    made) but must never RESOLVE, because #223 says nothing auto-resolves. Pinned
    here so a later edit that adds `engine` to `resolved_by` — or drops it from
    `asserted_by` — fails loudly instead of looking like tidying."""
    from routers.knowledge import RESOLVED_BY_VALUES

    assert set(RESOLVED_BY_VALUES) < set(profile_mod.ASSERTED_BY_VALUES)
    assert set(profile_mod.ASSERTED_BY_VALUES) - set(RESOLVED_BY_VALUES) == {"engine"}


def test_provenance_is_a_different_axis_from_the_capture_source():
    """`asserted_by` is NOT a rename of the `source` field the knowledge store and
    `POST /engine/response` already carry. `source` answers "through which channel
    did this arrive" (onboarding | chat | system, probe, hevy); `asserted_by`
    answers "who is making the claim". They are orthogonal — an entry can arrive via
    chat while being asserted by a clinician — which is why this adds a key rather
    than reusing one. Asserted as a disjointness property so a later merge of the
    two vocabularies has to argue with a test."""
    # `api` (#NEXT-source-api) joins the knowledge store's channel set. Widening
    # this literal is what keeps the disjointness claim honest as the channel
    # vocabulary grows -- but NOTE WHAT THIS ASSERTION DOES NOT DO: disjointness of
    # two word lists is not a guarantee that the axes stay separate. A future
    # `source` member naming an AUTHOR rather than a channel (`operator`, `physio`)
    # would be disjoint from ASSERTED_BY_VALUES and still collapse the two axes into
    # one. That the axes stay clean is a design commitment carried by
    # #NEXT-source-api and by the comment on SOURCE_VALUES, not by this test.
    channel_words = {"onboarding", "chat", "system", "api",
                     "probe", "self_report", "manual"}
    assert channel_words.isdisjoint(set(profile_mod.ASSERTED_BY_VALUES))


# ── writes require provenance ────────────────────────────────────────────────

@pytest.mark.parametrize("field", ["hard_stops", "live_signals"])
def test_an_entry_without_asserted_by_is_refused(db_session, field):
    u = _user(db_session, f"prov-missing-{field}@example.com")
    with pytest.raises(ValueError, match="asserted_by is required"):
        profile_mod.upsert_profile(db_session, u.id, {field: [{"reason": "x"}]})


@pytest.mark.parametrize("field", ["hard_stops", "live_signals"])
@pytest.mark.parametrize("bad", ["physio", "USER", "", "app", "system", "chat"])
def test_an_unknown_asserted_by_literal_is_refused(db_session, field, bad):
    u = _user(db_session, "prov-unknown@example.com")
    with pytest.raises(ValueError, match="unknown value"):
        profile_mod.upsert_profile(
            db_session, u.id,
            {field: [{"reason": "x", "asserted_by": bad, "asserted_on": "2026-08-19"}]})


@pytest.mark.parametrize("good", ["user", "engine", "clinician"])
def test_each_recognised_tier_is_accepted(db_session, good):
    """Negative control for the refusal battery — a validator that refused
    everything would satisfy every `pytest.raises` above and report green."""
    u = _user(db_session, f"prov-ok-{good}@example.com")
    p = profile_mod.upsert_profile(
        db_session, u.id,
        {"hard_stops": [{"reason": "x", "asserted_by": good, "asserted_on": "2026-08-19"}]})
    assert p.hard_stops[0]["asserted_by"] == good


@pytest.mark.parametrize("bad", [None, "19-08-2026", "2026-13-01", "2026-08-32",
                                 "yesterday", 20260819, "2026/08/19", ""])
def test_a_missing_or_malformed_asserted_on_is_refused(db_session, bad):
    u = _user(db_session, "prov-date@example.com")
    entry = {"reason": "x", "asserted_by": "user"}
    if bad is not None:
        entry["asserted_on"] = bad
    with pytest.raises(ValueError, match="asserted_on"):
        profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [entry]})


@pytest.mark.parametrize("bad", ["soon", "2026-13-01", 20261119])
def test_a_malformed_review_on_is_refused(db_session, bad):
    u = _user(db_session, "prov-review@example.com")
    with pytest.raises(ValueError, match="review_on"):
        profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [
            {**PROV, "reason": "x", "review_on": bad}]})


def test_review_on_may_be_null_meaning_standing_until_retired(db_session):
    u = _user(db_session, "prov-standing@example.com")
    p = profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [
        {**PROV, "reason": "standing rule", "review_on": None}]})
    assert p.hard_stops[0]["review_on"] is None


def test_review_on_may_be_omitted_entirely(db_session):
    u = _user(db_session, "prov-noreview@example.com")
    p = profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [
        {**PROV, "reason": "no review key at all"}]})
    assert "review_on" not in p.hard_stops[0]


def test_a_non_string_basis_is_refused(db_session):
    u = _user(db_session, "prov-basis@example.com")
    with pytest.raises(ValueError, match="basis"):
        profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [
            {**PROV, "reason": "x", "basis": 42}]})


def test_domain_keys_are_not_frozen_by_this_validator(db_session):
    """Only the PROVENANCE keys are validated. Entries are free-form domain dicts —
    `hard_stops` carry pattern/region_key/scope/side/reason, `live_signals` carry
    signal/branch_param/status/self_triage — and an unknown key must pass. This is
    deliberately unlike `validate_weekly_template`, whose slots are a closed shape."""
    u = _user(db_session, "prov-freeform@example.com")
    p = profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [
        {**PROV, "some_future_domain_key": "whatever", "nested": {"a": [1, 2]}}]})
    assert p.hard_stops[0]["some_future_domain_key"] == "whatever"


def test_a_refused_write_leaves_no_row_and_mutates_none(db_session):
    """Validation runs before the session is touched (#221's ordering, extended)."""
    u = _user(db_session, "prov-norow@example.com")
    with pytest.raises(ValueError):
        profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [{"reason": "x"}]})
    db_session.rollback()
    assert profile_mod.get_profile(db_session, u.id) is None

    profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [STOP_WITH_PROV]})
    with pytest.raises(ValueError):
        profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [{"reason": "y"}]})
    db_session.rollback()
    assert profile_mod.get_profile(db_session, u.id).hard_stops == [STOP_WITH_PROV]


# ── reads tolerate absence ───────────────────────────────────────────────────

def test_a_pre_provenance_profile_reads_without_error(db_session):
    """The backfill. Written straight to the column, bypassing the validator, which
    is exactly how the rows that predate this change got there."""
    u = _user(db_session, "prov-legacy@example.com")
    row = models.FortificationProfile(
        user_id=u.id, hard_stops=[STOP_LEGACY],
        live_signals=[{"signal": "flank tension", "side": "right"}],
    )
    db_session.add(row)
    db_session.commit()

    out = profile_mod.profile_to_dict(profile_mod.get_profile(db_session, u.id))
    assert out["hard_stops"][0]["asserted_by"] == "user"
    assert out["hard_stops"][0]["asserted_on"] is None
    assert out["hard_stops"][0]["review_on"] is None
    assert out["live_signals"][0]["asserted_by"] == "user"
    # The domain content is untouched by the backfill.
    assert out["hard_stops"][0]["region_key"] == "single_leg_hop"


def test_the_backfill_does_not_write_to_the_stored_column(db_session):
    """A read must not mutate. The column keeps the legacy shape; only the
    serialised view carries the default."""
    u = _user(db_session, "prov-nowrite@example.com")
    row = models.FortificationProfile(user_id=u.id, hard_stops=[STOP_LEGACY])
    db_session.add(row)
    db_session.commit()

    profile_mod.profile_to_dict(profile_mod.get_profile(db_session, u.id))
    db_session.expire_all()
    stored = db_session.query(models.FortificationProfile).filter_by(user_id=u.id).one()
    assert stored.hard_stops == [STOP_LEGACY]
    assert "asserted_by" not in stored.hard_stops[0]


def test_an_entry_that_carries_provenance_passes_through_verbatim(db_session):
    """No summarising, no computed "is stale" boolean — presentation decides that,
    not the store."""
    u = _user(db_session, "prov-verbatim@example.com")
    profile_mod.upsert_profile(db_session, u.id, {"hard_stops": [STOP_WITH_PROV]})
    out = profile_mod.profile_to_dict(profile_mod.get_profile(db_session, u.id))
    assert out["hard_stops"] == [STOP_WITH_PROV]
    assert not any(k.startswith("is_") for k in out["hard_stops"][0])


def test_a_mixed_profile_backfills_only_the_entries_that_need_it(db_session):
    u = _user(db_session, "prov-mixed@example.com")
    row = models.FortificationProfile(
        user_id=u.id, hard_stops=[STOP_LEGACY, STOP_WITH_PROV])
    db_session.add(row)
    db_session.commit()

    out = profile_mod.profile_to_dict(profile_mod.get_profile(db_session, u.id))
    assert out["hard_stops"][0]["asserted_on"] is None          # backfilled
    assert out["hard_stops"][1] == STOP_WITH_PROV               # verbatim


# ── round-trip ───────────────────────────────────────────────────────────────

def test_the_provenance_block_survives_put_then_get(db_session):
    """Over the wire, compared on the raw JSON substring as well as the parsed
    value — a dict comparison would pass a silently re-serialised date."""
    import json

    u = _user(db_session, "prov-rt@example.com")
    c = _client(db_session, u)
    put = c.put("/engine/profile", json={"hard_stops": [STOP_WITH_PROV]})
    assert put.status_code == 200, put.text
    got = c.get("/engine/profile")

    assert got.json()["profile"]["hard_stops"] == [STOP_WITH_PROV]
    assert '"asserted_on": "2026-08-01"' in json.dumps(
        got.json()["profile"]["hard_stops"][0], indent=None)
    assert '"asserted_by": "clinician"' in json.dumps(
        got.json()["profile"]["hard_stops"][0], indent=None)


def test_http_a_missing_asserted_by_is_422(db_session):
    u = _user(db_session, "prov-http422@example.com")
    r = _client(db_session, u).put(
        "/engine/profile", json={"hard_stops": [{"reason": "x"}]})
    assert r.status_code == 422
    assert "asserted_by is required" in r.json()["detail"]


def test_http_an_unknown_tier_is_422(db_session):
    u = _user(db_session, "prov-http-tier@example.com")
    r = _client(db_session, u).put("/engine/profile", json={
        "hard_stops": [{"reason": "x", "asserted_by": "physio",
                        "asserted_on": "2026-08-19"}]})
    assert r.status_code == 422
    assert "unknown value" in r.json()["detail"]


def test_the_legacy_read_shape_is_refused_on_write_and_says_why(db_session):
    """The known consequence of writes-require / reads-tolerate, pinned rather than
    left in prose: a legacy entry read back carries `asserted_on: null`, and
    re-sending it verbatim is refused. The message must tell the operator to state
    the date instead of re-sending null — otherwise this is a trap."""
    u = _user(db_session, "prov-rtlegacy@example.com")
    row = models.FortificationProfile(user_id=u.id, hard_stops=[STOP_LEGACY])
    db_session.add(row)
    db_session.commit()

    c = _client(db_session, u)
    read_back = c.get("/engine/profile").json()["profile"]["hard_stops"]
    assert read_back[0]["asserted_on"] is None

    r = c.put("/engine/profile", json={"hard_stops": read_back})
    assert r.status_code == 422
    assert "state the date" in r.json()["detail"]

    # And the fix is to supply one — the entry is otherwise acceptable.
    fixed = [{**read_back[0], "asserted_on": "2026-08-19"}]
    assert c.put("/engine/profile", json={"hard_stops": fixed}).status_code == 200


# ── REGRESSION: provenance must not change selection ─────────────────────────

def test_the_same_stop_blocks_identically_with_and_without_provenance(db_session):
    """THE regression gate. The same hard stop, in both shapes, through the real
    `is_contraindicated` path — same verdict, and the reason string is unchanged
    too. Running both shapes in one test is what makes this a comparison rather
    than an assumption that added keys are inert."""
    region, side = "single_leg_hop", taxonomy.SIDE_RIGHT
    assert _blocked(region, side, [STOP_LEGACY]) is True
    assert _blocked(region, side, [STOP_WITH_PROV]) is True

    _, legacy_reason = selection.is_contraindicated(
        taxonomy.by_key(region), side,
        profile_hard_stops=[STOP_LEGACY], active_injuries=[])
    _, prov_reason = selection.is_contraindicated(
        taxonomy.by_key(region), side,
        profile_hard_stops=[STOP_WITH_PROV], active_injuries=[])
    assert legacy_reason == prov_reason == "post-op precaution"


def test_select_next_returns_the_same_region_with_and_without_provenance(db_session):
    """End-to-end through `compute_probe_queue` -> `select_next`, which is what
    `/engine/next` consumes. Two users, identical profiles apart from the presence
    of provenance keys, must select identically."""
    plain = _user(db_session, "reg-plain@example.com")
    stamped = _user(db_session, "reg-stamped@example.com")

    seed_plain = dict(profile_mod.LUKE_PROFILE_SEED)
    seed_plain["hard_stops"] = [STOP_LEGACY]
    seed_plain["live_signals"] = [{"signal": "flank tension", "side": "right"}]
    # Written straight to the column — the legacy shape cannot pass the validator.
    db_session.add(models.FortificationProfile(
        user_id=plain.id,
        primary_target=seed_plain["primary_target"],
        vehicle_bias=seed_plain["vehicle_bias"],
        probe_budget=seed_plain["probe_budget"],
        horizon=seed_plain["horizon"],
        hard_stops=seed_plain["hard_stops"],
        live_signals=seed_plain["live_signals"],
    ))
    db_session.commit()

    seed_stamped = dict(profile_mod.LUKE_PROFILE_SEED)
    seed_stamped["hard_stops"] = [STOP_WITH_PROV]
    seed_stamped["live_signals"] = [
        {"signal": "flank tension", "side": "right", **PROV, "review_on": "2026-11-19"}]
    profile_mod.upsert_profile(db_session, stamped.id, seed_stamped)

    def selected(user_id):
        p = profile_mod.get_profile(db_session, user_id)
        queue = selection.compute_probe_queue(
            db_session, user_id, profile=p, loaded_region_keys=set())
        out = selection.select_next(db_session, user_id, profile=p, probe_queue=queue)
        return out["mode_recommended"], out["probe"], out["fortify"]["target"]

    assert selected(plain.id) == selected(stamped.id)


def test_the_seed_still_selects_what_it_did_before_provenance(db_session):
    """The seed gained provenance keys this session. Its selection must not have
    moved — pinned against the seed's declared target rather than a snapshot."""
    u = _user(db_session, "reg-seed@example.com")
    p = profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    queue = selection.compute_probe_queue(
        db_session, u.id, profile=p, loaded_region_keys=set())
    out = selection.select_next(db_session, u.id, profile=p, probe_queue=queue)

    assert out["fortify"]["target"] == "anti_lateral_flexion"
    assert out["probe"] is not None
    assert out["probe"]["region_key"] == queue[0]["region_key"]


# ── GUARD: nothing auto-expires ──────────────────────────────────────────────

PAST_REVIEW = {**STOP_WITH_PROV, "review_on": "2020-01-01"}


def test_a_hard_stop_with_a_past_review_on_still_blocks(db_session):
    """THE guard. `review_on` is a prompt, never an expiry. A stop that quietly
    stopped applying because a date passed would be a safety failure with no
    operator in the loop — the exact inversion of what provenance is for."""
    assert _blocked("single_leg_hop", taxonomy.SIDE_RIGHT, [PAST_REVIEW]) is True


def test_a_past_review_on_does_not_remove_the_region_from_the_queue(db_session):
    """The same guard one layer out, through the path `/engine/next` consumes."""
    u = _user(db_session, "guard-queue@example.com")
    p = profile_mod.upsert_profile(db_session, u.id, {
        "primary_target": "anti_lateral_flexion", "hard_stops": [PAST_REVIEW]})
    queue = selection.compute_probe_queue(
        db_session, u.id, profile=p, loaded_region_keys=set())
    assert ("single_leg_hop", taxonomy.SIDE_RIGHT) not in {
        (c["region_key"], c["side"]) for c in queue}


def test_the_stop_is_identical_whatever_review_on_says(db_session):
    """Past, future, null and absent all block the same. Asserted as one comparison
    so a future edit that reads `review_on` in the filter fails here."""
    region, side = "single_leg_hop", taxonomy.SIDE_RIGHT
    variants = [
        {**STOP_WITH_PROV, "review_on": "2020-01-01"},
        {**STOP_WITH_PROV, "review_on": "2099-01-01"},
        {**STOP_WITH_PROV, "review_on": None},
        {k: v for k, v in STOP_WITH_PROV.items() if k != "review_on"},
    ]
    assert [_blocked(region, side, [v]) for v in variants] == [True] * 4


def test_no_selection_code_reads_review_on(db_session):
    """Structural. `review_on` must never reach the filter path, so a later edit
    that makes it gate selection fails even if no behavioural test covers it."""
    import inspect

    for module in (selection,):
        assert "review_on" not in inspect.getsource(module), (
            f"{module.__name__} references review_on — retirement must stay an "
            "explicit write (#228)")


# -- the capture-channel vocabulary (#NEXT-source-api) ------------------------

def test_source_is_a_closed_four_member_channel_set():
    from routers.knowledge import SOURCE_VALUES

    assert SOURCE_VALUES == ("onboarding", "chat", "system", "api")


@pytest.mark.parametrize("bad", ["operator", "powershell", "CHAT", "", "user",
                                 "clinician", "engine", "hevy"])
def test_an_unknown_source_literal_is_refused(bad):
    """The authority words are in this list deliberately: `user`/`clinician`/`engine`
    belong to `asserted_by`, and a write that reaches for one of them here is the
    axis-mixing #NEXT-source-api refuses."""
    from routers.knowledge import KnowledgeEntryIn

    with pytest.raises(ValidationError, match="unknown source"):
        KnowledgeEntryIn(type="schedule_item", key="k", value={}, source=bad)


@pytest.mark.parametrize("good", ["onboarding", "chat", "system", "api"])
def test_each_declared_channel_is_accepted(good):
    """Negative control for the refusal battery above -- a validator that refused
    everything would satisfy every `pytest.raises` and report green."""
    from routers.knowledge import KnowledgeEntryIn

    assert KnowledgeEntryIn(type="schedule_item", key="k", value={},
                            source=good).source == good


def test_an_omitted_source_is_refused():
    """The second negative control, and the one this change exists for. `source` had
    a `"chat"` default, so an operator write that never chose a channel was silently
    labelled as one -- the four mislabelled rows were not a validation failure, they
    were a validation that never ran. Adding `api` while leaving the default in place
    would have left the defect exactly where it was."""
    from routers.knowledge import KnowledgeEntryIn

    with pytest.raises(ValidationError):
        KnowledgeEntryIn(type="schedule_item", key="k", value={})
