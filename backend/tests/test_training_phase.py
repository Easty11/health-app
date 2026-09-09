"""Training-phase ledger (Q112, #270) — schema invariants, validation, engine hooks.

Mirrors `test_cbti_substrate` for the append-only / one-open invariants and
`test_schedule_item_schema` for the fail-closed validation battery. The engine block
asserts the four E-hooks end-to-end through `select_next`, and the `None`-phase path is
pinned byte-identical to pre-Q112.

Refusal batteries carry NEGATIVE CONTROLS (a payload the validator MUST accept), so a
validator that refused everything could not report green (FEEDBACK §17).
"""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

import models
from engine import profile as profile_mod
from engine import selection, taxonomy
from engine import training_phase as phase_mod
from load_metrics import _local_day


def _user(db, email="phase@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _payload(**overrides):
    """A conforming open payload. Overrides mutate one field at a time so each test states
    exactly what it makes wrong."""
    base = {
        "label": "decompression",
        "intent": "Post-season recovery. Swims easy aerobic, no VO2 this block.",
        "probe_posture": "suppressed",
        "capacities": ["mobility", "stability"],
        "microcycle": {
            "sub_cycle_days": 7,
            "sub_cycles": [
                {"label": "flat", "slots": [
                    {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 40}]},
            ],
        },
        "entered_on": "2026-09-07",
        "review_on": "2026-10-05",
        "asserted_by": "user",
        "asserted_on": "2026-09-09",
        "source": "api",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not ...}


# ── the provenance-domain drift guard ────────────────────────────────────────

def test_model_check_domains_match_the_canonical_tuples():
    """models.py cannot import the canonical tuples without a cycle, so its DB CHECK domains
    are frozen snapshots. Pin them equal to the sources so a widening cannot drift past the
    constraint silently."""
    assert phase_mod.ASSERTED_BY_VALUES == ("user", "engine", "clinician")
    assert phase_mod.SOURCE_VALUES == ("onboarding", "chat", "system", "api")
    ddl = " ".join(
        str(c.sqltext) for c in models.TrainingPhase.__table__.constraints
        if hasattr(c, "sqltext")
    )
    for v in phase_mod.ASSERTED_BY_VALUES:
        assert f"'{v}'" in ddl
    for v in phase_mod.SOURCE_VALUES:
        assert f"'{v}'" in ddl
    for v in phase_mod.PROBE_POSTURE_VALUES:
        assert f"'{v}'" in ddl


# ── append-only + one-open invariants (mirror test_cbti_substrate) ───────────

def test_open_then_roundtrip(db_session):
    u = _user(db_session)
    phase = phase_mod.open_phase(db_session, u.id, _payload())
    assert phase.id is not None
    assert phase.closed_on is None and phase.close_reason is None
    assert phase.capacities == ["mobility", "stability"]        # verbatim
    assert phase.entered_on == date(2026, 9, 7)


def test_probe_posture_domain_check_rejects_invalid(db_session):
    """The one DB-enforced domain constraint, exercised like cbti's decision CHECK."""
    u = _user(db_session)
    bad = models.TrainingPhase(
        user_id=u.id, label="x", probe_posture="paused",       # not in the domain
        entered_on=date(2026, 9, 7), asserted_by="user",
        asserted_on=date(2026, 9, 9), source="api",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("col,val", [
    ("asserted_by", "coach"),      # not in ASSERTED_BY_VALUES
    ("source", "sms"),             # not in SOURCE_VALUES
])
def test_provenance_domain_checks_reject_invalid(db_session, col, val):
    u = _user(db_session, email=f"{col}@x.io")
    kwargs = dict(
        user_id=u.id, label="x", probe_posture="held", entered_on=date(2026, 9, 7),
        asserted_by="user", asserted_on=date(2026, 9, 9), source="api",
    )
    kwargs[col] = val
    db_session.add(models.TrainingPhase(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_closure_updates_only_closure_columns(db_session):
    """The ONLY permitted UPDATE: closed_on + close_reason. Every other column of the closed
    row is unchanged — the append-only invariant stated positively."""
    u = _user(db_session)
    p = phase_mod.open_phase(db_session, u.id, _payload())
    before = {c.name: getattr(p, c.name) for c in models.TrainingPhase.__table__.columns}

    closed = phase_mod.close_phase(db_session, u.id, "block complete")
    assert closed.id == p.id
    assert closed.closed_on == _local_day()
    assert closed.close_reason == "block complete"
    for col in ("label", "intent", "probe_posture", "capacities", "microcycle",
                "entered_on", "review_on", "asserted_by", "asserted_on", "source"):
        assert getattr(closed, col) == before[col], f"{col} must not change at closure"


def test_opening_a_second_closes_the_first_in_one_txn(db_session):
    """One-open invariant: opening a phase closes the current open row. The prior row's only
    mutated columns are closed_on (= new.entered_on, half-open handoff) and close_reason."""
    u = _user(db_session)
    first = phase_mod.open_phase(db_session, u.id, _payload(label="decompression"))
    second = phase_mod.open_phase(
        db_session, u.id,
        _payload(label="aerobic_base", entered_on="2026-09-09", capacities=None,
                 microcycle=None, close_prior_reason="moving to base"),
    )
    db_session.refresh(first)
    assert first.closed_on == date(2026, 9, 9)      # == second.entered_on
    assert first.close_reason == "moving to base"
    assert first.label == "decompression"            # untouched
    assert second.closed_on is None
    # Exactly one open row.
    open_rows = db_session.query(models.TrainingPhase).filter_by(
        user_id=u.id, closed_on=None).all()
    assert [r.id for r in open_rows] == [second.id]
    assert phase_mod.current_training_phase(db_session, u.id).id == second.id


def test_default_close_prior_reason_names_the_new_label(db_session):
    u = _user(db_session)
    phase_mod.open_phase(db_session, u.id, _payload(label="decompression"))
    phase_mod.open_phase(db_session, u.id,
                         _payload(label="aerobic_base", entered_on="2026-09-09"))
    first = db_session.query(models.TrainingPhase).filter_by(
        user_id=u.id, label="decompression").first()
    assert first.close_reason == "opened aerobic_base"


def test_close_with_nothing_open_raises_no_open_phase(db_session):
    u = _user(db_session)
    with pytest.raises(phase_mod.NoOpenPhase):
        phase_mod.close_phase(db_session, u.id, "nothing to close")
    # And after a close, the next close is a NoOpenPhase too (zero-open baseline).
    phase_mod.open_phase(db_session, u.id, _payload())
    phase_mod.close_phase(db_session, u.id, "done")
    assert phase_mod.current_training_phase(db_session, u.id) is None
    with pytest.raises(phase_mod.NoOpenPhase):
        phase_mod.close_phase(db_session, u.id, "again")


def test_zero_open_is_a_valid_baseline(db_session):
    u = _user(db_session)
    assert phase_mod.current_training_phase(db_session, u.id) is None
    phase_mod.open_phase(db_session, u.id, _payload())
    phase_mod.close_phase(db_session, u.id, "done")
    assert phase_mod.current_training_phase(db_session, u.id) is None


# ── validation battery (fail-closed) ─────────────────────────────────────────

@pytest.mark.parametrize("payload,match", [
    (_payload(capacities=["mobility", "cardio"]), "unknown capacity"),
    (_payload(capacities=["stability", "stability"]), "duplicate capacity"),
    (_payload(probe_posture="paused"), "probe_posture"),
    (_payload(probe_posture=...), "probe_posture is required"),
    (_payload(label=""), "label is required"),
    (_payload(label=...), "label is required"),
    (_payload(asserted_by="coach"), "asserted_by is required"),
    (_payload(source="sms"), "source is required"),
    (_payload(review_on="2026-09-01"), "review_on must be on or after"),
    (_payload(entered_on="2099-01-01"), "must not be in the future"),
    (_payload(microcycle={"sub_cycle_days": 2, "sub_cycles": [
        {"slots": [{"capacity": "stability", "sessions_per_cycle": 1, "minutes": 30}]}]}),
     "sub_cycle_days must be 3-28"),
    (_payload(microcycle={"sub_cycle_days": 7, "sub_cycles": []}), "must have 1-4 entries"),
    (_payload(microcycle={"sub_cycle_days": 7, "sub_cycles": [
        {"slots": [{"capacity": "stability", "sessions_per_cycle": 1, "minutes": 30},
                   {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}]}]}),
     "duplicate capacity"),
    (_payload(microcycle={"sub_cycle_days": 7, "sub_cycles": [
        {"slots": [{"capacity": "cardio", "sessions_per_cycle": 1, "minutes": 30}]}]}),
     "unknown capacity"),
    (_payload(microcycle={"sub_cycle_days": 7, "sub_cycles": [
        {"slots": [{"capacity": "stability", "sessions_per_cycle": 1, "minutes": 4}]}]}),
     "must be 5-180"),
])
def test_invalid_payloads_are_refused(payload, match):
    with pytest.raises(ValueError, match=match):
        phase_mod.validate_training_phase(payload)


def test_cross_sub_cycle_duplicate_capacity_passes():
    """The A/B point: the SAME capacity at DIFFERENT doses across sub-cycles is allowed; only
    a duplicate WITHIN one sub-cycle is the error. Negative control for the dup battery."""
    ok = _payload(microcycle={
        "sub_cycle_days": 7,
        "sub_cycles": [
            {"label": "A", "slots": [{"capacity": "strength", "sessions_per_cycle": 3, "minutes": 45}]},
            {"label": "B", "slots": [{"capacity": "strength", "sessions_per_cycle": 1, "minutes": 30}]},
        ],
    })
    assert phase_mod.validate_training_phase(ok)["microcycle"] is ok["microcycle"]


def test_null_capacities_and_microcycle_are_valid():
    """null = all live / fall back to weekly_template. Both must pass."""
    out = phase_mod.validate_training_phase(_payload(capacities=None, microcycle=None))
    assert out["capacities"] is None and out["microcycle"] is None


def test_non_monotonic_entered_on_is_refused(db_session):
    """entered_on >= the open phase's entered_on — history is monotonic."""
    u = _user(db_session)
    phase_mod.open_phase(db_session, u.id, _payload(entered_on="2026-09-07"))
    with pytest.raises(ValueError, match="monotonic"):
        phase_mod.open_phase(db_session, u.id,
                             _payload(label="earlier", entered_on="2026-09-01"))


def test_entered_on_defaults_to_local_day(db_session):
    u = _user(db_session)
    p = phase_mod.open_phase(db_session, u.id, _payload(entered_on=...))
    assert p.entered_on == _local_day()


# ── phase_at — half-open interval, same-day boundary ─────────────────────────

def test_phase_at_half_open_and_same_day_boundary(db_session):
    u = _user(db_session)
    first = phase_mod.open_phase(db_session, u.id, _payload(label="a", entered_on="2026-09-07"))
    # Same-day close/open boundary: second enters the day the first closes.
    second = phase_mod.open_phase(db_session, u.id, _payload(label="b", entered_on="2026-09-09"))
    db_session.refresh(first)
    assert first.closed_on == date(2026, 9, 9)

    # Before the first phase → None.
    assert phase_mod.phase_at(db_session, u.id, date(2026, 9, 6)) is None
    # Inside the first, before the boundary → first.
    assert phase_mod.phase_at(db_session, u.id, date(2026, 9, 8)).id == first.id
    assert phase_mod.phase_at(db_session, u.id, date(2026, 9, 8, ) ).id == first.id  # inside first, pre-boundary
    # ON the boundary → the SUCCESSOR wins (half-open: entered_on <= d < closed_on).
    assert phase_mod.phase_at(db_session, u.id, date(2026, 9, 9)).id == second.id
    # After the boundary, second is open (no upper bound).
    assert phase_mod.phase_at(db_session, u.id, date(2026, 9, 30)).id == second.id


# ── engine hooks E1–E5 ───────────────────────────────────────────────────────

def _seeded(db):
    u = _user(db)
    p = profile_mod.upsert_profile(db, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    queue = selection.compute_probe_queue(db, u.id, profile=p, loaded_region_keys=set())
    return u, p, queue


def test_none_phase_is_byte_identical(db_session):
    """E1: `None` (baseline) → output byte-identical to pre-Q112, no `training_phase` key."""
    u, p, queue = _seeded(db_session)
    without_kwarg = selection.select_next(db_session, u.id, profile=p, probe_queue=list(queue))
    with_none = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=None)
    assert with_none == without_kwarg
    assert "training_phase" not in without_kwarg
    assert without_kwarg["budget"] == {"probe": 0.25, "fortify": 0.75}


def test_suppressed_forces_fortify_and_zero_probe_budget(db_session):
    """E2: suppressed → effective probe budget 0, mode fortify; stored 0.25 intact."""
    u, p, queue = _seeded(db_session)
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="suppressed", capacities=None, microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    assert out["mode_recommended"] == "fortify"
    assert out["budget"] == {"probe": 0.0, "fortify": 1.0}
    # T1 — the probe block is withheld entirely under suppression.
    assert out["probe"] is None
    # Standing budget untouched in the store.
    assert profile_mod.get_profile(db_session, u.id).probe_budget == 0.25
    # E5 block present, naming the phase, with review_due.
    assert out["training_phase"]["label"] == "decompression"
    assert out["training_phase"]["probe_posture"] == "suppressed"
    assert out["training_phase"]["review_due"] in (True, False)
    assert any("decompression" in n for n in out["notes"])


def test_held_posture_keeps_probe_budget(db_session):
    u, p, queue = _seeded(db_session)
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="held", capacities=None, microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    assert out["budget"] == {"probe": 0.25, "fortify": 0.75}


def test_capacities_filter_removes_only_never_readmits(db_session):
    """E3: the phase capacity allow-list only ever NARROWS the queue — the surviving probe is
    a member of the unconstrained set and carries the allowed capacity (Q105 resolve-first)."""
    u, p, queue = _seeded(db_session)
    unconstrained = {(c["region_key"], c["side"]) for c in queue}
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="held", capacities=["stability"], microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    if out["probe"] is not None:
        assert (out["probe"]["region_key"], out["probe"]["side"]) in unconstrained
        assert out["probe"]["capacity"] == "stability"


def test_capacities_resolve_before_compare_uppercase_tokens(db_session):
    """Q105: a stored UPPERCASE token must still match the lowercase `.value` the queue
    carries — a verbatim compare would silently empty the queue."""
    u, p, queue = _seeded(db_session)
    stability_exists = any(c["capacity"] == "stability" for c in queue)
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="held", capacities=["STABILITY"], microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    if stability_exists:
        assert out["probe"] is not None
        assert out["probe"]["capacity"] == "stability"


def test_fortify_target_within_phase(db_session):
    """E4: the target (anti_lateral_flexion, a stability region) is never filtered; the block
    records whether the phase's capacities include it."""
    u, p, queue = _seeded(db_session)
    assert taxonomy.by_key("anti_lateral_flexion").capacity is taxonomy.Capacity.STABILITY

    within = phase_mod.open_phase(db_session, u.id, _payload(
        label="a", probe_posture="held", capacities=["stability"], microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=within)
    assert out["training_phase"]["fortify_target_within_phase"] is True
    assert out["fortify"]["target"] == "anti_lateral_flexion"       # still served

    excl = phase_mod.open_phase(db_session, u.id, _payload(
        label="b", probe_posture="held", capacities=["endurance"], microcycle=None))
    out2 = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=excl)
    assert out2["training_phase"]["fortify_target_within_phase"] is False
    assert out2["fortify"]["target"] == "anti_lateral_flexion"      # never dropped
    assert any("standing-vs-now" in n or "disagreement" in n for n in out2["notes"])


def test_null_capacities_target_within_phase_true(db_session):
    u, p, queue = _seeded(db_session)
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="held", capacities=None, microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    assert out["training_phase"]["fortify_target_within_phase"] is True


# ── T1 — probe emission under suppression ────────────────────────────────────

def test_suppressed_withholds_probe_block(db_session):
    """T1: under suppression `probe` is `None` — the phase withheld it — even though the
    queue is non-empty and `has_priority`/the E3 capacity filter still ran over it."""
    u, p, queue = _seeded(db_session)
    assert queue, "fixture precondition: a non-empty probe queue"
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="suppressed", capacities=None, microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    assert out["probe"] is None


def test_held_keeps_probe_block_identical_to_no_phase(db_session):
    """T1: `held` posture leaves the probe block exactly as the no-phase path emits it —
    the emission changes only under suppression."""
    u, p, queue = _seeded(db_session)
    baseline = selection.select_next(db_session, u.id, profile=p, probe_queue=list(queue))
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="held", capacities=None, microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    assert out["probe"] is not None
    assert out["probe"] == baseline["probe"]


# ── T2 — recovery-vehicle re-rank on a suppressed phase ──────────────────────

def test_suppressed_reranks_vehicles_recovery_first(db_session):
    """T2: a suppressed phase fires the same stable two-group re-rank — recovery vehicles
    first (their original relative order preserved), loaded vehicles after (order
    preserved), nothing dropped (#8). Its own reason is surfaced in notes."""
    u, p, queue = _seeded(db_session)
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="suppressed", capacities=None, microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    keys = [v["key"] for v in out["fortify"]["vehicles"]]
    # Seed order was pilates_clinical, offset_carry, unilateral_lifting, swim, hike,
    # barbell_floor_hold → recovery {swim, pilates_clinical, hike} lifted to the front.
    assert keys == ["pilates_clinical", "swim", "hike",
                    "offset_carry", "unilateral_lifting", "barbell_floor_hold"]
    recovery = [k for k in keys if k in selection.RECOVERY_VEHICLES]
    loaded = [k for k in keys if k not in selection.RECOVERY_VEHICLES]
    assert keys == recovery + loaded                        # stable two-group partition
    assert recovery == ["pilates_clinical", "swim", "hike"]  # within-group order preserved
    assert loaded == ["offset_carry", "unilateral_lifting", "barbell_floor_hold"]
    assert any("recovery vehicles ranked first" in n for n in out["notes"])


def test_held_phase_does_not_rerank_vehicles(db_session):
    """T2: `held` posture never triggers the recovery re-rank — the seed's order stands and
    no recovery note is surfaced."""
    u, p, queue = _seeded(db_session)
    phase = phase_mod.open_phase(db_session, u.id, _payload(
        probe_posture="held", capacities=None, microcycle=None))
    out = selection.select_next(
        db_session, u.id, profile=p, probe_queue=list(queue), training_phase=phase)
    keys = [v["key"] for v in out["fortify"]["vehicles"]]
    assert keys == ["pilates_clinical", "offset_carry", "unilateral_lifting",
                    "swim", "hike", "barbell_floor_hold"]
    assert not any("recovery vehicles ranked first" in n for n in out["notes"])


# ── T1 (context_builder) — the suppressed-PROBE line ─────────────────────────

def _selection_stub(**overrides):
    base = {
        "mode_recommended": "fortify",
        "budget": {"probe": 0.0, "fortify": 1.0},
        "fortify": {"target": "anti_lateral_flexion",
                    "target_label": "Anti-lateral flexion",
                    "vehicles": [], "dosing": {"windows": ["Neuromuscular"]}},
        "probe": None,
        "notes": [],
    }
    base.update(overrides)
    return base


def test_section_probe_renders_suppressed_line():
    """T1 (context): probe `None` + an open suppressed phase → the suppressed-PROBE line
    naming the phase, NOT the queue-empty sentence (they are different facts)."""
    from context_builder import _section_probe
    out = _section_probe(_selection_stub(
        training_phase={"label": "decompression", "probe_posture": "suppressed"}))
    assert "- PROBE: suppressed by training phase 'decompression'" in out
    assert "queue empty under current filters" not in out


def test_section_probe_renders_queue_empty_without_suppression():
    """The queue-empty line still renders when probe is genuinely `None` with no suppressing
    phase — no phase block at all, or a `held` one."""
    from context_builder import _section_probe
    out_no_phase = _section_probe(_selection_stub())
    assert "- PROBE: queue empty under current filters" in out_no_phase
    assert "suppressed by training phase" not in out_no_phase

    out_held = _section_probe(_selection_stub(
        training_phase={"label": "aerobic_base", "probe_posture": "held"}))
    assert "- PROBE: queue empty under current filters" in out_held
    assert "suppressed by training phase" not in out_held


# ── local-day (cross-cutting S7) ─────────────────────────────────────────────

def test_local_day_buckets_utc_crossing_to_aest():
    """A late-UTC instant is the NEXT AEST day (+10, no DST). The single-source helper both
    entered_on and resolved_on now use."""
    late = datetime(2026, 9, 9, 23, 30, tzinfo=timezone.utc)   # 09:30 AEST on the 10th
    assert _local_day(late) == date(2026, 9, 10)
    assert _local_day() == datetime.now(timezone.utc).astimezone(
        __import__("pytz").timezone("Australia/Brisbane")).date()


def test_resolve_endpoint_defaults_resolved_on_to_local_day(db_session):
    """S7: resolve_injury with no resolved_on stamps the operator-local day, not Railway UTC."""
    from routers.knowledge import KnowledgeEntryIn, ResolutionIn, resolve_injury, upsert_knowledge_entry

    u = _user(db_session)
    entry = upsert_knowledge_entry(
        u.id,
        KnowledgeEntryIn(type="injury", key="right_hamstring", source="chat",
                         value={"body_part": "right hamstring"}),
        db_session,
    )
    resolved = resolve_injury(entry.id, ResolutionIn(basis="healed", resolved_by="user"),
                              u, db_session)
    assert resolved.value["resolution"]["resolved_on"] == str(_local_day())


# ── the same surface over HTTP ───────────────────────────────────────────────
#
# The engine tests prove the logic; these prove the WIRING — a field validated in
# `engine/training_phase.py` but absent from `PhaseIn` would be silently dropped by
# pydantic and every engine test would still pass. Mirrors test_weekly_template.

from fastapi import FastAPI                          # noqa: E402
from fastapi.testclient import TestClient            # noqa: E402

from auth import get_current_user                    # noqa: E402
from database import get_db                          # noqa: E402
from routers import engine as engine_router          # noqa: E402
from routers import training_phase as phase_router   # noqa: E402


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(phase_router.router)
    app.include_router(engine_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_http_open_get_history_and_close(db_session):
    u = _user(db_session)
    c = _client(db_session, u)

    assert c.get("/engine/phase").json()["training_phase"] is None

    opened = c.post("/engine/phase", json=_payload())
    assert opened.status_code == 201, opened.text
    body = opened.json()["training_phase"]
    assert body["label"] == "decompression"
    assert body["capacities"] == ["mobility", "stability"]     # verbatim
    assert body["review_due"] is False                          # review_on 2026-10-05 > today

    cur = c.get("/engine/phase").json()["training_phase"]
    assert cur["id"] == body["id"]

    closed = c.post("/engine/phase/close", json={"close_reason": "done"})
    assert closed.status_code == 200, closed.text
    assert c.get("/engine/phase").json()["training_phase"] is None

    hist = c.get("/engine/phase/history").json()["history"]
    assert len(hist) == 1 and hist[0]["close_reason"] == "done"


def test_http_open_bad_payload_is_422(db_session):
    u = _user(db_session)
    c = _client(db_session, u)
    r = c.post("/engine/phase", json=_payload(capacities=["cardio"]))
    assert r.status_code == 422, r.text
    assert "unknown capacity" in r.json()["detail"]


def test_http_close_with_nothing_open_is_404(db_session):
    u = _user(db_session)
    c = _client(db_session, u)
    r = c.post("/engine/phase/close", json={"close_reason": "nothing open"})
    assert r.status_code == 404


def test_http_next_injects_the_open_phase(db_session):
    """/engine/next fetches and injects the open phase — a suppressed posture flips the wire
    response to fortify with a probe budget of 0, and the `training_phase` block appears."""
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, dict(profile_mod.LUKE_PROFILE_SEED))
    c = _client(db_session, u)

    # Baseline: no phase → no training_phase block, standing 0.25 budget.
    base = c.get("/engine/next").json()
    assert "training_phase" not in base
    assert base["budget"] == {"probe": 0.25, "fortify": 0.75}

    # A past review_on → review_due True, and the router folds review_on into the block
    # (selection.py never reads it, #228).
    c.post("/engine/phase", json=_payload(probe_posture="suppressed", capacities=None,
                                          microcycle=None, review_on="2026-09-08"))
    withphase = c.get("/engine/next").json()
    assert withphase["mode_recommended"] == "fortify"
    assert withphase["budget"] == {"probe": 0.0, "fortify": 1.0}
    tp = withphase["training_phase"]
    assert tp["label"] == "decompression"
    assert tp["review_on"] == "2026-09-08"       # folded in by the router
    assert tp["review_due"] is True              # 2026-09-08 <= today (2026-09-09+)
