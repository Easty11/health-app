"""The `get_lab_results` MCP tool — a thin text formatter over the #59/#47 read-back.

The tool reuses `routers.labs.get_lab_results` so the #47 withhold (no computed_flag,
no confidence, no is_derived, nothing interpretive) is INHERITED at the projection, not
re-implemented. These tests target the pure formatter `_format_lab_results` over the real
read's output — the `@mcp.tool()` wrapper adds only `_current_user_id()` + a session,
which need a live bearer token and are not the logic under test.

Rows are seeded via direct ORM (mirroring `test_labs_results_readback`) so the withhold
guard can force a `computed_flag`/`confidence` onto storage and prove they never surface.
"""
from datetime import date

import models
from mcp_server import _format_lab_results, _marker_matches
from routers.labs import get_lab_results as read_lab_results


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _report(db, uid, collected, panel="Panel", lab="SN", filename=None, zero=None):
    r = models.LabReport(user_id=uid, lab_name=lab, panel_name_raw=panel,
                         collected_date=collected, source_completeness="x",
                         source="file_extraction", overall_confidence=0.9,
                         source_doc_filename=filename, zero_row_reason=zero)
    db.add(r); db.commit(); db.refresh(r)
    return r


def _result(db, rid, raw, canon=None, value_num=None, value_operator=None,
            value_qualitative=None, unit=None, ref_low=None, ref_high=None,
            ref_low_exclusive=False, ref_high_exclusive=False,
            lab_flag=None, computed_flag=None, confidence=0.95):
    db.add(models.LabResult(
        lab_report_id=rid, marker_name_raw=raw, marker_canonical=canon,
        value_num=value_num, value_operator=value_operator,
        value_qualitative=value_qualitative, unit_canonical=unit,
        ref_low=ref_low, ref_high=ref_high,
        ref_low_exclusive=ref_low_exclusive, ref_high_exclusive=ref_high_exclusive,
        lab_flag=lab_flag, computed_flag=computed_flag, confidence=confidence))
    db.commit()


def _render(db, u, **kw):
    """Seed → real read → pure format, the path the tool takes minus auth/session glue."""
    return _format_lab_results(read_lab_results(current_user=u, db=db), **kw)


# --------------------------------------------------------------------------- #
# (a) a known marker renders with value + unit + ref                          #
# --------------------------------------------------------------------------- #

def test_marker_renders_value_unit_ref_and_header(db_session):
    u = _user(db_session, "render@example.com")
    rep = _report(db_session, u.id, date(2026, 5, 30), panel="Gonadal Hormones",
                  lab="Sullivan Nicolaides", filename="20260530__Gonadal.pdf")
    _result(db_session, rep.id, "Testosterone (total)", "testosterone_total",
            value_num=24.0, unit="nmol/L", ref_low=10.0, ref_high=28.0)

    out = _render(db_session, u)

    assert "=== Gonadal Hormones — 2026-05-30 (Sullivan Nicolaides) ===" in out
    assert "source: 20260530__Gonadal.pdf" in out
    assert "Testosterone (total): 24.0 nmol/L (ref 10.0–28.0)" in out


def test_one_sided_ref_and_operator_and_flag(db_session):
    u = _user(db_session, "onesided@example.com")
    rep = _report(db_session, u.id, date(2026, 5, 30))
    # ceiling-only ref (<21), a lab flag, and a censored value (<0.1 stored as 0.1 with op)
    _result(db_session, rep.id, "Bilirubin", value_num=28.0, unit="umol/L",
            ref_high=21.0, ref_high_exclusive=True, lab_flag="H")
    _result(db_session, rep.id, "hs-Troponin", value_num=0.1, value_operator="<", unit="ng/L")
    _result(db_session, rep.id, "eGFR", value_num=90.0, ref_low=60.0)  # floor-only, no unit

    out = _render(db_session, u)

    assert "Bilirubin: 28.0 umol/L (ref < 21.0) [H]" in out
    assert "hs-Troponin: < 0.1 ng/L" in out
    assert "eGFR: 90.0 (ref > 60.0)" in out


def test_qualitative_value_and_no_ref(db_session):
    u = _user(db_session, "qual@example.com")
    rep = _report(db_session, u.id, date(2026, 5, 30))
    _result(db_session, rep.id, "Urine Culture", value_qualitative="No growth")

    out = _render(db_session, u)
    assert "Urine Culture: No growth" in out
    assert "(ref" not in out  # neither bound → no range decoration


# --------------------------------------------------------------------------- #
# (b) marker= filters                                                         #
# --------------------------------------------------------------------------- #

def test_marker_filter_keeps_only_matching_rows_and_reports(db_session):
    u = _user(db_session, "filter@example.com")
    rep = _report(db_session, u.id, date(2026, 5, 30), panel="Chem")
    _result(db_session, rep.id, "Creatinine", "creatinine", value_num=80.0, unit="umol/L")
    _result(db_session, rep.id, "Sodium", "sodium", value_num=140.0, unit="mmol/L")

    out = _render(db_session, u, marker="creatinine")
    assert "Creatinine: 80.0 umol/L" in out
    assert "Sodium" not in out


def test_marker_filter_matches_urine_via_canonical_and_word_boundary(db_session):
    """"creatinine" must match "R U-Creatinine" (canonical creatinine_urine) — the #180
    markers — via the word-boundary rule, and must NOT match an unrelated substring."""
    u = _user(db_session, "urine@example.com")
    rep = _report(db_session, u.id, date(2026, 8, 4), panel="ACR")
    _result(db_session, rep.id, "R U-Creatinine", "creatinine_urine", value_num=8.6, unit="mmol/L")
    _result(db_session, rep.id, "R U-Albumin/Creat", "albumin_creatinine_ratio_urine",
            value_num=0.6, unit="mg/mmol")

    out = _render(db_session, u, marker="creatinine")
    assert "R U-Creatinine" in out
    # albumin/creat's canonical contains "creatinine" as a word too → also a legitimate hit
    assert "R U-Albumin/Creat" in out

    out2 = _render(db_session, u, marker="sodium")
    assert out2 == "No lab results on file."


def test_marker_matcher_is_word_boundary_not_substring(db_session):
    u = _user(db_session, "wb@example.com")
    rep = _report(db_session, u.id, date(2026, 5, 30))
    _result(db_session, rep.id, "Creatinine", "creatinine", value_num=80.0)
    (row,) = read_lab_results(current_user=u, db=db_session)[0].results
    assert _marker_matches("creat", row) is False   # substring, not a whole word
    assert _marker_matches("creatinine", row) is True
    assert _marker_matches("CREATININE", row) is True  # case-insensitive


# --------------------------------------------------------------------------- #
# limit — most-recent N reports                                               #
# --------------------------------------------------------------------------- #

def test_limit_keeps_most_recent_reports(db_session):
    u = _user(db_session, "limit@example.com")
    for d, panel in [(date(2026, 1, 1), "Oldest"), (date(2026, 3, 1), "Middle"),
                     (date(2026, 6, 1), "Newest")]:
        rep = _report(db_session, u.id, d, panel=panel)
        _result(db_session, rep.id, "Sodium", "sodium", value_num=140.0, unit="mmol/L")

    out = _render(db_session, u, limit=2)
    assert "Newest" in out and "Middle" in out
    assert "Oldest" not in out


# --------------------------------------------------------------------------- #
# zero-row report + empty                                                      #
# --------------------------------------------------------------------------- #

def test_zero_row_report_states_its_reason(db_session):
    u = _user(db_session, "zero@example.com")
    _report(db_session, u.id, date(2026, 5, 30), panel="Graph PDF",
            zero="no_values_extracted")

    out = _render(db_session, u)
    assert "(no rows ingested: no_values_extracted)" in out


def test_empty_is_stated_plainly(db_session):
    u = _user(db_session, "empty@example.com")
    assert _render(db_session, u) == "No lab results on file."


def test_declined_shell_is_suppressed_while_fault_shell_stays(db_session):
    """A re-confirm shell (`all_markers_declined`, no rows) is de-noised from the chat
    read-back; a `no_values_extracted` shell is a genuine fault and still renders; a populated
    report is untouched. The suppression is keyed on the reason, never on row count — the fault
    shell is also zero-row, and hiding it too would be absence-as-emptiness one layer along."""
    u = _user(db_session, "shellfilter@example.com")
    pop = _report(db_session, u.id, date(2026, 5, 30), panel="PSA", filename="psa.pdf")
    _result(db_session, pop.id, "Total PSA", "psa", value_num=0.7, unit="ug/L")
    _report(db_session, u.id, date(2026, 5, 30), panel="PSA", filename="psa.pdf",
            zero="all_markers_declined")
    _report(db_session, u.id, date(2026, 5, 30), panel="Graph", filename="graph.pdf",
            zero="no_values_extracted")

    out = _render(db_session, u)

    assert "all_markers_declined" not in out                 # the re-confirm shell is gone
    assert "(no rows ingested: no_values_extracted)" in out  # the fault stays visible
    assert "Total PSA: 0.7 ug/L" in out                      # populated report untouched


def test_declined_shell_does_not_consume_a_limit_slot(db_session):
    """The shell is dropped BEFORE `limit`, so `limit=1` yields the newest REAL report, not a
    phantom that would otherwise have eaten the slot and shown nothing."""
    u = _user(db_session, "shelllimit@example.com")
    # newest by date is the shell; the real report is older
    _report(db_session, u.id, date(2026, 6, 1), panel="PSA", filename="psa.pdf",
            zero="all_markers_declined")
    rep = _report(db_session, u.id, date(2026, 5, 1), panel="Chem")
    _result(db_session, rep.id, "Sodium", "sodium", value_num=140.0, unit="mmol/L")

    out = _render(db_session, u, limit=1)
    assert "Sodium: 140.0 mmol/L" in out
    assert "all_markers_declined" not in out


# --------------------------------------------------------------------------- #
# (c) #47 withhold guard — string level, belt-and-suspenders over projection  #
# --------------------------------------------------------------------------- #

def test_computed_flag_and_confidence_never_surface(db_session):
    """A row carrying computed_flag='H' and confidence=0.40 must render byte-identically
    to a clean row, and neither the field names nor the leaked values may appear."""
    u = _user(db_session, "withhold@example.com")

    r_clean = _report(db_session, u.id, date(2026, 5, 30), panel="Clean")
    _result(db_session, r_clean.id, "Glucose", "glucose", value_num=5.0, unit="mmol/L")

    r_loaded = _report(db_session, u.id, date(2026, 5, 30), panel="Loaded")
    _result(db_session, r_loaded.id, "Glucose", "glucose", value_num=5.0, unit="mmol/L",
            computed_flag="H", confidence=0.40)

    out = _render(db_session, u)

    # The two Glucose lines are identical — the withheld fields change nothing on screen.
    glucose_lines = [ln for ln in out.splitlines() if ln.startswith("Glucose:")]
    assert len(glucose_lines) == 2
    assert glucose_lines[0] == glucose_lines[1] == "Glucose: 5.0 mmol/L"

    # Field names never appear (they aren't even on the projection).
    assert "computed_flag" not in out
    assert "confidence" not in out
    # The leaked VALUES never surface: no computed [H] flag, no 0.4 confidence number.
    assert "[H]" not in out
    assert "0.4" not in out
