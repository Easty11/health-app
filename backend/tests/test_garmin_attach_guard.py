"""G4 -- the root-cause guard for the Garmin account mix-up.

`POST /integrations/garmin/token` resolves which Garmin account a token belongs to and refuses it
when that account is already linked to a DIFFERENT user (409, naming no user); it FAILS CLOSED
(503, nothing stored) when the account cannot be resolved. Two layers on purpose (FEEDBACK
section 23): the endpoint is tested with a faked client, and the profile-id resolver is tested
with the REAL `garminconnect` client faked at the transport, because the guard is only as good as
its reading of Garmin's response.
"""
import base64
import json
import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import models
from auth import get_current_user
from connectors import garmin as gc
from connectors.garmin import (
    GarminClient,
    GarminProfileUnresolvable,
    GarminReconnectError,
    account_fingerprint,
    extract_profile_id,
)
from database import get_db
from encryption import decrypt, encrypt
from routers import garmin as garmin_router

CONFLICT = "This Garmin account is already connected to a different user."


class FakeClient:
    def __init__(self, profile, blob="DUMPED_BLOB"):
        self._profile, self._blob = profile, blob

    def profile_id(self):
        if isinstance(self._profile, Exception):
            raise self._profile
        return self._profile

    def dump_token(self):
        return self._blob


def _user(db, uid):
    db.add(models.User(id=uid, email=f"user{uid}@example.com", hashed_password="x"))
    db.commit()
    return db.get(models.User, uid)


def _api(db, user):
    app = FastAPI()
    app.include_router(garmin_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _attach(db, user, monkeypatch, client_or_exc, token="SUBMITTED_BLOB"):
    def make(cls, token_json):
        if isinstance(client_or_exc, Exception):
            raise client_or_exc
        return client_or_exc
    monkeypatch.setattr(garmin_router.GarminClient, "from_token", classmethod(make))
    return _api(db, user).post("/integrations/garmin/token", json={"token": token})


def _rows(db, uid):
    return db.query(models.UserIntegration).filter_by(user_id=uid, provider="garmin").all()


# -- the guard ------------------------------------------------------------------------------

def test_attaching_users_1_account_to_user_4_is_refused_and_names_no_one(db_session, monkeypatch):
    u1, u4 = _user(db_session, 1), _user(db_session, 4)
    assert _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A")).status_code == 201
    r = _attach(db_session, u4, monkeypatch, FakeClient("ACCOUNT-A", blob="OTHER_BLOB"))
    assert r.status_code == 409 and r.json() == {"detail": CONFLICT}
    body = r.text.lower()
    for leak in ("user 1", "user1", "user_id", "example.com", "account-a"):
        assert leak not in body
    assert _rows(db_session, 4) == []                              # nothing stored for the refused user
    assert decrypt(_rows(db_session, 1)[0].api_key_encrypted) == "DUMPED_BLOB"   # owner untouched


def test_a_conflict_is_refused_before_any_write_is_attempted(db_session, monkeypatch):
    """The unique index is the backstop; the pre-check's own job is to refuse WITHOUT touching the
    database (no commit, so no IntegrityError rollback on the ordinary path)."""
    u1, u4 = _user(db_session, 1), _user(db_session, 4)
    _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A"))
    commits, real = [], db_session.commit
    monkeypatch.setattr(db_session, "commit", lambda: (commits.append(1), real())[1])
    assert _attach(db_session, u4, monkeypatch, FakeClient("ACCOUNT-A")).status_code == 409
    assert commits == []


def test_reattaching_the_same_account_to_the_same_user_is_allowed(db_session, monkeypatch):
    u1 = _user(db_session, 1)
    assert _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A", blob="FIRST")).status_code == 201
    assert _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A", blob="SECOND")).status_code == 201
    rows = _rows(db_session, 1)
    assert len(rows) == 1 and decrypt(rows[0].api_key_encrypted) == "SECOND"
    assert rows[0].account_fingerprint == account_fingerprint("ACCOUNT-A")


def test_a_different_account_for_another_user_is_allowed_and_can_replace_your_own(db_session, monkeypatch):
    u1, u4 = _user(db_session, 1), _user(db_session, 4)
    assert _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A")).status_code == 201
    assert _attach(db_session, u4, monkeypatch, FakeClient("ACCOUNT-B")).status_code == 201
    assert _attach(db_session, u4, monkeypatch, FakeClient("ACCOUNT-C")).status_code == 201   # replace own
    assert _rows(db_session, 4)[0].account_fingerprint == account_fingerprint("ACCOUNT-C")


def test_disconnecting_frees_the_account_for_another_user(db_session, monkeypatch):
    u1, u4 = _user(db_session, 1), _user(db_session, 4)
    _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A"))
    assert _api(db_session, u1).delete("/integrations/garmin").status_code == 204
    assert _attach(db_session, u4, monkeypatch, FakeClient("ACCOUNT-A")).status_code == 201


def test_stored_blob_is_the_clients_dump_not_the_submitted_text_and_is_encrypted(db_session, monkeypatch):
    u1 = _user(db_session, 1)
    _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A", blob="REFRESHED_DUMP"), token="OLD_SUBMITTED")
    row = _rows(db_session, 1)[0]
    assert row.api_key_encrypted not in ("REFRESHED_DUMP", "OLD_SUBMITTED")
    assert decrypt(row.api_key_encrypted) == "REFRESHED_DUMP"


def test_the_fingerprint_is_a_digest_never_the_raw_profile_id(db_session, monkeypatch):
    u1 = _user(db_session, 1)
    _attach(db_session, u1, monkeypatch, FakeClient("987654321"))
    fp = _rows(db_session, 1)[0].account_fingerprint
    assert fp == account_fingerprint("987654321") and "987654321" not in fp and len(fp) == 64


def test_a_concurrent_attach_that_loses_the_unique_index_race_is_a_409(db_session, monkeypatch):
    """The pre-check can be beaten by a concurrent commit; the partial unique index is the backstop."""
    u1, u4 = _user(db_session, 1), _user(db_session, 4)
    _attach(db_session, u1, monkeypatch, FakeClient("ACCOUNT-A"))
    monkeypatch.setattr(garmin_router, "_fingerprint_linked_elsewhere", lambda *a, **k: False)   # check misses
    r = _attach(db_session, u4, monkeypatch, FakeClient("ACCOUNT-A"))
    assert r.status_code == 409 and r.json() == {"detail": CONFLICT}
    assert _rows(db_session, 4) == []


# -- fail closed ----------------------------------------------------------------------------

def test_an_unresolvable_account_is_a_503_and_nothing_is_stored(db_session, monkeypatch, caplog):
    u4 = _user(db_session, 4)
    with caplog.at_level(logging.ERROR):
        r = _attach(db_session, u4, monkeypatch, FakeClient(GarminProfileUnresolvable("no id")))
    assert r.status_code == 503 and "retry" in r.json()["detail"].lower()
    assert _rows(db_session, 4) == []


def test_garmin_being_unreachable_also_fails_closed(db_session, monkeypatch, caplog):
    u4 = _user(db_session, 4)
    with caplog.at_level(logging.ERROR):
        r = _attach(db_session, u4, monkeypatch, ConnectionError("dns failure"))
    assert r.status_code == 503 and _rows(db_session, 4) == []
    assert any("attach BLOCKED" in rec.message for rec in caplog.records)      # alerts, not silent


def test_a_token_that_cannot_authenticate_is_a_424_and_stores_nothing(db_session, monkeypatch):
    u4 = _user(db_session, 4)
    r = _attach(db_session, u4, monkeypatch, GarminReconnectError("expired"))
    assert r.status_code == 424 and _rows(db_session, 4) == []


def test_empty_token_is_still_422(db_session):
    assert _api(db_session, _user(db_session, 4)).post("/integrations/garmin/token", json={"token": "  "}).status_code == 422


# -- the resolver, against the real client at the transport layer -----------------------------

def _jwt(exp_offset):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'ES256', 'typ': 'JWT'})}.{b64({'exp': time.time() + exp_offset, 'client_id': 'CID'})}.sig"


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._b, self.headers, self.ok = status, body, {}, status < 400
        self.text = json.dumps(body)

    def json(self):
        return self._b


class FakeSession:
    def __init__(self, body):
        self._body, self.calls = body, []

    def request(self, method, url, **kw):
        self.calls.append(url)
        return FakeResp(200, self._body)


def _real_client(body):
    from garminconnect import Garmin
    g = Garmin()
    g.client.loads(json.dumps({"di_token": _jwt(+3600), "di_refresh_token": "R", "di_client_id": "CID"}))
    sess = FakeSession(body)
    g.client._api_session = sess
    return GarminClient(g), sess


def test_the_real_client_resolves_the_profile_id_from_the_social_profile_response():
    client, sess = _real_client({"displayName": "x", "profileId": 555123456})
    assert client.profile_id() == "555123456"
    assert sess.calls[0].endswith("/userprofile-service/socialProfile")


def test_a_changed_response_shape_is_unresolvable_and_logs_key_names_only(caplog):
    client, _ = _real_client({"displayName": "SECRET-NAME", "somethingNew": 1})
    with caplog.at_level(logging.ERROR), pytest.raises(GarminProfileUnresolvable):
        client.profile_id()
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "UNRESOLVABLE" in text and "somethingNew" in text and "displayName" in text
    assert "SECRET-NAME" not in text                                       # names of keys, never values


def test_extract_profile_id_candidates_and_edge_cases():
    assert extract_profile_id({"profileId": 12}) == "12"
    assert extract_profile_id({"id": "ab-1"}) == "ab-1"
    assert extract_profile_id({"profileId": "  ", "id": 7}) == "7"          # a blank key falls through
    assert extract_profile_id({"displayName": "x"}) is None
    assert extract_profile_id(None) is None and extract_profile_id([1, 2]) is None


def test_g1_and_the_guard_share_one_resolver():
    """`scripts/garmin_identity.py` reports the same identity the guard enforces on."""
    from scripts import garmin_identity as gi
    assert gi._PROFILE_ID_KEYS is gc.PROFILE_ID_KEYS and gi._SOCIAL_PROFILE_PATH is gc.SOCIAL_PROFILE_PATH
    assert gi.extract_profile_id is gc.extract_profile_id


# -- unique index and lazy recording --------------------------------------------------------

def test_the_partial_unique_index_is_the_databases_own_refusal(db_session):
    _user(db_session, 1), _user(db_session, 4)
    fp = account_fingerprint("A")
    db_session.add(models.UserIntegration(user_id=1, provider="garmin", api_key_encrypted="x", account_fingerprint=fp))
    db_session.commit()
    db_session.add(models.UserIntegration(user_id=4, provider="garmin", api_key_encrypted="x", account_fingerprint=fp))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    # unconstrained: NULLs (any number), and the same digest under another provider
    for uid, prov in ((1, "hevy"), (4, "hevy"), (4, "polar")):
        db_session.add(models.UserIntegration(user_id=uid, provider=prov, api_key_encrypted="x"))
    db_session.add(models.UserIntegration(user_id=4, provider="garmin", api_key_encrypted="x"))   # NULL fingerprint
    db_session.add(models.UserIntegration(user_id=1, provider="strava", api_key_encrypted="x", account_fingerprint=fp))
    db_session.commit()


class SyncFake:
    def __init__(self, profile="ACCOUNT-A"):
        self._profile, self.profile_calls = profile, 0

    def profile_id(self):
        self.profile_calls += 1
        if isinstance(self._profile, Exception):
            raise self._profile
        return self._profile

    def dump_token(self):
        return "BLOB"

    def get_hrv_range(self, start, end):
        return []


def _connect(db, uid):
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encrypt("BLOB")))
    db.commit()


def _sync(db, monkeypatch, uid, fake):
    from datetime import date
    monkeypatch.setattr(garmin_router.GarminClient, "from_token", classmethod(lambda cls, t: fake))
    return garmin_router.sync_hrv_for_user(db, uid, date(2026, 9, 1), date(2026, 9, 2))


def test_a_sync_records_the_fingerprint_once(db_session, monkeypatch):
    _user(db_session, 1)
    _connect(db_session, 1)
    fake = SyncFake()
    _sync(db_session, monkeypatch, 1, fake)
    _sync(db_session, monkeypatch, 1, fake)
    assert _rows(db_session, 1)[0].account_fingerprint == account_fingerprint("ACCOUNT-A")
    assert fake.profile_calls == 1                                         # no extra API call once recorded


def test_a_duplicate_account_at_sync_time_alerts_and_never_fails_the_sync(db_session, monkeypatch, caplog):
    _user(db_session, 1), _user(db_session, 4)
    _connect(db_session, 1), _connect(db_session, 4)
    _sync(db_session, monkeypatch, 1, SyncFake("ACCOUNT-A"))
    with caplog.at_level(logging.ERROR):
        out = _sync(db_session, monkeypatch, 4, SyncFake("ACCOUNT-A"))     # the mix-up condition
    assert out["days_with_data"] == 0                                      # the sync completed
    assert _rows(db_session, 4)[0].account_fingerprint is None             # left unrecorded
    assert _rows(db_session, 1)[0].account_fingerprint == account_fingerprint("ACCOUNT-A")
    assert any("ALREADY connected to another user" in r.getMessage() for r in caplog.records)
    assert "user 1" not in " ".join(r.getMessage() for r in caplog.records)   # names only the syncing user


def test_an_unresolvable_profile_never_fails_the_sync(db_session, monkeypatch):
    _user(db_session, 1)
    _connect(db_session, 1)
    out = _sync(db_session, monkeypatch, 1, SyncFake(GarminProfileUnresolvable("none")))
    assert out["days_with_data"] == 0 and _rows(db_session, 1)[0].account_fingerprint is None


# -- migration DDL --------------------------------------------------------------------------

def test_the_migration_renders_the_column_and_the_partial_index_for_postgres():
    """Render the new revision's `upgrade()` against the Postgres dialect with alembic's own offline
    machinery: the DDL the deploy will run, without a database.

    Deliberately NOT `command.upgrade`: that executes `migrations/env.py`, whose `fileConfig(...)`
    disables every logger that already exists and silently breaks any later test that asserts on
    log output (found the hard way: six unrelated tests failed only in the full run)."""
    import importlib.util
    import io
    from pathlib import Path

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    path = (Path(__file__).resolve().parent.parent / "migrations" / "versions"
            / "a9c3e5f7b1d2_add_user_integrations_account_fingerprint.py")
    spec = importlib.util.spec_from_file_location("mig_a9c3e5f7b1d2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    buf = io.StringIO()
    ctx = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buf})
    with Operations.context(ctx):
        mod.upgrade()
    ddl = " ".join(buf.getvalue().split())
    assert "ALTER TABLE user_integrations ADD COLUMN account_fingerprint VARCHAR(64)" in ddl
    assert "CREATE UNIQUE INDEX uq_user_integrations_provider_fingerprint ON user_integrations" in ddl
    assert "(provider, account_fingerprint) WHERE account_fingerprint IS NOT NULL" in ddl

    down = io.StringIO()
    ctx = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": down})
    with Operations.context(ctx):
        mod.downgrade()
    assert "DROP INDEX uq_user_integrations_provider_fingerprint" in down.getvalue()
    assert "DROP COLUMN account_fingerprint" in down.getvalue()


def test_the_migration_tests_leave_logging_alone():
    """Regression for the contamination above: nothing here may disable pre-existing loggers."""
    import logging
    assert logging.getLogger("routers.garmin").disabled is False
    assert logging.getLogger("connectors.garmin").disabled is False


def test_the_revision_chains_from_the_prior_head_and_matches_the_model_index_name():
    """Invariants that stay true as later migrations land (not 'this is the head'): the history is
    still a single line, this revision revises `f7a2c9e1d3b5`, and the model declares the same
    index the migration creates (the SCHEMA.md / model / migration triple must not drift)."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    script = ScriptDirectory.from_config(cfg)          # reads the versions dir; never runs env.py
    assert len(script.get_heads()) == 1, "migration history branched"
    rev = script.get_revision("a9c3e5f7b1d2")
    assert rev.down_revision == "f7a2c9e1d3b5"
    names = {i.name for i in models.UserIntegration.__table__.indexes}
    assert "uq_user_integrations_provider_fingerprint" in names
