"""Migration c4e9a1f27b36 - `training_phases.vehicle_ranking` (Q212).

The Alembic chain cannot replay on SQLite, so this builds the PRE-migration `training_phases` table by
hand, runs the revision's `upgrade()` against it through an Alembic Operations context, and asserts the
backfill (behaviour-preserving, with the open phase set to standard by operator ruling), what it
prints, the CHECK, and the downgrade guard.
"""
import importlib.util
import io
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.exc import IntegrityError

import models

_PATH = (Path(__file__).resolve().parent.parent / "migrations" / "versions"
         / "c4e9a1f27b36_training_phase_vehicle_ranking.py")


def _load():
    spec = importlib.util.spec_from_file_location("mig_c4e9a1f27b36", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OLD_DDL = """
CREATE TABLE training_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    label VARCHAR(100) NOT NULL,
    probe_posture VARCHAR(10) NOT NULL,
    entered_on DATE NOT NULL,
    closed_on DATE,
    CONSTRAINT ck_training_phase_probe_posture CHECK (probe_posture IN ('suppressed','held'))
)
"""

# (label, probe_posture, closed_on) - ids 1..4 in insertion order.
_ROWS = [
    ("decompression", "suppressed", "2026-09-21"),    # closed, suppressed -> recovery_first
    ("maintenance", "held", "2026-10-04"),            # closed, held       -> standard
    ("old base", "suppressed", "2026-10-04"),         # closed, suppressed -> recovery_first
    ("aerobic base", "suppressed", None),             # the OPEN phase     -> standard (ruling)
]
_EXPECTED = {1: "recovery_first", 2: "standard", 3: "recovery_first", 4: "standard"}


@pytest.fixture()
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(sa.text(_OLD_DDL))
        for label, posture, closed_on in _ROWS:
            c.execute(sa.text(
                "INSERT INTO training_phases (user_id, label, probe_posture, entered_on, closed_on) "
                "VALUES (1, :l, :p, '2026-09-01', :c)"), {"l": label, "p": posture, "c": closed_on})
        yield c


def _upgrade(c):
    with Operations.context(MigrationContext.configure(c)):
        _load().upgrade()


def _downgrade(c):
    with Operations.context(MigrationContext.configure(c)):
        _load().downgrade()


def _values(c):
    return dict(c.execute(sa.text("SELECT id, vehicle_ranking FROM training_phases ORDER BY id")).fetchall())


def test_backfill_preserves_behaviour_and_flips_only_the_open_phase(conn):
    _upgrade(conn)
    assert _values(conn) == _EXPECTED
    # The open phase keeps its probe posture: only the ranking moved.
    assert conn.execute(sa.text("SELECT probe_posture FROM training_phases WHERE id = 4")).scalar() == "suppressed"


def test_the_migration_prints_every_id_and_value_it_wrote(conn, capsys):
    _upgrade(conn)
    out = capsys.readouterr().out
    for pid, value in _EXPECTED.items():
        line = next(ln for ln in out.splitlines() if f"id={pid} " in ln)
        assert f"vehicle_ranking={value}" in line
    line4 = next(ln for ln in out.splitlines() if "id=4 " in ln)
    assert "open phase (operator ruling)" in line4 and "probe_posture=suppressed" in line4
    assert "WARNING" not in out                      # exactly one open phase


def test_the_migration_warns_when_the_open_phase_count_is_not_one(conn, capsys):
    conn.execute(sa.text("UPDATE training_phases SET closed_on = '2026-10-05' WHERE id = 4"))
    _upgrade(conn)
    assert "expected exactly 1 open phase, found 0" in capsys.readouterr().out


def test_the_column_is_required_and_checked_after_the_upgrade(conn):
    _upgrade(conn)
    ins = ("INSERT INTO training_phases (user_id, label, probe_posture, vehicle_ranking, entered_on) "
           "VALUES (1, 'n', 'held', {v}, '2026-10-20')")
    conn.execute(sa.text(ins.format(v="'standard'")))                       # a legal value lands
    with pytest.raises(IntegrityError):
        conn.execute(sa.text(ins.format(v="'loaded_first'")))               # CHECK refuses
    with pytest.raises(IntegrityError):
        conn.execute(sa.text(ins.format(v="NULL")))                         # NOT NULL, no default


def test_downgrade_refuses_a_pair_the_old_column_cannot_express(conn):
    _upgrade(conn)                                   # row 4 is now suppressed + standard
    with pytest.raises(RuntimeError, match="Refusing to downgrade"):
        _downgrade(conn)


def test_downgrade_drops_the_column_when_every_pair_is_expressible(conn):
    _upgrade(conn)
    conn.execute(sa.text("UPDATE training_phases SET vehicle_ranking = 'recovery_first' WHERE id = 4"))
    _downgrade(conn)
    cols = [r[1] for r in conn.execute(sa.text("PRAGMA table_info(training_phases)")).fetchall()]
    assert "vehicle_ranking" not in cols and "probe_posture" in cols


def test_revision_chain_and_model_agree():
    mod = _load()
    assert mod.down_revision == "705a17c84d9a"
    assert mod._CK == "ck_training_phase_vehicle_ranking"
    names = {c.name for c in models.TrainingPhase.__table__.constraints}
    assert mod._CK in names
    col = models.TrainingPhase.__table__.c.vehicle_ranking
    assert col.nullable is False and col.default is None and col.server_default is None


def test_offline_sql_adds_the_column_then_constrains_it():
    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        _load().upgrade()
    ddl = " ".join(buf.getvalue().split())
    assert "ALTER TABLE training_phases ADD COLUMN vehicle_ranking VARCHAR(15)" in ddl
    assert "ALTER COLUMN vehicle_ranking SET NOT NULL" in ddl
    assert "ck_training_phase_vehicle_ranking CHECK (vehicle_ranking IN ('standard','recovery_first'))" in ddl
