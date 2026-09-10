"""GET /series/labs and /series/lab/{canonical} — the lab visuals read surface.

Read-only over lab_reports / lab_results, user-scoped, per-marker. What is proven:
per-point reference ranges (the band steps between draws), censored values marked
(operator carried, never a silent line vertex), the exclusive-flag verdict carried
verbatim from the platform's `computed_flag`, the three exclusion reasons, user
scoping, ascending order, and the index summary.

Rows are built through the ORM directly (the endpoints are pure readers); the marker
map is seeded so raw→canonical resolution and the unmapped-history path are exercised.
"""
from datetime import date

import models
from routers.series import get_lab_index, get_lab_series


def _detail(db, user, canonical=None, from_=None, to=None):
    """Call the detail reader with its Query-defaulted params supplied (the codebase
    test idiom — a direct call bypasses FastAPI's default resolution)."""
    return get_lab_series(canonical or CANON, from_=from_, to=to, current_user=user, db=db)

CANON = "testosterone_total"
RAW = "Testosterone"


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _report(db, uid, collected, lab="Lab A"):
    r = models.LabReport(user_id=uid, lab_name=lab, panel_name_raw="Androgens",
                         collected_date=collected, source_completeness="x",
                         source="file_extraction", overall_confidence=0.9)
    db.add(r); db.commit(); db.refresh(r)
    return r


def _result(db, rid, *, raw=RAW, canon=CANON, value_num=None, operator=None,
            qualitative=None, unit="nmol/L", ref_low=None, ref_high=None,
            ref_low_excl=False, ref_high_excl=False, lab_flag=None, computed_flag=None,
            is_derived=False, confidence=0.95):
    db.add(models.LabResult(
        lab_report_id=rid, marker_name_raw=raw, marker_canonical=canon,
        value_num=value_num, value_operator=operator, value_qualitative=qualitative,
        unit_canonical=unit, ref_low=ref_low, ref_high=ref_high,
        ref_low_exclusive=ref_low_excl, ref_high_exclusive=ref_high_excl,
        lab_flag=lab_flag, computed_flag=computed_flag, is_derived=is_derived,
        confidence=confidence))
    db.commit()


def _seed_marker(db, uid):
    """One marker across six plottable draws + one qualitative + one unmapped +
    one unit-mismatch, so every branch of the reader is exercised by one fixture."""
    # P1 in range (Lab A range 10–30 inclusive)
    r1 = _report(db, uid, date(2026, 1, 1), lab="Lab A")
    _result(db, r1.id, value_num=12.0, ref_low=10.0, ref_high=30.0)
    # P2 out of range, lab-and-computed agree low
    r2 = _report(db, uid, date(2026, 2, 1), lab="Lab A")
    _result(db, r2.id, value_num=8.0, ref_low=10.0, ref_high=30.0, lab_flag="L", computed_flag="L")
    # P3 Lab B, DIFFERENT range (8–28), value AT the exclusive upper bound → H by the
    #    exclusive-flag rule (would be in-range if inclusive). The platform's verdict, carried.
    r3 = _report(db, uid, date(2026, 3, 1), lab="Lab B")
    _result(db, r3.id, value_num=28.0, ref_low=8.0, ref_high=28.0, ref_high_excl=True, computed_flag="H")
    # P4 censored — '<0.3' below range. Carries operator; the bound is not a measurement.
    r4 = _report(db, uid, date(2026, 4, 1), lab="Lab B")
    _result(db, r4.id, value_num=0.3, operator="<", ref_low=8.0, ref_high=28.0, computed_flag="L")
    # P5 low confidence (< 0.85), in range
    r5 = _report(db, uid, date(2026, 5, 1), lab="Lab B")
    _result(db, r5.id, value_num=16.0, ref_low=8.0, ref_high=28.0, confidence=0.40)
    # P6 derived, in range
    r6 = _report(db, uid, date(2026, 6, 1), lab="Lab B")
    _result(db, r6.id, value_num=15.0, ref_low=8.0, ref_high=28.0, is_derived=True)
    # E1 qualitative — no numeric value
    e1 = _report(db, uid, date(2026, 6, 15), lab="Lab B")
    _result(db, e1.id, value_num=None, qualitative="Not detected", unit=None)
    # E2 unmapped — raw name maps to the canonical but this row was never promoted
    e2 = _report(db, uid, date(2026, 6, 20), lab="Lab B")
    _result(db, e2.id, canon=None, value_num=14.0)
    # E3 unit mismatch — pmol/L against the established nmol/L; never converted
    e3 = _report(db, uid, date(2026, 6, 25), lab="Lab B")
    _result(db, e3.id, value_num=500.0, unit="pmol/L")
    return {"r1": r1, "r4": r4, "e1": e1, "e2": e2, "e3": e3}


# ---------- detail: GET /series/lab/{canonical} ----------

def test_points_ascending_with_per_point_ranges(db_session):
    u = _user(db_session, "labser@example.com")
    _seed_marker(db_session, u.id)
    out = _detail(db_session, u)

    assert out.canonical == CANON
    assert out.unit == "nmol/L"
    dates = [p.date for p in out.points]
    assert dates == sorted(dates)  # ascending by collected_date
    assert dates == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1),
                     date(2026, 4, 1), date(2026, 5, 1), date(2026, 6, 1)]
    # Each point carries its OWN range — the two labs disagree, and the band steps because
    # of it. P1 is Lab A's 10–30; P3 is Lab B's 8–28.
    assert (out.points[0].ref_low, out.points[0].ref_high) == (10.0, 30.0)
    assert (out.points[2].ref_low, out.points[2].ref_high) == (8.0, 28.0)


def test_censored_carries_operator_and_bound_never_a_bare_value(db_session):
    u = _user(db_session, "cens@example.com")
    _seed_marker(db_session, u.id)
    out = _detail(db_session, u)
    p = next(p for p in out.points if p.date == date(2026, 4, 1))
    # The operator is what lets the chart draw a hollow marker and BREAK the line here rather
    # than plotting 0.3 as a measurement (D2). The endpoint never hides that it was censored.
    assert p.operator == "<"
    assert p.value == 0.3
    # Every non-censored point has a null operator, so censorship is unambiguous.
    assert [p.operator for p in out.points if p.date != date(2026, 4, 1)] == [None] * 5


def test_exclusive_flag_verdict_is_carried_from_computed_flag(db_session):
    """The chart must not re-derive a verdict. P3 sits AT an exclusive upper bound (28 with
    ref_high_exclusive) — H by the rule, in-range if it were inclusive. The endpoint carries
    the platform's stored computed_flag verbatim alongside the exclusive flag."""
    u = _user(db_session, "excl@example.com")
    _seed_marker(db_session, u.id)
    out = _detail(db_session, u)
    p3 = next(p for p in out.points if p.date == date(2026, 3, 1))
    assert p3.value == p3.ref_high == 28.0
    assert p3.ref_high_exclusive is True
    assert p3.computed_flag == "H"  # exclusive bound ⇒ H, not suppressed as in-range
    p1 = next(p for p in out.points if p.date == date(2026, 1, 1))
    assert p1.computed_flag is None  # in range, both bounds inclusive


def test_derived_and_low_confidence_are_marked_not_dropped(db_session):
    u = _user(db_session, "deriv@example.com")
    _seed_marker(db_session, u.id)
    out = _detail(db_session, u)
    derived = [p for p in out.points if p.is_derived]
    assert [p.date for p in derived] == [date(2026, 6, 1)]
    low = [p for p in out.points if p.confidence < 0.85]
    assert [p.date for p in low] == [date(2026, 5, 1)]


def test_three_exclusion_reasons(db_session):
    u = _user(db_session, "excl2@example.com")
    ids = _seed_marker(db_session, u.id)
    out = _detail(db_session, u)
    by_report = {e.report_id: e.reason for e in out.excluded}
    assert by_report[ids["e1"].id] == "qualitative"
    assert by_report[ids["e2"].id] == "unmapped"
    assert by_report[ids["e3"].id] == "unit_mismatch"
    assert {e.reason for e in out.excluded} == {"qualitative", "unmapped", "unit_mismatch"}
    # Excluded rows never leak into the plottable series.
    excluded_dates = {e.date for e in out.excluded}
    assert excluded_dates.isdisjoint({p.date for p in out.points})


def test_from_to_bounds_collected_date(db_session):
    u = _user(db_session, "range@example.com")
    _seed_marker(db_session, u.id)
    out = _detail(db_session, u, from_=date(2026, 2, 1), to=date(2026, 4, 1))
    assert [p.date for p in out.points] == [date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]


def test_detail_is_user_scoped(db_session):
    a = _user(db_session, "a@example.com")
    b = _user(db_session, "b@example.com")
    ra = _report(db_session, a.id, date(2026, 5, 30))
    rb = _report(db_session, b.id, date(2026, 5, 30))
    _result(db_session, ra.id, value_num=20.0, ref_low=8.0, ref_high=28.0)
    _result(db_session, rb.id, value_num=999.0, ref_low=8.0, ref_high=28.0)
    out = _detail(db_session, a)
    assert [p.value for p in out.points] == [20.0]  # never sees b's 999


def test_unknown_marker_404s(db_session):
    import pytest
    from fastapi import HTTPException
    u = _user(db_session, "u404@example.com")
    with pytest.raises(HTTPException) as ei:
        _detail(db_session, u, canonical="no_such_marker")
    assert ei.value.status_code == 404


# ---------- index: GET /series/labs ----------

def test_index_summarises_marker_newest_first(db_session):
    u = _user(db_session, "idx@example.com")
    _seed_marker(db_session, u.id)
    # a second marker with an older latest draw, to prove ordering (CRP is seeded in conftest)
    r = _report(db_session, u.id, date(2025, 1, 1))
    _result(db_session, r.id, raw="CRP", canon="crp", value_num=1.0, unit="mg/L", ref_high=5.0)

    out = get_lab_index(current_user=u, db=db_session)
    canons = [e.canonical for e in out]
    assert canons[0] == CANON and "crp" in canons  # testosterone (2026 draws) before crp (2025)
    tt = next(e for e in out if e.canonical == CANON)
    assert tt.unit == "nmol/L"
    assert tt.display_name == CANON  # display_name unwired on the seed ⇒ falls back to canonical
    assert tt.any_flagged is True   # P2/P3/P4 carry H/L
    assert tt.latest.date == date(2026, 6, 25)  # newest mapped draw (the unit-mismatch row)
    crp = next(e for e in out if e.canonical == "crp")
    assert crp.any_flagged is False


def test_index_is_user_scoped_and_mapped_only(db_session):
    a = _user(db_session, "ia@example.com")
    b = _user(db_session, "ib@example.com")
    ra = _report(db_session, a.id, date(2026, 5, 30))
    _result(db_session, ra.id, value_num=20.0, ref_low=8.0, ref_high=28.0)
    # b's marker, and an unmapped row for a (no canonical) — neither should appear for a
    rb = _report(db_session, b.id, date(2026, 5, 30))
    _result(db_session, rb.id, value_num=999.0, ref_low=8.0, ref_high=28.0)
    ra2 = _report(db_session, a.id, date(2026, 5, 31))
    _result(db_session, ra2.id, canon=None, raw="Mystery Marker", value_num=1.0)

    out = get_lab_index(current_user=a, db=db_session)
    assert [e.canonical for e in out] == [CANON]  # only a's mapped marker
