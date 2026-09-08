"""POST /interpretation/education-thread (increment 3) — the route, distinct from chat.

The route is user-scoped (it builds the seed from the caller's own interpretation payload),
fails closed with no model key (serves the authored mechanism, deterministic), and returns a
422 structural refusal for an untappable lever — never a bare thread. The model itself is
not exercised here (it is faked in the generator's own tests); with no ANTHROPIC_API_KEY the
route takes the deterministic template path, so this stays keyless in CI.
"""
from datetime import date

import pytest
from fastapi import HTTPException

import models
from interpretation.producer import _citable_lever
from routers.interpretation import _EducationThreadRequest, post_education_thread

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


def _seed_hpg_user(db, email):
    u = _user(db, email)
    prior = _report(db, u.id, date(2026, 1, 7))
    cur = _report(db, u.id, date(2026, 5, 30))
    for rid, o_flag in ((prior.id, None), (cur.id, "H")):
        _res(db, rid, "Oestradiol", "oestradiol", 150.0, lab_flag=o_flag)
        _res(db, rid, "Testosterone", "testosterone_total", 23.0)
        _res(db, rid, "SHBG", "shbg", 30.0)   # an hpg member the lever does NOT act on
    return u


def _req(**kw):
    kw.setdefault("messages", [{"role": "user", "content": "How does this work?"}])
    return _EducationThreadRequest(**kw)


def test_valid_tap_returns_deterministic_mechanism_without_a_key(db_session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # client=None -> template path
    u = _seed_hpg_user(db_session, "ep-ok@example.com")
    out = post_education_thread(body=_req(lever_key=_LEVER, marker_canonical="oestradiol"),
                                current_user=u, db=db_session)
    assert out["lever_key"] == _LEVER
    assert out["source"] == "template"
    assert out["deflected"] is False
    assert out["text"] == _citable_lever(_LEVER)["mechanism_summary"]


def test_uncited_lever_is_a_422_structural_refusal(db_session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    u = _seed_hpg_user(db_session, "ep-refuse@example.com")
    with pytest.raises(HTTPException) as e:
        post_education_thread(body=_req(lever_key="no_such_lever", marker_canonical="oestradiol"),
                              current_user=u, db=db_session)
    assert e.value.status_code == 422


def test_lever_not_acting_on_marker_is_a_422(db_session, monkeypatch):
    """testosterone_substrate_load acts on oestradiol/testosterone_total but NOT shbg, so a
    tap under shbg is not a valid surfacing join — a structural refusal, not a thread."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    u = _seed_hpg_user(db_session, "ep-wrong@example.com")
    with pytest.raises(HTTPException) as e:
        post_education_thread(body=_req(lever_key=_LEVER, marker_canonical="shbg"),
                              current_user=u, db=db_session)
    assert e.value.status_code == 422
