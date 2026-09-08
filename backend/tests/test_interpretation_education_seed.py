"""Education seed builder (increment 3 step 1, #49) — built against a REAL producer payload.

The seed is read from `build_foundation`'s output, so these tests seed a real HPG panel,
build the payload through the same `_resolve_payload` the endpoint uses, and assert the
seed's scoping and its structural refusals against it — never a hand-mocked payload, so a
producer shape change that would break the seed is caught here.
"""
from datetime import date

import models
from interpretation.education_seed import SEED_KEYS, build_education_seed
from interpretation.producer import _citable_lever
from routers.interpretation import _resolve_payload

# testosterone_substrate_load acts on oestradiol (raises) and testosterone_total; it is
# I1-cited in the asset. shbg is an hpg member the lever does NOT act on.
_LEVER = "testosterone_substrate_load"


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _report(db, user_id, collected):
    r = models.LabReport(user_id=user_id, lab_name="Lab", panel_name_raw="HPG",
                         collected_date=collected, source_completeness="sonic_dx_extract",
                         source="file_extraction", overall_confidence=0.99)
    db.add(r); db.commit(); db.refresh(r)
    return r


def _res(db, report_id, raw, canonical, value, lab_flag=None):
    db.add(models.LabResult(lab_report_id=report_id, marker_name_raw=raw,
                            marker_canonical=canonical, value_num=value,
                            lab_flag=lab_flag, confidence=0.99))
    db.commit()


def _hpg_payload(db, email):
    """A surfaced HPG panel: oestradiol flagged high on the current draw (gate 2 surfaces
    the group), plus testosterone_total and shbg present so the lever's members exist."""
    u = _user(db, email)
    prior = _report(db, u.id, date(2026, 1, 7))
    cur = _report(db, u.id, date(2026, 5, 30))
    for rid, o_flag in ((prior.id, None), (cur.id, "H")):
        _res(db, rid, "Oestradiol", "oestradiol", 150.0, lab_flag=o_flag)
        _res(db, rid, "Testosterone", "testosterone_total", 23.0)
        _res(db, rid, "SHBG", "shbg", 30.0)
    return _resolve_payload(db, u)


def test_valid_tap_builds_a_scoped_seed(db_session):
    payload = _hpg_payload(db_session, "seed-ok@example.com")
    result = build_education_seed(payload, _LEVER, "oestradiol")
    assert result.ok, result.refusal
    seed = result.seed
    assert set(seed) == SEED_KEYS
    assert seed["lever_key"] == _LEVER
    assert seed["marker"]["marker_canonical"] == "oestradiol"
    # mechanism is the authored asset projection, not generated
    node = _citable_lever(_LEVER)
    assert seed["mechanism"]["mechanism_summary"] == node["mechanism_summary"]
    assert seed["mechanism"]["citations"] == list(node["evidence_refs"])
    # why-surfaced is the producer's own effect for THIS marker (raises), read not recomputed
    assert seed["why_surfaced"]["lever_effect"] == {
        "lever_key": _LEVER, "direction": "raises", "grade": seed["why_surfaced"]["lever_effect"]["grade"]}
    # protocol context is the panel-dated snapshot (may be empty of factors, never absent-key)
    assert "protocol_context" in seed


def test_uncited_or_absent_lever_refuses(db_session):
    payload = _hpg_payload(db_session, "seed-uncited@example.com")
    result = build_education_seed(payload, "no_such_lever", "oestradiol")
    assert not result.ok
    assert "cited" in result.refusal


def test_lever_that_does_not_act_on_the_marker_refuses(db_session):
    """testosterone_substrate_load is cited and surfaces in the group, but it does not act
    on shbg — tapping it under shbg is not a valid surfacing join."""
    payload = _hpg_payload(db_session, "seed-wrongmarker@example.com")
    result = build_education_seed(payload, _LEVER, "shbg")
    assert not result.ok
    assert "does not act on" in result.refusal


def test_marker_not_in_interpretation_refuses(db_session):
    payload = _hpg_payload(db_session, "seed-nomarker@example.com")
    result = build_education_seed(payload, _LEVER, "ferritin")
    assert not result.ok
    assert "not in the interpretation" in result.refusal
