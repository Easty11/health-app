"""`scripts.garmin_identity` -- the read-only Garmin/Hevy identity check.

Two layers on purpose (FEEDBACK section 23): the report logic is tested with a faked
identity source, and the no-refresh guarantee is tested with the REAL `garminconnect` client
faked at the TRANSPORT (`_api_session`, `_http_post`), because the guarantee lives in the
library's own request path and a fake above it would prove nothing about that.
"""
import base64
import inspect
import io
import json
import time
from contextlib import redirect_stdout
from importlib import metadata

import pytest
from sqlalchemy import event

import database
import encryption
import models
from scripts import garmin_identity as gi

BLOB_A = json.dumps({"di_token": "tokA", "di_refresh_token": "refA", "di_client_id": "cid"})
BLOB_B = json.dumps({"di_token": "tokB", "di_refresh_token": "refB", "di_client_id": "cid"})
HEVY_KEY = "hevy-key-recognisable-secret"


def _add(db, uid, provider, secret):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.flush()
    db.add(models.UserIntegration(user_id=uid, provider=provider, api_key_encrypted=encryption.encrypt(secret)))
    db.commit()


class FakeSource:
    def __init__(self, result):
        self.result = result

    def social_profile(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _factory(by_blob, seen=None):
    def make(blob):
        if seen is not None:
            seen.append(blob)
        return FakeSource(by_blob[blob])
    return make


def _run(db, monkeypatch, ids, factory):
    monkeypatch.setattr(database, "engine", db.get_bind())
    out = io.StringIO()
    with redirect_stdout(out):
        rc = gi.main(["--user-ids", *map(str, ids)], factory=factory)
    assert rc == 0
    return out.getvalue()


# -- masking / parsing --------------------------------------------------------------------

def test_display_name_shows_three_chars_then_a_fixed_mask():
    assert gi.mask_display_name("Deborah") == "Deb***"
    assert gi.mask_display_name("Al") == "Al***"           # short names do not leak length either
    assert gi.mask_display_name("Débora") == "D\\xe9b***" and gi.mask_display_name("Débora").isascii()
    assert gi.mask_display_name(None) == "(none)"


def test_profile_id_shows_only_the_last_four_digits():
    assert gi.profile_id_tail({"profileId": 987654321}) == "...4321"
    assert gi.profile_id_tail({"id": "ab-12-34-56"}) == "...3456"
    assert gi.profile_id_tail({"profileId": 12}) == "...12"
    assert gi.profile_id_tail({"displayName": "x"}) == "(no id key in response)"


# -- report logic (faked identity source) -------------------------------------------------

def test_same_account_is_reported_and_only_masked_fields_appear(db_session, monkeypatch):
    _add(db_session, 1, "garmin", BLOB_A)
    _add(db_session, 4, "garmin", BLOB_B)             # a different login, same account
    prof = {"displayName": "Deborah", "fullName": "Deborah Full Name", "profileId": 987654321,
            "userName": "secret-username", "location": "Somewhere"}
    r = _run(db_session, monkeypatch, [1, 4], _factory({BLOB_A: prof, BLOB_B: prof}))
    assert "Deb***" in r and "...4321" in r
    assert "consistent with ONE Garmin account" in r
    assert "no two of these users hold an identical stored credential" in r      # blobs differ
    assert "a mismatch is NOT evidence of different accounts" in r
    for leaked in ("Deborah", "Full Name", "secret-username", "Somewhere", "987654321", "tokA", "refA", "tokB"):
        assert leaked not in r, leaked
    assert r.isascii()


def test_identical_stored_credentials_are_reported_as_a_copy(db_session, monkeypatch):
    _add(db_session, 1, "garmin", BLOB_A)
    _add(db_session, 4, "garmin", BLOB_A)
    prof = {"displayName": "Luke", "profileId": 1111}
    r = _run(db_session, monkeypatch, [1, 4], _factory({BLOB_A: prof}))
    assert "garmin: users 1, 4 hold the IDENTICAL stored credential." in r
    assert gi.digest12(BLOB_A) in r and BLOB_A not in r


def test_different_accounts_are_reported_as_different(db_session, monkeypatch):
    _add(db_session, 1, "garmin", BLOB_A)
    _add(db_session, 4, "garmin", BLOB_B)
    r = _run(db_session, monkeypatch, [1, 4], _factory({
        BLOB_A: {"displayName": "Luke", "profileId": 1111},
        BLOB_B: {"displayName": "Deborah", "profileId": 2222}}))
    assert "display name differs" in r and "profile id last-4 differs" in r
    assert "consistent with ONE" not in r


def test_hevy_is_digest_only_and_the_hevy_key_never_reaches_the_garmin_client(db_session, monkeypatch):
    _add(db_session, 1, "hevy", HEVY_KEY)
    _add(db_session, 4, "hevy", HEVY_KEY)
    _add(db_session, 1, "garmin", BLOB_A)
    seen: list[str] = []
    r = _run(db_session, monkeypatch, [1, 4], _factory({BLOB_A: {"displayName": "Luke", "profileId": 1}}, seen))
    assert seen == [BLOB_A]                                         # only the garmin blob was used
    assert "hevy: users 1, 4 hold the IDENTICAL stored credential." in r
    assert HEVY_KEY not in r and gi.digest12(HEVY_KEY) in r


def test_fetch_failure_prints_only_the_error_class(db_session, monkeypatch):
    _add(db_session, 1, "garmin", BLOB_A)
    boom = ConnectionError("token=refA Authorization: Bearer tokA https://internal/host")
    r = _run(db_session, monkeypatch, [1], _factory({BLOB_A: boom}))
    assert "identity fetch failed: ConnectionError" in r
    for leaked in ("refA", "tokA", "Bearer", "internal"):
        assert leaked not in r


def test_needs_refresh_is_reported_with_the_workaround(db_session, monkeypatch):
    _add(db_session, 1, "garmin", BLOB_A)
    r = _run(db_session, monkeypatch, [1], _factory({BLOB_A: gi.RefreshWouldBeNeeded()}))
    assert "identity SKIPPED" in r and "Open the app's Garmin card" in r


def test_user_with_no_integrations_and_missing_id_key(db_session, monkeypatch):
    _add(db_session, 1, "garmin", BLOB_A)
    db_session.add(models.User(id=6, email="u6@example.com", hashed_password="x"))
    db_session.commit()
    r = _run(db_session, monkeypatch, [1, 6], _factory({BLOB_A: {"displayName": "Luke"}}))
    assert "profile id (no id key in response)" in r
    assert "user 6\n  garmin  not connected\n  hevy    not connected" in r


def test_the_run_issues_only_select_statements(db_session, monkeypatch):
    _add(db_session, 1, "garmin", BLOB_A)
    _add(db_session, 1, "hevy", HEVY_KEY)
    e = db_session.get_bind()
    stmts: list[str] = []
    event.listen(e, "before_cursor_execute", lambda c, cur, st, p, ctx, m: stmts.append(st.strip().upper()))
    _run(db_session, monkeypatch, [1], _factory({BLOB_A: {"displayName": "Luke", "profileId": 1}}))
    assert stmts and all(s.startswith("SELECT") for s in stmts), stmts


# -- the no-refresh guarantee, against the REAL client, faked at the transport ---------------

def _jwt(exp_offset):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'ES256', 'typ': 'JWT'})}.{b64({'exp': time.time() + exp_offset, 'client_id': 'CID'})}.sig"


def _blob(exp_offset):
    return json.dumps({"di_token": _jwt(exp_offset), "di_refresh_token": "REFRESH", "di_client_id": "CID"})


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}
        self.text = json.dumps(self._body)
        self.headers = {}
        self.ok = status < 400

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, *responses):
        self.calls, self._responses = [], list(responses)

    def request(self, method, url, **kw):
        self.calls.append((method, url))
        return self._responses.pop(0)


@pytest.fixture()
def no_token_endpoint(monkeypatch):
    """Any POST to Garmin's token endpoint fails the test: that is what a refresh would send."""
    from garminconnect import client as gc

    def forbidden(*a, **k):
        raise AssertionError("a token refresh request was sent")
    monkeypatch.setattr(gc.Client, "_http_post", forbidden)


def test_real_client_fetches_the_profile_through_the_request_layer(no_token_endpoint):
    sess = FakeSession(FakeResp(200, {"displayName": "Deborah", "profileId": 555123456}))
    prof = gi.LibrarySource(_blob(+3600), session=sess).social_profile()
    assert prof["displayName"] == "Deborah"
    assert [m for m, _ in sess.calls] == ["GET"] and sess.calls[0][1].endswith("/userprofile-service/socialProfile")
    assert gi._garmin_identity(_blob(+3600), lambda b: gi.LibrarySource(
        b, session=FakeSession(FakeResp(200, {"displayName": "Deborah", "profileId": 555123456})))) == {
        "status": "ok", "display": "Deb***", "profile_id": "...3456"}


def test_an_expiring_token_is_never_refreshed_and_sends_nothing(no_token_endpoint):
    sess = FakeSession()                                             # any request would IndexError
    res = gi._garmin_identity(_blob(-60), lambda b: gi.LibrarySource(b, session=sess))
    assert res == {"status": "needs_refresh"}
    assert sess.calls == []                                          # not even the profile request


def test_a_401_does_not_trigger_the_retry_refresh_either(no_token_endpoint):
    sess = FakeSession(FakeResp(401))                                # valid token, server says 401
    res = gi._garmin_identity(_blob(+3600), lambda b: gi.LibrarySource(b, session=sess))
    assert res == {"status": "needs_refresh"}
    assert len(sess.calls) == 1                                      # no retry after a refresh


def test_token_state_is_untouched_after_a_fetch(no_token_endpoint):
    src = gi.LibrarySource(_blob(+3600), session=FakeSession(FakeResp(200, {"displayName": "x"})))
    before = (src._client.di_token, src._client.di_refresh_token)
    src.social_profile()
    assert (src._client.di_token, src._client.di_refresh_token) == before


def test_the_library_seams_the_guarantee_rests_on_still_exist():
    """Value guard (FEEDBACK section 34): the no-refresh override replaces a PRIVATE method and
    fakes a private session. A library upgrade that renames either must fail here, not silently
    turn the guarantee into a no-op."""
    from garminconnect import Garmin
    from garminconnect.client import Client
    assert metadata.version("garminconnect") == "0.3.11"
    c = Garmin().client
    for attr in ("_refresh_session", "_api_session", "loads", "connectapi", "di_token", "di_refresh_token"):
        assert hasattr(c, attr), attr
    src = inspect.getsource(Client._run_request)
    assert src.count("self._refresh_session()") >= 2, "both refresh paths (expiry + 401) must route via _refresh_session"
