"""Schema for `garmin_activity_metrics` (migration `a9d3f5b7c2e4`, SCHEMA.md §052): DDL render and model parity.

Rendered/applied through `MigrationContext` + `Operations.context` and `ScriptDirectory` only, never
`alembic.command.*` (FEEDBACK section 59), as in `test_garmin_selfeval_schema`.
"""
import importlib.util
import io
import re
from pathlib import Path

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import models

_BACKEND = Path(__file__).resolve().parent.parent
_MIG = _BACKEND / "migrations" / "versions" / "a9d3f5b7c2e4_add_garmin_activity_metrics.py"
_TABLE = "garmin_activity_metrics"
_METRICS = ("calories", "bmr_calories", "te_aerobic", "te_anaerobic", "training_load", "resp_avg", "resp_max",
            "resp_min", "recovery_hr", "intensity_min_moderate", "intensity_min_vigorous", "water_estimated_ml",
            "body_battery_delta", "duration_s")


def _load():
    spec = importlib.util.spec_from_file_location("mig_a9d3f5b7c2e4", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ddl(fn) -> str:
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        fn()
    return " ".join(buf.getvalue().split())


def test_upgrade_ddl_has_the_key_the_nullable_metrics_and_the_raw_summary():
    ddl = _ddl(_load().upgrade)
    assert f"CREATE TABLE {_TABLE}" in ddl
    assert "garmin_activity_id BIGINT NOT NULL" in ddl                         # ids exceed int32
    assert "CONSTRAINT uq_garmin_activity_metric UNIQUE (user_id, garmin_activity_id)" in ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl
    for col in _METRICS:
        assert f"{col} FLOAT," in ddl, col                                       # nullable, stored as received
    assert "te_label VARCHAR(64)," in ddl and "start_time_gmt TIMESTAMP WITH TIME ZONE," in ddl
    assert "summary_raw JSONB NOT NULL" in ddl and "fetched_at TIMESTAMP WITH TIME ZONE NOT NULL" in ddl
    assert "aerobic_session" not in ddl                                          # R1: no stored link
    assert not re.search(r"ALTER TABLE|\bUPDATE |\bDELETE FROM", ddl)           # touches nothing else


def test_downgrade_drops_only_this_table():
    ddl = _ddl(_load().downgrade)
    assert f"DROP TABLE {_TABLE}" in ddl and ddl.count("DROP TABLE") == 1


def test_the_revision_is_the_single_head_and_chains_from_the_anchors_migration():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["a9d3f5b7c2e4"], "migration history branched"
    assert script.get_revision("a9d3f5b7c2e4").down_revision == "e7b2a4c9d1f3"


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
        with Operations.context(MigrationContext.configure(conn)):
            _load().upgrade()
    mod = create_engine("sqlite://")
    with mod.begin() as conn:
        models.Base.metadata.tables["users"].create(conn)
        models.Base.metadata.tables[_TABLE].create(conn)
    assert _shape(mig) == _shape(mod)
