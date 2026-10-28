"""The token probe (Q239 item 4): driven against a fake host at the TRANSPORT layer, so the real client's exchange
and header shape are exercised and the verdict is read off what the host answers, not off a stub."""
import httpx

import load_sweep
import models
from connectors import garmin_personal as gp
from encryption import encrypt
from garmin_personal_fakes import FAKE_KEY, FakeHost, make_jwt
from scripts import garmin_token_probe as tp


class InvalidatingHost(FakeHost):
    """A host on which every new exchange kills all earlier tokens."""

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == gp.TOKEN_PATH:
            self.issued.clear()
        return super()._handle(request)


def _host(cls=FakeHost):
    host = cls()
    host.set(gp.HR_ZONES_PATH, [{"sport": "DEFAULT", "maxHeartRateUsed": 190}])
    return host


def _probe(host):
    return tp.probe(host.key, transport=host.transport(), pace_s=0.0, settle_s=0.0, sleep=lambda s: None)


def test_a_host_that_keeps_the_old_token_reads_no_invalidation():
    host = _host()
    out = _probe(host)
    assert out["verdict"] == "NO_INVALIDATION"
    assert (out["a_control"], out["a_after_b"], out["b"], out["a_after_settle"]) == (200, 200, 200, 200)
    assert host.exchanges == 2                      # A and B, nothing more


def test_a_host_that_kills_the_old_token_reads_invalidates():
    out = _probe(_host(InvalidatingHost))
    assert out["verdict"] == "INVALIDATES"
    assert out["a_control"] == 200 and out["a_after_b"] == 401 and out["b"] == 200


def test_a_failed_control_is_inconclusive_not_a_verdict():
    host = _host()
    host.status_for[gp.HR_ZONES_PATH] = 500
    out = _probe(host)
    assert out["verdict"] == "INCONCLUSIVE" and out["a_after_b"] is None


def test_an_identical_second_token_is_reported_as_such():
    host = _host()
    host.exchange_body = make_jwt(host.now + host.ttl)          # every exchange returns this one token
    out = _probe(host)
    assert out["verdict"] == "SAME_TOKEN" and out["tokens_differ"] is False


def test_main_prints_codes_and_a_verdict_but_no_token_or_key(db_session, capsys):
    db_session.add(models.User(id=1, email="u@example.com", hashed_password="x"))
    db_session.add(models.UserIntegration(user_id=1, provider="garmin_personal", api_key_encrypted=encrypt(FAKE_KEY)))
    db_session.commit()
    host = _host()
    rc = tp.main(["--user-id", "1", "--settle", "0"], db_factory=lambda: db_session, transport=host.transport(),
                 sleep=lambda s: None)
    out = capsys.readouterr().out
    assert rc == 0 and "VERDICT: NO_INVALIDATION" in out
    assert FAKE_KEY not in out and not any(t in out for t in host.issued)
    assert db_session.query(models.UserIntegration).one().access_token_encrypted is None       # it wrote nothing


def test_main_without_a_key_exits_1(db_session, capsys):
    db_session.add(models.User(id=1, email="u@example.com", hashed_password="x"))
    db_session.commit()
    assert tp.main(["--user-id", "1"], db_factory=lambda: db_session) == 1
    assert "no garmin_personal key" in capsys.readouterr().err


def test_the_nightly_brief_carries_the_wellness_counts():
    brief = load_sweep._summary_brief({"load": {}, "garmin": {"users_attempted": 2, "wellness": {"sleep_inserted": 2}}})
    assert brief["garmin"]["wellness"] == {"sleep_inserted": 2}
