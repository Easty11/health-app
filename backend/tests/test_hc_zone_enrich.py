"""HC zone enrichment (`hc_zone_enrich`, Q159 stage 2, G1) on the FK-enforced SQLite substrate.

Covers the DB half: which samples a row may use (same writer only), which HRmax applies (dated),
what is written and what is left alone, and what the metabolic transform and arbitration then do
with the zoned rows — including the 28 Sep reference bout (HC `fi.polar.polarflow` row 88,
HC Garmin row 89, `polar_v4` row 91) that must stay ONE canonical bout, depositing once.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import null

import hc_zone_enrich
import hr_zones
import load_events_metabolic
import models
from reads import aerobic_reads
from reads.aerobic_reads import arbitrate, arbitrated_sessions

GARMIN = "com.garmin.android.apps.connectmobile"
SHEALTH = "com.sec.android.app.shealth"
POLAR_FLOW = "fi.polar.polarflow"


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


# RHR 0 reduces Karvonen (% of HRmax - RHR) to the retired %HRmax arithmetic exactly, so every bpm
# expectation below (written against 173 / 190) still pins the fill under the per-class model. The
# Polar-branch and LTHR-class tests at the end use real anchors.
RHR0 = 0


def _hrmax(db, uid, eff, bpm, prov="observed", rhr=RHR0):
    """An HRmax row and, unless `rhr=None`, an RHR anchor of the same date (the `hrr` basis needs both)."""
    db.add(models.UserHrmax(user_id=uid, effective_from=eff, hrmax_bpm=bpm, provenance=prov, note="t"))
    if rhr is not None and not db.query(models.UserHrAnchor).filter_by(user_id=uid, kind="rhr", effective_from=eff).first():
        db.add(models.UserHrAnchor(user_id=uid, kind="rhr", effective_from=eff, bpm=rhr, provenance="stated", note="t"))
    db.commit()


def _anchor(db, uid, kind, eff, bpm, prov="stated", **kw):
    db.add(models.UserHrAnchor(user_id=uid, kind=kind, effective_from=eff, bpm=bpm, provenance=prov, note="t", **kw))
    db.commit()


def _row(db, uid, ssid, start, stop, *, pkg=GARMIN, sport="Walking", source="health_connect", **kw):
    if source == "health_connect":
        # A stage-1 HC row: z* are SQL NULL (the ingest's null()), not the column default 0.
        for z in ("z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds"):
            kw.setdefault(z, null())
    r = models.AerobicSession(
        user_id=uid, source=source, source_session_id=ssid,
        session_date=kw.pop("session_date", (start + timedelta(hours=10)).date()),
        start_time=start, stop_time=stop, sport_name=sport,
        duration_minutes=(stop - start).total_seconds() / 60.0,
        source_package=pkg if source == "health_connect" else None, **kw)
    db.add(r)
    db.commit()
    return r


def _samples(db, uid, pkg, start, step_s, bpms):
    db.add_all(models.HrSample(
        user_id=uid, sample_time=start + timedelta(seconds=step_s * i), bpm=b,
        source="health_connect", source_package=pkg) for i, b in enumerate(bpms))
    db.commit()


def _fresh(db, row):
    db.expire_all()
    return db.get(models.AerobicSession, row.id)


def _zones(r):
    return (r.z1_seconds, r.z2_seconds, r.z3_seconds, r.z4_seconds, r.z5_seconds)


S = _utc(2026, 9, 27, 6, 0, 0)
E = S + timedelta(minutes=10)


# ---- the basic fill ---------------------------------------------------------------------------

def test_a_covered_row_is_zoned_and_gets_hr_avg_and_hr_max(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [120] * 59 + [150])          # 120/173=69% z2; 150=86.7% z4
    out = hc_zone_enrich.enrich_user(db_session, 1)
    r = _fresh(db_session, row)
    assert out["zoned"] == 1 and out["reasons"]["none"] == 1 and out["changed"] == 1
    assert _zones(r) == (0, 590, 0, 10, 0)
    assert r.hr_max == 150 and r.hr_avg == round((120 * 590 + 150 * 10) / 600)


def test_a_second_run_changes_nothing(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)
    hc_zone_enrich.enrich_user(db_session, 1)
    before = _zones(_fresh(db_session, row))
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["changed"] == 0 and _zones(_fresh(db_session, row)) == before


# ---- same-writer rule ----------------------------------------------------------------------------

def test_ring_hr_inside_a_garmin_bout_is_ignored(db_session):
    """Samsung-written HR (the ring) lying inside a Garmin-recorded bout never zones it — and when
    the Garmin writer has too little of its own, the row is withheld, not rescued by the ring."""
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E, pkg=GARMIN)
    _samples(db_session, 1, SHEALTH, S, 10, [150] * 60)                  # perfect coverage, wrong writer
    out = hc_zone_enrich.enrich_user(db_session, 1)
    r = _fresh(db_session, row)
    assert out["reasons"]["no_same_writer_hr"] == 1 and out["zoned"] == 0
    assert _zones(r) == (None,) * 5 and r.hr_avg is None and r.hr_max is None


def test_the_ring_cannot_dilute_or_inflate_the_garmin_zones(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E, pkg=GARMIN)
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)                   # z2
    _samples(db_session, 1, SHEALTH, S, 10, [172] * 60)                  # would be z5 — must not count
    hc_zone_enrich.enrich_user(db_session, 1)
    r = _fresh(db_session, row)
    assert _zones(r) == (0, 600, 0, 0, 0) and r.hr_max == 120


def test_a_row_with_no_writer_falls_back_to_the_unknown_sentinel(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "u1", S, E, pkg="unknown")
    row.source_package = None
    db_session.commit()
    _samples(db_session, 1, "unknown", S, 10, [120] * 60)
    assert hc_zone_enrich.enrich_user(db_session, 1)["zoned"] == 1


# ---- dated HRmax -----------------------------------------------------------------------------------

def test_a_session_before_and_after_a_new_hrmax_zones_differently(db_session):
    """Same HR on both days; HRmax 173 from 1 Jun, 190 from 28 Sep. The earlier session keeps the
    old value in force; the later one uses the new — and a later recompute does not move either."""
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    _hrmax(db_session, 1, date(2026, 9, 28), 190)
    before = _row(db_session, 1, "b", S, E, session_date=date(2026, 9, 27))
    after_s = S + timedelta(days=1)
    after = _row(db_session, 1, "a", after_s, after_s + timedelta(minutes=10), session_date=date(2026, 9, 28))
    _samples(db_session, 1, GARMIN, S, 10, [140] * 60)
    _samples(db_session, 1, GARMIN, after_s, 10, [140] * 60)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, before)) == (0, 0, 0, 600, 0)       # 140/173 = 80.9% -> z4
    assert _zones(_fresh(db_session, after)) == (0, 0, 600, 0, 0)        # 140/190 = 73.7% -> z3
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, before)) == (0, 0, 0, 600, 0)


def test_a_new_hrmax_reflows_history_on_the_next_run(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E, session_date=date(2026, 9, 27))
    _samples(db_session, 1, GARMIN, S, 10, [140] * 60)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, row)) == (0, 0, 0, 600, 0)
    _hrmax(db_session, 1, date(2026, 9, 1), 190)                          # a NEW row; the old stays
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["changed"] == 1 and _zones(_fresh(db_session, row)) == (0, 0, 600, 0, 0)
    assert db_session.query(models.UserHrmax).count() == 2                # nothing edited or removed


def test_no_anchor_in_force_leaves_the_row_in_its_stage_one_state_and_is_counted(db_session):
    _user(db_session)
    _user(db_session, 4)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)                          # user 4 has none
    r1 = _row(db_session, 1, "g1", S, E)
    r4 = _row(db_session, 4, "g4", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)
    _samples(db_session, 4, GARMIN, S, 10, [120] * 60)
    assert hc_zone_enrich.enrich_user(db_session, 1)["zoned"] == 1
    out4 = hc_zone_enrich.enrich_user(db_session, 4)
    r = _fresh(db_session, r4)
    assert out4["reasons"]["no_anchor"] == 1 and out4["zoned"] == 0
    assert _zones(r) == (None,) * 5 and r.hr_avg is None
    assert _zones(_fresh(db_session, r1)) != (None,) * 5                  # user 1 unaffected


def test_a_session_before_the_first_effective_date_is_no_anchor(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 9, 28), 173)
    row = _row(db_session, 1, "g1", S, E, session_date=date(2026, 9, 27))
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)
    assert hc_zone_enrich.enrich_user(db_session, 1)["reasons"]["no_anchor"] == 1
    assert _zones(_fresh(db_session, row)) == (None,) * 5


# ---- over-ceiling: flagged, HRmax unchanged -----------------------------------------------------------

def test_over_ceiling_is_counted_and_listed_and_hrmax_is_never_raised(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [150] * 30 + [181] + [150] * 29)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["over_ceiling"] == 1
    assert out["over_ceiling_rows"] == [{"id": row.id, "date": row.session_date.isoformat(),
                                         "hr_max": 181, "hrmax_in_force": 173}]
    hm = db_session.query(models.UserHrmax).all()
    assert [(h.hrmax_bpm, h.provenance) for h in hm] == [(173, "observed")]      # unchanged
    assert _fresh(db_session, row).z5_seconds >= 10                              # the 181 credits z5


# ---- late HR fills on a later run; demotion; implausible ------------------------------------------------

def test_late_hr_fills_on_a_later_run(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E)
    first = hc_zone_enrich.enrich_user(db_session, 1)
    assert first["reasons"]["no_same_writer_hr"] == 1 and _zones(_fresh(db_session, row)) == (None,) * 5
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)                    # the HR arrives afterwards
    second = hc_zone_enrich.enrich_user(db_session, 1)
    assert second["zoned"] == 1 and _zones(_fresh(db_session, row)) == (0, 600, 0, 0, 0)


def test_a_row_that_stops_qualifying_returns_to_its_stage_one_state(db_session):
    """Recompute is two-way: if a row no longer zones (here: its samples are gone) it is withheld
    again, z*/hr_avg/hr_max NULL — never a stale zone split under a changed input."""
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)
    hc_zone_enrich.enrich_user(db_session, 1)
    db_session.query(models.HrSample).delete()
    db_session.commit()
    out = hc_zone_enrich.enrich_user(db_session, 1)
    r = _fresh(db_session, row)
    assert out["reasons"]["no_same_writer_hr"] == 1
    assert _zones(r) == (None,) * 5 and r.hr_avg is None and r.hr_max is None


def test_implausible_samples_are_dropped_and_counted_across_the_run(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    _row(db_session, 1, "g1", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [0, 255] + [120] * 58)
    assert hc_zone_enrich.enrich_user(db_session, 1)["dropped_implausible"] == 2


# ---- what the step does NOT touch -----------------------------------------------------------------------

def test_it_writes_only_zone_fields_and_never_arbitration_inputs_or_a_polar_row_without_a_trace(db_session):
    _user(db_session)
    _user(db_session, 2)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    hc = _row(db_session, 1, "g1", S, E)
    polar = _row(db_session, 1, "p1", S, E, source="polar_v4", z1_seconds=1, z2_seconds=2, z3_seconds=3,
                 z4_seconds=4, z5_seconds=5, hr_avg=140, hr_max=170)
    other = _row(db_session, 2, "g2", S, E)                               # another user's row
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)
    _samples(db_session, 2, GARMIN, S, 10, [120] * 60)
    snap = lambda r: (r.source, r.source_package, r.source_session_id, r.start_time, r.stop_time,
                      r.session_date, r.sport_name, r.duration_minutes, r.user_id)
    hc_before, polar_before = snap(hc), (snap(polar), _zones(polar), polar.hr_avg, polar.hr_max)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert snap(_fresh(db_session, hc)) == hc_before
    p = _fresh(db_session, polar)
    assert (snap(p), _zones(p), p.hr_avg, p.hr_max) == polar_before
    assert _zones(_fresh(db_session, other)) == (None,) * 5               # not user 2's run


def test_rows_without_a_usable_interval_are_counted_not_classified(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    r = _row(db_session, 1, "g1", S, E)
    r.stop_time = None
    db_session.commit()
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["skipped_no_interval"] == 1 and sum(out["reasons"].values()) == 0


def test_every_reason_key_is_always_present_in_the_report(db_session):
    _user(db_session)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert set(out["reasons"]) == {"sparse", "no_same_writer_hr", "no_anchor", "none"}
    assert out["rows"] == 0 and out["zoned"] == 0


# ---- the tier states (call 1, S0(a)(ii)) -------------------------------------------------------------------

def test_a_wholly_sub_band_row_writes_zeros_and_sits_at_tier_one_with_no_deposit(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [70] * 60)                     # 70 < 50% of 173
    hc_zone_enrich.enrich_user(db_session, 1)
    r = _fresh(db_session, row)
    assert _zones(r) == (0, 0, 0, 0, 0) and r.hr_avg == 70 and r.hr_max == 70
    assert aerobic_reads._has_usable_zones(r) is False                    # INV-7: nothing to score
    assert aerobic_reads._data_tier(r) == 1                               # #356: HR present, no zones
    ev = load_events_metabolic.compute_metabolic_load_events(db_session, 1)
    assert ev["events_written"] == 0 and ev["sessions_skipped_no_zones"] == 1


def test_a_zoned_row_is_tier_two_and_a_legacy_wiped_row_is_tier_one_until_the_chain_restores_it(db_session):
    """S2 means a re-sync no longer wipes z* (tested in test_hc_hr_ingest). The state the OLD
    UPDATE produced — z* NULL, hr_avg kept — is still reachable, so both ends are asserted: it is
    tier 1, and the next chain run returns it to tier 2."""
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    row = _row(db_session, 1, "g1", S, E)
    _samples(db_session, 1, GARMIN, S, 10, [120] * 60)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert aerobic_reads._data_tier(_fresh(db_session, row)) == 2
    r = _fresh(db_session, row)
    r.z1_seconds = r.z2_seconds = r.z3_seconds = r.z4_seconds = r.z5_seconds = None   # the legacy wipe
    db_session.commit()
    assert aerobic_reads._data_tier(_fresh(db_session, row)) == 1
    hc_zone_enrich.enrich_user(db_session, 1)
    assert aerobic_reads._data_tier(_fresh(db_session, row)) == 2


# ---- deposits ------------------------------------------------------------------------------------------------

def test_a_zoned_hc_walk_deposits_trimp_with_no_sport_exclusion(db_session):
    """#322 S2: no sport exclusion in the metabolic transform. A zoned HC Walking row deposits."""
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    walk_end = S + timedelta(minutes=50)
    row = _row(db_session, 1, "w1", S, walk_end, sport="Walking")
    _samples(db_session, 1, GARMIN, S, 10, [110] * 300)                   # 110/173 = 63.6% -> z2
    hc_zone_enrich.enrich_user(db_session, 1)
    ev = load_events_metabolic.compute_metabolic_load_events(db_session, 1)
    assert ev["events_written"] == 1
    le = db_session.query(models.LoadEvent).filter_by(source_ref=str(row.id)).one()
    assert le.load == pytest.approx(50 * 2)                               # 50 min x Edwards weight 2
    assert le.provenance["zone_source"] == "health_connect" and le.provenance["sport_name"] == "Walking"


# ---- the 28 Sep reference bout -------------------------------------------------------------------------------

def _reference_bout(db):
    """Rows 88 (HC fi.polar.polarflow, 1 s H10), 89 (HC Garmin, ~7 s wrist), 91 (polar_v4, Polar-zoned)."""
    start88, stop88 = _utc(2026, 9, 28, 5, 42, 31), _utc(2026, 9, 28, 6, 16, 16)
    start89, stop89 = _utc(2026, 9, 28, 5, 44, 18), _utc(2026, 9, 28, 6, 17, 2)
    r88 = _row(db, 1, "88", start88, stop88, pkg=POLAR_FLOW, sport="Elliptical", session_date=date(2026, 9, 28))
    r89 = _row(db, 1, "89", start89, stop89, pkg=GARMIN, sport="Elliptical", session_date=date(2026, 9, 28))
    r91 = _row(db, 1, "91", start88, stop88, source="polar_v4", sport="Fitness", session_date=date(2026, 9, 28),
               z1_seconds=19, z2_seconds=208, z3_seconds=679, z4_seconds=539, z5_seconds=466,
               hr_avg=137, hr_max=167)
    n88 = int((stop88 - start88).total_seconds()) + 1
    _samples(db, 1, POLAR_FLOW, start88, 1, [120 + (i % 50) for i in range(n88)])          # 120..169
    n89 = int((stop89 - start89).total_seconds() // 7) + 1
    _samples(db, 1, GARMIN, start89, 7, [118 + (i % 50) for i in range(n89)])
    return r88, r89, r91


def test_the_reference_bout_stays_one_canonical_bout_depositing_once(db_session):
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    r88, r89, r91 = _reference_bout(db_session)

    # BEFORE zoning: only 91 is scoreable and canonical (the live state).
    before = {r.id: r.canonical for r in arbitrated_sessions(1, db_session)}
    assert before == {r88.id: False, r89.id: False, r91.id: True}

    out = hc_zone_enrich.enrich_user(db_session, 1)
    # All three zone: 88 and 89 from their own writers, 91 (polar_v4) from the fi.polar.polarflow trace of
    # the same bout (R2's "samples exist" branch, 0010 row 1) — Polar's vendor zones are replaced.
    assert out["zoned"] == 3 and out["over_ceiling"] == 0
    assert out["polar_rezoned"] == 1 and out["polar_vendor_fallback"] == 0
    rows = {r.id: r for r in arbitrated_sessions(1, db_session)}
    assert all(aerobic_reads._data_tier(r) == 2 for r in rows.values())     # all three now carry zones
    assert _zones(rows[r91.id]) == _zones(rows[r88.id])                     # the same trace, the same zones
    assert _zones(rows[r91.id]) != (19, 208, 679, 539, 466)                 # not Polar's own split any more
    canonical = [i for i, r in rows.items() if r.canonical]
    assert canonical == [r91.id]                                            # 91 outranks HC (source rank)

    # Within HC alone, 88 beats 89 (same writer class, longer duration).
    hc_only = [_fresh(db_session, r88), _fresh(db_session, r89)]
    arbitrate(hc_only)
    assert [r.canonical for r in hc_only] == [True, False]

    ev = load_events_metabolic.compute_metabolic_load_events(db_session, 1)
    assert ev["events_written"] == 1 and ev["sessions_skipped_non_canonical"] == 2
    le = db_session.query(models.LoadEvent).one()
    assert le.source_ref == str(r91.id) and le.provenance["zone_source"] == "polar_v4"
    assert le.provenance["zoning_basis"] == "hrr" and le.formula_version == "metab-v2"


def test_the_reference_bout_still_deposits_once_if_the_polar_row_were_unzoned(db_session):
    """An unzoned Polar row (the v4 list endpoint carries no zones) is restored from the H10 trace the
    Polar Flow app wrote through Health Connect, so it is the richer twin again and carries the bout —
    exactly once. Without that trace the zoned HC twin (88) would carry it instead (next test)."""
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    r88, r89, r91 = _reference_bout(db_session)
    r91.z1_seconds = r91.z2_seconds = r91.z3_seconds = r91.z4_seconds = r91.z5_seconds = None
    r91.hr_avg = r91.hr_max = None
    db_session.commit()
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 1
    ev = load_events_metabolic.compute_metabolic_load_events(db_session, 1)
    assert ev["events_written"] == 1
    assert db_session.query(models.LoadEvent).one().source_ref == str(r91.id)


def test_an_unzoned_polar_row_with_no_trace_lets_the_zoned_hc_twin_carry_the_bout(db_session):
    """The richness-first tier: when the Polar row has no zones AND no Polar Flow trace exists, the zoned HC
    twin carries the bout — still exactly once (the winner is the HC row 88)."""
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 6, 1), 173)
    r88, r89, r91 = _reference_bout(db_session)
    r91.z1_seconds = r91.z2_seconds = r91.z3_seconds = r91.z4_seconds = r91.z5_seconds = None
    r91.hr_avg = r91.hr_max = None
    db_session.commit()
    db_session.query(models.HrSample).filter_by(source_package=POLAR_FLOW).delete()
    db_session.commit()
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 0 and out["polar_vendor_fallback"] == 1
    ev = load_events_metabolic.compute_metabolic_load_events(db_session, 1)
    assert ev["events_written"] == 1
    assert db_session.query(models.LoadEvent).one().source_ref == str(r89.id)


# ---- a restatement reflows through the chain step (#383, #384) ---------------------------------------
# 157 bpm sits on the boundary that matters: 157/173 = 90.75% (z5) but 157/175 = 89.71% (z4).

def _bout(db, ssid, start, bpm=157):
    r = _row(db, 1, ssid, start, start + timedelta(minutes=10))
    _samples(db, 1, GARMIN, start, 10, [bpm] * 61)
    return r


def test_a_restatement_at_the_seed_date_reflows_every_row_through_enrich(db_session):
    from scripts import set_hrmax
    _user(db_session)
    spring = _bout(db_session, "spring", _utc(2026, 5, 4, 6))
    autumn = _bout(db_session, "autumn", _utc(2026, 9, 28, 6))
    _hrmax(db_session, 1, date(2026, 3, 1), 173)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, spring))[4] == 600 and _zones(_fresh(db_session, autumn))[4] == 600   # z5 at 173

    set_hrmax.set_hrmax(db_session, user_id=1, effective_from=date(2026, 3, 1), bpm=175, provenance="adjusted",
                        restate=True, base_bpm=173, rationale="bike lower bound", note="Echo bike")
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["changed"] == 2 and out["reasons"]["none"] == 2
    for r in (spring, autumn):
        z = _zones(_fresh(db_session, r))
        assert z[4] == 0 and z[3] == 600                          # z5 -> z4 across the WHOLE history: no step


def test_a_dated_change_through_enrich_reflows_forward_only(db_session):
    """The same new value as a dated change from 1 Sep: the spring row keeps its 173 zones."""
    _user(db_session)
    spring = _bout(db_session, "spring", _utc(2026, 5, 4, 6))
    autumn = _bout(db_session, "autumn", _utc(2026, 9, 28, 6))
    _hrmax(db_session, 1, date(2026, 3, 1), 173)
    _hrmax(db_session, 1, date(2026, 9, 1), 175, prov="tested")
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, spring))[4] == 600           # still z5 at 173
    assert _zones(_fresh(db_session, autumn))[3] == 600           # z4 at 175


def test_chained_restatements_through_enrich_use_the_latest(db_session):
    from scripts import set_hrmax
    _user(db_session)
    row = _bout(db_session, "r", _utc(2026, 9, 28, 6), bpm=160)    # 160/173 = 92.5%, /175 = 91.4%, /178 = 89.9%
    _hrmax(db_session, 1, date(2026, 3, 1), 173)
    kw = dict(user_id=1, effective_from=date(2026, 3, 1), provenance="observed", restate=True)
    set_hrmax.set_hrmax(db_session, bpm=175, rationale="first", note="n", **kw)
    set_hrmax.set_hrmax(db_session, bpm=178, rationale="second", note="n", **kw)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, row))[3] == 600              # 178 is the chain's end: z4


def test_the_entry_order_the_database_returns_does_not_matter(db_session):
    """The restatement is inserted AFTER the seed, so a plain query returns the seed first - the very
    order that made the old resolver keep 173. Assert the DB order is the bad one and 175 still wins."""
    from scripts import set_hrmax
    _user(db_session)
    _hrmax(db_session, 1, date(2026, 3, 1), 173)
    set_hrmax.set_hrmax(db_session, user_id=1, effective_from=date(2026, 3, 1), bpm=175, provenance="observed",
                        restate=True, rationale="r", note="n")
    entries = [hr_zones.entry_from_row(h) for h in db_session.query(models.UserHrmax).order_by(models.UserHrmax.id)]
    assert [e.bpm for e in entries] == [173, 175]                  # seed first, as stored
    assert hr_zones.hrmax_in_force(entries, date(2026, 9, 28)) == 175


def test_an_incoherent_restatement_fails_the_step_loudly_and_changes_no_row(db_session):
    """The database does not enforce 'a restatement shares its target's date' (a composite FK would break
    `retire_user`), so a row written around the script must fail LOUD here, not be silently guessed at: the
    step raises (the chain's soft-step wrapper reports it) and every row keeps the zones it had."""
    _user(db_session)
    row = _bout(db_session, "r", _utc(2026, 9, 28, 6))
    _hrmax(db_session, 1, date(2026, 3, 1), 173)
    hc_zone_enrich.enrich_user(db_session, 1)
    before = _zones(_fresh(db_session, row))
    seed = db_session.query(models.UserHrmax).one()
    db_session.add(models.UserHrmax(user_id=1, effective_from=date(2026, 5, 1), hrmax_bpm=175, provenance="observed",
                                    note="n", restates_id=seed.id, rationale="r"))      # a different date: incoherent
    db_session.commit()
    with pytest.raises(ValueError, match="shares its target's date"):
        hc_zone_enrich.enrich_user(db_session, 1)
    db_session.rollback()
    assert _zones(_fresh(db_session, row)) == before


# ---- the per-class model: LTHR for the cycling class, HRR elsewhere (design 0010) --------------------
# Real anchors here: HRmax 179, RHR 51 (reserve 128: hrr edges 115/128/141/154/167), LTHR 158
# (lthr edges 0/128/143/149/158). 134 bpm is z2 under both; 120 bpm is z1 on HRR and z1 on LTHR;
# 145 bpm is z3 on both; the retired %HRmax model would have put 134 in z3 (74.9%).

def _real_anchors(db, uid=1, eff=date(2026, 3, 1), *, lthr=158, rhr=51, hrmax=179):
    _hrmax(db, uid, eff, hrmax, rhr=None)
    if rhr is not None:
        _anchor(db, uid, "rhr", eff, rhr)
    if lthr is not None:
        _anchor(db, uid, "lthr", eff, lthr, prov="device_estimated")


def test_a_cycling_row_zones_on_lthr_and_another_sport_on_hrr(db_session):
    _user(db_session)
    _real_anchors(db_session)
    bike = _row(db_session, 1, "bike", S, E, sport="Biking Stationary")          # the Echo bike via Garmin
    walk_s = S + timedelta(hours=2)
    walk = _row(db_session, 1, "walk", walk_s, walk_s + timedelta(minutes=10), sport="Walking")
    _samples(db_session, 1, GARMIN, S, 10, [134] * 30 + [145] * 30)
    _samples(db_session, 1, GARMIN, walk_s, 10, [134] * 30 + [145] * 30)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["zoned"] == 2 and out["by_basis"] == {"lthr": 1, "hrr": 1}
    assert _zones(_fresh(db_session, bike)) == (0, 300, 300, 0, 0)       # 134 in 128-142, 145 in 143-148
    assert _zones(_fresh(db_session, walk)) == (0, 300, 300, 0, 0)       # 134 in 128-140, 145 in 141-153
    # the same 134 bpm under the retired %HRmax model: 74.9% of 179 was z3 (the brief's defect)
    assert hr_zones.band_for(134, 179) == 3


def test_a_cycling_row_without_an_lthr_anchor_is_no_anchor_while_other_sports_still_zone(db_session):
    _user(db_session)
    _real_anchors(db_session, lthr=None)
    bike = _row(db_session, 1, "bike", S, E, sport="Indoor cycling")
    walk_s = S + timedelta(hours=2)
    walk = _row(db_session, 1, "walk", walk_s, walk_s + timedelta(minutes=10), sport="Walking")
    _samples(db_session, 1, GARMIN, S, 10, [134] * 60)
    _samples(db_session, 1, GARMIN, walk_s, 10, [134] * 60)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["reasons"]["no_anchor"] == 1 and out["zoned"] == 1
    assert _zones(_fresh(db_session, bike)) == (None,) * 5
    assert _zones(_fresh(db_session, walk)) == (0, 600, 0, 0, 0)


def test_without_an_rhr_anchor_every_non_cycling_row_is_no_anchor(db_session):
    """R3: RHR is the stored anchor, never a live device RHR — with none stored the HRR basis has no reserve."""
    _user(db_session)
    _real_anchors(db_session, rhr=None)
    _row(db_session, 1, "walk", S, E, sport="Walking")
    _samples(db_session, 1, GARMIN, S, 10, [134] * 60)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["reasons"]["no_anchor"] == 1 and out["zoned"] == 0


def test_a_dated_rhr_change_applies_forward_and_a_restated_rhr_reflows(db_session):
    _user(db_session)
    _real_anchors(db_session)                                                   # RHR 51 from 1 Mar
    spring = _row(db_session, 1, "spring", _utc(2026, 5, 4, 6), _utc(2026, 5, 4, 6, 10), sport="Walking",
                  session_date=date(2026, 5, 4))
    autumn = _row(db_session, 1, "autumn", _utc(2026, 9, 28, 6), _utc(2026, 9, 28, 6, 10), sport="Walking",
                  session_date=date(2026, 9, 28))
    for r in (spring, autumn):
        _samples(db_session, 1, GARMIN, r.start_time, 10, [140] * 61)           # 140: z2 at RHR 51 (128-140)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, spring))[1] == 600 and _zones(_fresh(db_session, autumn))[1] == 600
    _anchor(db_session, 1, "rhr", date(2026, 9, 1), 45)                         # dated: reserve 134, z3 from 139
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, spring))[1] == 600                        # before 1 Sep: unchanged
    assert _zones(_fresh(db_session, autumn))[2] == 600                        # from 1 Sep: z3
    seed = db_session.query(models.UserHrAnchor).filter_by(kind="rhr", effective_from=date(2026, 3, 1)).one()
    _anchor(db_session, 1, "rhr", date(2026, 3, 1), 45, restates_id=seed.id, rationale="better read")
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(_fresh(db_session, spring))[2] == 600                        # restated: the spring reflows too
    assert db_session.query(models.UserHrAnchor).count() == 4                  # append-only: nothing edited


# ---- Polar rows (R2): re-zoned from the Polar Flow trace where it covers them, else vendor kept -------

def _polar(db, ssid, start, stop, **kw):
    return _row(db, 1, ssid, start, stop, source="polar_v4", sport="Indoor cycling",
                z1_seconds=10, z2_seconds=20, z3_seconds=30, z4_seconds=40, z5_seconds=50, hr_avg=150, hr_max=170, **kw)


def test_a_polar_row_covered_by_the_polar_flow_trace_is_rezoned_and_its_vendor_zones_replaced(db_session):
    _user(db_session)
    _real_anchors(db_session)
    p = _polar(db_session, "p1", S, E)
    _samples(db_session, 1, POLAR_FLOW, S, 1, [134] * 601)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 1 and out["polar_vendor_fallback"] == 0 and out["by_basis"]["lthr"] == 1
    r = _fresh(db_session, p)
    assert _zones(r) == (0, 600, 0, 0, 0) and r.hr_avg == 134 and r.hr_max == 134


def test_a_polar_row_with_no_trace_keeps_polars_own_zones_and_is_counted_as_the_fallback(db_session):
    _user(db_session)
    _real_anchors(db_session)
    p = _polar(db_session, "p1", S, E)
    _samples(db_session, 1, GARMIN, S, 1, [134] * 601)          # a Garmin trace is NOT a Polar trace
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 0 and out["polar_vendor_fallback"] == 1 and out["changed"] == 0
    r = _fresh(db_session, p)
    assert _zones(r) == (10, 20, 30, 40, 50) and r.hr_avg == 150 and r.hr_max == 170


def test_a_sparse_trace_leaves_polars_zones_and_a_missing_anchor_does_too(db_session):
    _user(db_session)
    _real_anchors(db_session)
    sparse = _polar(db_session, "sparse", S, E)
    _samples(db_session, 1, POLAR_FLOW, S, 120, [134] * 5)       # 2-minute gaps: coverage ~0.5
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["reasons"]["sparse"] == 1 and out["polar_vendor_fallback"] == 1
    assert _zones(_fresh(db_session, sparse)) == (10, 20, 30, 40, 50)
    # no anchor for the class: the trace is not even read; vendor zones stay
    _user(db_session, 2)
    db_session.add(models.AerobicSession(user_id=2, source="polar_v4", source_session_id="p2", session_date=S.date(),
                                         start_time=S, stop_time=E, sport_name="Indoor cycling",
                                         z1_seconds=1, z2_seconds=2, z3_seconds=3, z4_seconds=4, z5_seconds=5))
    db_session.commit()
    out2 = hc_zone_enrich.enrich_user(db_session, 2)
    assert out2["reasons"]["no_anchor"] == 1 and out2["polar_vendor_fallback"] == 1


def test_a_rezoned_polar_row_is_stable_across_runs(db_session):
    _user(db_session)
    _real_anchors(db_session)
    p = _polar(db_session, "p1", S, E)
    _samples(db_session, 1, POLAR_FLOW, S, 1, [134] * 601)
    hc_zone_enrich.enrich_user(db_session, 1)
    before = _zones(_fresh(db_session, p))
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["changed"] == 0 and _zones(_fresh(db_session, p)) == before


def test_the_polar_sample_writers_constant_is_the_reverse_by(db_session, monkeypatch):
    """Empty tuple = pure vendor fallback for every Polar row (0010 row 1's reverse-by)."""
    monkeypatch.setattr(hc_zone_enrich, "POLAR_SAMPLE_WRITERS", ())
    _user(db_session)
    _real_anchors(db_session)
    p = _polar(db_session, "p1", S, E)
    _samples(db_session, 1, POLAR_FLOW, S, 1, [134] * 601)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 0 and out["polar_vendor_fallback"] == 1
    assert _zones(_fresh(db_session, p)) == (10, 20, 30, 40, 50)


def test_metab_v2_recompute_is_idempotent_and_removes_the_retired_version(db_session):
    _user(db_session)
    _real_anchors(db_session)
    row = _row(db_session, 1, "walk", S, E, sport="Walking")
    _samples(db_session, 1, GARMIN, S, 10, [134] * 60)
    hc_zone_enrich.enrich_user(db_session, 1)
    db_session.add(models.LoadEvent(user_id=1, source="aerobic_sessions", source_ref=str(row.id), load_window="metabolic",
                                    occurred_at=S, load=99.0, unit="trimp_edw_au", formula_version="metab-v1"))
    db_session.commit()
    first = load_events_metabolic.compute_metabolic_load_events(db_session, 1)
    assert first["formula_version"] == "metab-v2" and first["events_written"] == 1
    versions = [v for (v,) in db_session.query(models.LoadEvent.formula_version).all()]
    assert versions == ["metab-v2"]                                            # the metab-v1 row is gone
    load_events_metabolic.compute_metabolic_load_events(db_session, 1)
    rows = db_session.query(models.LoadEvent).all()
    assert len(rows) == 1 and rows[0].load == pytest.approx(10 * 2) and rows[0].provenance["zoning_basis"] == "hrr"
