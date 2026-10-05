"""S1 schema for Q159 stage 2: `hr_samples` + `user_hrmax`, model and Alembic in parity (G1).

The migration is rendered/applied through `MigrationContext` + `Operations.context` and
`ScriptDirectory` only — never `alembic.command.*`, whose `env.py` `fileConfig(...)` disables every
existing logger and breaks later log-asserting tests in the full run (FEEDBACK §59).
"""
import importlib.util
import io
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

import models

_BACKEND = Path(__file__).resolve().parent.parent
_MIG = _BACKEND / "migrations" / "versions" / "b4d6f8a1c3e5_add_hr_samples_and_user_hrmax.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig_b4d6f8a1c3e5", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ddl(fn, dialect="postgresql") -> str:
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name=dialect, opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        fn()
    return " ".join(buf.getvalue().split())


def test_upgrade_ddl_creates_both_tables_with_their_keys_and_the_provenance_check():
    ddl = _ddl(_load().upgrade)
    assert "CREATE TABLE hr_samples" in ddl and "CREATE TABLE user_hrmax" in ddl
    assert "CONSTRAINT uq_hr_sample UNIQUE (user_id, sample_time, source, source_package)" in ddl
    assert "source_package VARCHAR(255) NOT NULL" in ddl                     # coalesced to 'unknown', never NULL
    assert "CONSTRAINT uq_user_hrmax_effective UNIQUE (user_id, effective_from)" in ddl
    assert "CONSTRAINT ck_user_hrmax_provenance CHECK (provenance IN ('tested', 'observed'))" in ddl
    assert "estimated" not in ddl                                              # SCHEMA.md forbids it
    assert ddl.count("ON DELETE CASCADE") == 2


def test_downgrade_drops_both_tables():
    down = _ddl(_load().downgrade)
    assert "DROP TABLE hr_samples" in down and "DROP TABLE user_hrmax" in down


def test_the_revision_chains_from_the_prior_head_in_one_line():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)            # reads the versions dir; never runs env.py
    assert len(script.get_heads()) == 1, "migration history branched"
    rev = script.get_revision("b4d6f8a1c3e5")
    assert rev.down_revision == "a9c3e5f7b1d2"


def _shape(engine, table):
    insp = inspect(engine)
    cols = {c["name"]: (str(c["type"]).split("(")[0], bool(c["nullable"])) for c in insp.get_columns(table)}
    uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints(table)}
    fks = {(tuple(f["constrained_columns"]), f["referred_table"], (f["options"] or {}).get("ondelete"))
           for f in insp.get_foreign_keys(table)}
    return cols, uniques, fks


@pytest.mark.parametrize("table", ["hr_samples"])
def test_the_migration_builds_the_same_table_the_model_does(table):
    """Engine parity: apply the real migration on SQLite and compare with `create_all` from the
    models — columns, types, nullability, unique keys, FKs. (It caught `created_at` nullable in the
    migration vs NOT NULL in the model; the Postgres `\\d` diff of the two was identical after the fix.)

    `user_hrmax` is no longer compared here: `d6f8b1a3c5e7` reshaped it (partial keys, a composite FK,
    CHECKs: Postgres-only DDL), so its parity lives in `test_user_hrmax_restatement_schema.py`."""
    via_mig = create_engine("sqlite://")
    models.User.__table__.create(via_mig)
    with via_mig.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _load().upgrade()
    via_models = create_engine("sqlite://")
    models.Base.metadata.create_all(via_models)
    assert _shape(via_mig, table) == _shape(via_models, table)


def test_user_hrmax_rejects_an_estimated_row_at_the_database(db_session):
    db_session.add(models.User(id=1, email="a@x.com", hashed_password="x"))
    db_session.commit()
    db_session.add(models.UserHrmax(user_id=1, effective_from=__import__("datetime").date(2026, 6, 1),
                                    hrmax_bpm=173, provenance="estimated"))
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_the_unique_keys_refuse_duplicates(db_session):
    from datetime import date, datetime, timezone
    db_session.add(models.User(id=1, email="a@x.com", hashed_password="x"))
    db_session.commit()
    db_session.add(models.UserHrmax(user_id=1, effective_from=date(2026, 6, 1), hrmax_bpm=173, provenance="observed"))
    db_session.commit()
    db_session.add(models.UserHrmax(user_id=1, effective_from=date(2026, 6, 1), hrmax_bpm=180, provenance="tested"))
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()
    t = datetime(2026, 9, 28, tzinfo=timezone.utc)
    kw = dict(user_id=1, sample_time=t, bpm=100, source="health_connect", source_package="p")
    db_session.add(models.HrSample(**kw))
    db_session.commit()
    db_session.add(models.HrSample(**kw))
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_only_the_operator_script_writes_user_hrmax():
    """R2: no route, no UI, no chat write path, no update path. The model is CONSTRUCTED only in
    `scripts/set_hrmax.py`; nothing else in the app tree adds, updates or deletes it. (Reads are fine.)"""
    import re
    writers = []
    for path in _BACKEND.rglob("*.py"):
        rel = path.relative_to(_BACKEND).as_posix()
        if rel.startswith(("tests/", "migrations/")) or rel.endswith("/models.py") or rel == "models.py":
            continue
        src = path.read_text(encoding="utf-8")
        if re.search(r"UserHrmax\s*\(", src) or re.search(r"(delete|update)\([^)]*UserHrmax", src) \
                or re.search(r"UserHrmax[^\n]*\.(delete|update)\(", src):
            writers.append(rel)
    assert writers == ["scripts/set_hrmax.py"], writers
