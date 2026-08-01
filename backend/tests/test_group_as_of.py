"""Group-level as-of (`#159` rule 1, derivation fixed by `#160`).

The producer emits the date rather than leaving the view to derive it: a consumer that computed
`min(member dates)` itself would be a second source of truth, which is the same defect
`sections.js` had when it recomputed moved-ness from the gates instead of reading
`should_surface`.

Current side ONLY. The prior side spanning draws is `Q71`, and these tests pin that boundary so a
later "improvement" that folds prior dates in fails here rather than silently resolving part of a
question it does not address.
"""
from datetime import date

import models
from interpretation.producer import _group_as_of, build_foundation


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


def _group(out, key):
    return next(g for g in out["groups"] if g["group_key"] == key)


# ---------- the derivation, in isolation ----------

def test_a_coherent_group_reports_one_date_not_a_degenerate_range():
    members = [{"current": {"collected": "2026-03-06"}}, {"current": {"collected": "2026-03-06"}}]
    assert _group_as_of(members) == {
        "earliest": "2026-03-06", "latest": "2026-03-06", "spans_draws": False}


def test_a_spanning_group_reports_the_range_and_says_it_spans():
    members = [{"current": {"collected": "2026-05-30"}}, {"current": {"collected": "2026-01-07"}}]
    assert _group_as_of(members) == {
        "earliest": "2026-01-07", "latest": "2026-05-30", "spans_draws": True}


def test_no_members_with_a_current_date_yields_None():
    """None, not an empty range — the view omits the block rather than rendering a blank date."""
    assert _group_as_of([]) is None
    assert _group_as_of([{"current": None}]) is None


# ---------- the boundary that Q71 depends on ----------

def test_the_as_of_ignores_the_prior_side_entirely(db_session):
    """CURRENT-ONLY, asserted against a group whose prior side genuinely spans.

    This mirrors live `hpg_axis`: every current value from one draw, priors from three different
    draws. A both-sides derivation would report `spans_draws: True` and mislabel a group whose
    CONTENTS are coherent. It would also mark part of `Q71` resolved by a decision that does not
    address comparison intervals at all."""
    u = _user(db_session, "prior-span@example.com")
    old_a = _report(db_session, u.id, date(2026, 1, 7))
    old_b = _report(db_session, u.id, date(2026, 4, 20))
    cur = _report(db_session, u.id, date(2026, 5, 30))

    # priors land on two different draws...
    _result(db_session, old_a.id, "LH", "lh", 1.0)
    _result(db_session, old_b.id, "Testosterone", "testosterone_total", 22.0)
    # ...currents share one
    _result(db_session, cur.id, "LH", "lh", 0.5)
    _result(db_session, cur.id, "Testosterone", "testosterone_total", 24.0)

    out = build_foundation(u.id, db_session, trigger_panel=cur, prior_panel=old_b)
    hpg = _group(out, "hpg_axis")

    priors = {m["prior"]["collected"] for m in hpg["members"] if m.get("prior")}
    assert len(priors) > 1, "the fixture must actually span on the prior side, or this is vacuous"
    assert hpg["as_of"] == {
        "earliest": "2026-05-30", "latest": "2026-05-30", "spans_draws": False}


def test_a_group_off_the_trigger_draw_is_visible_from_the_output_alone(db_session):
    """The live `hepatocellular` case: the whole group current at an older draw than the trigger.
    The view's label is driven by comparing this against `meta.trigger_panel.collected`, so both
    must be present and must differ."""
    u = _user(db_session, "stale-group@example.com")
    march = _report(db_session, u.id, date(2026, 3, 6), "Liver")
    may = _report(db_session, u.id, date(2026, 5, 30), "PSA")
    for raw, canon, v in [("AST", "ast", 47.0), ("ALT", "alt", 53.0)]:
        _result(db_session, march.id, raw, canon, v)
    _result(db_session, may.id, "Total PSA", "psa", 0.7)

    out = build_foundation(u.id, db_session, trigger_panel=may, prior_panel=march)
    liver = _group(out, "hepatocellular")

    assert out["meta"]["trigger_panel"]["collected"] == "2026-05-30"
    assert liver["as_of"]["latest"] == "2026-03-06"
    assert liver["as_of"]["latest"] != out["meta"]["trigger_panel"]["collected"]


def test_every_group_carries_an_as_of(db_session):
    """A field present on some groups and absent on others reads as a rendering fault."""
    u = _user(db_session, "allgroups@example.com")
    r = _report(db_session, u.id, date(2026, 5, 30))
    for raw, canon, v in [("AST", "ast", 47.0), ("Haemoglobin", "haemoglobin", 153.0)]:
        _result(db_session, r.id, raw, canon, v)

    out = build_foundation(u.id, db_session, trigger_panel=r, prior_panel=None)
    assert out["groups"], "non-vacuity — an empty group list would pass the loop below"
    for g in out["groups"]:
        assert g["as_of"] is not None, f"{g['group_key']} carries no as_of"
