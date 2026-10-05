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


# ---- restatement mode and the `adjusted` provenance (#383, #384) ----------------------------------

SEED = date(2026, 3, 1)


def _seed(db, uid=1):
    """User 1's real seed row: 173, observed, on the user's earliest session date."""
    return _write(db, user_id=uid, effective_from=SEED, bpm=173, provenance="observed")


def _restate(db, **kw):
    args = dict(effective_from=SEED, bpm=175, provenance="adjusted", restate=True, base_bpm=173,
                rationale="bike-modality lower bound; Polar zones imply ~175",
                note="Echo bike, H10, 2026-06-17 and 2026-07-17")
    args.update(kw)
    return _write(db, **args)


def _rows(db):
    db.expire_all()
    return db.query(models.UserHrmax).order_by(models.UserHrmax.id).all()


def test_a_restatement_at_the_seeds_own_date_is_written_linked_and_the_seed_is_untouched(db_session):
    """The case the old key refused: a second row on 2026-03-01. The seed row stays byte-for-byte
    what it was; the new row points at it and records the base and the reason."""
    _user(db_session)
    _seed(db_session)
    before = [(h.id, h.effective_from, h.hrmax_bpm, h.provenance, h.note, h.restates_id, h.base_bpm, h.rationale)
              for h in _rows(db_session)]
    res = _restate(db_session)
    assert res["written"] is True
    assert res["restates"] == {"id": before[0][0], "bpm": 173, "provenance": "observed", "effective_from": SEED}
    seed, new = _rows(db_session)
    assert (seed.id, seed.effective_from, seed.hrmax_bpm, seed.provenance, seed.note, seed.restates_id,
            seed.base_bpm, seed.rationale) == before[0]
    assert (new.effective_from, new.hrmax_bpm, new.provenance, new.restates_id, new.base_bpm) == \
        (SEED, 175, "adjusted", seed.id, 173)
    assert new.rationale == "bike-modality lower bound; Polar zones imply ~175"
    assert new.note == "Echo bike, H10, 2026-06-17 and 2026-07-17"


def test_a_dated_change_on_an_existing_date_is_still_refused_and_points_at_restate(db_session):
    _user(db_session)
    _seed(db_session)
    with pytest.raises(ValueError, match="append-only") as ei:
        _write(db_session, effective_from=SEED, bpm=175)
    assert "--restate" in str(ei.value)
    assert len(_rows(db_session)) == 1


def test_a_restatement_needs_an_existing_row_on_that_date(db_session):
    _user(db_session)
    _seed(db_session)
    with pytest.raises(ValueError, match="nothing to restate") as ei:
        _restate(db_session, effective_from=date(2026, 4, 1))
    assert "--effective-from 2026-03-01" in str(ei.value)       # names the row actually in force
    assert len(_rows(db_session)) == 1


def test_a_restatement_with_no_row_before_it_says_so(db_session):
    _user(db_session)
    with pytest.raises(ValueError, match="nothing to restate"):
        _restate(db_session)


def test_a_restatement_requires_a_rationale_and_a_change_of_value(db_session):
    _user(db_session)
    _seed(db_session)
    # The SCRIPT's own message: a bare "rationale" would also match the database CHECK's name
    # (ck_user_hrmax_rationale) and hide a missing script check behind the second layer.
    with pytest.raises(ValueError, match="a restatement needs --rationale"):
        _restate(db_session, provenance="observed", base_bpm=None, rationale="  ")
    with pytest.raises(ValueError, match="same value"):
        _restate(db_session, bpm=173, provenance="observed", base_bpm=None)
    assert len(_rows(db_session)) == 1


def test_a_restatement_may_use_any_provenance(db_session):
    """A later measured maximum is also a restatement: observed or tested need no base."""
    _user(db_session)
    _seed(db_session)
    _restate(db_session, bpm=178, provenance="observed", base_bpm=None, rationale="hard run, H10 max 178",
             note="H10, field run")
    assert _rows(db_session)[-1].provenance == "observed"


def test_adjusted_requires_the_base_observation_and_a_rationale(db_session):
    _user(db_session)
    for kw, msg in ((dict(base_bpm=None), "adjusted needs --base-bpm"),
                    (dict(rationale=None), "adjusted needs --rationale"),
                    (dict(rationale="   "), "adjusted needs --rationale"),
                    (dict(base_bpm=173, bpm=173), "equals the base"),
                    (dict(base_bpm=29), "plausibility"), (dict(base_bpm=241), "plausibility")):
        with pytest.raises(ValueError, match=msg):
            _write(db_session, provenance="adjusted", restate=False, note="n",
                   **{**dict(base_bpm=173, rationale="r", bpm=175), **kw})
    assert db_session.query(models.UserHrmax).count() == 0


def test_a_first_adjusted_row_needs_no_restatement(db_session):
    """The two axes are separate: adjusted is how the number was reached, restate is its relation to history."""
    _user(db_session)
    _write(db_session, provenance="adjusted", base_bpm=173, rationale="r", bpm=175, note="n")
    h = db_session.query(models.UserHrmax).one()
    assert (h.provenance, h.base_bpm, h.restates_id) == ("adjusted", 173, None)


@pytest.mark.parametrize("prov", ["observed", "tested"])
def test_a_base_bpm_on_a_non_adjusted_row_is_refused(db_session, prov):
    _user(db_session)
    with pytest.raises(ValueError, match="only applies to provenance adjusted"):
        _write(db_session, provenance=prov, base_bpm=173)


def test_chained_restatements_each_correct_the_latest_not_the_seed(db_session):
    """Restating the same date twice corrects the row now in force (the chain's end), never the seed
    again, and the touched list is computed against the value then in force."""
    _user(db_session)
    _hc_row(db_session, 1, "a", date(2026, 9, 1))
    _seed(db_session)
    _restate(db_session)                                                            # 173 -> 175
    res = _restate(db_session, bpm=177, rationale="game max 177", note="H10 game")  # 175 -> 177
    seed, first, second = _rows(db_session)
    assert (first.restates_id, second.restates_id) == (seed.id, first.id)
    assert res["restates"]["id"] == first.id and res["restates"]["bpm"] == 175
    assert [(t["from"], t["to"]) for t in res["touched"]] == [(175, 177)]


def test_a_dry_run_restatement_writes_nothing_and_lists_the_rows_it_would_move(db_session):
    _user(db_session)
    for ssid, d in (("before", date(2026, 2, 1)), ("on", SEED), ("later", date(2026, 9, 28))):
        _hc_row(db_session, 1, ssid, d)
    _seed(db_session)
    res = _restate(db_session, dry_run=True)
    assert res["written"] is False and len(_rows(db_session)) == 1
    assert res["restates"]["bpm"] == 173
    assert {(t["date"], t["from"], t["to"]) for t in res["touched"]} == \
        {("2026-03-01", 173, 175), ("2026-09-28", 173, 175)}        # the 1 Feb row had no value and still has none


def test_a_restatement_moves_only_rows_before_the_next_dated_change(db_session):
    """Seed 173 (1 Mar), a dated change 190 from 1 Sep, then restate the seed to 175: rows in
    [1 Mar, 1 Sep) move 173 -> 175; rows from 1 Sep stay at 190. A restatement is not a blanket rewrite."""
    _user(db_session)
    for ssid, d in (("spring", date(2026, 5, 1)), ("autumn", date(2026, 9, 28))):
        _hc_row(db_session, 1, ssid, d)
    _seed(db_session)
    _write(db_session, effective_from=date(2026, 9, 1), bpm=190, provenance="tested")
    res = _restate(db_session, dry_run=True)
    assert [(t["date"], t["from"], t["to"]) for t in res["touched"]] == [("2026-05-01", 173, 175)]


def test_a_restatement_cannot_cross_users(db_session):
    _user(db_session)
    _user(db_session, 2)
    _seed(db_session, uid=2)
    with pytest.raises(ValueError, match="nothing to restate"):     # user 1 has no row to correct
        _restate(db_session, user_id=1)


def test_the_database_is_the_second_layer_for_the_rules_it_can_enforce(db_session):
    """The script refuses these first; the constraints refuse them if anything else ever tries. (Same user
    and same date are NOT database rules - see test_user_hrmax_restatement_schema - so they are asserted
    at the script and resolver instead.)"""
    import sqlalchemy as sa
    _user(db_session)
    _seed(db_session)
    _restate(db_session)
    seed_id = _rows(db_session)[0].id
    base = dict(user_id=1, hrmax_bpm=180, provenance="observed", note="n", rationale="r")
    for bad in (dict(effective_from=SEED, restates_id=seed_id),                    # seed already restated once
                dict(effective_from=SEED),                                         # second dated row on the date
                dict(effective_from=SEED, restates_id=9999)):                      # a target that does not exist
        db_session.add(models.UserHrmax(**{**base, **bad}))
        with pytest.raises(sa.exc.IntegrityError):
            db_session.commit()
        db_session.rollback()
    assert len(_rows(db_session)) == 2


def test_the_script_never_links_across_users_or_dates(db_session):
    """The two rules the database does not enforce, held by construction: the target is looked up by
    THIS user and THIS date, so the written row always carries both."""
    _user(db_session)
    _user(db_session, 2)
    _seed(db_session, uid=1)
    _write(db_session, user_id=2, effective_from=SEED, bpm=180, provenance="observed")
    _restate(db_session, user_id=2, bpm=182, provenance="observed", base_bpm=None)
    rows = {h.id: h for h in _rows(db_session)}
    for h in rows.values():
        if h.restates_id is not None:
            t = rows[h.restates_id]
            assert (t.user_id, t.effective_from) == (h.user_id, h.effective_from)


def test_main_restate_flow_and_output(db_session, monkeypatch, capsys):
    import database
    _user(db_session)
    monkeypatch.setattr(database, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    assert set_hrmax.main(["--user", "1", "--effective-from", "2026-03-01", "--bpm", "173",
                           "--provenance", "observed", "--note", "seed"]) == 0
    capsys.readouterr()
    argv = ["--user", "1", "--effective-from", "2026-03-01", "--bpm", "175", "--provenance", "adjusted",
            "--restate", "--base-bpm", "173", "--rationale", "bike lower bound", "--note", "Echo bike"]
    assert set_hrmax.main(argv + ["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "restatement" in out and "restates row #" in out and "173 bpm (observed)" in out
    assert db_session.query(models.UserHrmax).count() == 1
    assert set_hrmax.main(argv) == 0
    assert "WROTE" in capsys.readouterr().out and db_session.query(models.UserHrmax).count() == 2
    # refused paths exit 2 on stderr
    assert set_hrmax.main(["--user", "1", "--effective-from", "2026-03-01", "--bpm", "176",
                           "--provenance", "observed", "--note", "n"]) == 2
    assert "--restate" in capsys.readouterr().err
