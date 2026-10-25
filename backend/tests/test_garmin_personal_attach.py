"""S1: attaching a Personal API key -- storage, the same-account guard on userProfilePk, the HTTP route, the
operator script. Driven against the real client over a fake host (transport layer)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import garmin_personal_lanes as gpl
import models
from auth import get_current_user
from connectors import garmin_personal as gp
from connectors.garmin import account_fingerprint
from database import get_db
from encryption import decrypt
from garmin_personal_fakes import FAKE_KEY, FAKE_PK, FakeHost, hrv_payload, sleep_payload
from routers import garmin_personal as router_mod
from scripts import garmin_personal_attach

TODAY = datetime.now(timezone.utc).date()
EXPIRES = TODAY + timedelta(days=300)
FP = account_fingerprint(str(FAKE_PK))


def _user(db, uid):
    db.add(models.User(id=uid, email=f"user{uid}@example.com", hashed_password="x"))
    db.commit()


def _host(with_hrv=True, **kw):
    h = FakeHost(**kw)
    if with_hrv:
        h.set(gp.HRV_PATH.format(date=TODAY.isoformat()), hrv_payload(TODAY.isoformat()))
    return h


def _attach(db, uid, host, *, key=FAKE_KEY, expires=EXPIRES):
    return gpl.attach_key(db, uid, key, expires, today=TODAY, transport=host.transport())


def _code(db, uid, host, **kw):
    with pytest.raises(gpl.AttachError) as e:
        _attach(db, uid, host, **kw)
    return e.value.code


def test_attach_stores_the_key_encrypted_with_the_expiry_the_fingerprint_and_a_cached_token(db_session):
    _user(db_session, 1)
    out = _attach(db_session, 1, _host())
    assert out == {"key_expires_on": EXPIRES.isoformat(), "days_to_expiry": 300}
    row = gpl.get_row(db_session, 1)
    assert row.provider == "garmin_personal" and row.account_fingerprint == FP
    assert row.api_key_encrypted != FAKE_KEY and decrypt(row.api_key_encrypted) == FAKE_KEY
    assert row.key_expires_on == EXPIRES
    assert row.access_token_encrypted and decrypt(row.access_token_encrypted).count(".") == 2
    assert row.access_token_expires_at is not None
    assert db_session.query(models.IntegrationLaneStatus).filter_by(lane="personal_token").one().outcome == "ok"


def test_the_fingerprint_is_the_existing_function_of_the_pk_so_the_DI_row_digest_matches(db_session):
    """S0.1: user 1's stored DI fingerprint IS sha256('garmin:<pk>'), so a personal attach for the same
    account matches it and is not refused."""
    _user(db_session, 1)
    db_session.add(models.UserIntegration(user_id=1, provider="garmin", api_key_encrypted="x", account_fingerprint=FP))
    db_session.commit()
    _attach(db_session, 1, _host())
    assert gpl.get_row(db_session, 1).account_fingerprint == FP


def test_an_account_already_connected_to_another_user_is_refused_on_either_provider(db_session):
    _user(db_session, 1)
    _user(db_session, 4)
    db_session.add(models.UserIntegration(user_id=4, provider="garmin", api_key_encrypted="x", account_fingerprint=FP))
    db_session.commit()
    assert _code(db_session, 1, _host()) == "conflict"
    assert gpl.get_row(db_session, 1) is None
    db_session.query(models.UserIntegration).delete()
    db_session.add(models.UserIntegration(user_id=4, provider="garmin_personal", api_key_encrypted="x",
                                          account_fingerprint=FP))
    db_session.commit()
    assert _code(db_session, 1, _host()) == "conflict"


def test_R6_a_key_for_a_different_account_than_the_users_own_DI_connection_is_refused(db_session):
    _user(db_session, 1)
    db_session.add(models.UserIntegration(user_id=1, provider="garmin", api_key_encrypted="x",
                                          account_fingerprint=account_fingerprint("someone-else")))
    db_session.commit()
    assert _code(db_session, 1, _host()) == "own_mismatch"
    assert gpl.get_row(db_session, 1) is None


def test_a_DI_row_with_no_recorded_fingerprint_does_not_block_the_attach(db_session):
    _user(db_session, 1)
    db_session.add(models.UserIntegration(user_id=1, provider="garmin", api_key_encrypted="x"))
    db_session.commit()
    _attach(db_session, 1, _host())
    assert gpl.get_row(db_session, 1) is not None


def test_re_attaching_the_same_account_replaces_the_key_and_the_expiry_in_place(db_session):
    _user(db_session, 1)
    _attach(db_session, 1, _host())
    h2 = _host(); h2.key = "the-replacement-key-0002"
    _attach(db_session, 1, h2, key="the-replacement-key-0002", expires=EXPIRES + timedelta(days=60))
    rows = db_session.query(models.UserIntegration).filter_by(provider="garmin_personal").all()
    assert len(rows) == 1 and decrypt(rows[0].api_key_encrypted) == "the-replacement-key-0002"
    assert rows[0].key_expires_on == EXPIRES + timedelta(days=60)


def test_FAIL_CLOSED_when_the_account_cannot_be_resolved_nothing_is_stored(db_session):
    _user(db_session, 1)
    assert _code(db_session, 1, _host(with_hrv=False)) == "unverified"         # no payload carries a pk
    h = _host(with_hrv=False)
    h.set(gp.HRV_PATH.format(date=TODAY.isoformat()), hrv_payload(TODAY.isoformat(), with_pk=False))
    assert _code(db_session, 1, h) == "unverified"
    h2 = _host(); h2.status_for[gp.HRV_PATH.format(date=TODAY.isoformat())] = 503
    h2.routes.clear()
    assert _code(db_session, 1, h2) == "unverified"
    assert db_session.query(models.UserIntegration).count() == 0


def test_the_pk_is_found_in_an_earlier_day_or_in_the_sleep_payload(db_session):
    _user(db_session, 1)
    earlier = (TODAY - timedelta(days=3)).isoformat()
    h = _host(with_hrv=False)
    h.set(gp.HRV_PATH.format(date=earlier), hrv_payload(earlier))
    _attach(db_session, 1, h)
    db_session.query(models.UserIntegration).delete(); db_session.commit()
    h2 = _host(with_hrv=False)
    h2.set(gp.SLEEP_PATH, sleep_payload(TODAY.isoformat()), TODAY.isoformat())
    _attach(db_session, 1, h2)
    assert gpl.get_row(db_session, 1).account_fingerprint == FP


def test_a_refused_key_a_blank_key_and_a_bad_expiry_are_refused_before_anything_is_stored(db_session):
    _user(db_session, 1)
    assert _code(db_session, 1, _host(), key="wrong-key") == "refused"
    assert _code(db_session, 1, _host(), key="  ") == "empty_key"
    assert _code(db_session, 1, _host(), expires=TODAY) == "bad_expiry"
    assert db_session.query(models.UserIntegration).count() == 0


# -- the HTTP route --------------------------------------------------------------------------------

def _api(db, user, host, monkeypatch):
    orig = gp.PersonalClient
    monkeypatch.setattr(gp, "PersonalClient", lambda key, **kw: orig(key, **{**kw, "transport": host.transport()}))
    monkeypatch.setattr(router_mod, "_today", lambda: TODAY)
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_route_201_then_status_reports_days_to_expiry_and_the_lane_outcomes(db_session, monkeypatch):
    _user(db_session, 1)
    api = _api(db_session, db_session.get(models.User, 1), _host(), monkeypatch)
    r = api.post("/integrations/garmin-personal/key", json={"api_key": FAKE_KEY, "key_expires_on": EXPIRES.isoformat()})
    assert r.status_code == 201 and r.json()["days_to_expiry"] == 300
    assert FAKE_KEY not in r.text
    s = api.get("/integrations/garmin-personal/status").json()
    assert s["connected"] is True and s["days_to_expiry"] == 300 and s["lanes"]["personal_token"]["outcome"] == "ok"
    assert FAKE_KEY not in str(s)


@pytest.mark.parametrize("setup,status_code", [("conflict", 409), ("unverified", 503), ("refused", 424), ("expiry", 422)])
def test_route_status_codes(db_session, monkeypatch, setup, status_code):
    _user(db_session, 1)
    _user(db_session, 4)
    host = _host(with_hrv=setup != "unverified")
    key, exp = FAKE_KEY, EXPIRES
    if setup == "conflict":
        db_session.add(models.UserIntegration(user_id=4, provider="garmin", api_key_encrypted="x", account_fingerprint=FP))
        db_session.commit()
    if setup == "refused":
        key = "bad"
    if setup == "expiry":
        exp = TODAY - timedelta(days=1)
    api = _api(db_session, db_session.get(models.User, 1), host, monkeypatch)
    r = api.post("/integrations/garmin-personal/key", json={"api_key": key, "key_expires_on": exp.isoformat()})
    assert r.status_code == status_code
    assert "user 4" not in r.text and key not in r.text


def test_route_status_when_unconnected_and_delete_drops_the_row(db_session, monkeypatch):
    _user(db_session, 1)
    api = _api(db_session, db_session.get(models.User, 1), _host(), monkeypatch)
    assert api.get("/integrations/garmin-personal/status").json()["connected"] is False
    api.post("/integrations/garmin-personal/key", json={"api_key": FAKE_KEY, "key_expires_on": EXPIRES.isoformat()})
    assert api.delete("/integrations/garmin-personal").status_code == 204
    assert gpl.get_row(db_session, 1) is None


def test_the_existing_DI_attach_guard_now_also_sees_personal_rows(db_session):
    from routers.garmin import _fingerprint_linked_elsewhere
    _user(db_session, 1)
    _user(db_session, 4)
    db_session.add(models.UserIntegration(user_id=4, provider="garmin_personal", api_key_encrypted="x",
                                          account_fingerprint=FP))
    db_session.commit()
    assert _fingerprint_linked_elsewhere(db_session, FP, 1) is True
    assert _fingerprint_linked_elsewhere(db_session, FP, 4) is False


# -- the operator script ----------------------------------------------------------------------------

def test_script_reads_the_key_from_the_hidden_prompt_only_and_prints_no_secret(db_session, monkeypatch, capsys):
    _user(db_session, 1)
    host = _host()
    orig = gp.PersonalClient
    monkeypatch.setattr(gp, "PersonalClient", lambda key, **kw: orig(key, **{**kw, "transport": host.transport()}))
    prompts = []
    rc = garmin_personal_attach.main(
        ["--user-id", "1", "--expires", EXPIRES.isoformat()],
        read_key=lambda p: prompts.append(p) or FAKE_KEY, db_factory=lambda: db_session, today=TODAY)
    out = capsys.readouterr()
    assert rc == 0 and "300 days" in out.out and prompts
    assert FAKE_KEY not in out.out + out.err and str(FAKE_PK) not in out.out + out.err
    assert gpl.get_row(db_session, 1) is not None


def test_script_reports_a_refusal_with_a_nonzero_exit_and_a_bad_date_as_usage(db_session, monkeypatch, capsys):
    _user(db_session, 1)
    host = _host()
    orig = gp.PersonalClient
    monkeypatch.setattr(gp, "PersonalClient", lambda key, **kw: orig(key, **{**kw, "transport": host.transport()}))
    rc = garmin_personal_attach.main(["--user-id", "1", "--expires", EXPIRES.isoformat()],
                                     read_key=lambda p: "wrong", db_factory=lambda: db_session, today=TODAY)
    assert rc == 1 and "REFUSED (refused)" in capsys.readouterr().err
    assert garmin_personal_attach.main(["--user-id", "1", "--expires", "soon"], read_key=lambda p: "k",
                                       db_factory=lambda: db_session) == 2


def test_the_DI_status_route_reads_connected_for_a_personal_only_user(db_session):
    from routers import garmin as garmin_router
    _user(db_session, 1)
    app = FastAPI()
    app.include_router(garmin_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: db_session.get(models.User, 1)
    api = TestClient(app)
    assert api.get("/integrations/garmin/status").json() == {"connected": False, "personal_api": False}
    db_session.add(models.UserIntegration(user_id=1, provider="garmin_personal", api_key_encrypted="x"))
    db_session.commit()
    assert api.get("/integrations/garmin/status").json() == {"connected": True, "personal_api": True}
