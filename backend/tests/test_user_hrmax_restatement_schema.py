"""Schema for the HRmax restatement path (#383, #384): migration `d6f8b1a3c5e7`, model and constraints.

Three layers, because CI is SQLite-only and the migration is Postgres DDL (partial indexes, a self-FK,
named CHECKs) that SQLite cannot take through `Operations`:

1. DDL render (`as_sql`, postgresql dialect, no `env.py`: FEEDBACK §59) asserts the statements.
2. The MODEL's constraints are exercised on the FK-enforced SQLite substrate (FEEDBACK §33): every
   accept and refuse case below runs against real constraints, not a fiction.
3. `test_postgres_*` build the table both ways on a real Postgres and compare them, and run the
   downgrade guard. They SKIP unless `HEALTH_APP_TEST_PG_URL` names a Postgres the test may create and
   drop two scratch databases in (e.g. `postgresql://postgres@127.0.0.1:5544/postgres`); CI does not set
   it, so the parity claim for the migration is only as fresh as the last run with it set.
"""
import importlib.util
import io
import os
from datetime import date
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
_VERSIONS = _BACKEND / "migrations" / "versions"
_OLD = "b4d6f8a1c3e5_add_hr_samples_and_user_hrmax.py"
_NEW = "d6f8b1a3c5e7_user_hrmax_restatement_and_adjusted.py"


def _load(fname):
    spec = importlib.util.spec_from_file_location("mig_" + fname[:12], _VERSIONS / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ddl(fn) -> str:
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        fn()
    return " ".join(buf.getvalue().split())


# ---- 1. DDL render ----------------------------------------------------------------------------------

def test_the_revision_chains_from_the_prior_head_in_one_line():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1, "migration history branched"
    assert script.get_revision("d6f8b1a3c5e7").down_revision == "c5e7a9b1d3f2"


def test_upgrade_ddl_adds_the_columns_the_keys_the_fk_and_the_checks():
    ddl = _ddl(_load(_NEW).upgrade)
    for col in ("restates_id INTEGER", "base_bpm INTEGER", "rationale VARCHAR(1000)"):
        assert f"ALTER TABLE user_hrmax ADD COLUMN {col}" in ddl, col
    assert ("ADD CONSTRAINT fk_user_hrmax_restates FOREIGN KEY(restates_id) REFERENCES user_hrmax (id)") in ddl
    assert "FOREIGN KEY(restates_id, user_id" not in ddl         # no composite FK: retire_user refuses them
    assert "CREATE UNIQUE INDEX uq_user_hrmax_dated ON user_hrmax (user_id, effective_from) WHERE restates_id IS NULL" in ddl
    assert "CREATE UNIQUE INDEX uq_user_hrmax_restates ON user_hrmax (restates_id) WHERE restates_id IS NOT NULL" in ddl
    assert "DROP CONSTRAINT uq_user_hrmax_effective" in ddl
    assert "ADD CONSTRAINT ck_user_hrmax_provenance CHECK (provenance IN ('tested', 'observed', 'adjusted'))" in ddl
    assert "ck_user_hrmax_adjusted_base" in ddl and "ck_user_hrmax_rationale" in ddl
    assert "estimated" not in ddl                                       # SCHEMA.md still forbids it
    assert "DROP TABLE" not in ddl and "UPDATE" not in ddl and "DELETE" not in ddl     # touches no data


def test_the_new_unique_key_is_added_before_the_old_one_is_dropped():
    ddl = _ddl(_load(_NEW).upgrade)
    assert ddl.index("CREATE UNIQUE INDEX uq_user_hrmax_dated") < ddl.index("DROP CONSTRAINT uq_user_hrmax_effective")


def test_downgrade_ddl_restores_the_original_constraints():
    ddl = _ddl(_load(_NEW).downgrade)          # offline render skips the data guard (it needs a connection)
    assert "ADD CONSTRAINT uq_user_hrmax_effective UNIQUE (user_id, effective_from)" in ddl
    assert "ADD CONSTRAINT ck_user_hrmax_provenance CHECK (provenance IN ('tested', 'observed'))" in ddl
    for col in ("restates_id", "base_bpm", "rationale"):
        assert f"DROP COLUMN {col}" in ddl


# ---- 2. the model's constraints on the FK-enforced substrate ----------------------------------------------

def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _add(db, **kw):
    row = dict(user_id=1, effective_from=date(2026, 3, 1), hrmax_bpm=173, provenance="observed", note="n")
    row.update(kw)
    r = models.UserHrmax(**row)
    db.add(r)
    db.commit()
    return r


def _refused(db, **kw):
    db.add(models.UserHrmax(**{**dict(user_id=1, effective_from=date(2026, 3, 1), hrmax_bpm=173,
                                      provenance="observed", note="n"), **kw}))
    with pytest.raises(sa.exc.IntegrityError):
        db.commit()
    db.rollback()


def test_a_restatement_shares_its_targets_date_but_a_dated_row_cannot(db_session):
    _user(db_session)
    seed = _add(db_session)
    r = _add(db_session, hrmax_bpm=175, provenance="adjusted", base_bpm=173, rationale="r", restates_id=seed.id)
    assert (r.effective_from, r.restates_id) == (seed.effective_from, seed.id)
    _refused(db_session, hrmax_bpm=180)                                   # a second DATED row on the date


def test_the_fk_refuses_a_missing_target_but_not_a_cross_date_or_cross_user_link(db_session):
    """The database enforces that the target EXISTS. It does NOT enforce same user or same date: that is
    the script's rule (it finds its target by user and date) and the resolver's (it raises on a chain that
    breaks either), because a composite FK would have made `scripts/retire_user.py` refuse to run. This
    test pins the trade-off so nobody later assumes the database covers it. FKs are ON here (§33)."""
    assert db_session.execute(sa.text("PRAGMA foreign_keys")).scalar() == 1
    _user(db_session)
    _user(db_session, 2)
    seed = _add(db_session)
    _refused(db_session, restates_id=9999, rationale="r")                          # a target that does not exist
    cross_date = _add(db_session, effective_from=date(2026, 4, 1), restates_id=seed.id, rationale="r")
    cross_user = _add(db_session, user_id=2, restates_id=cross_date.id, rationale="r")
    assert (cross_date.effective_from, cross_user.user_id) == (date(2026, 4, 1), 2)   # accepted: not the DB's rule


def test_a_row_is_restated_at_most_once_so_a_chain_is_linear(db_session):
    _user(db_session)
    seed = _add(db_session)
    _add(db_session, hrmax_bpm=175, restates_id=seed.id, rationale="r")
    _refused(db_session, hrmax_bpm=176, restates_id=seed.id, rationale="r2")


def test_a_chain_extends_by_restating_the_latest(db_session):
    _user(db_session)
    seed = _add(db_session)
    second = _add(db_session, hrmax_bpm=175, restates_id=seed.id, rationale="r")
    third = _add(db_session, hrmax_bpm=177, restates_id=second.id, rationale="r2")
    assert third.restates_id == second.id


def test_the_provenance_check_admits_adjusted_and_still_refuses_estimated(db_session):
    _user(db_session)
    _add(db_session, provenance="adjusted", base_bpm=173, rationale="r", effective_from=date(2026, 5, 1))
    for prov in ("estimated", "age_predicted", "ADJUSTED"):
        _refused(db_session, provenance=prov, effective_from=date(2026, 6, 1))


def test_adjusted_and_base_bpm_go_together(db_session):
    _user(db_session)
    _refused(db_session, provenance="adjusted", rationale="r")                       # adjusted without a base
    _refused(db_session, provenance="observed", base_bpm=173)                        # a base without adjusted
    _refused(db_session, provenance="tested", base_bpm=173, rationale="r")


def test_an_adjustment_and_a_restatement_each_need_a_rationale(db_session):
    _user(db_session)
    seed = _add(db_session)
    _refused(db_session, provenance="adjusted", base_bpm=173)                        # adjusted, no rationale
    _refused(db_session, hrmax_bpm=175, restates_id=seed.id)                         # restatement, no rationale
    _add(db_session, effective_from=date(2026, 6, 1), hrmax_bpm=174)                 # a plain dated row needs none


def test_the_existing_seed_row_shape_satisfies_every_new_constraint(db_session):
    """User 1's real row (id 1, 173, observed, a note, no link, no base, no rationale) is the data the
    migration meets in prod: it must be legal under the new rules or the upgrade would fail."""
    _user(db_session)
    seed = _add(db_session, note="H10 chest strap max, Fitness sessions 2026-06-17 and 2026-07-17 (polar_v4 rows 35, 47)")
    assert (seed.restates_id, seed.base_bpm, seed.rationale) == (None, None, None)


# ---- 3. Postgres: parity with the model, and the downgrade guard ----------------------------------------------

_PG = os.getenv("HEALTH_APP_TEST_PG_URL")
pg = pytest.mark.skipif(not _PG, reason="HEALTH_APP_TEST_PG_URL not set (CI is SQLite-only)")


def _scratch(admin, name):
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(sa.text(f'CREATE DATABASE "{name}"'))
    return create_engine(sa.engine.make_url(_PG).set(database=name))


def _pg_shape(engine):
    insp = inspect(engine)
    t = "user_hrmax"
    cols = {c["name"]: (str(c["type"]), bool(c["nullable"])) for c in insp.get_columns(t)}
    uniques = {u["name"]: tuple(u["column_names"]) for u in insp.get_unique_constraints(t)}
    idx = {i["name"]: (tuple(i["column_names"]), bool(i["unique"]),
                       (i.get("dialect_options") or {}).get("postgresql_where"))
           for i in insp.get_indexes(t)}
    fks = {f["name"]: (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]),
                       (f["options"] or {}).get("ondelete"))
           for f in insp.get_foreign_keys(t)}
    checks = {c["name"]: " ".join(c["sqltext"].split()) for c in insp.get_check_constraints(t)}
    return cols, uniques, idx, fks, checks


@pytest.fixture()
def pg_engines():
    admin = create_engine(_PG)
    mig, mod = _scratch(admin, "hrmax_mig_test"), _scratch(admin, "hrmax_models_test")
    try:
        yield mig, mod
    finally:
        mig.dispose()
        mod.dispose()
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            for n in ("hrmax_mig_test", "hrmax_models_test"):
                c.execute(sa.text(f'DROP DATABASE IF EXISTS "{n}"'))
        admin.dispose()


def _apply(engine, *fns):
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            for fn in fns:
                fn()


@pg
def test_postgres_the_migration_builds_the_table_the_model_does(pg_engines):
    mig, mod = pg_engines
    models.User.__table__.create(mig)
    _apply(mig, _load(_OLD).upgrade, _load(_NEW).upgrade)
    models.User.__table__.create(mod)
    models.UserHrmax.__table__.create(mod)
    from_mig, from_models = _pg_shape(mig), _pg_shape(mod)
    for name, a, b in zip(("columns", "uniques", "indexes", "fks", "checks"), from_mig, from_models):
        assert a == b, f"{name} differ:\n migration: {a}\n model:     {b}"


@pg
def test_postgres_upgrade_keeps_the_seed_row_and_accepts_the_restatement(pg_engines):
    mig, _ = pg_engines
    models.User.__table__.create(mig)
    _apply(mig, _load(_OLD).upgrade)
    with mig.begin() as c:
        c.execute(sa.text("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@x.com', 'x')"))
        c.execute(sa.text("INSERT INTO user_hrmax (user_id, effective_from, hrmax_bpm, provenance, note) "
                          "VALUES (1, '2026-03-01', 173, 'observed', 'seed')"))
    _apply(mig, _load(_NEW).upgrade)
    with mig.begin() as c:
        c.execute(sa.text("INSERT INTO user_hrmax (user_id, effective_from, hrmax_bpm, provenance, note, "
                          "restates_id, base_bpm, rationale) VALUES (1, '2026-03-01', 175, 'adjusted', 'n', "
                          "(SELECT id FROM user_hrmax), 173, 'r')"))
        rows = c.execute(sa.text("SELECT hrmax_bpm, provenance, restates_id FROM user_hrmax ORDER BY id")).all()
    assert [(r[0], r[1]) for r in rows] == [(173, "observed"), (175, "adjusted")] and rows[1][2] is not None


@pg
def test_postgres_downgrade_restores_the_original_shape_and_refuses_over_a_restatement(pg_engines):
    mig, mod = pg_engines
    models.User.__table__.create(mig)
    models.User.__table__.create(mod)
    _apply(mod, _load(_OLD).upgrade)
    original = _pg_shape(mod)
    _apply(mig, _load(_OLD).upgrade, _load(_NEW).upgrade)
    with mig.begin() as c:
        c.execute(sa.text("INSERT INTO users (id, email, hashed_password) VALUES (1, 'a@x.com', 'x')"))
        c.execute(sa.text("INSERT INTO user_hrmax (user_id, effective_from, hrmax_bpm, provenance, note) "
                          "VALUES (1, '2026-03-01', 173, 'observed', 'seed')"))
        c.execute(sa.text("INSERT INTO user_hrmax (user_id, effective_from, hrmax_bpm, provenance, note, "
                          "restates_id, rationale) VALUES (1, '2026-03-01', 175, 'observed', 'n', "
                          "(SELECT id FROM user_hrmax), 'r')"))
    with pytest.raises(RuntimeError, match="refusing to downgrade"):
        _apply(mig, _load(_NEW).downgrade)
    assert _pg_shape(mig)[0].keys() >= {"restates_id", "base_bpm", "rationale"}      # nothing was dropped
    with mig.begin() as c:                                                           # operator clears it by hand
        c.execute(sa.text("DELETE FROM user_hrmax WHERE restates_id IS NOT NULL"))
    _apply(mig, _load(_NEW).downgrade)
    assert _pg_shape(mig) == original
    _apply(mig, _load(_NEW).upgrade)                                                 # and it re-applies
