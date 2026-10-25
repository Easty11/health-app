"""Schema for the Garmin Personal API migration (M1, `c4a8e2f6b190`): model and Alembic in parity, additive
only, no data step in the revision. Rendered through `MigrationContext` + `Operations.context` and
`ScriptDirectory`, never `alembic.command.*` (FEEDBACK section 59)."""
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
_REV = "c4a8e2f6b190"
_MIG = _BACKEND / "migrations" / "versions" / f"{_REV}_garmin_personal_api_tables.py"
_NEW_TABLES = {
    "garmin_raw_payloads": models.GarminRawPayload, "sleep_nights": models.SleepNight,
    "spo2_hourly": models.Spo2Hourly, "daily_physiology": models.DailyPhysiology,
    "hr_zone_config_snapshots": models.HrZoneConfigSnapshot, "integration_lane_status": models.IntegrationLaneStatus,
}


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


def test_upgrade_ddl_has_the_keys_the_cascades_and_the_jsonb_columns():
    ddl = _ddl(_load().upgrade)
    for t in _NEW_TABLES:
        assert f"CREATE TABLE {t}" in ddl
    for uq in ("uq_garmin_raw_payload UNIQUE (user_id, endpoint, ref, payload_sha256)",
               "uq_sleep_night_user_date_source UNIQUE (user_id, captured_at, source)",
               "uq_spo2_hourly_user_hour_source UNIQUE (user_id, hour_start, source)",
               "uq_daily_physiology_user_date_source UNIQUE (user_id, date, source)",
               "uq_integration_lane_user_lane UNIQUE (user_id, lane)"):
        assert f"CONSTRAINT {uq}" in ddl, uq
    assert ddl.count("FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE") == len(_NEW_TABLES)
    assert "payload JSONB NOT NULL" in ddl and "sleep_scores_subs JSONB" in ddl and "sleep_need JSONB" in ddl


def test_the_revision_is_additive_only_every_added_column_is_nullable_and_nothing_is_dropped_or_written():
    ddl = _ddl(_load().upgrade)
    assert "DROP" not in ddl and "UPDATE" not in ddl and "INSERT" not in ddl      # no data step: that is M2, held
    for col in ("key_expires_on DATE", "access_token_encrypted TEXT", "access_token_expires_at TIMESTAMP WITH TIME ZONE",
                "transport VARCHAR(20)"):
        assert f"ADD COLUMN {col}" in ddl and f"ADD COLUMN {col} NOT NULL" not in ddl, col


def test_downgrade_drops_what_upgrade_made_and_nothing_else():
    ddl = _ddl(_load().downgrade)
    for t in _NEW_TABLES:
        assert f"DROP TABLE {t}" in ddl
    for c, t in (("transport", "hrv_readings"), ("access_token_expires_at", "user_integrations"),
                 ("access_token_encrypted", "user_integrations"), ("key_expires_on", "user_integrations")):
        assert f"ALTER TABLE {t} DROP COLUMN {c}" in ddl
    assert ddl.count("DROP TABLE") == len(_NEW_TABLES)


def test_migration_and_model_agree_on_every_new_table_and_on_the_added_columns():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE user_integrations (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE hrv_readings (id INTEGER PRIMARY KEY)"))
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            _load().upgrade()
        insp = sa.inspect(conn)
        for name, model in _NEW_TABLES.items():
            assert {c["name"] for c in insp.get_columns(name)} == {c.name for c in model.__table__.columns}, name
            mig_unique = {tuple(u["column_names"]) for u in insp.get_unique_constraints(name)}
            model_unique = {tuple(c.name for c in k.columns) for k in model.__table__.constraints
                            if isinstance(k, sa.UniqueConstraint)}
            assert mig_unique == model_unique, name
            assert {i["name"] for i in insp.get_indexes(name)} == {i.name for i in model.__table__.indexes}, name
        added = {"user_integrations": {"key_expires_on", "access_token_encrypted", "access_token_expires_at"},
                 "hrv_readings": {"transport"}}
        for table, cols in added.items():
            assert cols <= {c["name"] for c in insp.get_columns(table)}
            model_cols = {c.name for c in models.Base.metadata.tables[table].columns}
            assert cols <= model_cols


def test_downgrade_then_upgrade_round_trips_on_a_scratch_database():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        for t in ("users", "user_integrations", "hrv_readings"):
            conn.execute(sa.text(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)"))
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig = _load()
            mig.upgrade()
            mig.downgrade()
            mig.upgrade()
        assert set(_NEW_TABLES) <= set(sa.inspect(conn).get_table_names())


def test_the_revision_chains_from_the_prior_head_in_one_line():
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    assert len(script.get_heads()) == 1, "migration history branched"
    assert script.get_revision(_REV).down_revision == "b8f3d6a2c915"
    assert _REV in {r.revision for r in script.walk_revisions(base="base", head=script.get_heads()[0])}


def test_new_tables_are_not_read_by_the_cbti_engine_nor_by_any_arbiter():
    """Sleep efficiency here is a device-window figure and reads higher than the diary SE; nothing that
    titrates a sleep window may read it. The readers (Q243, DECISIONS_LOG) are `reads/recovery_night.py`
    (the MCP recovery table, and the candidates the snapshot and the card resolve) and
    `reads/snapshot_reads.py` (which asks only for the newest night's date); every other reader, the
    CBT-I engine and every arbiter stays out."""
    import re
    forbidden = re.compile(r"SleepNight|sleep_nights|DailyPhysiology|daily_physiology|Spo2Hourly|spo2_hourly"
                           r"|GarminRawPayload|HrZoneConfigSnapshot")
    root = _BACKEND
    for sub in ("cbti", "engine", "reads", "load_metrics.py", "load_events.py", "hr_zones.py", "hr_nadir.py"):
        target = root / sub
        files = [target] if target.is_file() else list(target.rglob("*.py"))
        for f in files:
            if f in (root / "reads" / "recovery_night.py", root / "reads" / "snapshot_reads.py"):
                continue                                         # the readers (Q243)
            assert not forbidden.search(f.read_text(encoding="utf-8")), f"{f} reads a Personal API table"
    reader = (root / "reads" / "recovery_night.py").read_text(encoding="utf-8")
    assert "models.SleepNight" in reader and "models.DailyPhysiology" in reader
    assert "Spo2Hourly" not in reader and "HrZoneConfigSnapshot" not in reader    # the zones figure is never read
