"""Series-integrity guard at confirm (#156).

The gate model's invariants are conditional on the series being correct, and nothing tested
that. `I8` guarantees a `band_change` cannot be DEMOTED (#153 made that hold by construction);
it does not guarantee a band change is DETECTED. A duplicated newest episode gives
`marker_series` two same-draw rows at rn=1 and rn=2, drops the true earlier prior, resolves
both bands identically and returns `band_change: None` — so the safety arm never fires and the
marker reads as flat and quiet.

The consequence test below is the point of this file: it asserts the BAND CHANGE survives a
re-upload, not merely that a row was rejected. A test that asserted only "the row was rejected"
would prove the mechanism and nothing about why it exists.

`confirm_lab_report` is called directly with an explicit user + db, bypassing the auth
dependency — the same pattern as `test_labs_confirm_confidence.py`.
"""
from datetime import date, datetime

import models
from interpretation.producer import build_foundation
from routers.labs import (
    ExtractionResult, ReportDates, ReportEnvelope, ReportExtractionMeta,
    ResultItem, confirm_lab_report,
)

_E1 = datetime(2026, 1, 7, 9, 0, 0)    # older episode
_E2 = datetime(2026, 5, 30, 9, 0, 0)   # newest episode


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _envelope(collected, panel, results):
    return ExtractionResult(
        report=ReportEnvelope(
            lab_name="Sullivan Nicolaides", panel_name_raw=panel,
            dates=ReportDates(collected=collected),
            source_completeness="sonic_dx_extract",
            extraction=ReportExtractionMeta(extracted_at=collected, model="test"),
        ),
        results=results,
    )


def _hct(value):
    return ResultItem(marker_name_raw="Haematocrit", value_num=value,
                      ref_low=0.40, ref_high=0.54)


def _confirm(db, user, collected, panel, results, on_duplicate="skip"):
    return confirm_lab_report(_envelope(collected, panel, results),
                              on_duplicate=on_duplicate, current_user=user, db=db)


def _hct_member(db, user, trigger, prior):
    out = build_foundation(user.id, db, trigger, prior)
    return next(m for g in out["groups"] for m in g["members"]
                if m["marker_canonical"] == "haematocrit")


# ---------- the consequence: a band change survives a re-upload ----------

def test_reupload_does_not_mask_the_band_change(db_session):
    """THE reason this guard exists, asserted end to end.

    0.515 (`watch`) -> 0.530 (`elevated`) is an ESCALATION. It is constructed so the safety
    arm is the only possible source of news: both draws sit inside the lab's 0.40-0.54
    interval (gate 2 quiet) and +2.9% is under haematocrit's authored 8%
    min_meaningful_delta (delta arm quiet).

    Re-uploading the newest episode is then attempted. Without the guard, `marker_series`
    would take the duplicate and the original as current/prior, drop the 2026-01-07 draw, and
    return `band_change: None` — verified empirically before this guard was written. With it,
    the duplicate row is not written and the band change still resolves against the TRUE
    prior."""
    user = _user(db_session, "mask@example.com")
    _confirm(db_session, user, _E1, "Haematology", [_hct(0.515)])
    r2 = _confirm(db_session, user, _E2, "Haematology", [_hct(0.530)])

    trigger = db_session.get(models.LabReport, r2.lab_report_id)
    prior = db_session.query(models.LabReport).filter(
        models.LabReport.collected_date == date(2026, 1, 7)).one()

    before = _hct_member(db_session, user, trigger, prior)
    assert before["safety_gate"]["band_change"] == "escalated"
    assert before["news_gate"]["is_news"] is True
    assert "safety_band_escalated" in before["news_gate"]["basis"]

    # the re-upload: same collection date, same marker, a second document
    dup = _confirm(db_session, user, _E2, "Full Blood Count", [_hct(0.530)])
    assert len(dup.duplicates) == 1
    assert dup.duplicates[0].marker == "haematocrit"
    assert dup.duplicates[0].action == "skipped"
    assert dup.result_count == 0, "the colliding row must not be written"

    after = _hct_member(db_session, user, trigger, prior)
    assert after["safety_gate"]["band_change"] == "escalated", \
        "the band change must still resolve against the TRUE prior, not the duplicate"
    assert after["news_gate"]["is_news"] is True
    assert "safety_band_escalated" in after["news_gate"]["basis"]


def test_the_masking_is_real_when_the_guard_is_bypassed(db_session):
    """NON-VACUITY for the test above. `keep_both` writes the duplicate, and the masking then
    occurs exactly as described — band_change None, is_news False, the marker reading as flat.

    Without this, the test above could be passing because the scenario never masked anything.
    This is the control that proves the guard is load-bearing rather than decorative."""
    user = _user(db_session, "bypass@example.com")
    _confirm(db_session, user, _E1, "Haematology", [_hct(0.515)])
    r2 = _confirm(db_session, user, _E2, "Haematology", [_hct(0.530)])
    trigger = db_session.get(models.LabReport, r2.lab_report_id)
    prior = db_session.query(models.LabReport).filter(
        models.LabReport.collected_date == date(2026, 1, 7)).one()

    dup = _confirm(db_session, user, _E2, "Full Blood Count", [_hct(0.530)],
                   on_duplicate="keep_both")
    assert dup.duplicates[0].action == "written" and dup.result_count == 1

    masked = _hct_member(db_session, user, trigger, prior)
    assert masked["safety_gate"]["band_change"] is None, "the masking must reproduce here"
    assert masked["news_gate"]["is_news"] is False
    assert masked["news_gate"]["basis"] == ["flat_vs_prior"]


# ---------- the guard must not be a blanket reject ----------

def test_a_clean_second_panel_from_the_same_draw_ingests(db_session):
    """G3. Two panels from ONE draw is `#147`'s expected shape and must ingest untouched:
    different analytes, same collection date, no collision, both rows written.

    A guard that passed its tests by rejecting everything would be an outage, not a guard —
    so this is asserted alongside the rejection cases rather than assumed."""
    user = _user(db_session, "twopanel@example.com")
    first = _confirm(db_session, user, _E2, "Haematology", [_hct(0.48)])
    second = _confirm(db_session, user, _E2, "Androgens", [
        ResultItem(marker_name_raw="Testosterone", value_num=24.0, unit_canonical="nmol/L"),
    ])
    assert first.duplicates == [] and second.duplicates == []
    assert first.result_count == 1 and second.result_count == 1


def test_one_collision_does_not_fail_the_rest_of_the_upload(db_session):
    """A collision on one marker never fails the whole upload: the report is still created
    (the document genuinely exists — #155 retain-raw) and every non-colliding row is written."""
    user = _user(db_session, "partial@example.com")
    _confirm(db_session, user, _E2, "Haematology", [_hct(0.48)])
    second = _confirm(db_session, user, _E2, "Full Blood Count", [
        _hct(0.48),                                                       # collides
        ResultItem(marker_name_raw="Haemoglobin", value_num=155.0),       # does not
    ])
    assert len(second.duplicates) == 1 and second.duplicates[0].marker == "haematocrit"
    assert second.result_count == 1, "the non-colliding row still lands"
    assert db_session.get(models.LabReport, second.lab_report_id) is not None
    stored = {r.marker_name_raw for r in db_session.query(models.LabResult)
              .filter(models.LabResult.lab_report_id == second.lab_report_id).all()}
    assert stored == {"Haemoglobin"}


# ---------- the null-canonical path (G4) ----------

def test_unmapped_markers_are_guarded_by_their_raw_label(db_session):
    """G4. `marker_canonical` is nullable, so a canonical-only key would leave unmapped rows
    unguarded — and under `#155`'s retroactive promotion a duplicated unmapped raw becomes a
    duplicated SERIES the moment the marker is promoted, long after the upload that caused it.
    The key falls back to the raw label, so the gap is closed rather than documented."""
    user = _user(db_session, "unmapped@example.com")
    junk = ResultItem(marker_name_raw="Totally Unknown Analyte", value_num=1.0)
    first = _confirm(db_session, user, _E2, "Chemistry", [junk])
    assert first.unmapped == ["Totally Unknown Analyte"] and first.result_count == 1

    second = _confirm(db_session, user, _E2, "Chemistry (repeat)", [junk])
    assert len(second.duplicates) == 1
    assert second.duplicates[0].marker == "Totally Unknown Analyte"
    assert second.duplicates[0].marker_canonical is None
    assert second.result_count == 0


def test_the_same_marker_twice_in_one_submission_is_caught(db_session):
    """The `(lab_report_id, marker_name_raw)` constraint catches an identical raw label
    repeated in one report; it does NOT catch two different raw labels resolving to one
    canonical id. The in-batch check does."""
    user = _user(db_session, "inbatch@example.com")
    res = _confirm(db_session, user, _E2, "Haematology", [
        ResultItem(marker_name_raw="Haematocrit", value_num=0.48),
        ResultItem(marker_name_raw="HCT", value_num=0.48),
    ])
    canonical_hits = [d for d in res.duplicates if d.marker_canonical == "haematocrit"]
    if canonical_hits:                       # both labels map to one canonical id
        assert res.result_count == 1
    else:                                    # "HCT" is not a synonym in the map
        assert res.result_count == 2 and "HCT" in res.unmapped


# ---------- a different collection date is not a collision ----------

def test_the_same_marker_at_a_different_date_is_never_a_collision(db_session):
    """The key is per collection date. A genuine second draw is exactly what the series needs
    and must never be mistaken for a re-upload — this is the delta arm's whole substrate."""
    user = _user(db_session, "series@example.com")
    a = _confirm(db_session, user, _E1, "Haematology", [_hct(0.48)])
    b = _confirm(db_session, user, _E2, "Haematology", [_hct(0.53)])
    assert a.duplicates == [] and b.duplicates == []
    assert a.result_count == 1 and b.result_count == 1
