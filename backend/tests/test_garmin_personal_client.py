"""The Personal API client (connectors/garmin_personal.py), driven against a fake host at the transport layer."""
import logging
from datetime import datetime, timedelta, timezone

import pytest

from connectors import garmin_personal as gp
from garmin_personal_fakes import FAKE_KEY, FAKE_PK, FakeHost, make_jwt

NOW = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)


def _client(host, **kw):
    return gp.PersonalClient(host.key, transport=host.transport(), now=lambda: NOW, **kw)


def _host(**kw):
    return FakeHost(now=NOW, **kw)


def test_exchange_posts_the_key_as_an_apikey_header_with_no_body_and_reads_the_body_as_the_jwt():
    host = _host()
    host.set("/x", {"ok": 1})
    with _client(host) as c:
        assert c.get("/x") == {"ok": 1}
        token, expires = c.token_state()
    assert host.exchanges == 1
    assert token in host.issued and expires == NOW + timedelta(hours=24)       # exp read from the JWT, unverified


def test_a_token_with_more_than_an_hour_left_is_reused_and_one_without_is_exchanged_again():
    host = _host()
    host.set("/x", {})
    with _client(host) as c:
        c.get("/x")
        c.get("/x")
        assert host.exchanges == 1                                              # reused
    fresh = make_jwt(NOW + timedelta(hours=3))
    host.issued.add(fresh)
    with _client(host, access_token=fresh, token_expires_at=NOW + timedelta(hours=3)) as c:
        c.get("/x")
        assert host.exchanges == 1                                              # 3 h left: reused from the cache
    near = make_jwt(NOW + timedelta(minutes=30))
    with _client(host, access_token=near, token_expires_at=NOW + timedelta(minutes=30)) as c:
        c.get("/x")
        assert host.exchanges == 2                                              # under the hour: re-exchanged


def test_a_401_on_a_data_call_forces_one_reexchange_and_retries_once():
    host = _host()
    host.set("/x", {"ok": 1})
    with _client(host) as c:
        c.get("/x")
        host.reject_next_bearer = True
        assert c.get("/x") == {"ok": 1}
        assert host.exchanges == 2


def test_a_token_refused_twice_is_an_auth_error():
    host = _host()
    host.set("/x", {})
    host.status_for["/x"] = 401
    with _client(host) as c, pytest.raises(gp.PersonalAuthError):
        c.get("/x")


def test_a_refused_key_is_an_auth_error_and_other_exchange_failures_are_typed():
    host = _host()
    with gp.PersonalClient("wrong-key", transport=host.transport(), now=lambda: NOW) as c:
        with pytest.raises(gp.PersonalAuthError):
            c.get("/x")
    for status, exc in ((429, gp.PersonalRateLimited), (500, gp.PersonalTransientError)):
        h = _host()
        h.exchange_status = status
        with _client(h) as c, pytest.raises(exc):
            c.get("/x")


def test_a_malformed_token_body_is_a_transient_error_not_an_auth_error():
    host = _host()
    host.exchange_body = "not-a-jwt"
    with _client(host) as c, pytest.raises(gp.PersonalTransientError):
        c.get("/x")


def test_404_is_not_found_and_get_or_none_turns_it_into_an_empty_day_and_204_is_none():
    host = _host()
    host.set("/empty", None)
    with _client(host) as c:
        with pytest.raises(gp.PersonalNotFound):
            c.get("/missing")
        assert c.get_or_none("/missing") is None
        assert c.get("/empty") is None


def test_429_and_5xx_on_a_data_call_are_typed():
    host = _host()
    host.set("/x", {})
    host.status_for["/x"] = 429
    with _client(host) as c:
        with pytest.raises(gp.PersonalRateLimited):
            c.get("/x")
        host.status_for["/x"] = 503
        with pytest.raises(gp.PersonalTransientError):
            c.get("/x")


def test_an_empty_key_is_refused_at_construction():
    with pytest.raises(gp.PersonalAuthError):
        gp.PersonalClient("   ")


def test_neither_the_key_nor_the_token_reaches_a_log_or_an_exception_message(caplog):
    caplog.set_level(logging.DEBUG)
    host = _host()
    host.set("/x", {})
    host.status_for["/x"] = 503
    with _client(host) as c:
        with pytest.raises(gp.PersonalTransientError) as err:
            c.get("/x")
        token, _ = c.token_state()
    assert FAKE_KEY not in str(err.value) and token not in str(err.value)
    assert FAKE_KEY not in caplog.text and token not in caplog.text
    bad = _host()
    with gp.PersonalClient("a-wrong-key-xyz", transport=bad.transport()) as c, pytest.raises(gp.PersonalAuthError) as e2:
        c.get("/x")
    assert "a-wrong-key-xyz" not in str(e2.value)


def test_jwt_expiry_reads_exp_and_rejects_anything_else():
    assert gp.jwt_expiry(make_jwt(NOW)) == NOW
    for bad in ("", "a.b", "a.e30.c", "x"):
        with pytest.raises(gp.PersonalTransientError):
            gp.jwt_expiry(bad)


def test_profile_pk_is_read_from_either_spelling_and_never_from_a_non_dict():
    assert gp.extract_user_profile_pk({"userProfilePk": FAKE_PK}) == str(FAKE_PK)
    assert gp.extract_user_profile_pk({"userProfilePK": FAKE_PK}) == str(FAKE_PK)
    assert gp.extract_user_profile_pk({"userProfilePk": ""}) is None
    assert gp.extract_user_profile_pk([{"userProfilePk": 1}]) is None
    assert gp.extract_user_profile_pk(None) is None
