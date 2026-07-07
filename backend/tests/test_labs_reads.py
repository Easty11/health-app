"""
Tests for the shared latest-per-marker lab read (backend/reads/labs_reads.py)
and its two consumers (current_state.labs, context_builder's #60-firewall
render section).

(a) latest-per-marker partition on COALESCE(marker_canonical, marker_name_raw)
(b) user isolation — a second user's results never leak into the partition
(c) derived-staleness flag fires only when a derived row is older than the
    latest panel's collected_date
(d) context_builder's lab section withholds computed_flag/interpretation and
    renders unmapped markers as availability-only
(e) standing render withholds value/unit/ref entirely (#60 re-scope) — value
    only relays via the on-ask path, which itself withholds interpretation
"""
from datetime import date

import models
from reads.labs_reads import find_marker, latest_lab_results
from context_builder import _section_labs, render_asked_lab_value


def _make_user(db, email):
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_report(db, user_id, collected_date, panel_name="Routine Chemistry"):
    report = models.LabReport(
        user_id=user_id,
        lab_name="Test Lab",
        panel_name_raw=panel_name,
        collected_date=collected_date,
        source_completeness="unknown",
        source="file_extraction",
        overall_confidence=1.0,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _make_result(db, report_id, marker_name_raw, marker_canonical=None, value_num=None,
                  is_derived=False, lab_flag=None, computed_flag=None, unit_canonical=None,
                  ref_low=None, ref_high=None):
    result = models.LabResult(
        lab_report_id=report_id,
        marker_name_raw=marker_name_raw,
        marker_canonical=marker_canonical,
        is_derived=is_derived,
        value_num=value_num,
        lab_flag=lab_flag,
        computed_flag=computed_flag,
        unit_canonical=unit_canonical,
        ref_low=ref_low,
        ref_high=ref_high,
        confidence=1.0,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


# ---------- (a) latest-per-marker on COALESCE(canonical, raw) ----------

def test_missing_backfill_double_counts_a_pre_bump_marker(db_session):
    """Demonstrates the exact failure mode the backfill rider (step 0) guards
    against: the read never re-resolves canonicalisation (GUARD), so a raw-only
    row and a canonical-keyed row for the SAME real marker partition as two
    distinct COALESCE keys until the backfill UPDATE runs."""
    user = _make_user(db_session, "a@example.com")

    older = _make_report(db_session, user.id, date(2026, 1, 1))
    newer = _make_report(db_session, user.id, date(2026, 6, 1))

    # Pre-#57-bump row: raw name only, marker_canonical NULL (as it would be
    # pre-backfill for a marker whose canonical mapping didn't exist yet).
    _make_result(db_session, older.id, "Testosterone", marker_canonical=None, value_num=10.0)
    # Post-bump row for the SAME real-world marker, now canonical-keyed.
    _make_result(db_session, newer.id, "Testosterone", marker_canonical="testosterone_total", value_num=12.0)

    rows = latest_lab_results(user.id, db_session)
    matching = [r for r in rows if r.marker_name_raw == "Testosterone" or r.marker_canonical == "testosterone_total"]
    assert len(matching) == 2  # the bug, absent a backfill


def test_backfill_collapses_pre_and_post_bump_rows_to_one(db_session):
    """Post-backfill gate: after applying the same UPDATE
    backfill_marker_canonical.py runs, the pre-bump raw-only row and the
    post-bump canonical-keyed row collapse to exactly one latest-per-marker
    row (the newer report wins)."""
    user = _make_user(db_session, "a2@example.com")

    older = _make_report(db_session, user.id, date(2026, 1, 1))
    newer = _make_report(db_session, user.id, date(2026, 6, 1))

    _make_result(db_session, older.id, "Testosterone", marker_canonical=None, value_num=10.0)
    _make_result(db_session, newer.id, "Testosterone", marker_canonical="testosterone_total", value_num=12.0)

    # Apply the backfill (same predicate as backfill_marker_canonical.py).
    db_session.query(models.LabResult).filter(
        models.LabResult.marker_name_raw == "Testosterone",
        models.LabResult.marker_canonical.is_(None),
    ).update({"marker_canonical": "testosterone_total"})
    db_session.commit()

    rows = latest_lab_results(user.id, db_session)
    matching = [r for r in rows if r.marker_canonical == "testosterone_total"]
    assert len(matching) == 1
    assert matching[0].value_num == 12.0
    assert matching[0].collected_date == date(2026, 6, 1)


def test_latest_per_marker_picks_most_recent_report(db_session):
    user = _make_user(db_session, "b@example.com")

    r1 = _make_report(db_session, user.id, date(2026, 1, 1))
    r2 = _make_report(db_session, user.id, date(2026, 3, 1))
    r3 = _make_report(db_session, user.id, date(2026, 6, 1))

    _make_result(db_session, r1.id, "Sodium", marker_canonical="sodium", value_num=138.0)
    _make_result(db_session, r2.id, "Sodium", marker_canonical="sodium", value_num=140.0)
    _make_result(db_session, r3.id, "Sodium", marker_canonical="sodium", value_num=141.0)

    rows = latest_lab_results(user.id, db_session)
    sodium = [r for r in rows if r.marker_canonical == "sodium"]
    assert len(sodium) == 1
    assert sodium[0].value_num == 141.0
    assert sodium[0].collected_date == date(2026, 6, 1)


# ---------- (b) user isolation ----------

def test_cross_user_results_do_not_leak(db_session):
    user_a = _make_user(db_session, "c@example.com")
    user_b = _make_user(db_session, "d@example.com")

    report_a = _make_report(db_session, user_a.id, date(2026, 6, 1))
    report_b = _make_report(db_session, user_b.id, date(2026, 6, 1))

    _make_result(db_session, report_a.id, "Sodium", marker_canonical="sodium", value_num=138.0)
    _make_result(db_session, report_b.id, "Sodium", marker_canonical="sodium", value_num=999.0)

    rows_a = latest_lab_results(user_a.id, db_session)
    assert len(rows_a) == 1
    assert rows_a[0].value_num == 138.0


# ---------- (c) derived staleness ----------

def test_derived_row_older_than_latest_panel_is_flagged_stale(db_session):
    user = _make_user(db_session, "e@example.com")

    older_panel = _make_report(db_session, user.id, date(2026, 1, 1))
    latest_panel = _make_report(db_session, user.id, date(2026, 6, 1))

    _make_result(db_session, older_panel.id, "eGFR", marker_canonical="egfr",
                 value_num=90.0, is_derived=True)
    _make_result(db_session, latest_panel.id, "Sodium", marker_canonical="sodium", value_num=140.0)

    rows = latest_lab_results(user.id, db_session)
    rendered = _section_labs(rows)

    assert "stale" in rendered
    egfr_line = next(l for l in rendered.splitlines() if "egfr" in l)
    assert "stale" in egfr_line


def test_derived_row_matching_latest_panel_is_not_flagged_stale(db_session):
    user = _make_user(db_session, "f@example.com")

    latest_panel = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, latest_panel.id, "eGFR", marker_canonical="egfr",
                 value_num=90.0, is_derived=True)
    _make_result(db_session, latest_panel.id, "Sodium", marker_canonical="sodium", value_num=140.0)

    rows = latest_lab_results(user.id, db_session)
    rendered = _section_labs(rows)

    assert "stale" not in rendered


# ---------- (d) render-policy firewall ----------

def test_render_withholds_computed_flag_and_shows_lab_flag_only(db_session):
    user = _make_user(db_session, "g@example.com")
    report = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, report.id, "Bilirubin", marker_canonical="bilirubin_total",
                 value_num=28.0, lab_flag="H", computed_flag="H")

    rows = latest_lab_results(user.id, db_session)
    rendered = _section_labs(rows)

    assert "[H, lab-asserted]" in rendered
    assert "computed_flag" not in rendered
    # the literal computed_flag VALUE should not leak either, beyond the
    # lab-asserted flag rendered above (same value here would be a false
    # negative, so assert the withheld field name never appears verbatim)
    assert "computed" not in rendered.lower()


def test_render_unmapped_marker_shows_availability_only(db_session):
    user = _make_user(db_session, "h@example.com")
    report = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, report.id, "Some New Marker", marker_canonical=None, value_num=5.0)

    rows = latest_lab_results(user.id, db_session)
    rendered = _section_labs(rows)

    assert "Some New Marker: available, unmapped" in rendered
    assert "5.0" not in rendered


# ---------- (e) standing render withholds value; on-ask path relays it ----------

def test_standing_render_withholds_value_unit_and_ref(db_session):
    user = _make_user(db_session, "i@example.com")
    report = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, report.id, "Bilirubin", marker_canonical="bilirubin_total",
                 value_num=28.0, unit_canonical="umol/L", ref_low=None, ref_high=21.0, lab_flag="H")

    rows = latest_lab_results(user.id, db_session)
    rendered = _section_labs(rows)

    assert "bilirubin_total" in rendered
    assert "[H, lab-asserted]" in rendered
    assert "28.0" not in rendered
    assert "umol/L" not in rendered
    assert "21.0" not in rendered


def test_find_marker_matches_raw_name_and_canonical(db_session):
    user = _make_user(db_session, "j@example.com")
    report = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, report.id, "Calculated Free Testosterone",
                 marker_canonical="testosterone_free_calculated", value_num=250.0)
    _make_result(db_session, report.id, "Sodium", marker_canonical="sodium", value_num=140.0)

    rows = latest_lab_results(user.id, db_session)

    by_raw = find_marker(rows, "what's my sodium level?")
    assert by_raw is not None
    assert by_raw.marker_canonical == "sodium"

    by_canonical_spaced = find_marker(rows, "what's my testosterone_free_calculated?".replace("_", " "))
    assert by_canonical_spaced is not None
    assert by_canonical_spaced.marker_canonical == "testosterone_free_calculated"

    assert find_marker(rows, "how was my workout today?") is None


def test_render_asked_lab_value_relays_value_and_ref_but_no_interpretation(db_session):
    user = _make_user(db_session, "k@example.com")
    report = _make_report(db_session, user.id, date(2026, 6, 1))
    _make_result(db_session, report.id, "Bilirubin", marker_canonical="bilirubin_total",
                 value_num=28.0, unit_canonical="umol/L", ref_high=21.0, lab_flag="H", computed_flag="H")

    rows = latest_lab_results(user.id, db_session)
    row = find_marker(rows, "what's my bilirubin?")
    assert row is not None

    rendered = render_asked_lab_value(row)

    assert "28.0" in rendered
    assert "umol/L" in rendered
    assert "21.0" in rendered
    assert "Metrics page" in rendered  # temporary route pointer (#60)
    assert "computed" not in rendered.lower()
    assert "delta" not in rendered.lower()
    assert "axis" not in rendered.lower()
    assert "lever" not in rendered.lower()
