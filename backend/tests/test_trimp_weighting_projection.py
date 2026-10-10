"""`scripts/trimp_weighting_projection.py` - the read-only Q230 projection. SYNTHETIC DATA ONLY (public repo):
every number below is invented for the test.

GATES
  W   the Banister-derived zone table: Z1 = 1, increasing, reserve-based (moves with resting HR), the band
      mid-points come from `hr_zones.BAND_PCT`, and a rest that leaves Z1 at or below rest is refused.
  S   the series IS the production rollup: the Edwards series equals `compute_window_series` fed an
      independently built daily dict with the metabolic tau; day bucketing is the AEST `_local_day`, the
      `rpe_complete_from` epoch and the as-of day cut as in `compute_load_metrics`.
  P   plumbing: identical weights give a zero delta; a Z1-only day loads the same under both tables.
  C   the integrity control flags an export that is not the production set.
  I   inputs: BOM, `+00` offsets, blank cells, missing columns named, the all-day median HR column is never
      read, no nadir is an error with no default.
  Q   the export statements run on the test DB and select exactly the production set; their columns are the
      models' columns (FEEDBACK 43).
  R   the script opens no database.
Mutations run against the real source and caught: the reserve ignored, normalised to Z5, UTC day
bucketing, a hard-coded fatigue tau, the epoch truncation dropped (listed in the PR body).
"""
import csv
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

import models
from hr_zones import BAND_PCT, HrmaxEntry
from load_events_metabolic import EDWARDS_WEIGHTS, compute_metabolic_load
from load_metrics import TAU_FATIGUE_DAYS, compute_window_series
from scripts import trimp_weighting_projection as tw

MALE = (0.64, 1.92)
AS_OF = date(2026, 9, 30)


def _utc(d, hh=1, mm=0):
    return datetime(2026, 9, d, hh, mm, tzinfo=timezone.utc)


def _row(sid, day, zones_s, *, hh=1, deposited=None, epoch=None, user=1, source="polar_v4", sport="Running"):
    """A SessionRow whose deposited load is the Edwards TRIMP of its zones unless given."""
    occurred = _utc(day, hh)
    dep = deposited if deposited is not None else sum(s / 60 * w for s, w in zip(zones_s, (1, 2, 3, 4, 5)))
    return tw.SessionRow(user_id=user, session_id=sid, session_date=occurred.date(), occurred_at=occurred,
                         sport=sport, source=source, deposited_load=dep, zones=tuple(zones_s), rpe_complete_from=epoch)


def _sessions(n_days=20):
    rows = []
    for i, d in enumerate(range(1, n_days + 1)):
        if d % 3 == 0:
            continue
        rows.append(_row(i + 1, d, [60 * (1 + i % 4), 120 * (1 + i % 3), 300, 60 * (i % 5), 30 * (i % 4)]))
    return rows


def _nadir(days=30, base=52.0):
    return [(date(2026, 9, d), base + (d % 3)) for d in range(1, days + 1)]


HRMAX = [HrmaxEntry(date(2026, 1, 1), 180, 1, None)]


def _project(sessions=None, **kw):
    kw.setdefault("user_id", 1)
    kw.setdefault("as_of", AS_OF)
    kw.setdefault("days", 30)
    return tw.project(sessions if sessions is not None else _sessions(), kw.pop("hrmax", HRMAX),
                      kw.pop("nadir", _nadir()), **kw)


# --------------------------------------------------------------------------- #
# W - the weight table                                                         #
# --------------------------------------------------------------------------- #

def test_w_midpoints_come_from_the_platform_bands():
    assert BAND_PCT == (50, 60, 70, 80, 90)
    assert tw.band_midpoints_pct() == {1: 55.0, 2: 65.0, 3: 75.0, 4: 85.0, 5: 95.0}


def test_w_the_table_matches_a_hand_computed_case():
    hrmax, rest = 190.0, 50.0

    def w(pct):
        x = (pct / 100 * hrmax - rest) / (hrmax - rest)
        return x * 0.64 * math.exp(1.92 * x)

    got = tw.banister_zone_weights(hrmax, rest, MALE)
    assert got[1] == 1.0
    assert got[3] == pytest.approx(w(75) / w(55))
    assert got[5] == pytest.approx(w(95) / w(55))
    assert got[5] == pytest.approx(6.79, abs=0.01)      # worked by hand: x1 .3893 -> w1 .526; x5 .9321 -> w5 3.573


def test_w_the_table_is_reserve_based_so_it_moves_with_resting_hr():
    lo, hi = tw.banister_zone_weights(180, 45, MALE), tw.banister_zone_weights(180, 65, MALE)
    assert all(lo[z] < lo[z + 1] for z in (1, 2, 3, 4)) and all(hi[z] < hi[z + 1] for z in (1, 2, 3, 4))
    assert hi[5] > lo[5] and hi[4] > lo[4]               # a higher resting HR steepens the table
    assert hi != lo


def test_w_a_rest_that_leaves_z1_at_or_below_rest_is_refused():
    with pytest.raises(tw.InputError, match="at or below rest"):
        tw.banister_zone_weights(100, 60, MALE)           # Z1 mid-point 55 bpm < rest 60
    with pytest.raises(tw.InputError, match="must lie between"):
        tw.banister_zone_weights(180, 200, MALE)


def test_w_edwards_is_the_production_table_and_trimp_matches_the_transform():
    assert tw.EDWARDS_WEIGHTS is EDWARDS_WEIGHTS
    zones = [300, 600, 900, 120, 60]
    prod = compute_metabolic_load({1: 300, 2: 600, 3: 900, 4: 120, 5: 60}).trimp
    assert tw.session_trimp(zones, EDWARDS_WEIGHTS) == pytest.approx(prod)


def test_w_the_coefficients_are_the_male_pair_and_sex_is_a_per_user_constant():
    assert tw.SEX_COEFFICIENTS == {"male": MALE} and tw.DEFAULT_SEX == "male"
    assert tw.USER_SEX.get(1, tw.DEFAULT_SEX) == "male"
    assert _project().sex == "male" and _project().coeffs == MALE


# --------------------------------------------------------------------------- #
# S - the series is the production rollup                                      #
# --------------------------------------------------------------------------- #

def test_s_the_edwards_series_equals_the_production_function_on_an_independent_dict():
    sessions = _sessions()
    p = _project(sessions)
    daily = {}
    for s in sessions:
        daily[s.occurred_at.date()] = daily.get(s.occurred_at.date(), 0.0) + s.deposited_load
    expect = compute_window_series(daily, AS_OF, tau_fatigue_days=TAU_FATIGUE_DAYS["metabolic"])
    got = {r["date"]: r for r in p.rows}
    assert len(got) == len(expect) == 30
    for m in expect:
        r = got[m.day.isoformat()]
        assert r["edwards_fitness"] == pytest.approx(m.fitness)
        assert r["edwards_fatigue"] == pytest.approx(m.fatigue)
        assert r["edwards_form"] == pytest.approx(m.form)
    assert TAU_FATIGUE_DAYS["metabolic"] == 4            # the tau-set in force; the test fails if it is retuned unseen


def test_s_days_are_bucketed_in_aest_not_utc():
    # 15:00Z on the 10th is 01:00 on the 11th in Brisbane
    late = _row(1, 10, [600, 0, 0, 0, 0], hh=15)
    daily = tw.daily_loads([late], EDWARDS_WEIGHTS, AS_OF)
    assert list(daily) == [date(2026, 9, 11)]


def test_s_the_epoch_and_the_as_of_cut_match_compute_load_metrics():
    rows = [_row(1, 2, [600, 0, 0, 0, 0], epoch=date(2026, 9, 5)),    # before the epoch: dropped
            _row(2, 6, [600, 0, 0, 0, 0], epoch=date(2026, 9, 5)),
            _row(3, 28, [600, 0, 0, 0, 0], epoch=date(2026, 9, 5))]   # after as_of below: dropped
    daily = tw.daily_loads(rows, EDWARDS_WEIGHTS, date(2026, 9, 20))
    assert set(daily) == {date(2026, 9, 6)}
    assert [s.session_id for s in tw._in_scope(rows, date(2026, 9, 20))] == [2]


# --------------------------------------------------------------------------- #
# P - plumbing                                                                 #
# --------------------------------------------------------------------------- #

def test_p_identical_weights_give_a_zero_delta_everywhere(monkeypatch):
    monkeypatch.setattr(tw, "banister_zone_weights", lambda *a, **k: dict(EDWARDS_WEIGHTS))
    p = _project()
    assert all(abs(r["form_delta"]) < 1e-12 for r in p.rows)
    for s in p.summaries:
        assert s["max_abs"] == pytest.approx(0) and s["scaled_max_abs"] == pytest.approx(0)
        assert s["load_ratio"] == pytest.approx(1.0)
    assert all(abs(m["delta"]) < 1e-12 for m in p.top)


def test_p_a_z1_only_day_loads_the_same_and_a_z5_day_loads_more():
    rows = [_row(1, 3, [1800, 0, 0, 0, 0]), _row(2, 4, [0, 0, 0, 0, 1800])] + _sessions()[4:]
    p = _project(rows)
    by = {r["date"]: r for r in p.rows}
    z1, z5 = by["2026-09-03"], by["2026-09-04"]
    assert z1["candidate_load"] == pytest.approx(z1["edwards_load"])      # Z1 = 1 in both: the normalisation
    assert z5["candidate_load"] > z5["edwards_load"] * 1.3


def test_p_the_shape_only_delta_removes_the_level_shift():
    p = _project()
    for s in p.summaries:
        assert s["load_ratio"] > 1.0                                       # the Z1 = 1 table is heavier overall
        assert s["scaled_mean_abs"] < s["mean_abs"]                        # rescaling removes the level part


def test_p_the_top_sessions_are_the_largest_absolute_moves_in_order_and_in_window():
    rows = _sessions() + [_row(90, 25, [0, 0, 0, 0, 3000]), _row(91, 26, [0, 0, 0, 1800, 0])]
    p = _project(rows, top_n=5)
    assert len(p.top) == 5
    assert [m["session_id"] for m in p.top][:2] == [90, 91]
    assert [abs(m["delta"]) for m in p.top] == sorted((abs(m["delta"]) for m in p.top), reverse=True)
    short = _project(rows, days=10)                                         # only 21-30 Sep are in window
    assert all(m["date"] >= "2026-09-21" for m in short.top)


def test_p_ties_break_deterministically():
    twins = [_row(5, 4, [0, 0, 0, 0, 600]), _row(4, 4, [0, 0, 0, 0, 600], hh=2)]
    p = _project(twins + _sessions()[3:], top_n=2)
    assert [m["session_id"] for m in p.top] == [5, 4]                       # same delta: earlier occurred_at first


def test_p_the_sensitivity_tables_are_minus_five_central_plus_five():
    p = _project()
    assert [o for o, _ in p.tables] == [-5.0, 0.0, 5.0]
    assert p.tables[2][1][5] > p.tables[1][1][5] > p.tables[0][1][5]
    assert [round(s["rhr"] - p.rhr, 6) for s in p.summaries] == [-5.0, 0.0, 5.0]
    assert _project(rhr_offset=2.0).tables[0][0] == -2.0


# --------------------------------------------------------------------------- #
# C - the integrity control                                                    #
# --------------------------------------------------------------------------- #

def test_c_a_matching_export_passes_and_a_tampered_one_is_flagged():
    ok = _project()
    assert ok.check_mismatches == 0 and ok.check_max_abs_diff < 1e-9
    assert "OK: all" in tw.render(ok)
    sessions = _sessions()
    bad = sessions[:3] + [_row(99, 12, [600, 600, 0, 0, 0], deposited=999.0)] + sessions[3:]
    p = _project(bad)
    assert p.check_mismatches == 1 and p.check_max_abs_diff > 900
    assert "WARNING: 1 of" in tw.render(p)


# --------------------------------------------------------------------------- #
# I - inputs                                                                   #
# --------------------------------------------------------------------------- #

def test_i_the_resting_hr_is_the_window_mean_of_non_null_nadirs_only():
    nadir = [(date(2026, 8, 1), 80.0)] + _nadir(30, base=50.0)       # one night outside the window
    p = _project(nadir=nadir)
    in_window = [b for d, b in nadir if d >= date(2026, 9, 1)]
    assert p.rhr == pytest.approx(sum(in_window) / len(in_window)) and p.rhr_n == 30
    assert p.rhr_min == min(in_window) and p.rhr_max == max(in_window)


def test_i_no_nadir_is_an_error_that_names_the_unusable_column():
    with pytest.raises(tw.InputError, match="resting_heart_rate"):
        _project(nadir=[])
    with pytest.raises(tw.InputError, match="no HRmax in force"):
        _project(hrmax=[HrmaxEntry(date(2026, 10, 1), 180, 1, None)])
    with pytest.raises(tw.InputError, match="no sessions"):
        _project(sessions=[])


def test_i_hrmax_follows_the_restatement_chain_and_warns_when_it_changes_inside_the_window():
    entries = [HrmaxEntry(date(2026, 1, 1), 170, 1, None), HrmaxEntry(date(2026, 1, 1), 176, 2, 1),
               HrmaxEntry(date(2026, 9, 15), 182, 3, None)]
    p = _project(hrmax=entries)
    assert p.hrmax == 182 and [e.bpm for e in p.hrmax_changes] == [182]
    assert "WARNING: an HRmax row dated 2026-09-15" in tw.render(p)
    quiet = _project(hrmax=entries[:2])
    assert quiet.hrmax == 176 and quiet.hrmax_changes == []


def _write(path, header, rows, bom=False):
    with open(path, "w", newline="", encoding="utf-8-sig" if bom else "utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return str(path)


SESSION_HEADER = ["user_id", "session_id", "session_date", "start_time", "occurred_at", "sport_name", "source",
                  "load", "z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds", "rpe_complete_from"]


def test_i_csv_parsing_handles_bom_short_offsets_blank_cells_and_the_editors_timestamp_shape(tmp_path):
    path = _write(tmp_path / "s.csv", SESSION_HEADER, [
        [1, 7, "2026-09-10", "2026-09-10 09:30:00+00", "2026-09-10 09:30:00+00", "Running", "polar_v4",
         "10.5", 60, "", 120, "", 0, ""],
        [1, 8, "2026-09-11", "", "2026-09-11T09:30:00Z", "", "health_connect", "3", 180, 0, 0, 0, 0, "2026-09-01"],
        [1, 9, "2026-09-12", "", "2026-09-12 09:30:00", "Ride", "polar_v4", "3", 180, 0, 0, 0, 0, ""],
    ], bom=True)
    a, b, c = tw.sessions_from_csv(path)
    assert a.occurred_at == datetime(2026, 9, 10, 9, 30, tzinfo=timezone.utc)
    assert a.zones == (60.0, None, 120.0, None, 0.0) and a.rpe_complete_from is None
    assert b.occurred_at == datetime(2026, 9, 11, 9, 30, tzinfo=timezone.utc) and b.sport == "unknown"
    assert b.rpe_complete_from == date(2026, 9, 1)
    assert c.occurred_at.tzinfo is not None and c.occurred_at.hour == 9           # naive read as UTC


def test_i_a_missing_column_is_named_and_a_bad_value_is_located(tmp_path):
    path = _write(tmp_path / "s.csv", [h for h in SESSION_HEADER if h != "z4_seconds"], [])
    with pytest.raises(tw.InputError, match="z4_seconds"):
        tw.sessions_from_csv(path)
    bad = _write(tmp_path / "b.csv", SESSION_HEADER,
                 [[1, 1, "2026-09-10", "", "not-a-time", "R", "polar_v4", 1, 1, 1, 1, 1, 1, ""]])
    with pytest.raises(tw.InputError, match="occurred_at"):
        tw.sessions_from_csv(bad)
    with pytest.raises(tw.InputError, match="not found"):
        tw.sessions_from_csv(str(tmp_path / "nope.csv"))


def _files(tmp_path, sessions=None, nadir_extra=False):
    sessions = sessions if sessions is not None else _sessions()
    s = _write(tmp_path / "sessions.csv", SESSION_HEADER, [
        [r.user_id, r.session_id, r.session_date, r.occurred_at.isoformat(), r.occurred_at.isoformat(), r.sport,
         r.source, r.deposited_load, *r.zones, ""] for r in sessions])
    h = _write(tmp_path / "hrmax.csv", ["id", "user_id", "effective_from", "hrmax_bpm", "restates_id"],
               [[1, 1, "2026-01-01", 180, ""]])
    header = ["user_id", "date", "hr_nadir_bpm", "hr_nadir_reason"] + (["resting_heart_rate"] if nadir_extra else [])
    n = _write(tmp_path / "nadir.csv", header,
               [[1, d.isoformat(), b, ""] + ([140] if nadir_extra else []) for d, b in _nadir()])
    return s, h, n


def test_i_the_all_day_median_hr_column_is_ignored_even_when_it_is_present(tmp_path, capsys):
    s, h, n = _files(tmp_path, nadir_extra=True)
    assert tw.main(["--sessions", s, "--hrmax", h, "--nadir", n, "--as-of", "2026-09-30", "--days", "30"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"mean hr_nadir_bpm over the window = 5[2-4]\.\d bpm", out)   # not 140


# --------------------------------------------------------------------------- #
# End to end through main()                                                    #
# --------------------------------------------------------------------------- #

def test_main_prints_every_section_and_writes_the_daily_csv(tmp_path, capsys):
    s, h, n = _files(tmp_path)
    out_csv = tmp_path / "daily.csv"
    code = tw.main(["--sessions", s, "--hrmax", h, "--nadir", n, "--as-of", "2026-09-30", "--days", "30",
                    "--csv-out", str(out_csv)])
    out = capsys.readouterr().out
    assert code == 0
    for needle in ("READ ONLY", "operator run", "PRIMARY (Banister 1991) was NOT read", "HRmax in force",
                   "Zone weights", "Edwards (metab-v1)", "RHR -5", "RHR +5", "Form delta", "max |delta|",
                   "sessions whose TRIMP moves most", "Integrity control", "Daily fitness / fatigue / form"):
        assert needle in out, needle
    assert all(ord(ch) < 128 for ch in out)                                        # a Windows console renders it
    rows = list(csv.DictReader(open(out_csv, encoding="utf-8")))
    assert len(rows) == 30 and rows[0]["date"] == "2026-09-01"
    assert set(rows[0]) >= {"edwards_form", "candidate_form", "form_delta"}


def test_main_refuses_several_users_without_a_choice_and_reports_input_errors(tmp_path, capsys):
    two = _sessions() + [_row(500, 5, [600, 0, 0, 0, 0], user=2)]
    s, h, n = _files(tmp_path, sessions=two)
    assert tw.main(["--sessions", s, "--hrmax", h, "--nadir", n, "--as-of", "2026-09-30"]) == 2
    assert "pass --user N" in capsys.readouterr().err
    assert tw.main(["--sessions", s, "--hrmax", h, "--nadir", n, "--user", "1", "--as-of", "2026-09-30", "--days", "30"]) == 0
    capsys.readouterr()
    assert tw.main(["--sessions", s]) == 2
    assert "--sessions, --hrmax and --nadir are all required" in capsys.readouterr().err
    assert tw.main(["--sessions", s, "--hrmax", h, "--nadir", n, "--days", "3"]) == 2


def test_main_print_sql_emits_three_single_line_statements(capsys):
    assert tw.main(["--print-sql", "--user", "1", "--days", "90"]) == 0
    out = capsys.readouterr().out
    stmts = [l for l in out.splitlines() if l.startswith("SELECT")]
    assert len(stmts) == 3 and all(l.endswith(";") for l in stmts)
    assert "interval '90 days'" in stmts[0] and "current_date - 90" in stmts[2]
    assert "resting_heart_rate" not in out                                          # never exported


# --------------------------------------------------------------------------- #
# Q - the export statements, run on the test database                          #
# --------------------------------------------------------------------------- #

def _runnable(sql):
    """The two Postgres-only cutoff fragments become a constant for SQLite; asserted present first so a
    reworded statement fails here instead of silently skipping the filter."""
    for frag in ("now() - interval '90 days'", "current_date - 90"):
        sql = sql.replace(frag, "'1900-01-01'") if frag in sql else sql
    return sql


def _seed(db):
    for uid in (1, 2):
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x",
                           rpe_complete_from=date(2026, 9, 1) if uid == 1 else None))
    db.flush()
    sess = {}
    for sid, uid in ((1, 1), (2, 1), (3, 1), (4, 2), (5, 1)):
        a = models.AerobicSession(id=sid, user_id=uid, source="polar_v4", session_date=date(2026, 9, 10),
                                  start_time=_utc(10), stop_time=_utc(10, 2), sport_name="Running",
                                  z1_seconds=60, z2_seconds=60, z3_seconds=60, z4_seconds=60, z5_seconds=60)
        db.add(a)
        sess[sid] = a
    db.flush()

    def ev(ref, uid, win="metabolic", ver="metab-v1", src="aerobic_sessions", load=15.0):
        db.add(models.LoadEvent(user_id=uid, source=src, source_ref=str(ref), load_window=win, occurred_at=_utc(10),
                                load=load, unit="trimp_edw_au", formula_version=ver))
    ev(1, 1, load=15.0)                       # selected
    ev(2, 1, ver="metab-v0")                  # an older formula version
    ev(3, 1, win="mechanical")                # another window
    ev(4, 2)                                  # another user
    ev(5, 1, src="hevy")                      # another source
    db.add(models.UserHrmax(user_id=1, effective_from=date(2026, 1, 1), hrmax_bpm=180, provenance="observed"))
    db.add(models.UserHrmax(user_id=2, effective_from=date(2026, 1, 1), hrmax_bpm=150, provenance="observed"))
    db.add(models.HealthConnectSync(user_id=1, date=date(2026, 9, 10), hr_nadir_bpm=51.5))
    db.add(models.HealthConnectSync(user_id=2, date=date(2026, 9, 10), hr_nadir_bpm=70.0))
    db.commit()


def test_q_the_sessions_statement_selects_exactly_the_production_set(db_session):
    _seed(db_session)
    stmts = tw.export_statements(1, 90)
    assert "now() - interval '90 days'" in stmts["sessions.csv"]
    rows = db_session.execute(text(_runnable(stmts["sessions.csv"]))).mappings().all()
    assert [r["session_id"] for r in rows] == [1]
    r = rows[0]
    assert set(r.keys()) == set(SESSION_HEADER)
    assert r["load"] == 15.0 and r["z5_seconds"] == 60 and r["source"] == "polar_v4"
    assert str(r["rpe_complete_from"]).startswith("2026-09-01")                    # the epoch rides along


def test_q_the_hrmax_and_nadir_statements_are_scoped_to_the_user(db_session):
    _seed(db_session)
    stmts = tw.export_statements(1, 90)
    assert "current_date - 90" in stmts["nadir.csv"]
    hr = db_session.execute(text(_runnable(stmts["hrmax.csv"]))).mappings().all()
    assert [(r["user_id"], r["hrmax_bpm"]) for r in hr] == [(1, 180)] and "restates_id" in hr[0].keys()
    nd = db_session.execute(text(_runnable(stmts["nadir.csv"]))).mappings().all()
    assert [(r["user_id"], r["hr_nadir_bpm"]) for r in nd] == [(1, 51.5)]
    assert "resting_heart_rate" not in " ".join(stmts.values())


def test_q_the_statement_for_another_user_selects_that_user(db_session):
    _seed(db_session)
    rows = db_session.execute(text(_runnable(tw.export_statements(2, 90)["sessions.csv"]))).mappings().all()
    assert [r["session_id"] for r in rows] == [4]


def test_q_each_statement_is_one_statement_with_no_line_break():
    for sql in tw.export_statements(1, 90).values():
        assert "\n" not in sql and sql.count(";") == 0 and sql.lstrip().upper().startswith("SELECT")


# --------------------------------------------------------------------------- #
# R - read only                                                                #
# --------------------------------------------------------------------------- #

def test_r_the_script_opens_no_database_and_writes_only_the_csv_it_is_asked_for():
    src = Path(tw.__file__).read_text(encoding="utf-8")
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    assert not re.search(r"^\s*(from|import)\s+database\b", code, re.M)
    for banned in ("SessionLocal", "create_engine", "psycopg", ".commit(", "session.add", "db.add", "INSERT INTO",
                   "UPDATE ", "DELETE FROM"):
        assert banned not in code, banned
    assert code.count("open(") == 2                                                  # one read, one --csv-out
