"""The operator seed script — S6 of the typed-entries brief (#NEXT).

Built against the id-29 / prod-ledger fixture (`test_injury_sweep_prod_fixture`, verbatim prod
shapes). THE FIXTURE EXPECTATION the operator's dry-run is reviewed against:
  * id 29 (right hamstring) and id 18 (left) are RESOLVED in prod → seed NOTHING;
  * id 94 (lumbar, active) carries 3 restrictions → 3 planned advisory rows;
  * id 77 (finger, active) — its restrictions were not in the listing; the fixture has none.
  => 3 planned, 0 skipped, 0 conflicts, for this ledger.
Plus: had id 29 been active, its 3 restrictions would plan 3 rows (the control).

Gates: dry-run writes nothing; --confirm writes the plan in one transaction and the rows read
back as confirmed advisory constraints (rendered, never engine-read); re-running is a no-op; a
RESOLVED seeded row is never re-created; `ra_flare` is skipped; a key clash is reported, not
written; the injury rows are untouched.
"""
import importlib.util
import os
from datetime import date

import pytest

import models
import typed_entries
from engine import selection
from load_metrics import _local_day
from test_injury_sweep_prod_fixture import LUMBAR_94, PROD_LEDGER, RESTRICTIONS_29

_SPEC = importlib.util.spec_from_file_location(
    "seed_constraints", os.path.join(os.path.dirname(__file__), "..", "scripts", "seed_constraints.py"))
seed = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed)

REVIEW = date(2026, 12, 1)


def _row(db, **kw):
    row = models.UserKnowledgeEntry(type="injury", source="system", added_at=date(2026, 7, 1), **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def ledger(db_session):
    u = models.User(email="seed@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    _row(db_session, id=18, user_id=u.id, key="injury_hamstring_left", active=False,
         value={"body_part": "hamstring", "side": "left", "restrictions": ["striding", "sprinting"]})
    _row(db_session, id=29, user_id=u.id, key="injury_hamstring_right", active=False,
         value={"body_part": "hamstring", "side": "right", "restrictions": RESTRICTIONS_29})
    for id_, key, active, body in PROD_LEDGER:
        _row(db_session, id=id_, user_id=u.id, key=key, active=active,
             value={"body_part": body, "signal_type": "mechanical", "restrictions": []})
    _row(db_session, id=94, user_id=u.id, key="injury_lumbar_spine", active=True, value=LUMBAR_94)
    return {"db": db_session, "user": u}


def _snapshot(db):
    db.expire_all()
    return [(r.id, r.type, r.key, r.value, r.active) for r in
            db.query(models.UserKnowledgeEntry).order_by(models.UserKnowledgeEntry.id)]


def _run(ledger, *flags, review="2026-12-01"):
    db = ledger["db"]
    return seed.main([str(ledger["user"].id), "--review-by", review, *flags],
                     db_factory=lambda: _NoClose(db))


class _NoClose:
    """The test session outlives the script's `finally: db.close()`."""
    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


# ── the fixture expectation ──────────────────────────────────────────────────

def test_prod_ledger_plan_matches_the_fixture_expectation(ledger):
    plan = seed.plan_seed(ledger["db"], ledger["user"].id, REVIEW)
    assert [i["key"] for i in plan["injuries"]] == ["injury_finger_left", "injury_lumbar_spine"]
    assert [p["parent_key"] for p in plan["planned"]] == ["injury_lumbar_spine"] * 3
    assert [p["value"]["scope"]["text"] for p in plan["planned"]] == LUMBAR_94["restrictions"]
    assert plan["skipped"] == [] and plan["conflicts"] == []
    assert not any(p["parent_key"] == "injury_hamstring_right" for p in plan["planned"])   # id 29


def test_id_29_active_would_plan_its_three_restrictions(ledger):
    """Control: the resolved state is what keeps id 29 out, not the restriction strings."""
    db = ledger["db"]
    db.query(models.UserKnowledgeEntry).filter_by(id=29).one().active = True
    db.commit()
    planned = [p for p in seed.plan_seed(db, ledger["user"].id, REVIEW)["planned"]
               if p["parent_key"] == "injury_hamstring_right"]
    assert [p["value"]["scope"]["text"] for p in planned] == RESTRICTIONS_29
    v = planned[0]["value"]
    assert v["scope"] == {"tier": "advisory", "text": "striding"}
    assert v["exit"] == {"with_parent": True} and v["parent_key"] == "injury_hamstring_right"
    assert (v["status"], v["asserted_by"], v["kind"], v["review_by"]) == ("confirmed", "user", "block", "2026-12-01")


# ── dry-run / confirm ────────────────────────────────────────────────────────

def test_dry_run_writes_nothing(ledger, capsys):
    before = _snapshot(ledger["db"])
    assert _run(ledger, "--dry-run") == 0
    assert _snapshot(ledger["db"]) == before
    out = capsys.readouterr().out
    assert "PLANNED (3)" in out and "DRY RUN — nothing written." in out
    assert "#94 injury_lumbar_spine: 3 restriction(s)" in out


def test_confirm_writes_rows_the_chat_reads_and_the_engine_does_not(ledger, capsys):
    db, uid = ledger["db"], ledger["user"].id
    injuries_before = [r for r in _snapshot(db) if r[1] == "injury"]
    assert _run(ledger, "--confirm") == 0
    assert "constraint rows after: {'active': 3, 'total': 3}" in capsys.readouterr().out
    rows = db.query(models.UserKnowledgeEntry).filter_by(user_id=uid, type="constraint").all()
    assert all(r.source == "system" and "seeded from injury_lumbar_spine" in r.notes for r in rows)
    lifted = typed_entries.lift_constraints(db.query(models.UserKnowledgeEntry).filter_by(user_id=uid, active=True).all())
    assert len(lifted) == 3                                        # confirmed → rendered
    assert selection.gather_active_constraints(db, uid) == []     # advisory → never engine-read
    assert [r for r in _snapshot(db) if r[1] == "injury"] == injuries_before   # restrictions untouched


def test_rerun_is_a_no_op(ledger, capsys):
    _run(ledger, "--confirm")
    capsys.readouterr()
    before = _snapshot(ledger["db"])
    assert _run(ledger, "--confirm") == 0
    out = capsys.readouterr().out
    assert "PLANNED (0)" in out and "SKIPPED (3)" in out and "WROTE 0 row(s)" in out
    assert _snapshot(ledger["db"]) == before


def test_a_resolved_seeded_row_is_never_recreated(ledger, capsys):
    db = ledger["db"]
    _run(ledger, "--confirm")
    first = db.query(models.UserKnowledgeEntry).filter_by(type="constraint").order_by(models.UserKnowledgeEntry.id).first()
    first.active = False                                        # the operator retired it
    db.commit()
    capsys.readouterr()
    _run(ledger, "--confirm")
    out = capsys.readouterr().out
    assert "WROTE 0 row(s)" in out and "already seeded (resolved/superseded" in out


def test_ra_flare_token_is_skipped(ledger):
    db = ledger["db"]
    _row(db, id=200, user_id=ledger["user"].id, key="injury_hand", active=True,
         value={"body_part": "hand", "restrictions": ["ra_flare", "no heavy grip"]})
    plan = seed.plan_seed(db, ledger["user"].id, REVIEW)
    assert [s["text"] for s in plan["skipped"]] == ["ra_flare"]
    assert "no heavy grip" in [p["value"]["scope"]["text"] for p in plan["planned"]]


def test_a_key_clash_is_reported_never_written(ledger, capsys):
    db = ledger["db"]
    key = "constraint_injury_lumbar_spine_end_range_lumbar_flexion_combined_with_twisting"
    db.add(models.UserKnowledgeEntry(user_id=ledger["user"].id, type="preference", key=key, value={},
                                     source="api", active=True))
    db.commit()
    plan = seed.plan_seed(db, ledger["user"].id, REVIEW)
    assert [c["key"] for c in plan["conflicts"]] == [key] and len(plan["planned"]) == 2


def test_confirm_is_one_transaction(ledger, monkeypatch):
    db = ledger["db"]
    real, calls = seed._stage_upsert_entry, []

    def flaky(*a, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("boom")
        return real(*a, **kw)

    monkeypatch.setattr(seed, "_stage_upsert_entry", flaky)
    with pytest.raises(ValueError):
        seed.apply_seed(db, seed.plan_seed(db, ledger["user"].id, REVIEW))
    assert db.query(models.UserKnowledgeEntry).filter_by(type="constraint").count() == 0


@pytest.mark.parametrize("argv", [
    ["--review-by", "2026-12-01"],                               # neither mode
    ["--review-by", "2026-12-01", "--dry-run", "--confirm"],     # both
    ["--dry-run"],                                               # no review_by
    ["--review-by", "December", "--dry-run"],
    ["--review-by", "2020-01-01", "--dry-run"],                   # past
])
def test_bad_invocations_exit_2_and_write_nothing(ledger, argv):
    before = _snapshot(ledger["db"])
    db = ledger["db"]
    assert seed.main([str(ledger["user"].id), *argv], db_factory=lambda: _NoClose(db)) == 2
    assert _snapshot(ledger["db"]) == before


def test_review_by_today_is_allowed(ledger):
    assert _run(ledger, "--dry-run", review=str(_local_day())) == 0
