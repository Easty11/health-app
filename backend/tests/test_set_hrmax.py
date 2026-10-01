"""`scripts/set_hrmax.py` — the operator's only write path to `user_hrmax` (R2)."""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
from scripts import set_hrmax

GARMIN = "com.garmin.android.apps.connectmobile"


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _hc_row(db, uid, ssid, day):
    start = datetime(day.year, day.month, day.day, 5, tzinfo=timezone.utc)
    db.add(models.AerobicSession(user_id=uid, source="health_connect", source_session_id=ssid,
                                 session_date=day, start_time=start, stop_time=start + timedelta(minutes=30),
                                 sport_name="Walking", source_package=GARMIN))
    db.commit()


def _write(db, **kw):
    args = dict(user_id=1, effective_from=date(2026, 6, 1), bpm=173, provenance="observed",
                note="H10 chest strap max", dry_run=False)
    args.update(kw)
    return set_hrmax.set_hrmax(db, **args)


def test_writes_one_row_with_provenance_and_note(db_session):
    _user(db_session)
    res = _write(db_session)
    assert res["written"] is True
    h = db_session.query(models.UserHrmax).one()
    assert (h.user_id, h.effective_from, h.hrmax_bpm, h.provenance, h.note) == \
        (1, date(2026, 6, 1), 173, "observed", "H10 chest strap max")


def test_a_duplicate_key_is_refused_and_the_existing_row_is_untouched(db_session):
    _user(db_session)
    _write(db_session)
    with pytest.raises(ValueError, match="append-only"):
        _write(db_session, bpm=180, provenance="tested")
    h = db_session.query(models.UserHrmax).one()
    assert (h.hrmax_bpm, h.provenance) == (173, "observed")


@pytest.mark.parametrize("prov", ["estimated", "age_predicted", "", "OBSERVED"])
def test_provenance_is_the_closed_set_and_estimated_is_refused(db_session, prov):
    _user(db_session)
    # The SCRIPT refuses it before the database does (the CHECK is a second layer, not the first).
    with pytest.raises(ValueError, match="provenance must be one of"):
        _write(db_session, provenance=prov)
    assert db_session.query(models.UserHrmax).count() == 0


@pytest.mark.parametrize("bpm", [29, 241, 0, -5])
def test_bpm_outside_the_plausibility_bounds_is_refused(db_session, bpm):
    _user(db_session)
    with pytest.raises(ValueError, match="plausibility"):
        _write(db_session, bpm=bpm)


def test_a_note_and_a_real_user_are_required(db_session):
    _user(db_session)
    with pytest.raises(ValueError, match="note"):
        _write(db_session, note="   ")
    with pytest.raises(ValueError, match="no user"):
        _write(db_session, user_id=99)


def test_dry_run_writes_nothing_but_still_lists_the_touched_rows(db_session):
    _user(db_session)
    _hc_row(db_session, 1, "a", date(2026, 9, 1))
    res = _write(db_session, dry_run=True)
    assert res["written"] is False and db_session.query(models.UserHrmax).count() == 0
    assert [t["id"] for t in res["touched"]] == [db_session.query(models.AerobicSession).one().id]


def test_it_lists_exactly_the_rows_whose_hrmax_in_force_changes(db_session):
    """Seed 173 from 1 Jun; a new value effective 28 Sep moves only rows on/after 28 Sep. A row on
    27 Sep keeps 173; the 28 Sep and later rows go 173 -> 190. A row before 1 Jun gained nothing."""
    _user(db_session)
    for ssid, d in (("early", date(2026, 5, 20)), ("pre", date(2026, 9, 27)),
                    ("on", date(2026, 9, 28)), ("post", date(2026, 10, 1))):
        _hc_row(db_session, 1, ssid, d)
    _write(db_session)                                                   # 173 from 1 Jun
    res = _write(db_session, effective_from=date(2026, 9, 28), bpm=190, provenance="tested")
    changed = {(t["date"], t["from"], t["to"]) for t in res["touched"]}
    assert changed == {("2026-09-28", 173, 190), ("2026-10-01", 173, 190)}


def test_the_first_value_touches_rows_that_had_none(db_session):
    _user(db_session)
    _hc_row(db_session, 1, "a", date(2026, 9, 1))
    _hc_row(db_session, 1, "early", date(2026, 5, 1))
    res = _write(db_session)
    assert [(t["date"], t["from"], t["to"]) for t in res["touched"]] == [("2026-09-01", None, 173)]


def test_other_users_rows_and_polar_rows_are_never_listed(db_session):
    _user(db_session)
    _user(db_session, 2)
    _hc_row(db_session, 2, "other", date(2026, 9, 1))
    db_session.add(models.AerobicSession(user_id=1, source="polar_v4", source_session_id="p",
                                         session_date=date(2026, 9, 1)))
    db_session.commit()
    assert _write(db_session)["touched"] == []


def test_main_exit_codes_refused_is_2(db_session, monkeypatch, capsys):
    """The CLI maps a refusal to exit 2 and prints it on stderr (no traceback)."""
    import database
    _user(db_session)
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    rc = set_hrmax.main(["--user", "1", "--effective-from", "2026-06-01", "--bpm", "300",
                         "--provenance", "observed", "--note", "x"])
    assert rc == 2 and "plausibility" in capsys.readouterr().err
    rc = set_hrmax.main(["--user", "1", "--effective-from", "2026-06-01", "--bpm", "173",
                         "--provenance", "observed", "--note", "ok", "--dry-run"])
    assert rc == 0 and "DRY RUN" in capsys.readouterr().out
