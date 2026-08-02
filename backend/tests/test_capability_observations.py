"""`capability_observations` — validation, append-only, and the §7 boundary
(DECISIONS_LOG #161).

Three gates live here, and the third is the reason the table is allowed to hold
numbers at all: the app may MEASURE, but must not CLEAR. That boundary is enforced
here rather than in prose so a later edit cannot quietly cross it — the same
construction as `tests/test_injury_probes.py`.

The clearance gate carries NEGATIVE CONTROLS: strings it MUST catch. A gate that
cannot fail reports zero forever and is worth less than no gate at all
(FEEDBACK 10, false-green instruments).
"""
import re
from datetime import date, timedelta

import pytest

import models
from engine import observations as obs
from engine import taxonomy
from routers.engine import get_observations


def _user(db, email="obs@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _rec(db, user_id, **kw):
    kw.setdefault("region_key", "ankle_df")
    kw.setdefault("measure_key", "knee_to_wall_cm")
    kw.setdefault("side", taxonomy.SIDE_LEFT)
    kw.setdefault("value", 9.0)
    return obs.record_observation(db, user_id, **kw)


# ── gate 1: writes are validated fail-closed against the taxonomy ─────────────

def test_unknown_region_is_refused(db_session):
    u = _user(db_session)
    with pytest.raises(ValueError, match="unknown region_key"):
        _rec(db_session, u.id, region_key="not_a_region", measure_key="knee_to_wall_cm")


def test_unknown_measure_for_a_real_region_is_refused(db_session):
    """The region exists and IS observable — only the measure key is wrong. This is
    the drift case the measure registry exists to stop."""
    u = _user(db_session)
    with pytest.raises(ValueError, match="unknown measure_key"):
        _rec(db_session, u.id, region_key="ankle_df", measure_key="ankle_rom_deg")


def test_a_region_with_no_declared_measure_is_not_observable(db_session):
    """`hinge` is a real, queue-eligible region with no instrument chosen. Refusing
    it is the correct default, not a gap — and the message says so rather than
    offering an empty list of alternatives."""
    u = _user(db_session)
    assert taxonomy.by_key("hinge") is not None
    assert taxonomy.measures_for("hinge") == ()
    with pytest.raises(ValueError, match="declares no measures"):
        _rec(db_session, u.id, region_key="hinge", measure_key="anything")


def test_side_must_be_legal_for_the_measure(db_session):
    u = _user(db_session)
    with pytest.raises(ValueError, match="side .* is not valid"):
        _rec(db_session, u.id, side="bilateral")   # knee_to_wall is per-side


def test_a_whole_body_instrument_records_bilateral_on_a_per_side_region(db_session):
    """THE case the brief's §8 table got wrong. `deceleration_landing` is
    `per_side=True` — the region is readable per-side — but a trunk-mounted GPS
    unit produces one figure for the athlete and cannot attribute it to a leg.
    Sidedness is the INSTRUMENT's property, so the bilateral write must succeed
    and the per-side write must not."""
    u = _user(db_session)
    assert taxonomy.by_key("deceleration_landing").per_side is True

    row = _rec(db_session, u.id, region_key="deceleration_landing",
               measure_key="peak_decel_ms2", side="bilateral", value=4.2,
               source="catapult", method="session")
    assert row.side == "bilateral" and row.unit == "m/s^2"

    with pytest.raises(ValueError, match="side .* is not valid"):
        _rec(db_session, u.id, region_key="deceleration_landing",
             measure_key="peak_decel_ms2", side="left", value=4.2, source="catapult")


def test_unit_comes_from_the_taxonomy_and_a_mismatch_refuses_rather_than_converts(db_session):
    """A conversion we invented is a value we made up."""
    u = _user(db_session)
    assert _rec(db_session, u.id).unit == "cm"
    with pytest.raises(ValueError, match="does not match the declared unit"):
        _rec(db_session, u.id, unit="mm")


@pytest.mark.parametrize("field,bad", [
    ("method", "eyeballed"), ("source", "fitbit"), ("confidence", "pretty_sure"),
])
def test_enum_fields_are_closed(db_session, field, bad):
    u = _user(db_session)
    with pytest.raises(ValueError, match=f"unknown {field}"):
        _rec(db_session, u.id, **{field: bad})


def test_a_future_measurement_date_is_refused(db_session):
    """It would sort ahead of every real row in `latest()`."""
    u = _user(db_session)
    with pytest.raises(ValueError, match="in the future"):
        _rec(db_session, u.id, observed_on=date.today() + timedelta(days=1))


def test_the_seeded_measures_are_exactly_the_briefed_battery():
    """Narrow-first is a decision, not an oversight — pin it so a later broad
    seeding sweep is a visible change."""
    got = {(r.key, m.key, m.unit) for r in taxonomy.observable_regions() for m in r.measures}
    assert got == {
        ("hip_flexion_pc_length", "aslr_deg", "deg"),
        ("single_leg_hop", "hop_distance_cm", "cm"),
        ("ankle_df", "knee_to_wall_cm", "cm"),
        ("frontal_single_leg_stability", "stance_seconds", "s"),
        ("shoulder_mobility", "er_rom_deg", "deg"),
        ("deceleration_landing", "peak_decel_ms2", "m/s^2"),
        ("change_of_direction", "cod_count", "count"),
    }


# ── gate 2: append-only ───────────────────────────────────────────────────────

def test_the_model_carries_no_updated_at(db_session):
    """Structural, not conventional. `capability_state` has `updated_at` because it
    is overwritten in place; this table must not, or in-place edits become
    expressible and the history stops being one."""
    cols = set(models.CapabilityObservation.__table__.columns.keys())
    assert "updated_at" not in cols
    assert "created_at" in cols and "observed_on" in cols


def test_the_module_exposes_no_update_or_delete_path():
    """A negative control on the API surface itself: if someone adds one, this
    fails rather than the discipline quietly lapsing."""
    banned = [n for n in dir(obs)
              if not n.startswith("_")
              and re.search(r"update|delete|edit|amend|correct|upsert|set_", n)]
    assert banned == []


def test_a_correction_is_a_new_row_and_the_original_survives(db_session):
    u = _user(db_session)
    day = date(2026, 7, 1)
    _rec(db_session, u.id, value=9.0, observed_on=day)
    _rec(db_session, u.id, value=11.5, observed_on=day)

    rows = obs.series(db_session, u.id, region_key="ankle_df",
                      measure_key="knee_to_wall_cm", side=taxonomy.SIDE_LEFT)
    assert [r.value for r in rows] == [9.0, 11.5], "the superseded row must remain in the series"
    assert obs.latest(db_session, u.id, region_key="ankle_df",
                      measure_key="knee_to_wall_cm", side=taxonomy.SIDE_LEFT).value == 11.5


def test_a_correction_backdated_does_not_displace_a_later_real_measurement(db_session):
    """Supersession is `observed_on` first, `created_at` only as the tie-break. A
    correction entered today for June must not become 'current' over a July
    measurement — that would silently rewind the series."""
    u = _user(db_session)
    _rec(db_session, u.id, value=9.0, observed_on=date(2026, 6, 1))
    _rec(db_session, u.id, value=12.0, observed_on=date(2026, 7, 1))
    _rec(db_session, u.id, value=9.4, observed_on=date(2026, 6, 1))   # late correction to June

    assert obs.latest(db_session, u.id, region_key="ankle_df",
                      measure_key="knee_to_wall_cm", side=taxonomy.SIDE_LEFT).value == 12.0


def test_recording_an_observation_does_not_touch_capability_state(db_session):
    """The change is purely additive. The verdict table is written only by the
    adaptation loop."""
    u = _user(db_session)
    _rec(db_session, u.id)
    assert db_session.query(models.CapabilityState).count() == 0


def test_one_users_series_contains_nothing_of_anothers(db_session):
    a, b = _user(db_session, "a@example.com"), _user(db_session, "b@example.com")
    _rec(db_session, a.id, value=9.0)
    _rec(db_session, b.id, value=99.0)
    got = obs.series(db_session, a.id, region_key="ankle_df", measure_key="knee_to_wall_cm")
    assert [r.value for r in got] == [9.0]


# ── gate 3: measurement, never clearance ──────────────────────────────────────

# Clearance-shaped language: a verdict about whether the user may DO something,
# or a graded severity. Deliberately NOT applied to the taxonomy reference text,
# which legitimately quotes the >=90% return-to-sport figure as a documented
# expectation FLAG (taxonomy docstring, "How to read"). The gate is on the
# OBSERVATION read paths, which must not restate it as a finding.
_FORBIDDEN_VERDICT = re.compile(
    r"\b(cleared|clearance|safe to \w+|unsafe|return[ -]to[ -]sport|rts\b|"
    r"severity|grade [0-9ivx]|fit to (?:play|train|return)|"
    r"(?:meets|passes|fails)\b.{0,20}\b(?:criteri|threshold|standard)|"
    r"ready to (?:play|return|compete))",
    re.I,
)


@pytest.mark.parametrize("bad", [
    "Cleared for return to sport.",
    "LSI 94% — meets return-to-sport criteria.",
    "Grade 2 hamstring deficit.",
    "Symmetry within normal limits; safe to sprint.",
    "Not yet fit to play.",
    "Severity: moderate.",
    "Ready to return at full intensity.",
])
def test_clearance_detector_catches_verdicts(bad):
    """NEGATIVE CONTROLS — the gate below is worthless if it cannot bite."""
    assert _FORBIDDEN_VERDICT.search(bad), f"detector missed a clearance: {bad!r}"


@pytest.mark.parametrize("good", [
    "knee_to_wall_cm 9.0 cm, left, observed 2026-07-01",
    "index_pct 91.3; lower_side left",
    "Single-leg hop (distance)",
    "Deceleration / landing control",
])
def test_clearance_detector_permits_measurements(good):
    """The mirror control: a detector that rejects legitimate output would be
    'passed' by simply emitting nothing."""
    assert not _FORBIDDEN_VERDICT.search(good), f"detector false-positived on {good!r}"


def _read_paths_text(db, user_id):
    """Every observation read path, flattened to one string."""
    import json
    payloads = [
        get_observations(region_key="ankle_df", measure_key="knee_to_wall_cm",
                         side=None, since=None, current_user=_Stub(user_id), db=db),
        get_observations(region_key="single_leg_hop", measure_key="hop_distance_cm",
                         side=None, since=None, current_user=_Stub(user_id), db=db),
        obs.symmetry(db, user_id, region_key="single_leg_hop", measure_key="hop_distance_cm"),
        [obs.observation_to_dict(r) for r in obs.series(
            db, user_id, region_key="ankle_df", measure_key="knee_to_wall_cm")],
    ]
    return json.dumps(payloads, default=str)


class _Stub:
    def __init__(self, uid):
        self.id = uid


def test_no_observation_read_path_emits_a_clearance(db_session):
    """THE boundary gate. A populated, asymmetric series — the exact shape that
    tempts a verdict — and no read path may produce one."""
    u = _user(db_session)
    _rec(db_session, u.id, value=8.0, side=taxonomy.SIDE_LEFT)
    _rec(db_session, u.id, value=11.0, side=taxonomy.SIDE_RIGHT)
    for side, val in ((taxonomy.SIDE_LEFT, 150.0), (taxonomy.SIDE_RIGHT, 172.0)):
        _rec(db_session, u.id, region_key="single_leg_hop",
             measure_key="hop_distance_cm", side=side, value=val,
             method="baseline_battery")

    text = _read_paths_text(db_session, u.id)

    # POSITIVE CONTROL — the gate above is green on an empty payload too, so prove
    # the read paths actually returned the seeded series and a computed symmetry
    # before trusting the negative (#103: controls discriminate on identity).
    for token in ("knee_to_wall_cm", "hop_distance_cm", "index_pct", "lower_side", "172.0"):
        assert token in text, f"read paths returned nothing containing {token!r}"

    hit = _FORBIDDEN_VERDICT.search(text)
    assert hit is None, f"a read path emitted clearance-shaped output: {hit.group(0)!r}"


def test_symmetry_returns_a_ratio_and_a_direction_only(db_session):
    """It must not acquire a verdict key. The >=90% comparison is a clearance
    criterion and belongs to a clinician, not to this tier."""
    u = _user(db_session)
    _rec(db_session, u.id, region_key="single_leg_hop", measure_key="hop_distance_cm",
         side=taxonomy.SIDE_LEFT, value=150.0)
    _rec(db_session, u.id, region_key="single_leg_hop", measure_key="hop_distance_cm",
         side=taxonomy.SIDE_RIGHT, value=172.0)

    s = obs.symmetry(db_session, u.id, region_key="single_leg_hop",
                     measure_key="hop_distance_cm")
    assert s["index_pct"] == pytest.approx(87.2, abs=0.1)
    assert s["lower_side"] == taxonomy.SIDE_LEFT
    assert set(s) == {
        "region_key", "measure_key", "unit", "higher_is_better", "left", "right",
        "left_observed_on", "right_observed_on", "as_of", "index_pct", "lower_side",
    }


def test_symmetry_is_none_without_both_sides(db_session):
    """Half a comparison is not a quiet 100% — it is no answer."""
    u = _user(db_session)
    _rec(db_session, u.id, side=taxonomy.SIDE_LEFT, value=9.0)
    assert obs.symmetry(db_session, u.id, region_key="ankle_df",
                        measure_key="knee_to_wall_cm") is None


def test_symmetry_is_none_for_a_whole_body_measure(db_session):
    u = _user(db_session)
    _rec(db_session, u.id, region_key="change_of_direction", measure_key="cod_count",
         side="bilateral", value=41, source="catapult", method="session")
    assert obs.symmetry(db_session, u.id, region_key="change_of_direction",
                        measure_key="cod_count") is None


def test_symmetry_carries_both_collection_dates(db_session):
    """A ratio built from a left measured in March and a right measured in July is
    a comparison across time. The reader must be able to see that."""
    u = _user(db_session)
    _rec(db_session, u.id, side=taxonomy.SIDE_LEFT, value=9.0, observed_on=date(2026, 3, 2))
    _rec(db_session, u.id, side=taxonomy.SIDE_RIGHT, value=10.0, observed_on=date(2026, 7, 4))
    s = obs.symmetry(db_session, u.id, region_key="ankle_df", measure_key="knee_to_wall_cm")
    assert s["left_observed_on"] == "2026-03-02"
    assert s["right_observed_on"] == "2026-07-04"
    assert s["as_of"] == "2026-07-04"
