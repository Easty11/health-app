"""`scripts/garmin_activity_backfill.py`: dry run by default, idempotent, counts only, and the probe's token guard
on the Personal API token (never an exchange outside the lane's own path). Driven through the REAL
`PersonalClient` against a fake host at the TRANSPORT (FEEDBACK section 23)."""
from datetime import date

import pytest

from connectors import garmin_personal as gp
from garmin_personal_fakes import FAKE_KEY, FakeHost
from scripts import garmin_activity_backfill as bf
from test_garmin_activity_metrics import AID, NOW, _details, _item, _metric_rows, _ride, _stream, _summary, _user


def _bf_host():
    host = FakeHost()
    host.set(gp.ACTIVITY_LIST_PATH, lambda params: [_item()] if params.get("start") == "0" else [])
    host.set(f"{gp.ACTIVITY_PATH}/{AID}", {"activityId": AID, "summaryDTO": _summary()})
    host.set(f"{gp.ACTIVITY_PATH}/{AID}/details", _details(_ride(seconds=59)))
    return host


def _guarded(host):
    client = gp.PersonalClient(FAKE_KEY, transport=host.transport())
    client.exchange()
    return client, bf.GuardedSource(client)


def test_a_dry_run_reads_and_counts_and_writes_nothing(db_session):
    _user(db_session)
    host = _bf_host()
    client, src = _guarded(host)
    out = bf.backfill(db_session, 1, src, since=date(2026, 3, 1), confirm=False, now=NOW)
    client.close()
    assert (out["activities_listed"], out["metrics_found"], out["streams_with_hr"], out["samples_found"]) == (1, 1, 1, 60)
    assert out["metrics_written"] == 0 and out["samples_written"] == 0 and out["median_interval_s"] == 1.0
    assert _metric_rows(db_session) == [] and _stream(db_session) == []
    assert host.exchanges == 1                                   # the test's own exchange; the run made none


def test_a_confirmed_run_writes_and_a_rerun_skips_what_is_captured(db_session):
    _user(db_session)
    host = _bf_host()
    client, src = _guarded(host)
    first = bf.backfill(db_session, 1, src, since=date(2026, 3, 1), confirm=True, now=NOW)
    n = len(host.requests)
    again = bf.backfill(db_session, 1, src, since=date(2026, 3, 1), confirm=True, now=NOW)
    client.close()
    assert first["metrics_written"] == 1 and first["samples_written"] == 60 and len(_stream(db_session)) == 60
    assert again["already_captured"] == 1 and again["details_fetched"] == 0 and len(host.requests) == n + 1   # the list only


def test_the_token_guard_refuses_a_token_that_needs_an_exchange():
    with gp.PersonalClient(FAKE_KEY, transport=FakeHost().transport()) as client:
        with pytest.raises(bf.RefreshWouldBeNeeded):
            bf.GuardedSource(client)


def test_the_guard_stops_when_the_token_changes_mid_walk():
    host = _bf_host()
    client, src = _guarded(host)
    host.reject_next_bearer = True                               # a 401 forces a re-exchange inside get()
    with pytest.raises(RuntimeError, match="token changed"):
        src.get(gp.ACTIVITY_LIST_PATH, {"start": "0"})
    client.close()


def test_a_dry_run_counts_why_streams_came_back_empty(db_session):
    _user(db_session)
    host = _bf_host()
    d = _details([])
    d["totalMetricsCount"] = 3712
    host.set(f"{gp.ACTIVITY_PATH}/{AID}/details", d)
    client, src = _guarded(host)
    out = bf.backfill(db_session, 1, src, since=date(2026, 3, 1), confirm=False, now=NOW)
    client.close()
    assert out["empty_reasons"] == {"no_rows": 1} and out["streams_unmarked"] == 1 and out["thinned"] == 1


def test_diagnose_compares_the_asked_and_bare_shapes_and_writes_nothing(db_session):
    _user(db_session)
    host = _bf_host()
    host.set(f"{gp.ACTIVITY_PATH}/{AID}/details",
             lambda params: {**_details([]), "totalMetricsCount": 60} if params else _details(_ride(seconds=59)))
    client, src = _guarded(host)
    lines = bf.diagnose(src, activity_ids=[AID], since=date(2026, 3, 1), limit=3)
    client.close()
    assert len(lines) == 2 and lines[0].startswith(f"activity {AID} asked:") and lines[1].startswith(f"activity {AID} bare:")
    assert "'samples': 0" in lines[0] and "'empty_reason': 'no_rows'" in lines[0]
    assert "'samples': 60" in lines[1] and "'empty_reason': None" in lines[1]
    assert _metric_rows(db_session) == [] and _stream(db_session) == []
    assert [p for _, _, p in host.requests] == [{"maxChartSize": "100000", "maxPolylineSize": "0"}, {}]


def test_diagnose_without_ids_takes_the_first_listed(db_session):
    host = _bf_host()
    client, src = _guarded(host)
    lines = bf.diagnose(src, activity_ids=[], since=date(2026, 3, 1), limit=3)
    client.close()
    assert [l.split(":")[0] for l in lines] == [f"activity {AID} asked", f"activity {AID} bare"]
