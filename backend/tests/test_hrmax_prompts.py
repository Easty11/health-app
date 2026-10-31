"""'Restate HRmax?' prompts: the over-ceiling rows `hc_zone_enrich` detects, surfaced on the freshness read.

`enrich_user` returns `over_ceiling_rows` per chain run and nothing persists or reads them. The prompt list
is derived on read from the stored samples (`over_ceiling_prompts`, one aggregate query) with the chain's
own definition, so the tests pin PARITY with a chain run, then the surface (freshness key, snapshot line),
and that nothing is ever written to `user_hrmax`.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import null

import hc_zone_enrich
import models
from reads import freshness_reads as fr

GARMIN = "com.garmin.android.apps.connectmobile"
POLAR_FLOW = "fi.polar.polarflow"
S = datetime(2026, 9, 27, 6, 0, 0, tzinfo=timezone.utc)
E = S + timedelta(minutes=10)
NOW = datetime(2026, 10, 25, 9, 0, 0, tzinfo=timezone.utc)


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _hrmax(db, eff, bpm, *, restates=None, prov="observed"):
    h = models.UserHrmax(user_id=1, effective_from=eff, hrmax_bpm=bpm, provenance=prov, note="t",
                         restates_id=restates,
                         rationale="a higher observed maximum" if restates else None)
    db.add(h)
    db.commit()
    return h


def _row(db, ssid, start, stop, *, pkg=GARMIN, sport="Indoor cycling", day_offset=0):
    r = models.AerobicSession(
        user_id=1, source="health_connect", source_session_id=ssid,
        session_date=(start + timedelta(hours=10)).date() + timedelta(days=day_offset),
        start_time=start, stop_time=stop, sport_name=sport,
        duration_minutes=(stop - start).total_seconds() / 60.0, source_package=pkg,
        **{z: null() for z in ("z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds")})
    db.add(r)
    db.commit()
    return r


def _samples(db, pkg, start, step_s, bpms):
    db.add_all(models.HrSample(user_id=1, sample_time=start + timedelta(seconds=step_s * i), bpm=b,
                               source="health_connect", source_package=pkg) for i, b in enumerate(bpms))
    db.commit()


def _seed_mix(db):
    """HRmax 175 from 2026-03-01. One bout per case, an hour apart."""
    _user(db)
    base = _hrmax(db, date(2026, 3, 1), 175)
    over = _row(db, "over", S, E)
    _samples(db, GARMIN, S, 10, [150] * 30 + [177] + [150] * 29)
    equal = _row(db, "equal", S + timedelta(hours=1), E + timedelta(hours=1))
    _samples(db, GARMIN, S + timedelta(hours=1), 10, [150] * 30 + [175] + [150] * 29)
    sparse = _row(db, "sparse", S + timedelta(hours=2), E + timedelta(hours=2))
    _samples(db, GARMIN, S + timedelta(hours=2), 120, [150, 178, 150, 150, 150])
    other = _row(db, "other-writer", S + timedelta(hours=3), E + timedelta(hours=3))
    _samples(db, POLAR_FLOW, S + timedelta(hours=3), 10, [150] * 30 + [190] + [150] * 29)   # not the row's writer
    junk = _row(db, "implausible", S + timedelta(hours=4), E + timedelta(hours=4))
    _samples(db, GARMIN, S + timedelta(hours=4), 10, [150] * 30 + [300] + [150] * 29)     # outside 30-240
    early = _row(db, "before-any-hrmax", datetime(2026, 2, 10, 6, 0, tzinfo=timezone.utc),
                 datetime(2026, 2, 10, 6, 10, tzinfo=timezone.utc))
    _samples(db, GARMIN, datetime(2026, 2, 10, 6, 0, tzinfo=timezone.utc), 10, [200] * 60)
    return base, {"over": over, "equal": equal, "sparse": sparse, "other": other, "junk": junk, "early": early}


def test_prompts_list_the_row_sport_and_sample_against_the_hrmax_in_force(db_session):
    _, rows = _seed_mix(db_session)
    got = hc_zone_enrich.over_ceiling_prompts(db_session, 1)
    assert {g["id"] for g in got} == {rows["over"].id, rows["sparse"].id}     # equal, other writer, junk, no HRmax: none
    over = next(g for g in got if g["id"] == rows["over"].id)
    assert over == {"id": rows["over"].id, "date": rows["over"].session_date.isoformat(),
                    "sport": "Indoor cycling", "hr_max": 177, "hrmax_in_force": 175}
    assert [g["date"] for g in got] == sorted(g["date"] for g in got)


def test_prompts_match_the_chain_runs_over_ceiling_rows(db_session):
    _seed_mix(db_session)
    chain = hc_zone_enrich.enrich_user(db_session, 1)["over_ceiling_rows"]
    prompts = hc_zone_enrich.over_ceiling_prompts(db_session, 1)
    shared = ("id", "date", "hr_max", "hrmax_in_force")
    assert [{k: p[k] for k in shared} for p in prompts] == [{k: c[k] for k in shared} for c in chain]
    # the sparse row carries the sample too: the chain lists it though it is not zoned
    assert any(p["hr_max"] == 178 for p in prompts)


def test_a_restatement_above_the_sample_clears_the_prompt_and_nothing_is_written(db_session):
    base, rows = _seed_mix(db_session)
    before = [(h.id, h.hrmax_bpm) for h in db_session.query(models.UserHrmax).all()]
    assert hc_zone_enrich.over_ceiling_prompts(db_session, 1)
    assert [(h.id, h.hrmax_bpm) for h in db_session.query(models.UserHrmax).all()] == before   # reading wrote nothing
    _hrmax(db_session, date(2026, 3, 1), 178, restates=base.id)
    assert hc_zone_enrich.over_ceiling_prompts(db_session, 1) == []      # 178 is not exceeded by 177 or 178


def test_another_users_samples_and_rows_are_not_listed(db_session):
    _seed_mix(db_session)
    assert hc_zone_enrich.over_ceiling_prompts(db_session, 4) == []


def test_the_prompts_ride_in_the_freshness_read_and_the_snapshot_lines(db_session):
    _, rows = _seed_mix(db_session)
    f = fr.freshness(db_session, 1, now=NOW)
    assert {p["id"] for p in f["hrmax_prompts"]} == {rows["over"].id, rows["sparse"].id}
    lines = fr.freshness_snapshot_lines(f)
    mine = [l for l in lines if l.startswith("  HRMAX, restate?")]
    assert len(mine) == 2
    assert f"row {rows['over'].id} {rows['over'].session_date.isoformat()} Indoor cycling: a sample of 177 bpm against 175 in force" in mine[0]
    clean = fr.freshness_snapshot_lines({**f, "hrmax_prompts": []})
    assert not any("HRMAX" in l for l in clean)


def test_a_failure_reads_as_no_prompts_and_does_not_take_the_freshness_read_down(db_session, monkeypatch):
    _user(db_session)

    def boom(db, uid):
        raise ValueError("ambiguous HRmax chain")
    monkeypatch.setattr(fr, "over_ceiling_prompts", boom)
    f = fr.freshness(db_session, 1, now=NOW)
    assert f["hrmax_prompts"] == []
    assert "pipes" in f and "garmin_alerts" in f


# ---- one bout, two writers: one prompt (rows 144/145 on 2026-10-28) -----------------------------------------

P_START = datetime(2026, 10, 28, 5, 5, 15, tzinfo=timezone.utc)      # Polar row, the longer window
P_STOP = datetime(2026, 10, 28, 5, 36, 3, tzinfo=timezone.utc)
G_START = datetime(2026, 10, 28, 5, 11, 19, tzinfo=timezone.utc)     # Garmin row, wholly inside it
G_STOP = datetime(2026, 10, 28, 5, 33, 35, tzinfo=timezone.utc)


def _one_ride_two_writers(db, *, polar_top, garmin_top):
    _user(db)
    _hrmax(db, date(2026, 3, 1), 177)
    polar = _row(db, "polar", P_START, P_STOP, pkg=POLAR_FLOW, sport="Biking Stationary")
    garmin = _row(db, "garmin", G_START, G_STOP, pkg=GARMIN, sport="Biking")
    peak = datetime(2026, 10, 28, 5, 31, 47, tzinfo=timezone.utc)
    for pkg, start, stop, top in ((POLAR_FLOW, P_START, P_STOP, polar_top), (GARMIN, G_START, G_STOP, garmin_top)):
        n = int((stop - start).total_seconds() // 5)
        bpms = [150] * n
        bpms[int((peak - start).total_seconds() // 5)] = top
        _samples(db, pkg, start, 5, bpms)
    return polar, garmin


def test_one_bout_recorded_by_two_writers_prompts_once_on_the_primary_row(db_session):
    polar, garmin = _one_ride_two_writers(db_session, polar_top=179, garmin_top=179)
    chain = hc_zone_enrich.enrich_user(db_session, 1)["over_ceiling_rows"]
    assert {c["id"] for c in chain} == {polar.id, garmin.id}                 # the chain still lists each raw row
    prompts = hc_zone_enrich.over_ceiling_prompts(db_session, 1)
    assert [p["id"] for p in prompts] == [polar.id]                          # the prompt is per bout
    assert prompts[0]["hr_max"] == 179 and prompts[0]["hrmax_in_force"] == 177
    assert {p["id"] for p in prompts} <= {c["id"] for c in chain}


def test_a_sample_held_only_by_the_suppressed_twin_still_prompts(db_session):
    polar, garmin = _one_ride_two_writers(db_session, polar_top=150, garmin_top=179)
    prompts = hc_zone_enrich.over_ceiling_prompts(db_session, 1)
    assert [p["id"] for p in prompts] == [garmin.id]                         # the only row holding the 179


def test_two_separate_rides_over_the_ceiling_still_prompt_twice(db_session):
    _seed_mix(db_session)                                                    # rows an hour apart: no twins
    assert len(hc_zone_enrich.over_ceiling_prompts(db_session, 1)) == 2
