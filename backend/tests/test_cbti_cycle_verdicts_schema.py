"""Step 1 of the CBT-I verdict store: the `cbti_cycle_verdicts` table (DECISIONS_LOG #437, #440).

Nothing reads or writes the table yet, so this pins only its SHAPE: every named check fires on the
row it exists to refuse, the unique keys and the two partial indexes behave, the foreign keys cascade
as designed, and the migration builds exactly what the model does. SYNTHETIC rows only.

The Alembic chain cannot replay on SQLite, so the migration is run through an Alembic Operations
context against hand-built prerequisite tables, as test_open_phase_indoor_cycling_migration.py does.
"""
import importlib.util
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

import database
import models

_BACKEND = Path(__file__).resolve().parent.parent
_MIG_PATH = next((_BACKEND / "migrations" / "versions").glob("b8e4d2f61a39_*.py"))
START = date(2026, 10, 21)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_b8e4d2f61a39", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def world(db_session):
    u = models.User(email="verdict@x.io", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    block = models.CBTIBlock(user_id=u.id, opened_on=date(2026, 7, 24), wake_anchor="05:45", open_reason="test")
    db_session.add(block)
    db_session.commit()

    def _rx(eff, decision="adopt"):
        r = models.CBTIPrescription(block_id=block.id, effective_from=eff, prescribed_lights_out="21:48",
                                    wake_anchor="05:45", window_minutes=477, decision=decision)
        db_session.add(r)
        db_session.commit()
        return r

    return {"db": db_session, "user": u, "block": block, "rx": _rx(START), "rx2": _rx(START + timedelta(days=5), "extend"),
            "make_rx": _rx}


def _v(w, start=START, **over):
    base = dict(block_id=w["block"].id, prescription_id=w["rx"].id, cycle_start=start,
                cycle_end=start + timedelta(days=3), status="applied", decision="hold", outcome="hold",
                sufficient=True, converged=False, reason="r", window_minutes=477, rec_window_minutes=477,
                rec_lights_out="21:48", basis_tst_min=400, basis_se_pct=90.0, basis_nights_n=4,
                basis_nights_logged=4, excluded_nights={}, basis_ledger=[],
                ruleset_version="cbti-basis/2026-10-21.1")
    base.update(over)
    return models.CBTICycleVerdict(**base)


def _insert(w, v):
    w["db"].add(v)
    w["db"].commit()
    return v


def _refused(w, v, constraint=None):
    w["db"].add(v)
    with pytest.raises(IntegrityError) as ei:
        w["db"].commit()
    w["db"].rollback()
    if constraint:
        assert constraint in str(ei.value), str(ei.value)


# ── the four kinds of row the engine writes ──────────────────────────────────

def test_the_four_legal_kinds_of_verdict_are_accepted(world):
    w = world
    _insert(w, _v(w, START))                                                        # a merits HOLD, applied
    _insert(w, _v(w, START + timedelta(days=4), sufficient=False, outcome="no_decision",
                  basis_tst_min=None, basis_se_pct=None, basis_nights_n=2))          # an insufficiency HOLD, applied
    _insert(w, _v(w, START + timedelta(days=8), status="offered", decision="extend", outcome="extend"))   # a move
    c = _insert(w, _v(w, START + timedelta(days=12)))                                # an adherence HOLD, applied
    assert w["db"].query(models.CBTICycleVerdict).count() == 4
    assert c.origin == "engine" and c.basis_n_flagged == 0 and c.created_at is not None


def test_a_converged_verdict_is_offered_not_applied(world):
    """#440 item 6: the plateau HOLD needs the witnessed accept."""
    w = world
    _insert(w, _v(w, status="offered", decision="hold", outcome="converged", converged=True))
    _refused(w, _v(w, START + timedelta(days=4), status="applied", decision="hold", outcome="converged",
                   converged=True), "ck_cbti_verdict_kind")


def test_accepted_and_lapsed_rows_carry_their_lifecycle_columns(world):
    w = world
    offered = _insert(w, _v(w, START, status="offered", decision="compress", outcome="compress"))
    nxt = _insert(w, _v(w, START + timedelta(days=4)))
    offered.status, offered.lapsed_by_id, offered.lapsed_on = "lapsed", nxt.id, START + timedelta(days=8)
    w["db"].commit()
    acc = _insert(w, _v(w, START + timedelta(days=8), status="accepted", decision="extend", outcome="extend",
                        minted_prescription_id=w["rx2"].id, applied_on=START + timedelta(days=13),
                        accepted_at=datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc),
                        unscored_from=START + timedelta(days=12), unscored_to=START + timedelta(days=13)))
    assert offered.status == "lapsed" and acc.minted_prescription_id == w["rx2"].id


def test_a_backfilled_hold_may_carry_the_prescription_it_minted(world):
    """ck_cbti_verdict_mint exempts origin = 'backfill': a historical HOLD did mint a row."""
    w = world
    _insert(w, _v(w, minted_prescription_id=w["rx2"].id, origin="backfill"))
    _refused(w, _v(w, START + timedelta(days=4), minted_prescription_id=w["rx2"].id, origin="engine"),
             "ck_cbti_verdict_mint")


# ── each named check refuses the row it exists for ───────────────────────────

@pytest.mark.parametrize("name, over", [
    ("ck_cbti_verdict_kind", dict(status="applied", decision="extend", outcome="extend")),      # a move cannot apply on its own
    ("ck_cbti_verdict_kind", dict(status="offered", decision="hold", outcome="hold")),          # a plain HOLD cannot be offered
    ("ck_cbti_verdict_kind", dict(status="lapsed", decision="hold", outcome="hold", lapsed_by_id=1)),
    ("ck_cbti_verdict_conv", dict(status="applied", decision="hold", outcome="converged", converged=False)),
    ("ck_cbti_verdict_conv", dict(status="offered", decision="hold", outcome="hold", converged=True)),
    ("ck_cbti_verdict_conv", dict(status="offered", decision="extend", outcome="converged", converged=True)),
    ("ck_cbti_verdict_suff", dict(status="offered", decision="extend", outcome="extend", sufficient=False)),
    ("ck_cbti_verdict_suff", dict(sufficient=False, outcome="hold")),                            # insufficient but not 'no_decision'
    ("ck_cbti_verdict_accept", dict(status="accepted", decision="extend", outcome="extend")),    # accepted mints a row
    ("ck_cbti_verdict_lapse", dict(status="lapsed", decision="extend", outcome="extend")),       # lapsed names its successor
    ("ck_cbti_verdict_lapse", dict(status="offered", decision="extend", outcome="extend", lapsed_by_id=1)),
    ("ck_cbti_verdict_status", dict(status="done")),
    ("ck_cbti_verdict_decision", dict(decision="close")),
    ("ck_cbti_verdict_outcome", dict(outcome="converge")),
    ("ck_cbti_verdict_origin", dict(origin="manual")),
    ("ck_cbti_verdict_span", dict(cycle_end=START - timedelta(days=1))),
])
def test_each_check_refuses_its_row(world, name, over):
    w = world
    if over.get("lapsed_by_id") == 1:                       # point at a real verdict so only the check can refuse it
        over = {**over, "lapsed_by_id": _insert(w, _v(w, START + timedelta(days=40))).id}
    _refused(w, _v(w, START, **over), name)


def test_a_non_decision_is_a_hold_that_says_so(world):
    w = world
    _insert(w, _v(w, sufficient=False, outcome="no_decision", basis_tst_min=None, basis_se_pct=None))


# ── unique keys and the partial indexes ──────────────────────────────────────

def test_one_verdict_per_cycle_per_block(world):
    w = world
    _insert(w, _v(w, START))
    _refused(w, _v(w, START), "cbti_cycle_verdicts.block_id")                       # UNIQUE (block_id, cycle_start)
    other = models.CBTIBlock(user_id=w["user"].id, opened_on=date(2026, 1, 1), wake_anchor="05:00", open_reason="t")
    w["db"].add(other)
    w["db"].commit()
    rx_o = models.CBTIPrescription(block_id=other.id, effective_from=START, prescribed_lights_out="22:00",
                                   wake_anchor="05:00", window_minutes=420, decision="adopt")
    w["db"].add(rx_o)
    w["db"].commit()
    _insert(w, _v(w, START, block_id=other.id, prescription_id=rx_o.id))             # same start, another block: fine


def test_at_most_one_pending_offer_per_block(world):
    w = world
    _insert(w, _v(w, START, status="offered", decision="extend", outcome="extend"))
    _refused(w, _v(w, START + timedelta(days=4), status="offered", decision="compress", outcome="compress"))
    # an applied HOLD and an already-lapsed row do not count as a pending offer
    nxt = _insert(w, _v(w, START + timedelta(days=4)))
    done = _insert(w, _v(w, START + timedelta(days=8), status="lapsed", decision="extend", outcome="extend",
                         lapsed_by_id=nxt.id))
    assert done.status == "lapsed"


def test_the_two_partial_indexes_are_partial_on_sqlite_too(world):
    sql = {r[0]: r[1] for r in world["db"].execute(
        sa.text("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='cbti_cycle_verdicts'")).all()}
    assert "WHERE status = 'offered'" in sql["uq_cbti_verdicts_one_offer"]
    assert "WHERE status IN ('applied','accepted') AND basis_tst_min IS NOT NULL" in sql["ix_cbti_verdicts_plateau"]
    assert "WHERE" not in sql["ix_cbti_verdicts_block"]


# ── foreign keys ─────────────────────────────────────────────────────────────

def test_deleting_a_block_cascades_to_its_verdicts(world):
    w = world
    _insert(w, _v(w, START))
    _insert(w, _v(w, START + timedelta(days=4), status="accepted", decision="extend", outcome="extend",
                  minted_prescription_id=w["rx2"].id))
    w["db"].execute(sa.delete(models.CBTIBlock).where(models.CBTIBlock.id == w["block"].id))
    w["db"].commit()
    assert w["db"].query(models.CBTICycleVerdict).count() == 0


def test_a_verdict_must_name_a_real_block_and_prescription(world):
    w = world
    _refused(w, _v(w, block_id=999999))
    _refused(w, _v(w, prescription_id=999999))


def test_deleting_a_chain_predecessor_nulls_the_link(world):
    w = world
    first = _insert(w, _v(w, START))
    second = _insert(w, _v(w, START + timedelta(days=4), chains_from_id=first.id))
    w["db"].execute(sa.delete(models.CBTICycleVerdict).where(models.CBTICycleVerdict.id == first.id))
    w["db"].commit()
    w["db"].refresh(second)
    assert second.chains_from_id is None


# ── the migration builds exactly what the model does ─────────────────────────

def _engine():
    eng = sa.create_engine("sqlite:///:memory:")
    event.listen(eng, "connect", lambda c, _r: c.execute("PRAGMA foreign_keys=ON"))
    return eng


def _prereqs(eng):
    database.Base.metadata.create_all(eng, tables=[models.User.__table__, models.CBTIBlock.__table__,
                                                   models.CBTIPrescription.__table__])


def _fingerprint(eng):
    insp = sa.inspect(eng)
    t = "cbti_cycle_verdicts"
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    return {
        "columns": sorted((c["name"], c["nullable"], str(c["type"])) for c in insp.get_columns(t)),
        "checks": sorted((c["name"], norm(c["sqltext"])) for c in insp.get_check_constraints(t)),
        "uniques": sorted((u["name"], tuple(u["column_names"])) for u in insp.get_unique_constraints(t)),
        "fks": sorted((tuple(f["constrained_columns"]), f["referred_table"], (f["options"] or {}).get("ondelete"))
                      for f in insp.get_foreign_keys(t)),
        "indexes": sorted((i["name"], bool(i["unique"]), tuple(i["column_names"])) for i in insp.get_indexes(t)),
        "index_sql": sorted((n, norm(s)) for n, s in eng.connect().execute(
            sa.text("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=:t AND sql IS NOT NULL"),
            {"t": t}).all()),
    }


def _run(eng, fn_name):
    mod = _load_migration()
    with eng.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(mod, fn_name)()


def test_the_migration_creates_what_the_model_declares():
    from_model, from_migration = _engine(), _engine()
    _prereqs(from_model)
    models.CBTICycleVerdict.__table__.create(from_model)
    _prereqs(from_migration)
    _run(from_migration, "upgrade")
    assert _fingerprint(from_migration) == _fingerprint(from_model)


def test_the_migration_downgrades_cleanly():
    eng = _engine()
    _prereqs(eng)
    _run(eng, "upgrade")
    assert "cbti_cycle_verdicts" in sa.inspect(eng).get_table_names()
    _run(eng, "downgrade")
    assert "cbti_cycle_verdicts" not in sa.inspect(eng).get_table_names()
    with eng.connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM sqlite_master WHERE name LIKE '%cbti_verdict%'")).scalar() == 0


def test_the_migration_is_the_single_head_and_follows_the_indoor_cycling_one():
    mod = _load_migration()
    assert mod.revision == "b8e4d2f61a39" and mod.down_revision == "e5b2c8a91d47"
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, heads
