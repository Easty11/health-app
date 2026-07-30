"""Gate-level guard for relation-based demotion of gate 1's delta arm (§4).

The predicate lives in `gates.demoting_relations` and is a DECISION, not an implementation
detail, so every clause of it is pinned here with a control that fails when the clause is
removed. Three constraints bound the authority and each gets a test that puts it under
pressure rather than proving it by absence:

  * §4  — the delta arm only. A non-feedback relation, an unsatisfied precondition, or a
          degraded operand set must not demote.
  * I8  — a `safety_gate.band_change` forces news, non-demotable. Tested PAIRED: the same
          call without the band change demotes, which is what proves the demotion path was
          live rather than unavailable.
  * I5  — gate 2 is untouchable. Structurally out of reach here (this function returns gate
          1 only), so the end-to-end pressure test lives with the producer, where
          `should_surface` reads all three gates.

WHY THE I8 TEST IS UNIT-LEVEL AND NOT END-TO-END: no marker can currently carry both a
safety band and a demotable relation - the asset bands `haematocrit` alone, and the sole
`feedback` relation renders on `lh`/`fsh`. That intersection is CONTINGENT, not structural,
and `test_banded_and_feedback_markers_do_not_yet_intersect` is the tripwire that fires when
it stops being empty.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from interpretation.gates import demoting_relations, news_gate

_REFERENCE = Path(__file__).resolve().parent.parent / "reference"

_FEEDBACK_KEY = "hpg_gonadotropin_suppression"


def _relation(kind="feedback", precondition_status="satisfied", operand_status="complete",
              relation_key=_FEEDBACK_KEY):
    return {"relation_key": relation_key, "kind": kind, "reads": "...",
            "precondition_status": precondition_status, "operand_status": operand_status}


def _delta(magnitude="meaningful", crossed_ref=None, direction="down"):
    return {"direction": direction, "abs_change": -5.0, "pct_change": -60.0,
            "crossed_ref": crossed_ref, "magnitude": magnitude, "censored": False,
            "min_meaningful_delta": {"mode": "relative", "value": 0.30}}


# ---------- the predicate, clause by clause ----------

def test_qualifying_relation_is_selected():
    assert demoting_relations([_relation()]) == [_FEEDBACK_KEY]


@pytest.mark.parametrize("kind", ["ratio", "co_movement", "discriminator", "context"])
def test_non_feedback_kinds_never_demote(kind):
    """The kind restriction. These four carry a narrative `reads` and operand lists and NO
    machine-readable demotion condition, so the producer cannot know whether they hold —
    demoting on one would assert an explanation it never checked."""
    assert demoting_relations([_relation(kind=kind, precondition_status="not_applicable")]) == []


@pytest.mark.parametrize("status", ["not_satisfied", "unresolvable", "not_applicable", None])
def test_only_a_satisfied_precondition_demotes(status):
    """`not_satisfied` means the expected reading does not apply — that is news, not an
    explanation. `unresolvable` means we could not tell, which is never grounds for silence."""
    assert demoting_relations([_relation(precondition_status=status)]) == []


def test_degraded_operands_never_demote():
    """A degraded relation is precisely the case where the producer NAMES what it could not
    see; it cannot simultaneously be a full explanation."""
    assert demoting_relations([_relation(operand_status="degraded")]) == []


def test_no_relations_is_not_a_demotion():
    assert demoting_relations(None) == [] and demoting_relations([]) == []


# ---------- the gate: demotion applies, and names itself ----------

def test_delta_arm_is_demoted_and_names_the_relation():
    out = news_gate(_delta(), relations_rendered=[_relation()])
    assert out["is_news"] is False
    assert out["basis"] == ["delta_meaningful", f"relation_demoted_{_FEEDBACK_KEY}"], \
        "a demotion must name the relation that bought it, or it is indistinguishable " \
        "from a marker that never moved"
    assert set(out) == {"is_news", "basis"}, "return shape is contract surface"


def test_undemoted_delta_arm_is_unchanged_without_relations():
    """Control for the test above: identical delta, no relation -> still news. Without this
    the demotion assertion could be passing on a delta that was never news."""
    out = news_gate(_delta())
    assert out["is_news"] is True and out["basis"] == ["delta_meaningful"]


def test_a_quiet_delta_arm_is_not_touched():
    """Demotion only withdraws an existing news verdict; it never adds a basis token to a
    marker that was already quiet."""
    out = news_gate(_delta(magnitude="within_noise"), relations_rendered=[_relation()])
    assert out["is_news"] is False
    assert out["basis"] == ["delta_within_min_meaningful"]


# ---------- I8 under pressure: demotion AVAILABLE and REFUSED ----------

def test_band_change_survives_an_otherwise_valid_demotion():
    """I8. The demotion path is LIVE here, not unavailable — proven by the paired call below,
    which is the same delta and the same relation minus the band change and DOES demote. So
    this asserts a refusal, not an absence.

    The guarantee is structural: `news_gate` applies demotion before the safety arm, and the
    safety arm re-forces news unconditionally, so no code path lets a demotion outlive a band
    change."""
    delta, relation = _delta(), _relation()

    # control: same inputs, no band change -> demotion happens
    control = news_gate(delta, relations_rendered=[relation])
    assert control["is_news"] is False, "control must demote or the test below is vacuous"

    guarded = news_gate(delta, safety_gate={"band_change": "escalated"},
                        relations_rendered=[relation])
    assert guarded["is_news"] is True, "a band change must survive demotion (I8)"
    assert f"relation_demoted_{_FEEDBACK_KEY}" in guarded["basis"], \
        "the attempted demotion stays recorded — the reader sees both claims"
    assert "safety_band_escalated" in guarded["basis"]


@pytest.mark.parametrize("change", ["entered", "escalated", "de_escalated",
                                    "first_observation_in_band"])
def test_every_band_change_value_survives_demotion(change):
    out = news_gate(_delta(), safety_gate={"band_change": change},
                    relations_rendered=[_relation()])
    assert out["is_news"] is True and f"safety_band_{change}" in out["basis"]


# ---------- clause 1: a reference-bound crossing is never demoted ----------

def test_into_range_crossing_is_never_demoted():
    """The case clause 1 exists for, and the reason it is NOT justified by I5.

    On `into_range` gate 2 goes QUIET (the value is back inside the interval), so I5 offers
    no protection at all here — nothing else would surface this member. `_magnitude` returns
    `meaningful` precisely BECAUSE of the crossing, so an in-phase relation would swallow
    "this marker returned to range", which is real news to a reader whatever the mechanism."""
    out = news_gate(_delta(crossed_ref="into_range"), relations_rendered=[_relation()])
    assert out["is_news"] is True
    assert "crossed_ref_into_range" in out["basis"]
    assert not any(b.startswith("relation_demoted_") for b in out["basis"])


def test_out_of_range_crossing_is_also_not_demoted():
    """The other direction. Here gate 2 WOULD keep the member surfacing regardless, so the
    clause is belt-and-braces rather than load-bearing — recorded so a later reader does not
    mistake this for the case that justifies the clause."""
    out = news_gate(_delta(crossed_ref="out_of_range"), relations_rendered=[_relation()])
    assert out["is_news"] is True
    assert not any(b.startswith("relation_demoted_") for b in out["basis"])


# ---------- first observation: no delta arm to demote ----------

def test_first_observation_is_unaffected_by_relations():
    out = news_gate(None, relations_rendered=[_relation()])
    assert out == {"is_news": False, "basis": ["no_prior_first_observation"]}


def test_first_observation_in_band_still_forces_news_with_relations_present():
    out = news_gate(None, safety_gate={"band_change": "first_observation_in_band"},
                    relations_rendered=[_relation()])
    assert out["is_news"] is True


# ---------- the emptiness tripwire (stands in for an end-to-end I8 test) ----------

def test_banded_and_feedback_markers_do_not_yet_intersect():
    """TRIPWIRE, not an invariant. It records WHY the I8 pressure test above is unit-level:
    no marker can currently carry both a safety band and a demotable relation, so the
    end-to-end version would be vacuous.

    WHEN THIS TEST FAILS, DO NOT RELAX IT. The intersection becoming non-empty means the
    end-to-end I8 test has become constructible — a marker now has both a band and a
    feedback relation. Write that test through `build_foundation` (seed the marker so a
    `band_change` fires while its precondition is satisfied and its operands are complete,
    and assert it still surfaces), then DELETE this test. It exists only to stop the
    unit-level test from silently reading as full coverage after the gap closes."""
    groups = json.loads((_REFERENCE / "marker_groups.json").read_text(encoding="utf-8"))
    thresholds = json.loads((_REFERENCE / "safety_thresholds.json").read_text(encoding="utf-8"))

    banded = set(thresholds["thresholds"])
    feedback_rendered = {marker
                         for group in groups["groups"]
                         for relation in group.get("relations", [])
                         if relation["kind"] == "feedback"
                         for marker in relation.get("render_on", [])}

    assert banded, "no banded marker at all — the tripwire would pass vacuously"
    assert feedback_rendered, "no feedback relation at all — the tripwire would pass vacuously"
    assert banded & feedback_rendered == set(), (
        f"banded and feedback-rendered markers now intersect: "
        f"{sorted(banded & feedback_rendered)}. The end-to-end I8 test is now constructible "
        f"— write it through build_foundation and delete this tripwire."
    )
