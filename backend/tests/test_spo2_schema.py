"""Schema for Q150's raw Garmin overnight SpO2 capture: `spo2_nights`, `spo2_samples` and
`breathing_disruption_intervals`, model and Alembic in parity.

Rendered through `MigrationContext` + `Operations.context` and `ScriptDirectory` only, never
`alembic.command.*` (FEEDBACK section 59), as in `test_garmin_selfeval_schema`.
"""
import importlib.util
import io
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

import models

_BACKEND = Path(__file__).resolve().parent.parent
_REV = "e0d53feadc9d"
_MIG = _BACKEND / "migrations" / "versions" / f"{_REV}_add_spo2_nights_samples_breathing_intervals.py"
_TABLES = {"spo2_nights": models.Spo2Night, "spo2_samples": models.Spo2Sample,
           "breathing_disruption_intervals": models.BreathingDisruptionInterval}


def _load():
    spec = importlib.util.spec_from_file_location(f"mig_{_REV}", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ddl(fn, dialect="postgresql") -> str:
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name=dialect, opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        fn()
    return " ".join(buf.getvalue().split())


def test_upgrade_ddl_has_the_keys_the_cascades_and_the_nullability():
    ddl = _ddl(_load().upgrade)
    for t in _TABLES:
        assert f"CREATE TABLE {t}" in ddl
    assert "CONSTRAINT uq_spo2_night_user_date_source UNIQUE (user_id, captured_at, source)" in ddl
    assert "CONSTRAINT uq_spo2_sample_night_time UNIQUE (spo2_night_id, reading_time)" in ddl
    assert "CONSTRAINT uq_breathing_interval_night_seq UNIQUE (spo2_night_id, seq)" in ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl
    assert ddl.count("FOREIGN KEY(spo2_night_id) REFERENCES spo2_nights (id) ON DELETE CASCADE") == 2
    assert "reading_count INTEGER NOT NULL" in ddl and "gap_count INTEGER NOT NULL" in ddl
    # raw capture: a reading, its confidence and an interval's value may all be absent as sent
    assert "spo2_pct FLOAT," in ddl and "reading_confidence FLOAT," in ddl and "value FLOAT," in ddl


def test_downgrade_drops_children_before_the_parent():
    ddl = _ddl(_load().downgrade)
    assert ddl.index("DROP TABLE breathing_disruption_intervals") < ddl.index("DROP TABLE spo2_nights")
    assert ddl.index("DROP TABLE spo2_samples") < ddl.index("DROP TABLE spo2_nights")


def test_migration_and_model_agree_on_every_table_and_column():
    """Apply the migration to an empty SQLite and compare each table's columns and uniques with the model."""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _load().upgrade()
        insp = sa.inspect(conn)
        for name, model in _TABLES.items():
            assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in model.__table__.columns}, name
            mig_unique = {tuple(u["column_names"]) for u in insp.get_unique_constraints(name)}
            model_unique = {tuple(c.name for c in k.columns) for k in model.__table__.constraints
                            if isinstance(k, sa.UniqueConstraint)}
            assert mig_unique == model_unique, name


def test_the_revision_chains_from_the_prior_head_in_one_line():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1, "migration history branched"
    assert script.get_revision(_REV).down_revision == "e2a4c6d8f1b3"
    assert script.get_heads() == [_REV]
