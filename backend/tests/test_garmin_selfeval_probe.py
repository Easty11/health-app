"""`scripts.garmin_selfeval_probe` -- the read-only Garmin activity self-evaluation probe (Q209).

Two layers on purpose (FEEDBACK section 23), as in `test_garmin_identity`: the scan and report
logic is tested with a faked source, and the no-refresh and two-request guarantees are tested with
the REAL `garminconnect` client faked at the TRANSPORT (`_api_session`, `_http_post`), because they
live in the library's own request path and a fake above it would prove nothing about that.
Fixtures use the null the API actually sends where a field is empty (FEEDBACK section 60).
"""
import base64
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
from scripts import garmin_selfeval_probe as sp

BLOB = json.dumps({"di_token": "tok-recognisable-secret", "di_refresh_token": "ref-recognisable-secret",
                   "di_client_id": "cid"})

LIST_ITEM = {
    "activityId": 111222333,
    "activityName": "SECRET-ACTIVITY-NAME",
    "startTimeLocal": "2026-10-03 07:41:05",
    "activityType": {"typeKey": "running", "typeId": 1},
    "averageHR": 987654.0,
}
DETAIL = {
    "activityId": 111222333,
    "summaryDTO": {"averageHR": 123456.0, "directWorkoutRpe": 70, "directWorkoutFeel": 50,
                   "secretField": "SECRET-VALUE"},
    "splits": [{"lapIndex": 1, "perceivedFeelNote": None}],
}


def _add_user_garmin(db, uid=1, secret=BLOB):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.flush()
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encryption.encrypt(secret)))
    db.commit()


class FakeSource:
    """Stands in for ProbeSource: returns the list then the detail, recording each request."""

    def __init__(self, listing=None, detail=None):
        self.calls = []
        self._listing = [LIST_ITEM] if listing is None else listing
        self._detail = DETAIL if detail is None else detail

    def get(self, path, params=None):
        self.calls.append((path, params))
        return self._listing if path == sp.ACTIVITY_LIST_PATH else self._detail


def _run(db, monkeypatch, argv, factory):
    monkeypatch.setattr(database, "engine", db.get_bind())
    out = io.StringIO()
    with redirect_stdout(out):
        rc = sp.main(argv, factory=factory)
    return rc, out.getvalue()


# -- scan -------------------------------------------------------------------------------------

def test_scan_finds_matching_keys_anywhere_case_insensitively_with_paths():
    hits = dict(sp.scan(DETAIL))
    assert hits["summaryDTO.directWorkoutRpe"] == 70
    assert hits["summaryDTO.directWorkoutFeel"] == 50
    assert hits["splits[0].perceivedFeelNote"] is None          # the API's null is a hit, not a miss
    assert not any("averageHR" in p or "secretField" in p for p in hits)
    assert dict(sp.scan({"SelfEvaluation": {"x": 1}, "RPE": 3})) == {"SelfEvaluation": {"x": 1}, "RPE": 3}


def test_a_matching_container_is_one_hit_and_is_not_descended():
    assert sp.scan({"selfEvaluation": {"directWorkoutRpe": 40}}) == [("selfEvaluation", {"directWorkoutRpe": 40})]


def test_scan_of_a_payload_with_nothing_matching_is_empty():
    assert sp.scan({"summaryDTO": {"averageHR": 1}, "x": [1, {"y": 2}]}) == []
    assert sp.scan("rpe") == [] and sp.scan(None) == []


# -- report: names and values of matching keys only ------------------------------------------

def test_report_prints_matching_names_and_values_and_nothing_else():
    src = FakeSource()
    text_out = sp.format_report(sp.probe(src, limit=10, activity_id=None), "sqlite file=x")
    assert "summaryDTO.directWorkoutRpe = 70" in text_out
    assert "summaryDTO.directWorkoutFeel = 50" in text_out
    assert "splits[0].perceivedFeelNote = null" in text_out
    assert "activity 111222333  2026-10-03  running" in text_out
    for leaked in ("SECRET-ACTIVITY-NAME", "SECRET-VALUE", "987654", "123456", "07:41"):
        assert leaked not in text_out                              # only a DATE and type are identifying
    assert text_out.isascii()
    assert "NEGATIVE" not in text_out                              # there were hits


def test_a_negative_is_stated_narrowly():
    src = FakeSource(detail={"summaryDTO": {"averageHR": 1}})
    out = sp.format_report(sp.probe(src, limit=10, activity_id=None), "t")
    assert "NEGATIVE, narrowly" in out and "may omit the key" in out and "--activity-id" in out


def test_long_values_are_truncated_and_non_ascii_is_escaped():
    big = {"selfEvaluation": "x" * 500 + "é"}
    rendered = sp.render_value(big["selfEvaluation"])
    assert rendered.endswith("...(truncated)") and len(rendered) < 200
    assert sp.render_value("café").isascii()


def test_empty_list_and_no_activity_id_fetches_no_detail():
    src = FakeSource(listing=[])
    result = sp.probe(src, limit=5, activity_id=None)
    assert result["detail"] is None and [p for p, _ in src.calls] == [sp.ACTIVITY_LIST_PATH]
    assert "not fetched" in sp.format_report(result, "t")


def test_detail_targets_the_given_activity_id_else_the_most_recent():
    src = FakeSource()
    sp.probe(src, limit=3, activity_id=None)
    assert src.calls == [(sp.ACTIVITY_LIST_PATH, {"start": "0", "limit": "3"}),
                         (f"{sp.ACTIVITY_PATH}/111222333", None)]
    src = FakeSource()
    sp.probe(src, limit=3, activity_id="999")
    assert src.calls[1] == (f"{sp.ACTIVITY_PATH}/999", None)


# -- main: database, argument and failure handling ------------------------------------------

def test_the_run_issues_only_select_statements_and_prints_no_token(db_session, monkeypatch):
    _add_user_garmin(db_session)
    stmts: list[str] = []
    event.listen(db_session.get_bind(), "before_cursor_execute",
                 lambda c, cur, st, p, ctx, m: stmts.append(st.strip().upper()))
    blobs = []
    rc, out = _run(db_session, monkeypatch, ["--user-id", "1"], lambda b: blobs.append(b) or FakeSource())
    assert rc == 0 and blobs == [BLOB]
    assert stmts and all(s.startswith("SELECT") for s in stmts), stmts
    assert "tok-recognisable-secret" not in out and "ref-recognisable-secret" not in out


def test_a_user_with_no_garmin_connection_fetches_nothing(db_session, monkeypatch):
    def must_not_build(_blob):
        raise AssertionError("a source was built for a user with no Garmin connection")
    rc, out = _run(db_session, monkeypatch, ["--user-id", "1"], must_not_build)
    assert rc == 1 and "no Garmin connection" in out


def test_a_fetch_failure_prints_only_the_error_class(db_session, monkeypatch):
    _add_user_garmin(db_session)

    class Boom(FakeSource):
        def get(self, path, params=None):
            raise ConnectionError("detail with tok-recognisable-secret in it")
    rc, out = _run(db_session, monkeypatch, ["--user-id", "1"], lambda b: Boom())
    assert rc == 1 and out.strip() == "Garmin fetch failed: ConnectionError"


def test_a_refresh_need_is_reported_with_the_workaround_and_exit_2(db_session, monkeypatch):
    _add_user_garmin(db_session)

    class NeedsRefresh(FakeSource):
        def get(self, path, params=None):
            raise gi.RefreshWouldBeNeeded()
    rc, out = _run(db_session, monkeypatch, ["--user-id", "1"], lambda b: NeedsRefresh())
    assert rc == 2 and "Open the app's Garmin card" in out


@pytest.mark.parametrize("argv", [["--user-id", "1", "--limit", "0"], ["--user-id", "1", "--limit", "51"],
                                  ["--user-id", "1", "--activity-id", "12/../3"], ["--user-id", "1", "--activity-id", "abc"]])
def test_bad_arguments_are_refused(db_session, monkeypatch, argv):
    monkeypatch.setattr(database, "engine", db_session.get_bind())
    with pytest.raises(SystemExit) as exc:
        sp.main(argv, factory=lambda b: FakeSource())
    assert exc.value.code == 2


# -- the no-refresh and two-request guarantees, against the REAL client, faked at the transport ---

def _jwt(exp_offset):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'ES256', 'typ': 'JWT'})}.{b64({'exp': time.time() + exp_offset, 'client_id': 'CID'})}.sig"


def _blob(exp_offset):
    return json.dumps({"di_token": _jwt(exp_offset), "di_refresh_token": "REFRESH", "di_client_id": "CID"})


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body if body is not None else {}
        self.text = json.dumps(self._body)
        self.headers = {}
        self.ok = status < 400

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, *responses):
        self.calls, self._responses = [], list(responses)

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw.get("params")))
        return self._responses.pop(0)


@pytest.fixture()
def no_token_endpoint(monkeypatch):
    """Any POST to Garmin's token endpoint fails the test: that is what a refresh would send."""
    from garminconnect import client as gc

    def forbidden(*a, **k):
        raise AssertionError("a token refresh request was sent")
    monkeypatch.setattr(gc.Client, "_http_post", forbidden)


def test_real_client_sends_exactly_two_gets_with_the_expected_paths(no_token_endpoint):
    sess = FakeSession(FakeResp(200, [LIST_ITEM]), FakeResp(200, DETAIL))
    result = sp.probe(sp.ProbeSource(_blob(+3600), session=sess), limit=7, activity_id=None)
    assert [m for m, _, _ in sess.calls] == ["GET", "GET"]
    assert sess.calls[0][1].endswith(sp.ACTIVITY_LIST_PATH) and sess.calls[0][2] == {"start": "0", "limit": "7"}
    assert sess.calls[1][1].endswith(f"{sp.ACTIVITY_PATH}/111222333") and sess.calls[1][2] is None
    assert dict(result["detail"]["hits"])["summaryDTO.directWorkoutRpe"] == 70


def test_an_expiring_token_is_never_refreshed_and_sends_nothing(no_token_endpoint):
    sess = FakeSession()                                             # any request would IndexError
    with pytest.raises(gi.RefreshWouldBeNeeded):
        sp.probe(sp.ProbeSource(_blob(-60), session=sess), limit=5, activity_id=None)
    assert sess.calls == []


def test_a_401_does_not_trigger_the_retry_refresh_either(no_token_endpoint):
    sess = FakeSession(FakeResp(401))                                # valid token, server says 401
    with pytest.raises(gi.RefreshWouldBeNeeded):
        sp.probe(sp.ProbeSource(_blob(+3600), session=sess), limit=5, activity_id=None)
    assert len(sess.calls) == 1                                      # no retry after a refresh


def test_token_state_is_untouched_after_a_probe(no_token_endpoint):
    src = sp.ProbeSource(_blob(+3600), session=FakeSession(FakeResp(200, [LIST_ITEM]), FakeResp(200, DETAIL)))
    before = (src._client.di_token, src._client.di_refresh_token)
    sp.probe(src, limit=5, activity_id=None)
    assert (src._client.di_token, src._client.di_refresh_token) == before


def test_the_probe_source_inherits_the_no_refresh_override():
    """The guarantee is #361's, reused rather than re-implemented: the subclass must keep it."""
    assert issubclass(sp.ProbeSource, gi.LibrarySource)
    src = sp.ProbeSource(_blob(+3600))
    with pytest.raises(gi.RefreshWouldBeNeeded):
        src._client._refresh_session()


def test_the_endpoint_paths_still_match_the_pinned_library():
    """Value guard (FEEDBACK section 34): the two paths are copied constants. A library upgrade that
    moves them must fail here, not make the probe query a path the library no longer uses."""
    from garminconnect import Garmin
    assert metadata.version("garminconnect") == "0.3.11"
    g = Garmin()
    assert sp.ACTIVITY_LIST_PATH == g.garmin_connect_activities
    assert sp.ACTIVITY_PATH == g.garmin_connect_activity
