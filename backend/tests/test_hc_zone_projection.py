"""G2: the read-only HC zone projection (`scripts/arbitration_flip_report.py --hc-zones`, Q159 stage 2).

It must (a) project exactly what the chain step would write, (b) write nothing, (c) report the
flips, per-day TRIMP delta, near-threshold rows and the HC-vs-Polar band comparison the operator
reviews before merge, and (d) work pre-merge from HR timestamps alone (coverage/reason, no zones).
"""
import csv
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event, null

import hc_zone_enrich
import models
from scripts import arbitration_flip_report as rep

GARMIN = "com.garmin.android.apps.connectmobile"
SHEALTH = "com.sec.android.app.shealth"
POLAR_FLOW = "fi.polar.polarflow"
HRMAX = {1: [(date(2026, 6, 1), 173)]}


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _row(db, ssid, start, stop, *, pkg=GARMIN, sport="Walking", source="health_connect", uid=1, **kw):
    if source == "health_connect":
        for z in ("z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds"):
            kw.setdefault(z, null())
    r = models.AerobicSession(
        user_id=uid, source=source, source_session_id=ssid, session_date=kw.pop("session_date", start.date()),
        start_time=start, stop_time=stop, sport_name=sport,
        duration_minutes=(stop - start).total_seconds() / 60.0,
        source_package=pkg if source == "health_connect" else None, **kw)
    db.add(r)
    db.commit()
    return r


def _samples(db, pkg, start, step_s, bpms, uid=1):
    db.add_all(models.HrSample(user_id=uid, sample_time=start + timedelta(seconds=step_s * i), bpm=b,
                               source="health_connect", source_package=pkg) for i, b in enumerate(bpms))
    db.commit()


def _index(db):
    return rep.SampleIndex((h.user_id, h.source_package, rep._utc(h.sample_time), h.bpm)
                           for h in db.query(models.HrSample).all())


def _all_rows(db):
    return db.query(models.AerobicSession).order_by(models.AerobicSession.id).all()


S = _utc(2026, 9, 27, 6, 0, 0)
E = S + timedelta(minutes=10)


def _mixed_scenario(db):
    """Five HC rows spanning every outcome: zoned, sparse (passive 2-min), no_same_writer_hr,
    a NEAR-threshold row (coverage ~0.62), and an over-ceiling row."""
    _user(db)
    a = _row(db, "zoned", S, E)
    _samples(db, GARMIN, S, 10, [120] * 60)
    s2 = S + timedelta(hours=2)
    b = _row(db, "sparse", s2, s2 + timedelta(minutes=10))
    _samples(db, GARMIN, s2, 120, [95] * 5)                                 # 5 x 60 s credited = 0.5
    s3 = S + timedelta(hours=4)
    c = _row(db, "nowriter", s3, s3 + timedelta(minutes=10))
    _samples(db, SHEALTH, s3, 10, [150] * 60)                                # ring only
    s4 = S + timedelta(hours=6)
    d = _row(db, "near", s4, s4 + timedelta(minutes=10))
    _samples(db, GARMIN, s4 + timedelta(seconds=228), 10, [130] * 38)        # 372 of 600 s = 0.62
    s5 = S + timedelta(hours=8)
    e = _row(db, "over", s5, s5 + timedelta(minutes=10))
    _samples(db, GARMIN, s5, 10, [150] * 30 + [185] + [150] * 29)
    return a, b, c, d, e


# ---- (a) it projects exactly what the chain step writes ---------------------------------------------------

def test_the_projection_equals_what_the_chain_step_then_writes(db_session):
    rows = _mixed_scenario(db_session)
    db_session.add(models.UserHrmax(user_id=1, effective_from=date(2026, 6, 1), hrmax_bpm=173,
                                    provenance="observed", note="t"))
    db_session.commit()
    recs, _after = rep.project_hc_zones(_all_rows(db_session), _index(db_session), HRMAX)
    proj = {r["id"]: r for r in recs}

    hc_zone_enrich.enrich_user(db_session, 1)
    db_session.expire_all()
    for row in rows:
        live = db_session.get(models.AerobicSession, row.id)
        p = proj[row.id]
        zs = (live.z1_seconds, live.z2_seconds, live.z3_seconds, live.z4_seconds, live.z5_seconds)
        assert (p["zones"] or (None,) * 5) == zs, row.source_session_id
        assert (p["hr_avg"], p["hr_max"]) == (live.hr_avg, live.hr_max)
    assert {r["reason"] for r in recs} == {"none", "sparse", "no_same_writer_hr"}


def test_near_threshold_rows_are_marked_and_far_rows_are_not(db_session):
    a, b, c, d, e = _mixed_scenario(db_session)
    recs = {r["id"]: r for r in rep.project_hc_zones(_all_rows(db_session), _index(db_session), HRMAX)[0]}
    assert recs[d.id]["near"] is True and 0.55 <= recs[d.id]["coverage"] <= 0.65
    assert recs[a.id]["near"] is False and recs[b.id]["near"] is False         # 1.0 and 0.5: 0.1 away
    assert recs[c.id]["near"] is False                                          # no coverage computed


def test_over_ceiling_is_listed_and_never_changes_hrmax(db_session):
    *_, e = _mixed_scenario(db_session)
    recs = {r["id"]: r for r in rep.project_hc_zones(_all_rows(db_session), _index(db_session), HRMAX)[0]}
    assert recs[e.id]["over_ceiling"] is True and recs[e.id]["hr_max"] == 185
    assert HRMAX == {1: [(date(2026, 6, 1), 173)]}


# ---- (b) it writes nothing ----------------------------------------------------------------------------------

def test_it_writes_nothing_and_every_statement_is_a_select(db_session, monkeypatch, capsys):
    _mixed_scenario(db_session)
    db_session.add(models.UserHrmax(user_id=1, effective_from=date(2026, 6, 1), hrmax_bpm=173,
                                    provenance="observed", note="t"))
    db_session.commit()
    import database
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    stmts: list[str] = []
    event.listen(db_session.get_bind(), "before_cursor_execute",
                 lambda conn, cur, st, params, ctx, many: stmts.append(st.strip().split()[0].upper()))
    snap = [(r.id, r.z1_seconds, r.hr_avg, r.hr_max) for r in _all_rows(db_session)]
    assert rep.main(["--hc-zones"]) == 0
    assert stmts and set(stmts) <= {"SELECT"}, set(stmts)           # it ran queries, and only reads
    db_session.expire_all()
    assert [(r.id, r.z1_seconds, r.hr_avg, r.hr_max) for r in _all_rows(db_session)] == snap
    assert not db_session.dirty and not db_session.new
    out = capsys.readouterr().out
    assert "HC rows: 5. Projected zoned: 3" in out and "OVER-CEILING" in out and "NEAR" in out


# ---- (c) flips, TRIMP delta, Polar comparison ----------------------------------------------------------------

def _reference_bout(db, *, polar_zoned=True):
    start88, stop88 = _utc(2026, 9, 28, 5, 42, 31), _utc(2026, 9, 28, 6, 16, 16)
    start89, stop89 = _utc(2026, 9, 28, 5, 44, 18), _utc(2026, 9, 28, 6, 17, 2)
    _user(db)
    r88 = _row(db, "88", start88, stop88, pkg=POLAR_FLOW, sport="Elliptical", session_date=date(2026, 9, 28))
    r89 = _row(db, "89", start89, stop89, pkg=GARMIN, sport="Elliptical", session_date=date(2026, 9, 28))
    z = dict(z1_seconds=19, z2_seconds=208, z3_seconds=679, z4_seconds=539, z5_seconds=466,
             hr_avg=137, hr_max=167) if polar_zoned else {}
    r91 = _row(db, "91", start88, stop88, source="polar_v4", sport="Fitness", session_date=date(2026, 9, 28), **z)
    _samples(db, POLAR_FLOW, start88, 1, [120 + (i % 50) for i in range(int((stop88 - start88).total_seconds()) + 1)])
    _samples(db, GARMIN, start89, 7, [118 + (i % 50) for i in range(int((stop89 - start89).total_seconds() // 7) + 1)])
    return r88, r89, r91


def test_the_reference_bout_has_no_flip_and_no_trimp_delta_and_a_per_band_comparison(db_session):
    r88, r89, r91 = _reference_bout(db_session)
    rows = _all_rows(db_session)
    before = [rep._clone(s) for s in rows]
    recs, after = rep.project_hc_zones(rows, _index(db_session), HRMAX)
    assert rep.canonical_flips(before, after) == []                            # 91 stays canonical
    assert rep.trimp_delta(before, after) == []                                # an already-scored bout adds nothing
    twins = rep.polar_twin_comparison(after, recs)
    assert {(t["hc_id"], t["polar_id"]) for t in twins} == {(r88.id, r91.id), (r89.id, r91.id)}
    t88 = next(t for t in twins if t["hc_id"] == r88.id)
    assert t88["polar_min"] == [0.32, 3.47, 11.32, 8.98, 7.77]                 # Polar's stored zones, in minutes
    assert len(t88["hc_min"]) == 5 and sum(t88["hc_min"]) > 30                 # 1 s H10: ~full coverage


def test_a_zoned_hc_twin_flips_the_bout_when_the_polar_row_has_no_zones(db_session):
    r88, r89, r91 = _reference_bout(db_session, polar_zoned=False)
    rows = _all_rows(db_session)
    before = [rep._clone(s) for s in rows]
    _recs, after = rep.project_hc_zones(rows, _index(db_session), HRMAX)
    flips = rep.canonical_flips(before, after)
    assert len(flips) == 1
    f = flips[0]
    assert f["old"]["id"] == r91.id and f["new"]["id"] == r88.id and f["newly_scoreable"] is True
    deltas = rep.trimp_delta(before, after)
    assert [d for d, _b, _a in deltas] == ["2026-09-28"] and deltas[0][1] == 0.0 and deltas[0][2] > 100


def test_a_zoned_hc_walk_adds_trimp_to_its_day(db_session):
    _user(db_session)
    _row(db_session, "w", S, S + timedelta(minutes=30), sport="Walking")
    _samples(db_session, GARMIN, S, 10, [110] * 180)                            # z2 for 30 min
    rows = _all_rows(db_session)
    before = [rep._clone(s) for s in rows]
    _recs, after = rep.project_hc_zones(rows, _index(db_session), HRMAX)
    [(day, b, a)] = rep.trimp_delta(before, after)
    assert (day, b) == ("2026-09-27", 0.0) and a == pytest.approx(60.0)         # 30 min x weight 2


# ---- (d) pre-merge: timestamps only ----------------------------------------------------------------------------

_AERO_COLS = ("id", "user_id", "source", "source_package", "session_date", "start_time", "stop_time", "sport_name",
              "duration_minutes", "hr_avg", "hr_max", "z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds")


def _write_csvs(db, tmp_path):
    with open(tmp_path / "aero.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_AERO_COLS)
        for r in _all_rows(db):
            w.writerow([r.id, r.user_id, r.source, r.source_package or "", r.session_date.isoformat(),
                        r.start_time.strftime("%Y-%m-%d %H:%M:%S+00"), r.stop_time.strftime("%Y-%m-%d %H:%M:%S+00"),
                        r.sport_name, r.duration_minutes, "", "", "", "", "", "", ""])
    with open(tmp_path / "times.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["user_id", "record_start", "source_package"])
        for h in db.query(models.HrSample).all():
            w.writerow([h.user_id, h.sample_time.strftime("%Y-%m-%dT%H:%M:%S") + ".123456789Z", h.source_package])
    with open(tmp_path / "samples.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["user_id", "sample_time", "bpm", "source_package"])
        for h in db.query(models.HrSample).all():
            w.writerow([h.user_id, h.sample_time.strftime("%Y-%m-%d %H:%M:%S+00"), h.bpm, h.source_package])


def test_timestamps_only_gives_exact_coverage_and_reasons_but_no_zones(db_session, tmp_path, capsys):
    a, b, c, d, e = _mixed_scenario(db_session)
    _write_csvs(db_session, tmp_path)
    live = {r["id"]: r for r in rep.project_hc_zones(_all_rows(db_session), _index(db_session), HRMAX)[0]}

    rc = rep.main(["--hc-zones", "--csv", str(tmp_path / "aero.csv"),
                   "--record-sources-csv", str(tmp_path / "times.csv"), "--hrmax", "1=173@2026-06-01"])
    out = capsys.readouterr().out
    assert rc == 0 and "TIMESTAMPS-ONLY" in out
    for row in (a, b, c, d, e):
        line = next(l for l in out.splitlines() if l.startswith(f"| #{row.id} "))
        want = live[row.id]
        assert f"| {want['reason']} |" in line
        if want["coverage"] is not None:
            assert f"{want['coverage']:.3f}" in line                            # coverage is exact
    zoned_line = next(l for l in out.splitlines() if l.startswith(f"| #{a.id} "))
    assert "| - | - |" in zoned_line                                            # zones and hr: not available


def test_csv_mode_with_samples_agrees_with_the_db_projection(db_session, tmp_path):
    _mixed_scenario(db_session)
    _write_csvs(db_session, tmp_path)
    by_user = rep.rows_from_csv(str(tmp_path / "aero.csv"))
    samples = rep.samples_from_csv(str(tmp_path / "samples.csv"))
    csv_recs, _ = rep.project_hc_zones(by_user[1], samples, HRMAX)
    db_recs, _ = rep.project_hc_zones(_all_rows(db_session), _index(db_session), HRMAX)
    strip = lambda rs: sorted(({k: v for k, v in r.items()} for r in rs), key=lambda r: r["id"])
    assert strip(csv_recs) == strip(db_recs)


def test_hrmax_arg_parsing():
    assert rep.parse_hrmax_args(["1=173@2026-06-01", "1=180@2026-09-28"]) == {
        1: [(date(2026, 6, 1), 173), (date(2026, 9, 28), 180)]}
    for bad in ("1=173", "x=1@2026-06-01", "1=173@06/01/2026"):
        with pytest.raises(SystemExit):
            rep.parse_hrmax_args([bad])


def test_a_user_without_hrmax_projects_no_hrmax_and_the_report_says_so(db_session):
    _mixed_scenario(db_session)
    recs, _ = rep.project_hc_zones(_all_rows(db_session), _index(db_session), {})
    assert {r["reason"] for r in recs} == {"no_hrmax"}
    text = rep.render_hc_zone_report(recs, [], [], [])
    assert "no_hrmax=5" in text and "Projected zoned: 0" in text


def test_the_projection_never_touches_the_rows_it_was_given(db_session):
    """In-memory too, not just in the database: the report works on transient clones, so the real
    (session-attached) rows keep their values and are never marked dirty. Mutation: projecting onto
    the given rows instead of clones fails this (a rollback alone would hide it)."""
    _mixed_scenario(db_session)
    rows = _all_rows(db_session)
    snap = [(r.id, r.z1_seconds, r.z2_seconds, r.hr_avg, r.hr_max) for r in rows]
    recs, after = rep.project_hc_zones(rows, _index(db_session), HRMAX)
    assert any(r["zones"] for r in recs)                                       # the projection did zone something
    assert [(r.id, r.z1_seconds, r.z2_seconds, r.hr_avg, r.hr_max) for r in rows] == snap
    assert not db_session.dirty
    assert all(a is not r for a, r in zip(after, rows))


# ---- restated HRmax in the projection (#383, #384) -----------------------------------------------------------

def _restated_seed(db, bpm=175):
    db.add(models.UserHrmax(user_id=1, effective_from=date(2026, 6, 1), hrmax_bpm=173, provenance="observed", note="t"))
    db.commit()
    seed = db.query(models.UserHrmax).one()
    db.add(models.UserHrmax(user_id=1, effective_from=date(2026, 6, 1), hrmax_bpm=bpm, provenance="adjusted",
                            note="t", restates_id=seed.id, base_bpm=173, rationale="r"))
    db.commit()


def test_db_mode_projects_under_the_restated_hrmax_not_the_seed_read_first(db_session, monkeypatch, capsys):
    _mixed_scenario(db_session)
    _restated_seed(db_session)
    import database
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    assert rep.main(["--hc-zones"]) == 0
    out = capsys.readouterr().out
    assert " 175 |" in out and " 173 |" not in out                     # the HRmax column reads the restatement


def test_a_hrmax_projection_on_a_stored_date_is_refused_clearly_and_a_later_date_still_works(
        db_session, monkeypatch, capsys):
    """It used to be ignored without a word (the tie kept the stored row). It is now an error that names
    the way out; dating the projection after the stored row is the supported shape and projects."""
    _mixed_scenario(db_session)
    _restated_seed(db_session)
    import database
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    with pytest.raises(SystemExit, match="cannot be resolved"):
        rep.main(["--hc-zones", "--hrmax", "1=177@2026-06-01"])
    assert rep.main(["--hc-zones", "--hrmax", "1=177@2026-06-02"]) == 0
    assert " 177 |" in capsys.readouterr().out
