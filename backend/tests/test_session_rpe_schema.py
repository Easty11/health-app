"""Schema for the source-neutral sRPE store: `session_rpe_observations`, model and Alembic in parity, and the
verbatim copy of `garmin_activity_selfevals` the migration performs.

Rendered/applied through `MigrationContext` + `Operations.context` and `ScriptDirectory` only, never
`alembic.command.*` (FEEDBACK section 59), as in `test_garmin_selfeval_schema`.
"""
import importlib.util
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import models

_BACKEND = Path(__file__).resolve().parent.parent
_MIG = _BACKEND / "migrations" / "versions" / "e2a4c6d8f1b3_add_session_rpe_observations.py"
_TABLE = "session_rpe_observations"


def _load():
    spec = importlib.util.spec_from_file_location("mig_e2a4c6d8f1b3", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ddl(fn, dialect="postgresql") -> str:
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name=dialect, opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        fn()
    return " ".join(buf.getvalue().split())


def test_upgrade_ddl_has_the_key_the_nullability_and_the_cascade():
    ddl = _ddl(_load().upgrade)
    assert f"CREATE TABLE {_TABLE}" in ddl
    assert "CONSTRAINT uq_session_rpe_obs_capture UNIQUE (user_id, source, source_activity_ref, captured_at)" in ddl
    assert "rpe_raw FLOAT," in ddl and "rpe_cr10 FLOAT," in ddl and "feel INTEGER," in ddl   # nullable: unrated is a row
    assert "raw_scale VARCHAR(32) NOT NULL" in ddl and "provenance JSONB NOT NULL" in ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl
    assert "INSERT INTO" not in ddl                      # offline mode cannot read rows: the copy is skipped, not mangled


def test_downgrade_drops_the_table():
    assert f"DROP TABLE {_TABLE}" in _ddl(_load().downgrade)


def test_the_revision_chains_from_the_prior_head_in_one_line():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1, "migration history branched"
    assert script.get_revision("e2a4c6d8f1b3").down_revision == "295da687b02e"


def _shape(engine):
    insp = inspect(engine)
    cols = {c["name"]: (str(c["type"]).split("(")[0], bool(c["nullable"])) for c in insp.get_columns(_TABLE)}
    uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints(_TABLE)}
    fks = {(tuple(f["constrained_columns"]), f["referred_table"], (f["options"] or {}).get("ondelete"))
           for f in insp.get_foreign_keys(_TABLE)}
    return cols, uniques, fks


def _parents(conn):
    for t in ("users", "aerobic_sessions", "garmin_activity_selfevals"):
        models.Base.metadata.tables[t].create(conn)


def test_the_migration_builds_the_same_table_the_model_does():
    mig = create_engine("sqlite://")
    with mig.begin() as conn:
        _parents(conn)
        with Operations.context(MigrationContext.configure(conn)):
            _load().upgrade()
    mod = create_engine("sqlite://")
    with mod.begin() as conn:
        _parents(conn)
        models.Base.metadata.tables[_TABLE].create(conn)
    assert _shape(mig) == _shape(mod)


# -- the data step: Garmin rows copied verbatim ---------------------------------------------------------------

T = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)


def _seed_old(conn):
    conn.execute(sa.text("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@x', 'x'), (2, 'b@x', 'x')"))
    conn.execute(sa.text(
        "INSERT INTO aerobic_sessions (id, user_id, source, source_session_id, session_date) "
        "VALUES (7, 1, 'health_connect', 'hc-7', '2026-10-03')"))
    old = models.Base.metadata.tables["garmin_activity_selfevals"]
    s = T - timedelta(hours=9)
    conn.execute(old.insert(), [
        # a rated, linked row; the same activity re-rated later (a second row); an unrated marker; another user's;
        # a Garmin id above int32; a half-step value.
        dict(id=1, user_id=1, garmin_activity_id=24564069469, captured_at=T, rpe_cr10=4.0, feel=25,
             garmin_type="strength_training", start_time=s, stop_time=s + timedelta(minutes=45), aerobic_session_id=7),
        dict(id=2, user_id=1, garmin_activity_id=24564069469, captured_at=T + timedelta(days=1), rpe_cr10=6.0, feel=50,
             garmin_type="strength_training", start_time=s, stop_time=s + timedelta(minutes=45), aerobic_session_id=7),
        dict(id=3, user_id=1, garmin_activity_id=12, captured_at=T, rpe_cr10=None, feel=None,
             garmin_type="running", start_time=s, stop_time=None, aerobic_session_id=None),
        dict(id=4, user_id=2, garmin_activity_id=24564069469, captured_at=T, rpe_cr10=7.0, feel=None,
             garmin_type="cycling", start_time=s, stop_time=s + timedelta(hours=1), aerobic_session_id=None),
        dict(id=5, user_id=1, garmin_activity_id=13, captured_at=T, rpe_cr10=4.5, feel=75,
             garmin_type=None, start_time=s, stop_time=s + timedelta(minutes=10), aerobic_session_id=None),
    ])


def _migrated():
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        _parents(conn)
        _seed_old(conn)
        with Operations.context(MigrationContext.configure(conn)):
            _load().upgrade()
    return eng


def test_every_garmin_row_is_copied_verbatim_with_its_capture_time_and_window():
    eng = _migrated()
    with eng.connect() as conn:
        old = conn.execute(sa.text(
            "SELECT user_id, CAST(garmin_activity_id AS TEXT), start_time, stop_time, rpe_cr10, feel, captured_at "
            "FROM garmin_activity_selfevals ORDER BY id")).all()
        new = conn.execute(sa.text(
            f"SELECT user_id, source_activity_ref, start_time, stop_time, rpe_cr10, feel, captured_at "
            f"FROM {_TABLE} ORDER BY id")).all()
        assert len(new) == len(old) == 5
        assert [tuple(r) for r in new] == [tuple(r) for r in old]            # byte-for-byte, captured_at included
        srcs = conn.execute(sa.text(f"SELECT DISTINCT source, raw_scale FROM {_TABLE}")).all()
        assert [tuple(r) for r in srcs] == [("garmin", "garmin_0_100")]


def test_the_raw_value_is_the_cr10_value_times_ten_and_null_stays_null():
    eng = _migrated()
    with eng.connect() as conn:
        got = conn.execute(sa.text(f"SELECT rpe_raw, rpe_cr10 FROM {_TABLE} ORDER BY id")).all()
    assert [tuple(r) for r in got] == [(40.0, 4.0), (60.0, 6.0), (None, None), (70.0, 7.0), (45.0, 4.5)]


def test_the_old_link_and_row_id_travel_as_provenance_only():
    eng = _migrated()
    with eng.connect() as conn:
        rows = conn.execute(sa.select(models.Base.metadata.tables[_TABLE].c.provenance)
                            .order_by(models.Base.metadata.tables[_TABLE].c.id)).scalars().all()
    assert rows[0] == {"garmin_type": "strength_training", "aerobic_session_id": 7,
                       "copied_from": "garmin_activity_selfevals", "copied_from_id": 1}
    assert rows[2]["aerobic_session_id"] is None and rows[2]["garmin_type"] == "running"


def test_the_old_table_is_left_exactly_as_it_was():
    eng = _migrated()
    with eng.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM garmin_activity_selfevals")).scalar() == 5
        assert conn.execute(sa.text("SELECT aerobic_session_id FROM garmin_activity_selfevals WHERE id = 1")).scalar() == 7


def test_an_empty_old_table_copies_nothing_and_does_not_fail():
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        _parents(conn)
        with Operations.context(MigrationContext.configure(conn)):
            _load().upgrade()
        assert conn.execute(sa.text(f"SELECT count(*) FROM {_TABLE}")).scalar() == 0
