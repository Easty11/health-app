"""Schema for Q209 path (a): `garmin_activity_selfevals`, model and Alembic in parity.

Rendered/applied through `MigrationContext` + `Operations.context` and `ScriptDirectory` only, never
`alembic.command.*` (FEEDBACK section 59), as in `test_hr_zones_schema`.
"""
import importlib.util
import io
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import models

_BACKEND = Path(__file__).resolve().parent.parent
_MIG = _BACKEND / "migrations" / "versions" / "c5e7a9b1d3f2_add_garmin_activity_selfevals.py"
_TABLE = "garmin_activity_selfevals"


def _load():
    spec = importlib.util.spec_from_file_location("mig_c5e7a9b1d3f2", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ddl(fn, dialect="postgresql") -> str:
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name=dialect, opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        fn()
    return " ".join(buf.getvalue().split())


def test_upgrade_ddl_has_the_keys_the_nullability_and_the_set_null_link():
    ddl = _ddl(_load().upgrade)
    assert f"CREATE TABLE {_TABLE}" in ddl
    assert "garmin_activity_id BIGINT NOT NULL" in ddl                    # ids exceed int32
    assert "rpe_cr10 FLOAT," in ddl and "feel INTEGER," in ddl            # nullable: an unrated sighting is a row
    assert "CONSTRAINT uq_garmin_selfeval_capture UNIQUE (user_id, garmin_activity_id, captured_at)" in ddl
    assert "FOREIGN KEY(aerobic_session_id) REFERENCES aerobic_sessions (id) ON DELETE SET NULL" in ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl


def test_downgrade_drops_the_table():
    assert f"DROP TABLE {_TABLE}" in _ddl(_load().downgrade)


def test_the_revision_chains_from_the_prior_head_in_one_line():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1, "migration history branched"
    assert script.get_revision("c5e7a9b1d3f2").down_revision == "b4d6f8a1c3e5"


def _shape(engine):
    insp = inspect(engine)
    cols = {c["name"]: (str(c["type"]).split("(")[0], bool(c["nullable"])) for c in insp.get_columns(_TABLE)}
    uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints(_TABLE)}
    fks = {(tuple(f["constrained_columns"]), f["referred_table"], (f["options"] or {}).get("ondelete"))
           for f in insp.get_foreign_keys(_TABLE)}
    return cols, uniques, fks


def test_the_migration_builds_the_same_table_the_model_does():
    mig = create_engine("sqlite://")
    with mig.begin() as conn:
        models.Base.metadata.tables["users"].create(conn)
        models.Base.metadata.tables["aerobic_sessions"].create(conn)
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _load().upgrade()
    mod = create_engine("sqlite://")
    with mod.begin() as conn:
        models.Base.metadata.tables["users"].create(conn)
        models.Base.metadata.tables["aerobic_sessions"].create(conn)
        models.Base.metadata.tables[_TABLE].create(conn)
    assert _shape(mig) == _shape(mod)
