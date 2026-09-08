"""Eval: seed-is-scoped (#49 lock, increment 3 step 4).

The seed carries EXACTLY marker + mechanism + why-surfaced + protocol context, and nothing
else — no full personal-context leak, no other markers. This is the #49 lock as a gate: a
future change that widens the seed (a general-context sweep, a sibling marker's result,
another lever) is caught here.

Built against a REAL payload that contains OTHER markers (a ferritin draw alongside the HPG
panel), so "no other markers" is a live assertion, not a vacuous one.
"""
import json
from datetime import date

import models
from interpretation.education_seed import SEED_KEYS, build_education_seed
from interpretation.producer import _SNAPSHOT_FIELDS
from routers.interpretation import _resolve_payload

_LEVER = "testosterone_substrate_load"
# canonical keys of OTHER markers present in the payload — none may appear in the seed.
_OTHER_MARKER_KEYS = ["ferritin", "shbg", "testosterone_total", "testosterone_free_calculated"]


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _report(db, user_id, collected):
    r = models.LabReport(user_id=user_id, lab_name="Lab", panel_name_raw="Panel",
                         collected_date=collected, source_completeness="sonic_dx_extract",
                         source="file_extraction", overall_confidence=0.99)
    db.add(r); db.commit(); db.refresh(r)
    return r


def _res(db, report_id, raw, canonical, value, lab_flag=None):
    db.add(models.LabResult(lab_report_id=report_id, marker_name_raw=raw,
                            marker_canonical=canonical, value_num=value,
                            lab_flag=lab_flag, confidence=0.99))
    db.commit()


def _payload_with_other_markers(db):
    u = _user(db, "scoped@example.com")
    prior = _report(db, u.id, date(2026, 1, 7))
    cur = _report(db, u.id, date(2026, 5, 30))
    for rid, o_flag in ((prior.id, None), (cur.id, "H")):
        _res(db, rid, "Oestradiol", "oestradiol", 150.0, lab_flag=o_flag)
        _res(db, rid, "Testosterone", "testosterone_total", 23.0)
        _res(db, rid, "SHBG", "shbg", 30.0)
        _res(db, rid, "Ferritin", "ferritin", 120.0)   # a marker in NEITHER the tap nor the lever
    return _resolve_payload(db, u)


def test_seed_carries_only_the_locked_four_and_no_other_marker(db_session):
    payload = _payload_with_other_markers(db_session)
    result = build_education_seed(payload, _LEVER, "oestradiol")
    assert result.ok, result.refusal
    seed = result.seed

    # 1. exactly the #49-locked top-level keys
    assert set(seed) == SEED_KEYS == {"lever_key", "marker", "mechanism", "why_surfaced", "protocol_context"}

    # 2. the marker block is identity only — the tapped marker, no sibling
    assert seed["marker"]["marker_canonical"] == "oestradiol"

    # 3. no OTHER marker's canonical key appears anywhere in the seed
    blob = json.dumps(seed, default=str)
    for key in _OTHER_MARKER_KEYS:
        assert key not in blob, f"seed leaked another marker: {key}"

    # 4. why-surfaced is this marker's own gates + the tapped lever's effect only
    assert set(seed["why_surfaced"]) == {"delta", "news_gate", "range_gate", "safety_gate", "lever_effect"}
    assert seed["why_surfaced"]["lever_effect"]["lever_key"] == _LEVER

    # 5. protocol context is the declared-state snapshot — factors carry ONLY snapshot fields,
    #    never a lab value or a marker result (that is the general-context leak this guards)
    ctx = seed["protocol_context"]
    if ctx is not None:
        assert set(ctx) <= {"as_of", "factors"}
        for factor in ctx.get("factors", []):
            assert set(factor) <= set(_SNAPSHOT_FIELDS)
    assert "value_num" not in blob  # no raw lab-result value ever enters the seed
