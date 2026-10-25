"""Migration e5b2c8a91d47 - "Indoor cycling" joins the open phase's metabolic `device_sports` (21 Oct 2026).

The Alembic chain cannot replay on SQLite, so this builds the `training_phases` table by hand, runs the
revision's `upgrade()` through an Alembic Operations context, and asserts what it changed, what it left
alone, what it printed, and that the edited list is the one that makes the 21 Oct session count.
"""
import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

import models
from engine import resolver

_BACKEND = Path(__file__).resolve().parent.parent
_PATH = _BACKEND / "migrations" / "versions" / "e5b2c8a91d47_open_phase_metabolic_add_indoor_cycling.py"

LIVE = ["Biking Stationary", "Biking", "Jogging", "Running", "Elliptical", "Cross-trainer",
        "Treadmill running", "Rowing", "Indoor rowing", "Cycling", "Hiking"]


def _load():
    spec = importlib.util.spec_from_file_location("mig_e5b2c8a91d47", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _micro(*slot_lists):
    return {"sub_cycle_days": 7, "sub_cycles": [
        {"label": "ABCD"[i], "slots": slots} for i, slots in enumerate(slot_lists)]}


def _metabolic(sports, q=7):
    return {"load_window": "metabolic", "device_sports": list(sports), "sessions_per_cycle": q, "minutes": 30}


PILATES = {"activity": "Pilates", "device_sports": ["Pilates"], "sessions_per_cycle": 2, "minutes": 50}
STRENGTH = {"capacity": "strength", "sessions_per_cycle": 3, "minutes": 60}

_DDL = """
CREATE TABLE training_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    label VARCHAR(100) NOT NULL,
    entered_on DATE NOT NULL,
    closed_on DATE,
    microcycle JSON
)
"""


@pytest.fixture()
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(sa.text(_DDL))
        yield c


def _insert(c, uid, label, closed_on, micro):
    c.execute(sa.text(
        "INSERT INTO training_phases (user_id, label, entered_on, closed_on, microcycle) "
        "VALUES (:u, :l, '2026-10-08', :c, :m)"),
        {"u": uid, "l": label, "c": closed_on, "m": json.dumps(micro) if micro is not None else None})


def _micro_of(c, pid):
    raw = c.execute(sa.text("SELECT microcycle FROM training_phases WHERE id = :i"), {"i": pid}).scalar()
    return json.loads(raw) if raw is not None else None


def _upgrade(c):
    with Operations.context(MigrationContext.configure(c)):
        _load().upgrade()


def _downgrade(c):
    with Operations.context(MigrationContext.configure(c)):
        _load().downgrade()


def test_the_open_phase_gains_the_sport_at_the_end_and_nothing_else_moves(conn, capsys):
    before = _micro(([PILATES, _metabolic(LIVE), STRENGTH]))
    _insert(conn, 1, "aerobic base", None, before)
    _upgrade(conn)
    after = _micro_of(conn, 1)
    slots = after["sub_cycles"][0]["slots"]
    assert slots[1]["device_sports"] == LIVE + ["Indoor cycling"]       # appended, order kept
    assert slots[0] == PILATES and slots[2] == STRENGTH                 # other slots untouched
    assert after["sub_cycle_days"] == 7 and after["sub_cycles"][0]["label"] == "A"
    assert "id=1 user_id=1: added 'Indoor cycling' to 1 metabolic slot(s)" in capsys.readouterr().out


def test_a_closed_phase_is_never_touched(conn):
    old = _micro([_metabolic(LIVE)])
    _insert(conn, 1, "decompression", "2026-10-08", old)
    _insert(conn, 1, "aerobic base", None, _micro([_metabolic(LIVE)]))
    _upgrade(conn)
    assert _micro_of(conn, 1) == old
    assert "Indoor cycling" in _micro_of(conn, 2)["sub_cycles"][0]["slots"][0]["device_sports"]


def test_it_is_idempotent_and_never_duplicates(conn, capsys):
    _insert(conn, 1, "aerobic base", None, _micro([_metabolic(LIVE)]))
    _upgrade(conn)
    once = _micro_of(conn, 1)
    capsys.readouterr()
    _upgrade(conn)
    assert _micro_of(conn, 1) == once
    assert once["sub_cycles"][0]["slots"][0]["device_sports"].count("Indoor cycling") == 1
    assert "already lists 'Indoor cycling'; unchanged" in capsys.readouterr().out


def test_a_differently_cased_entry_counts_as_present(conn):
    mixed = _micro([_metabolic(LIVE + ["indoor CYCLING"])])
    _insert(conn, 1, "aerobic base", None, mixed)
    _upgrade(conn)
    assert _micro_of(conn, 1) == mixed


def test_every_sub_cycle_with_a_metabolic_slot_is_edited(conn, capsys):
    _insert(conn, 1, "aerobic base", None, _micro([_metabolic(LIVE)], [STRENGTH], [_metabolic(["Running"])]))
    _upgrade(conn)
    subs = _micro_of(conn, 1)["sub_cycles"]
    assert subs[0]["slots"][0]["device_sports"][-1] == "Indoor cycling"
    assert subs[1]["slots"] == [STRENGTH]
    assert subs[2]["slots"][0]["device_sports"] == ["Running", "Indoor cycling"]
    assert "added 'Indoor cycling' to 2 metabolic slot(s)" in capsys.readouterr().out


def test_an_open_phase_with_no_metabolic_slot_is_left_alone_and_says_so(conn, capsys):
    only = _micro([PILATES, STRENGTH])
    _insert(conn, 1, "aerobic base", None, only)
    _upgrade(conn)
    assert _micro_of(conn, 1) == only
    assert "no metabolic slot; unchanged" in capsys.readouterr().out


def test_an_open_phase_without_a_microcycle_is_left_alone(conn):
    _insert(conn, 1, "baseline-ish", None, None)
    _upgrade(conn)
    assert _micro_of(conn, 1) is None


def test_no_open_phase_warns_and_writes_nothing(conn, capsys):
    closed = _micro([_metabolic(LIVE)])
    _insert(conn, 1, "old", "2026-10-08", closed)
    _upgrade(conn)
    assert _micro_of(conn, 1) == closed
    assert "WARNING: no open phase found" in capsys.readouterr().out


def test_the_downgrade_leaves_the_sport_in_place(conn):
    _insert(conn, 1, "aerobic base", None, _micro([_metabolic(LIVE)]))
    _upgrade(conn)
    once = _micro_of(conn, 1)
    _downgrade(conn)
    assert _micro_of(conn, 1) == once


def test_the_revision_chains_from_c4e9a1f27b36_and_the_history_has_one_head():
    """Not "is the head": a later revision (b8f3d6a2c915, Rugby) now sits on top of it. What stays true is the
    parent and that it is an ancestor of the one head."""
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, "migration history branched"
    assert script.get_revision("e5b2c8a91d47").down_revision == "c4e9a1f27b36"
    assert "e5b2c8a91d47" in {r.revision for r in script.walk_revisions(base="base", head=heads[0])}


# ---- the point of it: the edited list makes the 21 Oct session count -----------------------------------

def test_the_edited_list_counts_the_21_oct_indoor_cycling_session(conn, db_session):
    """Same session, same window: unclaimed under the list as it stood, counted under the migrated one."""
    _insert(conn, 1, "aerobic base", None, _micro([PILATES, _metabolic(LIVE), STRENGTH]))
    before = _micro_of(conn, 1)
    _upgrade(conn)
    after = _micro_of(conn, 1)

    u = models.User(email="mig@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    entered = date(2026, 10, 8)
    ph = models.TrainingPhase(
        user_id=u.id, label="aerobic base", probe_posture="suppressed", vehicle_ranking="standard",
        microcycle=before, entered_on=entered, asserted_by="user", asserted_on=entered, source="api")
    db_session.add(ph)
    db_session.add(models.AerobicSession(
        user_id=u.id, source="polar_v4", source_session_id="polar-21oct", session_date=date(2026, 10, 21),
        start_time=datetime(2026, 10, 21, 6, 30, tzinfo=timezone.utc),
        stop_time=datetime(2026, 10, 21, 7, 5, tzinfo=timezone.utc), sport_name="Indoor cycling",
        duration_minutes=35.0, z1_seconds=60, z2_seconds=180, z3_seconds=300, z4_seconds=540, z5_seconds=960))
    db_session.commit()

    today = date(2026, 10, 21)

    def metabolic(res):
        return next(s for s in res["slots"] if s["kind"] == "load_window")

    res = resolver.resolve(db_session, u.id, today=today)
    assert metabolic(res)["done"] == 0
    assert [x["reason"] for x in res["uncounted"]] == ["unclaimed_session"]

    ph.microcycle = after
    db_session.commit()
    res = resolver.resolve(db_session, u.id, today=today)
    assert metabolic(res)["done"] == 1
    assert res["uncounted"] == []
