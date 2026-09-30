"""`scripts.retire_user` -- FK-graph discovery, dry run, and the guarded execute path.

The suite's SQLite substrate enforces foreign keys (conftest `_enforce_sqlite_fks`, FEEDBACK
section 33), so the cascades exercised here are real ones, not an ORM-side fiction. The
graph under test is discovered from the live schema, so these tests also pin that it agrees
with `models.py`.
"""
import io
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

import database
import models
from scripts import retire_user as ru

CIPHERTEXT = "gAAAA-not-a-real-token-but-a-recognisable-one"
NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


def _seed_user(db, uid: int, email: str, *, hevy_prefix: str):
    """A user with rows at every depth: direct child, transitive child, integration, template + tag."""
    db.add(models.User(id=uid, email=email, hashed_password="x", full_name=f"user {uid}"))
    db.flush()
    for provider in ("hevy", "garmin"):
        db.add(models.UserIntegration(user_id=uid, provider=provider, api_key_encrypted=CIPHERTEXT))
    db.add(models.HevyWorkout(hevy_id=f"{hevy_prefix}-w1", user_id=uid, raw={"id": f"{hevy_prefix}-w1"}))
    db.flush()  # parent before child: autoflush is off and there is no relationship()
    db.add(models.HevySet(workout_id=f"{hevy_prefix}-w1", exercise_template_id="T", block_index=0, set_index=0))
    db.add(models.HrvReading(user_id=uid, captured_at=date(2026, 9, 29), source="garmin", rmssd_ms=50.0))
    db.flush()
    reading = db.query(models.HrvReading).filter_by(user_id=uid).one()
    db.add(models.HrvSample(hrv_reading_id=reading.id, reading_time=NOW, rmssd_ms=51.0))
    db.add(models.UserKnowledgeEntry(user_id=uid, type="preference", key=f"k{uid}", value={}, source="chat"))
    db.commit()


@pytest.fixture()
def two_users(db_session):
    _seed_user(db_session, 1, "operator@example.com", hevy_prefix="u1")
    _seed_user(db_session, 7, "testacct@example.com", hevy_prefix="u7")
    return db_session


def _engine(db):
    return db.get_bind()


def _counts(db, table, col="user_id", uid=None):
    return db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :u"), {"u": uid}).scalar_one()


def _token(db, uid):
    e = _engine(db)
    g = ru.discover_graph(e)
    with e.connect() as c:
        return ru.build_plan(c, e, g, uid).token


# -- graph discovery ----------------------------------------------------------------------

def test_graph_agrees_with_models_on_direct_user_children(db_session):
    """Identity control (#103): the live-schema graph must find exactly the tables whose ORM
    columns FK to users.id -- neither a subset (a missed table orphans rows) nor extras."""
    graph = ru.discover_graph(_engine(db_session))
    direct_live = {e.child for e in graph.edges if e.parent == "users"}
    direct_orm = {
        t.name for t in database.Base.metadata.tables.values()
        for fk in t.foreign_keys if fk.column.table.name == "users"
    }
    assert direct_live == direct_orm
    assert "user_integrations" in direct_live


def test_transitive_children_are_in_scope_and_set_null_is_not(db_session):
    graph = ru.discover_graph(_engine(db_session))
    for t in ("hevy_sets", "hrv_samples", "exercise_region_tags"):
        assert t in graph.scope, f"{t} is reached only through a parent and must still be scoped"
    # marker_canonical_entries.created_by_user_id is ON DELETE SET NULL: rows survive.
    assert "marker_canonical_entries" not in graph.scope


def test_no_unenforced_user_reference_columns_in_the_schema(db_session):
    """A future `user_id` column added without an FK would orphan on delete; make it loud here."""
    assert ru.discover_graph(_engine(db_session)).unenforced == []


def test_non_rederivable_columns_still_exist():
    """Value guard (FEEDBACK section 34): the at-risk queries name these columns as literals; a
    rename must fail here, not silently turn the data-loss gate into a no-op."""
    hw = {c.name for c in models.HevyWorkout.__table__.columns}
    tp = {c.name for c in models.HevyExerciseTemplate.__table__.columns}
    assert {"excluded_at", "user_id"} <= hw
    assert {"laterality", "adjudicated_at", "bw_fraction", "owner_user_id"} <= tp


# -- dry run ------------------------------------------------------------------------------

def test_dry_run_changes_nothing_and_lists_the_rows(two_users, monkeypatch):
    db = two_users
    monkeypatch.setattr(database, "engine", _engine(db))
    before = {t: db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
              for t in ("users", "user_integrations", "hevy_workouts", "hevy_sets", "hrv_readings", "hrv_samples")}
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = ru.main(["--user-id", "7"])
    text_out = out.getvalue()
    assert rc == 0, err.getvalue()
    for t in ("user_integrations", "hevy_workouts", "hevy_sets", "hrv_readings", "hrv_samples"):
        assert t in text_out
    assert "DRY RUN - nothing was changed." in text_out
    assert "hevy" in text_out and "garmin" in text_out            # provider list
    after = {t: db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in before}
    assert after == before


def test_report_is_ascii_and_never_carries_the_credential(two_users, monkeypatch):
    db = two_users
    monkeypatch.setattr(database, "engine", _engine(db))
    out = io.StringIO()
    with redirect_stdout(out):
        ru.main(["--user-id", "7"])
    report = out.getvalue()
    assert CIPHERTEXT not in report and "gAAAA" not in report
    assert "testacct@example.com" not in report                     # masked, not printed
    assert "t***@example.com" in report
    assert report.isascii()                                         # PowerShell mojibake, section 30


def test_dry_run_reports_hevy_ownership_and_at_risk_rows(two_users, monkeypatch):
    """The shared-key hazard: an operator adjudication on a row the target owns is surfaced."""
    db = two_users
    db.execute(text("UPDATE hevy_workouts SET excluded_at = :t WHERE hevy_id = 'u7-w1'"), {"t": NOW})
    db.add(models.HevyExerciseTemplate(id="custom-1", title="Custom", is_custom=True, owner_user_id=7,
                                       laterality="unilateral"))
    db.flush()
    db.add(models.ExerciseRegionTag(hevy_exercise_template_id="custom-1", region_key="r"))
    db.commit()
    monkeypatch.setattr(database, "engine", _engine(db))
    out = io.StringIO()
    with redirect_stdout(out):
        ru.main(["--user-id", "7"])
    report = out.getvalue()
    assert "user 1: 1 workouts" in report and "user 7: 1 workouts, 1 excluded" in report
    assert "hevy_workouts with excluded_at set" in report
    assert "hevy_exercise_templates annotated" in report
    assert "exercise_region_tags on templates owned by the target" in report
    assert "EXECUTE WILL REFUSE unless --accept-loss" in report


# -- guards -------------------------------------------------------------------------------

def test_the_protected_set_is_exactly_the_real_accounts():
    """Operator ruling 30 Sep 2026: users 1, 4 and 5 are real and never in scope."""
    assert ru.PROTECTED_USER_IDS == frozenset({1, 4, 5})


@pytest.mark.parametrize("pid", [1, 4, 5])
def test_protected_users_are_refused_at_every_layer(two_users, monkeypatch, pid):
    db = two_users
    e = _engine(db)
    monkeypatch.setattr(database, "engine", e)
    graph = ru.discover_graph(e)
    with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
        assert ru.main(["--user-id", str(pid)]) == 2                                      # CLI dry run
        assert ru.main(["--user-id", str(pid), "--execute", "--confirm", "x"]) == 2       # CLI execute
    with pytest.raises(ru.ProtectedUserError):
        ru.execute_retirement(e, pid, "anything", graph=graph)                            # API
    with e.connect() as c, pytest.raises(ru.ProtectedUserError):
        ru.build_plan(c, e, graph, pid)                                                   # planner
    assert _counts(db, "users", "id", 1) == 1 and _counts(db, "hevy_workouts", uid=1) == 1


def test_retiring_a_candidate_leaves_every_protected_account_identical(db_session):
    """Users 1, 4 and 5 each carry a full tree; retiring 7 must not move any of them."""
    for uid, prefix in ((1, "u1"), (4, "u4"), (5, "u5"), (7, "u7")):
        _seed_user(db_session, uid, f"user{uid}@example.com", hevy_prefix=prefix)
    e = _engine(db_session)
    graph = ru.discover_graph(e)
    with e.connect() as c:
        before = {p: ru.snapshot(c, e, graph, p) for p in (1, 4, 5)}
    result = ru.execute_retirement(e, 7, _token(db_session, 7), graph=graph)
    with e.connect() as c:
        after = {p: ru.snapshot(c, e, graph, p) for p in (1, 4, 5)}
    assert before == after and all(sum(v.values()) > 0 for v in before.values())
    assert set(result.protected_counts) == {1, 4, 5}


def test_protected_ids_cannot_be_reached_through_a_coerced_id(two_users):
    e = _engine(two_users)
    with pytest.raises(ru.ProtectedUserError):
        ru.execute_retirement(e, "1", "x")            # string id coerces to the protected 1
    with pytest.raises(ru.ProtectedUserError):
        ru.execute_retirement(e, True, "x")           # True == 1


def test_execute_needs_the_matching_confirm_token(two_users):
    db, e = two_users, _engine(two_users)
    with pytest.raises(ru.ConfirmMismatch):
        ru.execute_retirement(e, 7, None)
    with pytest.raises(ru.ConfirmMismatch):
        ru.execute_retirement(e, 7, "000000000000")
    assert _counts(db, "users", "id", 7) == 1


def test_unknown_user_is_refused(two_users):
    with pytest.raises(ru.NoSuchUser):
        ru.execute_retirement(_engine(two_users), 99, "x")


# -- execute ------------------------------------------------------------------------------

def test_execute_removes_target_tree_and_leaves_user_1_identical(two_users):
    db, e = two_users, _engine(two_users)
    graph = ru.discover_graph(e)
    tables = sorted(graph.scope)
    with e.connect() as c:
        u1_before = ru.snapshot(c, e, graph, 1)
    result = ru.execute_retirement(e, 7, _token(db, 7), graph=graph)
    db.expire_all()

    assert sorted(result.integrations_deleted) == ["garmin", "hevy"]
    assert _counts(db, "users", "id", 7) == 0
    for t in ("user_integrations", "hevy_workouts", "hrv_readings", "user_knowledge_entries"):
        assert _counts(db, t, uid=7) == 0, t
    # transitive children are gone too, and only theirs
    assert db.execute(text("SELECT COUNT(*) FROM hevy_sets")).scalar_one() == 1
    assert db.execute(text("SELECT COUNT(*) FROM hrv_samples")).scalar_one() == 1
    with e.connect() as c:
        assert ru.snapshot(c, e, graph, 1) == u1_before and sum(u1_before.values()) > 0
        assert all(n == 0 for n in ru.snapshot(c, e, graph, 7).values())
    assert len(tables) > 5


def test_execute_is_idempotent_refusal_second_time(two_users):
    db, e = two_users, _engine(two_users)
    tok = _token(db, 7)
    ru.execute_retirement(e, 7, tok)
    with pytest.raises(ru.NoSuchUser):
        ru.execute_retirement(e, 7, tok)


def test_invariant_failure_rolls_the_whole_transaction_back(two_users, monkeypatch):
    """If user 1's counts move mid-transaction, NOTHING is deleted (the control that discriminates:
    the target's rows are still there afterwards, not merely 'an error was raised')."""
    db, e = two_users, _engine(two_users)
    graph = ru.discover_graph(e)
    tok = _token(db, 7)
    real = ru.snapshot
    calls = {"n": 0}

    def flaky(conn, engine, g, uid):
        snap = real(conn, engine, g, uid)
        if uid == 1:
            calls["n"] += 1
            if calls["n"] == 2:                      # the AFTER snapshot of the protected user
                snap["user_integrations"] += 1
        return snap

    monkeypatch.setattr(ru, "snapshot", flaky)
    with pytest.raises(ru.InvariantError):
        ru.execute_retirement(e, 7, tok, graph=graph)
    db.expire_all()
    assert _counts(db, "users", "id", 7) == 1
    assert _counts(db, "user_integrations", uid=7) == 2
    assert _counts(db, "hevy_workouts", uid=7) == 1
    assert _counts(db, "users", "id", 1) == 1


def test_cross_user_no_action_reference_blocks_execute(two_users):
    """A user 1 knowledge entry superseded_by a user 7 entry (a NO ACTION self-FK) would make the
    delete fail on Postgres; the planner refuses first, readably, with nothing removed."""
    db, e = two_users, _engine(two_users)
    u7 = db.query(models.UserKnowledgeEntry).filter_by(user_id=7).one()
    u1 = db.query(models.UserKnowledgeEntry).filter_by(user_id=1).one()
    u1.superseded_by = u7.id
    db.commit()
    with pytest.raises(ru.Blocked, match="NO ACTION"):
        ru.execute_retirement(e, 7, _token(db, 7))
    assert _counts(db, "users", "id", 7) == 1


def test_set_null_references_are_reported_and_survive(two_users, monkeypatch):
    db, e = two_users, _engine(two_users)
    db.add(models.MarkerCanonicalEntry(marker_name_raw="probe-marker", source="bind", created_by_user_id=7))
    db.commit()
    graph = ru.discover_graph(e)
    with e.connect() as c:
        plan = ru.build_plan(c, e, graph, 7)
    assert ("marker_canonical_entries", "created_by_user_id", 1) in plan.nulled
    ru.execute_retirement(e, 7, plan.token, graph=graph)
    db.expire_all()
    row = db.query(models.MarkerCanonicalEntry).filter_by(marker_name_raw="probe-marker").one()
    assert row.created_by_user_id is None


def test_at_risk_rows_block_execute_until_loss_is_accepted(two_users):
    db, e = two_users, _engine(two_users)
    db.execute(text("UPDATE hevy_workouts SET excluded_at = :t WHERE hevy_id = 'u7-w1'"), {"t": NOW})
    db.commit()
    tok = _token(db, 7)
    with pytest.raises(ru.Blocked, match="non-re-derivable"):
        ru.execute_retirement(e, 7, tok)
    assert _counts(db, "users", "id", 7) == 1                         # refused, nothing removed
    ru.execute_retirement(e, 7, tok, accept_loss=True)
    db.expire_all()
    assert _counts(db, "users", "id", 7) == 0
    assert _counts(db, "hevy_workouts", uid=1) == 1                   # user 1's own workout untouched


def test_execute_cli_reports_and_commits(two_users, monkeypatch):
    db = two_users
    monkeypatch.setattr(database, "engine", _engine(db))
    tok = _token(db, 7)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = ru.main(["--user-id", "7", "--execute", "--confirm", tok])
    assert rc == 0, err.getvalue()
    report = out.getvalue()
    assert "EXECUTED: user 7 retired" in report and "identical before and after" in report
    assert CIPHERTEXT not in report and report.isascii()
    db.expire_all()
    assert _counts(db, "users", "id", 7) == 0 and _counts(db, "users", "id", 1) == 1


def test_confirm_without_execute_is_rejected(two_users, monkeypatch):
    monkeypatch.setattr(database, "engine", _engine(two_users))
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
        ru.main(["--user-id", "7", "--confirm", "abc"])


# -- sign-in artefacts, knowledge, identity (scope update 30 Sep) ---------------------------

def test_report_covers_signin_artefacts_knowledge_and_identity(two_users, monkeypatch):
    db = two_users
    db.add(models.PasswordResetToken(user_id=7, token="t-1", expires_at=NOW))
    db.add(models.UserKnowledgeEntry(user_id=7, type="injury", key="k-inj", value={}, source="onboarding"))
    db.add(models.UserKnowledge(user_id=7, category="legacy", content="x"))
    db.commit()
    monkeypatch.setattr(database, "engine", _engine(db))
    out = io.StringIO()
    with redirect_stdout(out):
        assert ru.main(["--user-id", "7"]) == 0
    r = out.getvalue()
    assert "full_name='user 7'" in r                                    # identity, not just a mask
    assert "No last-login is recorded anywhere" in r
    assert "password_reset_tokens: 1 row(s), 1 unused" in r
    assert "MCP OAuth" in r and "NOT persisted" in r and "until the backend restarts" in r
    assert "user_knowledge_entries type=preference source=chat active=True: 1" in r
    assert "user_knowledge_entries type=injury source=onboarding active=True: 1" in r
    assert "user_knowledge (legacy category store): 1" in r


def test_non_ascii_full_name_keeps_the_report_ascii(two_users, monkeypatch):
    db = two_users
    db.execute(text("UPDATE users SET full_name = :n WHERE id = 7"), {"n": "D\u00e9bora"})
    db.commit()
    monkeypatch.setattr(database, "engine", _engine(db))
    out = io.StringIO()
    with redirect_stdout(out):
        ru.main(["--user-id", "7"])
    assert out.getvalue().isascii() and "D\\xe9bora" in out.getvalue()


def test_mcp_provider_really_persists_nothing():
    """The report asserts the MCP OAuth provider keeps no DB state (FEEDBACK section 46: a
    sentence about runtime capability is a claim that needs a test). If someone gives it a table,
    this fails and the report's MCP paragraph must be rewritten with a real inventory."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "oauth_provider.py").read_text(encoding="utf-8")
    for needle in ("import database", "from database", "SessionLocal", "import models", "from models", "sqlalchemy"):
        assert needle not in src, f"oauth_provider.py now touches {needle!r}: the MCP report text is stale"
