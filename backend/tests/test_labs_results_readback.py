"""GET /labs/results — the #59 read-back consumer.

Raw values/ranges/lab-flags only (#47): computed_flag, confidence, and anything
interpretive are withheld at the projection. User-scoped (#42). Grouped by report,
newest collected_date first. confirm_lab_report is exercised as the writer so the
read-back is tested against real stored rows, not hand-built ORM objects.
"""
from datetime import date

import models
from routers.labs import get_lab_results


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _report(db, uid, collected, panel="Panel", lab="SN"):
    r = models.LabReport(user_id=uid, lab_name=lab, panel_name_raw=panel,
                         collected_date=collected, source_completeness="x",
                         source="file_extraction", overall_confidence=0.9)
    db.add(r); db.commit(); db.refresh(r)
    return r


def _result(db, rid, raw, canon=None, value_num=None, unit=None, lab_flag=None,
            computed_flag=None, confidence=0.95):
    db.add(models.LabResult(lab_report_id=rid, marker_name_raw=raw, marker_canonical=canon,
                            value_num=value_num, unit_canonical=unit, lab_flag=lab_flag,
                            computed_flag=computed_flag, confidence=confidence))
    db.commit()


def test_results_grouped_by_report_newest_first(db_session):
    u = _user(db_session, "rb@example.com")
    r_old = _report(db_session, u.id, date(2026, 1, 7), panel="Androgens")
    r_new = _report(db_session, u.id, date(2026, 5, 30), panel="Gonadal Hormones")
    _result(db_session, r_old.id, "Testosterone (total)", "testosterone_total", 22.5, "nmol/L")
    _result(db_session, r_new.id, "Testosterone (total)", "testosterone_total", 24.0, "nmol/L")
    _result(db_session, r_new.id, "FSH", "fsh", 0.1, "IU/L", lab_flag="L")

    out = get_lab_results(current_user=u, db=db_session)

    assert [rep.collected_date for rep in out] == [date(2026, 5, 30), date(2026, 1, 7)]  # newest first
    newest = out[0]
    assert newest.panel_name_raw == "Gonadal Hormones"
    assert {r.marker_name_raw for r in newest.results} == {"Testosterone (total)", "FSH"}
    fsh = next(r for r in newest.results if r.marker_name_raw == "FSH")
    assert fsh.value_num == 0.1 and fsh.unit_canonical == "IU/L" and fsh.lab_flag == "L"


def test_readback_withholds_computed_flag_and_confidence_I47(db_session):
    """#47: the read-back is values / ranges / LAB-asserted flags only. A row stored
    with a computed_flag and a confidence must expose NEITHER in the projection."""
    u = _user(db_session, "bound@example.com")
    rep = _report(db_session, u.id, date(2026, 5, 30))
    _result(db_session, rep.id, "AST", "ast", 99.0, "U/L", lab_flag=None,
            computed_flag="H", confidence=0.40)

    out = get_lab_results(current_user=u, db=db_session)
    row = out[0].results[0]
    dumped = row.model_dump()
    assert "computed_flag" not in dumped, "computed_flag leaked into the read-back (V2 withhold / #47)"
    assert "confidence" not in dumped, "extraction confidence leaked into the read-back (#47)"
    assert row.lab_flag is None  # lab asserted nothing; the computed H is not surfaced
    assert set(dumped) == {"marker_name_raw", "marker_canonical", "value_num", "value_operator",
                           "value_qualitative", "unit_canonical", "ref_low", "ref_high",
                           "ref_low_exclusive", "ref_high_exclusive", "lab_flag"}


def test_results_are_user_scoped_I42(db_session):
    a = _user(db_session, "a@example.com")
    b = _user(db_session, "b@example.com")
    ra = _report(db_session, a.id, date(2026, 5, 30))
    rb = _report(db_session, b.id, date(2026, 5, 30))
    _result(db_session, ra.id, "AST", "ast", 20.0, "U/L")
    _result(db_session, rb.id, "AST", "ast", 999.0, "U/L")

    out_a = get_lab_results(current_user=a, db=db_session)
    assert len(out_a) == 1
    assert out_a[0].results[0].value_num == 20.0  # never sees b's 999


def test_no_reports_returns_empty_list(db_session):
    u = _user(db_session, "empty@example.com")
    assert get_lab_results(current_user=u, db=db_session) == []
