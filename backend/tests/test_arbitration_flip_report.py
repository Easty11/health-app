"""Brief A / A6 — the read-only dry run (`scripts/arbitration_flip_report.py`).

It must (1) list exactly the bouts whose canonical row flips under the richness-first tier, with the old/new
row and tiers; (2) list NOTHING for bouts the tier does not change; (3) write nothing; (4) read a psql
`\\copy ... CSV HEADER` export (timestamps in psql's `YYYY-MM-DD HH:MM:SS+00` shape) and agree with DB mode.
Fixtures are synthetic placeholders.
"""
import csv
from datetime import date, datetime, timedelta, timezone

import models
from scripts import arbitration_flip_report as rep

D1 = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)
D2 = datetime(2026, 9, 26, 5, 0, tzinfo=timezone.utc)
ZONED = (0, 600, 1800, 300, 0)


def _add(db, user, source, start, *, sport, sid, hr=None, zones=None, minutes=45, package=None):
    z = zones or (None,) * 5
    db.add(models.AerobicSession(
        user_id=user.id, source=source, source_session_id=sid, session_date=start.date(), start_time=start,
        stop_time=start + timedelta(minutes=minutes), duration_minutes=minutes, sport_name=sport, hr_avg=hr,
        z1_seconds=z[0], z2_seconds=z[1], z3_seconds=z[2], z4_seconds=z[3], z5_seconds=z[4], source_package=package))
    db.commit()


def _world(db):
    u = models.User(email="r@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    # bout A: zoneless flow_export (tier 0) vs zoned v4 (tier 2) -> FLIPS export -> v4, newly scoreable
    _add(db, u, "polar_flow_export", D1, sport="Elliptical", sid="a-export")
    _add(db, u, "polar_v4", D1 + timedelta(minutes=1), sport="Elliptical", sid="a-v4", hr=140, zones=ZONED)
    # bout B: both zoned -> source rank decides both before and after -> NO flip
    _add(db, u, "polar_flow_export", D2, sport="Run", sid="b-export", hr=150, zones=ZONED)
    _add(db, u, "polar_v4", D2 + timedelta(minutes=1), sport="Run", sid="b-v4", hr=150, zones=ZONED)
    # bout C: a lone session -> canonical before and after -> NO flip
    _add(db, u, "health_connect", D1 + timedelta(hours=6), sport="Walk", sid="c-hc", hr=90)
    return u


def _tables(db):
    return {t: db.query(t).count() for t in (models.AerobicSession, models.LoadEvent)}


def test_lists_exactly_the_flipped_bout_with_old_new_and_tiers(db_session):
    u = _world(db_session)
    recs = rep.flip_report(db_session, u.id)

    assert len(recs) == 1
    r = recs[0]
    assert r["date"] == "2026-09-28" and r["sport"] == "Elliptical"
    assert (r["old"]["source"], r["old"]["tier"]) == ("polar_flow_export", 0)
    assert (r["new"]["source"], r["new"]["tier"]) == ("polar_v4", 2)
    assert r["newly_scoreable"] is True and r["no_longer_scoreable"] is False


def test_the_dry_run_writes_nothing(db_session):
    u = _world(db_session)
    before = _tables(db_session)
    rep.flip_report(db_session, u.id)
    assert _tables(db_session) == before
    assert not db_session.new and not db_session.dirty and not db_session.deleted


def test_the_real_tier_is_restored_after_the_dry_run(db_session):
    """The neutralised-tier pass must not leak into the process: after the report the shipped ordering holds."""
    u = _world(db_session)
    rep.flip_report(db_session, u.id)
    from reads.aerobic_reads import arbitrated_sessions
    canon = {s.source_session_id for s in arbitrated_sessions(u.id, db_session) if s.canonical}
    assert "a-v4" in canon and "a-export" not in canon


def test_no_flip_reports_none(db_session):
    u = models.User(email="n@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    _add(db_session, u, "polar_v4", D1, sport="Run", sid="only", hr=140, zones=ZONED)
    assert rep.flip_report(db_session, u.id) == []
    assert "No flips" in rep.render_markdown([], sessions_seen=1)


def test_csv_mode_reads_a_psql_export_and_agrees_with_db_mode(db_session, tmp_path):
    u = _world(db_session)
    path = tmp_path / "aerobic_sessions.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(rep._CSV_COLUMNS)
        for s in db_session.query(models.AerobicSession).order_by(models.AerobicSession.id):
            def ts(dt):   # psql's timestamptz text form, e.g. 2026-09-28 00:00:00+00
                return "" if dt is None else dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
            w.writerow([s.id, s.user_id, s.source, s.source_package or "", s.session_date.isoformat(),
                        ts(s.start_time), ts(s.stop_time), s.sport_name or "", s.duration_minutes,
                        "" if s.hr_avg is None else s.hr_avg, "" if s.hr_max is None else s.hr_max,
                        *["" if v is None else v for v in (s.z1_seconds, s.z2_seconds, s.z3_seconds,
                                                            s.z4_seconds, s.z5_seconds)]])
    by_user = rep.rows_from_csv(str(path))
    from_csv = [r for rows in by_user.values() for r in rep.flip_report_from_rows(rows)]
    assert from_csv == rep.flip_report(db_session, u.id)


def test_markdown_table_names_the_effect(db_session):
    u = _world(db_session)
    md = rep.render_markdown(rep.flip_report(db_session, u.id), sessions_seen=5)
    assert "Bouts whose canonical row flips: 1." in md
    assert "polar_flow_export (tier 0)" in md and "polar_v4 (tier 2)" in md and "bout NEWLY scored" in md
