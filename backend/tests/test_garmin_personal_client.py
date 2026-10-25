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


# -- pacing: the host answers 429 to a burst (25 Oct 2026) and 200 to requests two seconds apart ----------

class _Clock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def _paced(host, clock, interval):
    return gp.PersonalClient(host.key, transport=host.transport(), now=lambda: NOW, min_interval_s=interval,
                             sleep=clock.sleep, monotonic=clock.monotonic)


def test_data_requests_are_spaced_by_the_interval_and_the_first_is_never_delayed():
    host, clock = _host(), _Clock()
    host.set("/x", {})
    with _paced(host, clock, 2.0) as c:
        c.get("/x")
        assert clock.slept == []
        c.get("/x")
        c.get("/x")
    assert clock.slept == [2.0, 2.0]


def test_time_already_elapsed_counts_towards_the_gap_and_zero_disables_pacing():
    host, clock = _host(), _Clock()
    host.set("/x", {})
    with _paced(host, clock, 2.0) as c:
        c.get("/x")
        clock.t += 1.5
        c.get("/x")
    assert clock.slept == [pytest.approx(0.5)]
    host2, clock2 = _host(), _Clock()
    host2.set("/x", {})
    with _paced(host2, clock2, 0.0) as c:
        c.get("/x"); c.get("/x")
    assert clock2.slept == []


def test_the_401_retry_is_paced_too_and_the_exchange_is_not_counted_as_a_data_request():
    host, clock = _host(), _Clock()
    host.set("/x", {"ok": 1})
    with _paced(host, clock, 2.0) as c:
        c.get("/x")
        host.reject_next_bearer = True
        c.get("/x")                        # 401, re-exchange, retry: two data requests after the first
    assert clock.slept == [2.0, 2.0]


def test_the_real_host_is_paced_and_an_injected_transport_is_not():
    import garmin_personal_lanes as gpl
    from encryption import encrypt
    import models
    row = models.UserIntegration(user_id=1, provider="garmin_personal", api_key_encrypted=encrypt(FAKE_KEY))
    assert gpl.build_client(row)._min_interval == gpl.PACE_S == 2.0
    assert gpl.build_client(row, transport=_host().transport())._min_interval == 0.0
    assert gpl.build_client(row, min_interval_s=0.5)._min_interval == 0.5
