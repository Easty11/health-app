"""Schema for `user_hr_anchors` (design 0010 §1; migration `e7b2a4c9d1f3`, SCHEMA.md §051).

Two layers, as for `user_hrmax` (`test_user_hrmax_restatement_schema.py`): CI is SQLite-only and the
migration is Postgres DDL (partial indexes, a self-FK, named CHECKs), so

1. the DDL is rendered (`as_sql`, postgresql dialect, no `env.py`: FEEDBACK §59) and asserted, and the
   migration's table is diffed against the model's (`create_all`) column by column;
2. the MODEL's constraints are exercised on the FK-enforced SQLite substrate (FEEDBACK §33).

Plus the single-writer guard: nothing but `hr_anchors.py` constructs, updates or deletes the model.
"""
import importlib.util
import io
import re
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

import models

_BACKEND = Path(__file__).resolve().parent.parent
_VERSIONS = _BACKEND / "migrations" / "versions"
_NEW = "e7b2a4c9d1f3_add_user_hr_anchors.py"


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


# ---- 1. DDL render and model parity ------------------------------------------------------------------

def test_the_revision_chains_from_the_prior_head_in_one_line():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1, "migration history branched"
    assert script.get_heads() == ["e7b2a4c9d1f3"]
    assert script.get_revision("e7b2a4c9d1f3").down_revision == "c4a8e2f6b190"


def test_upgrade_ddl_creates_the_table_with_its_keys_fk_and_checks():
    ddl = _ddl(_load(_NEW).upgrade)
    assert "CREATE TABLE user_hr_anchors" in ddl
    for col in ("kind VARCHAR(10) NOT NULL", "effective_from DATE NOT NULL", "bpm INTEGER NOT NULL",
                "provenance VARCHAR(20) NOT NULL", "note VARCHAR(1000) NOT NULL", "restates_id INTEGER",
                "rationale VARCHAR(1000)"):
        assert col in ddl, col
    assert "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE" in ddl
    assert "CONSTRAINT fk_user_hr_anchor_restates FOREIGN KEY(restates_id) REFERENCES user_hr_anchors (id)" in ddl
    assert "FOREIGN KEY(restates_id, user_id" not in ddl                 # no composite FK: retire_user refuses them
    assert "CREATE UNIQUE INDEX uq_user_hr_anchor_dated ON user_hr_anchors (user_id, kind, effective_from) WHERE restates_id IS NULL" in ddl
    assert "CREATE UNIQUE INDEX uq_user_hr_anchor_restates ON user_hr_anchors (restates_id) WHERE restates_id IS NOT NULL" in ddl
    assert "CONSTRAINT ck_user_hr_anchor_kind CHECK (kind IN ('lthr', 'rhr'))" in ddl
    assert "CONSTRAINT ck_user_hr_anchor_provenance CHECK (provenance IN ('tested', 'observed', 'device_estimated', 'stated'))" in ddl
    assert "CONSTRAINT ck_user_hr_anchor_rationale CHECK (restates_id IS NULL OR rationale IS NOT NULL)" in ddl
    assert "estimated'" not in ddl.replace("device_estimated", "")        # no age-predicted provenance
    assert not re.search(r"ALTER TABLE user_hrmax|\bUPDATE |\bDELETE FROM", ddl)   # touches nothing else


def test_downgrade_refuses_while_rows_exist_and_drops_only_this_table(db_session):
    """The data guard needs a connection, so it is exercised on the SQLite substrate through the migration
    module's `downgrade` with `op` bound to this session (the DROP statements never run on a refusal)."""
    from alembic.migration import MigrationContext as _Ctx
    _user(db_session)
    _add(db_session)
    mod = _load(_NEW)
    ctx = _Ctx.configure(db_session.connection())
    with Operations.context(ctx):
        with pytest.raises(RuntimeError, match="refusing to drop user_hr_anchors"):
            mod.downgrade()
    assert db_session.query(models.UserHrAnchor).count() == 1
    src = (_VERSIONS / _NEW).read_text(encoding="utf-8")
    assert src.count("op.drop_table(") == 1 and "op.drop_table('user_hr_anchors')" in src


def test_the_migration_builds_the_same_table_the_model_does():
    """Every model column, with its Postgres type and nullability, appears verbatim in the rendered CREATE
    TABLE, and the DDL declares no column the model lacks (SQLite cannot take the partial indexes through
    `Operations`; the index predicates are asserted in the DDL test above)."""
    from sqlalchemy.dialects import postgresql
    ddl = _ddl(_load(_NEW).upgrade)
    body = ddl.split("CREATE TABLE user_hr_anchors (", 1)[1].split("CREATE INDEX ix_user_hr_anchors_id")[0]
    table = models.UserHrAnchor.__table__
    assert body.startswith(" id SERIAL NOT NULL, ")                     # the PK; SERIAL is the model's autoincrement
    for c in table.columns:
        if c.name == "id":
            continue
        typ = c.type.compile(dialect=postgresql.dialect())
        want = f", {c.name} {typ}" + (" DEFAULT now()," if c.name == "created_at" else
                                       " NOT NULL" if not c.nullable else ",")
        assert want in body, want
    ddl_cols = set(re.findall(r"(?:^ | )([a-z_]+) (?:SERIAL|INTEGER|VARCHAR|DATE|TIMESTAMP)", body))
    assert ddl_cols == {c.name for c in table.columns}


# ---- 2. the model's constraints on the FK-enforced substrate --------------------------------------------

def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _add(db, **kw):
    row = dict(user_id=1, kind="rhr", effective_from=date(2026, 3, 1), bpm=51, provenance="stated", note="n")
    row.update(kw)
    r = models.UserHrAnchor(**row)
    db.add(r)
    db.commit()
    return r


def _refused(db, **kw):
    db.add(models.UserHrAnchor(**{**dict(user_id=1, kind="rhr", effective_from=date(2026, 3, 1), bpm=51,
                                         provenance="stated", note="n"), **kw}))
    with pytest.raises(sa.exc.IntegrityError):
        db.commit()
    db.rollback()


def test_one_dated_row_per_user_kind_and_date_and_a_restatement_may_share_the_date(db_session):
    _user(db_session)
    seed = _add(db_session)
    _add(db_session, kind="lthr", bpm=158, provenance="device_estimated")       # another kind, same date: fine
    _refused(db_session, bpm=48)                                                  # a second DATED rhr on the date
    r = _add(db_session, bpm=48, restates_id=seed.id, rationale="better read")
    assert (r.effective_from, r.restates_id) == (seed.effective_from, seed.id)
    _refused(db_session, bpm=47, restates_id=seed.id, rationale="again")        # restated at most once


def test_a_restatement_needs_a_rationale_and_a_real_target(db_session):
    _user(db_session)
    seed = _add(db_session)
    _refused(db_session, bpm=48, restates_id=seed.id)                            # no rationale
    _refused(db_session, bpm=48, restates_id=999, rationale="r")                 # FK: the target must exist


@pytest.mark.parametrize("bad", [dict(kind="hrmax"), dict(kind="max_hr"), dict(provenance="estimated"),
                                 dict(provenance="adjusted"), dict(provenance="OBSERVED")])
def test_the_closed_sets_are_enforced_at_the_database(db_session, bad):
    _user(db_session)
    _refused(db_session, **bad)


def test_a_note_is_required(db_session):
    _user(db_session)
    _refused(db_session, note=None)


def test_rows_cascade_with_their_user(db_session):
    _user(db_session)
    _add(db_session)
    db_session.delete(db_session.get(models.User, 1))
    db_session.commit()
    assert db_session.query(models.UserHrAnchor).count() == 0


# ---- the single writer --------------------------------------------------------------------------------

def test_only_the_anchor_writer_module_writes_user_hr_anchors():
    """No route body, no UI, no chat write path, no update or delete path. The model is CONSTRUCTED only in
    `hr_anchors.py`; nothing else in the app tree adds, updates or deletes it. (Reads are fine.)"""
    writers = []
    for path in _BACKEND.rglob("*.py"):
        rel = path.relative_to(_BACKEND).as_posix()
        if rel.startswith(("tests/", "migrations/")) or rel == "models.py":
            continue
        src = path.read_text(encoding="utf-8")
        if re.search(r"UserHrAnchor\s*\(", src) or re.search(r"(delete|update)\([^)]*UserHrAnchor", src) \
                or re.search(r"UserHrAnchor[^\n]*\.(delete|update)\(", src):
            writers.append(rel)
    assert writers == ["hr_anchors.py"], writers
