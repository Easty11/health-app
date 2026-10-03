"""polar-sport-map: `import_polar.SPORT_NAMES` is the Polar Flow sport-id list, and the backfill script
relabels stored rows to it.

Evidence behind the table: id 4 displays as "Jogging" and id 55 as "Cross-trainer" in Polar Flow,
the opposite of the old table ("Walking", "Fitness"); 17 of the old 20 entries disagreed with the
list. The table is the id space BOTH Polar transports carry (the v4 parser reuses the export parser),
so these tests drive both."""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
from connectors.polar import PolarV4Client
from import_polar import SPORT_NAMES, _parse_session
from reads.psychological_reads import _duration_min_by_day
from scripts import polar_sport_backfill as backfill
from sport_classes import is_non_training

GAPS = {21, 26, 31, 37, *range(72, 83), 93, 97, 98, 99, 106}


def _raw(sport_id, *, sid="p1", start=datetime(2026, 8, 5, 7, 0)):
    """A Polar session body as the export and v4 both deliver it (`sport: {id}`)."""
    return {
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "stopTime": (start + timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%S"),
        "timezoneOffsetMinutes": 0,
        "identifier": {"id": sid},
        "sport": {"id": sport_id},
        "hrAvg": 140, "hrMax": 170,
        "durationMillis": 40 * 60 * 1000,
    }


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()
    return uid


# ── the table ─────────────────────────────────────────────────────────────────────

def test_table_is_the_flow_list_with_its_gaps_left_unmapped():
    assert len(SPORT_NAMES) == 122
    assert {int(k) for k in SPORT_NAMES} == set(range(1, 143)) - GAPS
    assert all(k == str(int(k)) and v and v == v.strip() and v.isascii() for k, v in SPORT_NAMES.items())


@pytest.mark.parametrize("sport_id,name", [
    (1, "Running"), (2, "Cycling"), (3, "Walking"), (4, "Jogging"), (8, "Rowing"),
    (15, "Strength training"), (16, "Other outdoor"), (17, "Treadmill running"),
    (27, "Trail running"), (36, "Track&field running"), (43, "Rugby"), (55, "Cross-trainer"),
    (57, "Functional training"), (117, "Indoor rowing"), (126, "Core"), (134, "LES MILLS SH'BAM"),
])
def test_ids_carry_the_published_names(sport_id, name):
    assert SPORT_NAMES[str(sport_id)] == name


@pytest.mark.parametrize("sport_id,name", [(4, "Jogging"), (55, "Cross-trainer"), (16, "Other outdoor"),
                                           (43, "Rugby")])
def test_both_transports_label_the_ids_seen_in_prod_the_same_way(sport_id, name):
    """Row 95 (id 4) was stored "Walking" against Polar Flow's "Jogging"; ids 16 and 43 were NULL / the
    wrong name. Export and v4 go through one parser, so one table."""
    raw = _raw(sport_id)
    export = _parse_session(raw)
    v4 = PolarV4Client.parse_session(raw)
    assert (export["sport_id"], export["sport_name"], export["source"]) == (str(sport_id), name, "polar_flow_export")
    assert (v4["sport_id"], v4["sport_name"], v4["source"]) == (str(sport_id), name, "polar_v4")


@pytest.mark.parametrize("sport_id", [21, 72, 106, 999])
def test_an_id_outside_the_list_keeps_sport_name_null_and_retains_the_id(sport_id):
    f = PolarV4Client.parse_session(_raw(sport_id))
    assert f["sport_name"] is None and f["sport_id"] == str(sport_id)


# ── NON_TRAINING_SPORTS flips, through the real parser and the real consumer ──────

def _felt_minutes(db, sport_id):
    """Store one session parsed from `sport_id` and read it back through felt load's duration reader."""
    uid = _user(db)
    fields = PolarV4Client.parse_session(_raw(sport_id))
    db.add(models.AerobicSession(user_id=uid, **fields))
    db.commit()
    return _duration_min_by_day(db, uid)


def test_old_walking_id_4_is_now_jogging_and_counts_as_training(db_session):
    assert is_non_training("Walking") and not is_non_training("Jogging")     # the line it crosses
    assert _felt_minutes(db_session, 4) == {date(2026, 8, 5): (40.0, 1)}


def test_id_3_is_now_walking_and_contributes_nothing(db_session):
    assert not is_non_training("Cross-country skiing") and is_non_training("Walking")
    assert _felt_minutes(db_session, 3) == {}


def test_old_yoga_id_36_is_now_track_and_field_running_and_counts(db_session):
    assert is_non_training("Yoga") and not is_non_training("Track&field running")
    assert _felt_minutes(db_session, 36) == {date(2026, 8, 5): (40.0, 1)}


def test_the_real_yoga_pilates_stretching_ids_are_still_non_training(db_session):
    for sid in (33, 65, 66):
        assert is_non_training(SPORT_NAMES[str(sid)]), sid


# ── the backfill ──────────────────────────────────────────────────────────────────

def _row(db, uid, source, sid, sport_id, sport_name, day=date(2026, 6, 1), pkg=None):
    db.add(models.AerobicSession(user_id=uid, source=source, source_session_id=sid, session_date=day,
                                 sport_id=sport_id, sport_name=sport_name, source_package=pkg))
    db.commit()
    return db.query(models.AerobicSession).filter_by(source_session_id=sid).one().id


def _seed(db):
    _user(db, 1)
    _user(db, 2)
    ids = {
        "v4_walk": _row(db, 1, "polar_v4", "a", "4", "Walking", date(2026, 10, 1)),        # row-95 shape
        "flow_fit": _row(db, 1, "polar_flow_export", "b", "55", "Fitness"),
        "null16": _row(db, 1, "polar_v4", "c", "16", None),                                # NULL -> named
        "already": _row(db, 1, "polar_v4", "d", "1", "Running"),                           # correct
        "unmapped": _row(db, 1, "polar_v4", "e", "21", "Whatever"),                        # id not in list
        "no_id": _row(db, 1, "polar_v4", "f", None, "Walking"),                            # nothing to derive
        "hc": _row(db, 1, "health_connect", "g", "56", "Running", pkg="com.garmin"),       # not Polar
        "other_user": _row(db, 2, "polar_v4", "h", "3", "Cross-country skiing"),
    }
    return ids


def test_plan_lists_exactly_the_polar_rows_whose_label_changes(db_session):
    ids = _seed(db_session)
    got = {p["id"]: p for p in backfill.plan(db_session)}
    assert set(got) == {ids["v4_walk"], ids["flow_fit"], ids["null16"], ids["other_user"]}
    p = got[ids["v4_walk"]]
    assert (p["source"], p["session_date"], p["sport_id"], p["old"], p["new"]) == \
        ("polar_v4", "2026-10-01", "4", "Walking", "Jogging")
    assert (got[ids["flow_fit"]]["old"], got[ids["flow_fit"]]["new"]) == ("Fitness", "Cross-trainer")
    assert (got[ids["null16"]]["old"], got[ids["null16"]]["new"]) == (None, "Other outdoor")


def test_plan_flags_the_rows_that_cross_the_non_training_line(db_session):
    ids = _seed(db_session)
    got = {p["id"]: p["class_flip"] for p in backfill.plan(db_session)}
    assert got[ids["v4_walk"]] is True       # Walking -> Jogging: now training
    assert got[ids["other_user"]] is True    # Cross-country skiing -> Walking: now non-training
    assert got[ids["flow_fit"]] is False and got[ids["null16"]] is False


def test_plan_can_be_limited_to_one_user(db_session):
    ids = _seed(db_session)
    assert ids["other_user"] not in {p["id"] for p in backfill.plan(db_session, 1)}
    assert {p["id"] for p in backfill.plan(db_session, 2)} == {ids["other_user"]}


def test_plan_alone_writes_nothing(db_session):
    _seed(db_session)
    before = sorted((r.id, r.sport_id, r.sport_name) for r in db_session.query(models.AerobicSession))
    backfill.plan(db_session)
    db_session.expire_all()
    assert before == sorted((r.id, r.sport_id, r.sport_name) for r in db_session.query(models.AerobicSession))


def test_apply_sets_sport_name_only_on_the_planned_rows_and_is_idempotent(db_session):
    ids = _seed(db_session)
    rows = backfill.plan(db_session)
    assert backfill.apply(db_session, rows) == 4
    db_session.expire_all()
    name = {k: db_session.get(models.AerobicSession, v).sport_name for k, v in ids.items()}
    assert name == {"v4_walk": "Jogging", "flow_fit": "Cross-trainer", "null16": "Other outdoor",
                    "already": "Running", "unmapped": "Whatever", "no_id": "Walking", "hc": "Running",
                    "other_user": "Walking"}
    # sport_id is never written; the untouched rows keep their id
    assert db_session.get(models.AerobicSession, ids["v4_walk"]).sport_id == "4"
    assert db_session.get(models.AerobicSession, ids["no_id"]).sport_id is None
    assert backfill.plan(db_session) == []                      # a second run lists nothing


def test_apply_skips_a_row_re_keyed_since_the_plan(db_session):
    ids = _seed(db_session)
    rows = backfill.plan(db_session)
    r = db_session.get(models.AerobicSession, ids["v4_walk"])
    r.sport_id = "1"
    db_session.commit()
    assert backfill.apply(db_session, rows) == 3
    assert db_session.get(models.AerobicSession, ids["v4_walk"]).sport_name == "Walking"


class _Session:
    """The fixture session with `close` a no-op, standing in for database.SessionLocal()."""
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


def _run_main(monkeypatch, db, argv, capsys):
    import database
    monkeypatch.setattr(database, "SessionLocal", lambda: _Session(db))
    code = backfill.main(argv)
    return code, capsys.readouterr().out


def test_main_is_report_only_without_apply(db_session, monkeypatch, capsys):
    ids = _seed(db_session)
    code, out = _run_main(monkeypatch, db_session, [], capsys)
    assert code == 0 and "REPORT ONLY" in out and "WROTE" not in out
    assert f"#{ids['v4_walk']} u1 polar_v4 2026-10-01 sport_id=4  Walking -> Jogging  [class flips]" in out
    assert "Polar rows whose sport_name changes: 4" in out and "Rows crossing the non-training line: 2" in out
    db_session.expire_all()
    assert db_session.get(models.AerobicSession, ids["v4_walk"]).sport_name == "Walking"


def test_main_apply_writes_and_names_the_refresh_step(db_session, monkeypatch, capsys):
    ids = _seed(db_session)
    code, out = _run_main(monkeypatch, db_session, ["--apply", "--user", "1"], capsys)
    assert code == 0 and "WROTE: 3 row(s)" in out and "refresh_load" in out
    db_session.expire_all()
    assert db_session.get(models.AerobicSession, ids["v4_walk"]).sport_name == "Jogging"
    assert db_session.get(models.AerobicSession, ids["other_user"]).sport_name == "Cross-country skiing"
