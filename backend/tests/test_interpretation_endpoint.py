"""GET /interpretation — trigger resolution (#147) and user isolation (#42).

`#42` is DEMONSTRATED, not asserted. A test that greps the source for `user_id ==` proves the
filter was typed, not that it works: the endpoint reaches the database through three separate
reads (the panel queries, `marker_series`, and `current_state` via the protocol snapshot), and a
leak in any one of them would still leave the other two looking correct. So a second user is
seeded with DIFFERENT markers at a DIFFERENT date, and the assertion is that neither user's output
contains anything of the other's.
"""
from datetime import date

import models
from routers.interpretation import get_interpretation
import pytest
from fastapi import HTTPException


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _report(db, user_id, collected, panel="Panel"):
    r = models.LabReport(
        user_id=user_id, lab_name="Lab", panel_name_raw=panel, collected_date=collected,
        source_completeness="sonic_dx_extract", source="file_extraction", overall_confidence=0.99,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _result(db, report_id, raw, canonical, value):
    db.add(models.LabResult(lab_report_id=report_id, marker_name_raw=raw,
                            marker_canonical=canonical, value_num=value, confidence=0.99))
    db.commit()


def _markers(out):
    found = {m["marker_canonical"] for g in out["groups"] for m in g["members"]}
    return found | {r["marker_canonical"] for r in out["ungrouped"]}


# ---------- #42 ----------

def test_one_users_interpretation_contains_nothing_of_anothers(db_session):
    """THE isolation gate. Two users, disjoint markers, disjoint draw dates."""
    a = _user(db_session, "a@example.com")
    b = _user(db_session, "b@example.com")

    a1 = _report(db_session, a.id, date(2026, 1, 7), "A-prior")
    a2 = _report(db_session, a.id, date(2026, 5, 30), "A-current")
    _result(db_session, a1.id, "AST", "ast", 40.0)
    _result(db_session, a2.id, "AST", "ast", 47.0)

    b1 = _report(db_session, b.id, date(2025, 3, 3), "B-prior")
    b2 = _report(db_session, b.id, date(2025, 9, 9), "B-current")
    _result(db_session, b1.id, "Ferritin", "ferritin", 100.0)
    _result(db_session, b2.id, "Ferritin", "ferritin", 181.0)

    out_a = get_interpretation(current_user=a, db=db_session)
    out_b = get_interpretation(current_user=b, db=db_session)

    assert _markers(out_a) == {"ast"}, "user A's output leaked a marker it does not own"
    assert _markers(out_b) == {"ferritin"}, "user B's output leaked a marker it does not own"

    # the panel envelope is user-scoped too — a leaked trigger date would mis-date the whole read
    assert out_a["meta"]["trigger_panel"]["collected"] == "2026-05-30"
    assert out_a["meta"]["compared_against"]["collected"] == "2026-01-07"
    assert out_b["meta"]["trigger_panel"]["collected"] == "2025-09-09"
    assert out_b["meta"]["compared_against"]["collected"] == "2025-03-03"


def test_a_users_newest_draw_is_not_shadowed_by_a_newer_draw_of_anothers(db_session):
    """NON-VACUITY for the test above. B's draw is NEWER than A's, so an unscoped
    `MAX(collected_date)` would resolve A's trigger to B's date and the isolation test would
    still pass on markers alone. This is the ordering that catches it."""
    a = _user(db_session, "a2@example.com")
    b = _user(db_session, "b2@example.com")

    a1 = _report(db_session, a.id, date(2026, 1, 7))
    _result(db_session, a1.id, "AST", "ast", 40.0)

    b1 = _report(db_session, b.id, date(2026, 12, 25))   # strictly newer than anything A has
    _result(db_session, b1.id, "Ferritin", "ferritin", 100.0)

    out_a = get_interpretation(current_user=a, db=db_session)
    assert out_a["meta"]["trigger_panel"]["collected"] == "2026-01-07"
    assert _markers(out_a) == {"ast"}


# ---------- #147 trigger resolution ----------

def test_the_trigger_is_a_draw_not_a_report(db_session):
    """#147 — one draw prints several reports sharing a date. All of them must contribute to the
    same interpretation rather than the newest report alone becoming the panel."""
    u = _user(db_session, "draw@example.com")
    old = _report(db_session, u.id, date(2026, 1, 7), "Old")
    _result(db_session, old.id, "AST", "ast", 40.0)
    _result(db_session, old.id, "Ferritin", "ferritin", 90.0)

    r1 = _report(db_session, u.id, date(2026, 5, 30), "Chemistry")
    r2 = _report(db_session, u.id, date(2026, 5, 30), "Haematinics")
    _result(db_session, r1.id, "AST", "ast", 47.0)
    _result(db_session, r2.id, "Ferritin", "ferritin", 181.0)

    out = get_interpretation(current_user=u, db=db_session)
    assert _markers(out) == {"ast", "ferritin"}, \
        "both reports from the triggering draw must contribute, not just one"
    assert out["meta"]["trigger_panel"]["collected"] == "2026-05-30"


def test_the_comparison_is_the_next_distinct_date_back(db_session):
    """Not the next report — two reports from one draw must not compare against each other."""
    u = _user(db_session, "cmp@example.com")
    _report(db_session, u.id, date(2026, 5, 30), "Same-draw A")
    r2 = _report(db_session, u.id, date(2026, 5, 30), "Same-draw B")
    _result(db_session, r2.id, "AST", "ast", 47.0)
    old = _report(db_session, u.id, date(2026, 1, 7), "Older")
    _result(db_session, old.id, "AST", "ast", 40.0)

    out = get_interpretation(current_user=u, db=db_session)
    assert out["meta"]["compared_against"]["collected"] == "2026-01-07"


# ---------- edges ----------

def test_a_user_with_no_reports_gets_404_not_an_empty_object(db_session):
    """An empty interpretation is indistinguishable from a broken one."""
    u = _user(db_session, "empty@example.com")
    with pytest.raises(HTTPException) as e:
        get_interpretation(current_user=u, db=db_session)
    assert e.value.status_code == 404


def test_a_single_draw_is_a_first_ever_panel_not_an_error(db_session):
    """One draw is a legitimate state — the producer's first_ever_panel path."""
    u = _user(db_session, "first@example.com")
    r = _report(db_session, u.id, date(2026, 5, 30))
    _result(db_session, r.id, "AST", "ast", 47.0)

    out = get_interpretation(current_user=u, db=db_session)
    assert out["meta"]["first_ever_panel"] is True
    assert out["meta"]["compared_against"] is None
    row = next(m for g in out["groups"] for m in g["members"] if m["marker_canonical"] == "ast")
    assert row["news_gate"]["basis"] == ["no_prior_first_observation"]
