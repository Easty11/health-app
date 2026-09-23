"""Sliding token renewal on /health-connect/sync (#NEXT; cross-ref HCA #44).

A companion that syncs on a schedule but is never opened must not reach the access-
token expiry. Every SUCCESSFUL sync returns `renewed_token`, minted with the login
route's claim set ({"sub": email}) and lifetime; no failed sync carries one.

Driven through the REAL router and the REAL get_current_user (bearer decode), with only
get_db overridden, so the request token is genuinely validated and the 4xx paths are the
production ones — not a direct call to sync() that would skip auth entirely.

  a) success      -> renewed_token decodes to the same subject, later exp than the
                     request token, same lifetime as login.
  b) 422 / 401    -> no renewed_token in the body.
  c) existing sync tests unregressed — the rest of the suite, run whole.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth
import database
import models
from routers import health_connect

_EMAIL = "hc-token-renewal@example.com"
_SECRET = "test-only-token-renewal"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(auth, "SECRET_KEY", _SECRET)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    database.Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    s = Session()
    s.add(models.User(email=_EMAIL, hashed_password="x"))
    s.commit()
    s.close()

    def _db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(health_connect.router)
    app.dependency_overrides[database.get_db] = _db
    return TestClient(app, raise_server_exceptions=False)


def _token(exp: datetime, sub: str = _EMAIL) -> str:
    return jwt.encode({"sub": sub, "exp": exp}, _SECRET, algorithm=auth.ALGORITHM)


def _decode(tok: str) -> dict:
    return jwt.decode(tok, _SECRET, algorithms=[auth.ALGORITHM])


def _body() -> dict:
    return {"sleep": [], "hrv": [], "heartRate": [], "steps": [], "workouts": []}


def _post(client, token, body):
    return client.post("/health-connect/sync", json=body,
                       headers={"Authorization": f"Bearer {token}"})


# ---------- a) success carries a renewed token ----------

def test_successful_sync_returns_renewed_token_same_subject_later_exp(client):
    now = datetime.now(timezone.utc)
    req_tok = _token(now + timedelta(minutes=1))     # about to expire
    r = _post(client, req_tok, _body())
    assert r.status_code == 200
    body = r.json()

    renewed = body["renewed_token"]
    assert renewed and renewed != req_tok
    claims = _decode(renewed)
    assert claims["sub"] == _EMAIL == _decode(req_tok)["sub"]
    assert claims["exp"] > _decode(req_tok)["exp"]
    # Same lifetime as login (no new env var): exp ~= now + ACCESS_TOKEN_EXPIRE_MINUTES.
    expected = now + timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    assert abs(claims["exp"] - expected.timestamp()) < 60
    # Same claim set as the login route: sub + exp, nothing else.
    assert set(claims) == {"sub", "exp"}

    # Additive: the existing response keys are untouched.
    for k in ("synced", "dates", "rejected_pre_2020", "sources_captured",
              "received", "aggregated", "unattributed", "exercise_ingest"):
        assert k in body


def test_renewed_token_authenticates_the_next_sync(client):
    """The chain a scheduled companion relies on: sync N's renewed token is accepted
    by get_current_user on sync N+1."""
    r1 = _post(client, _token(datetime.now(timezone.utc) + timedelta(minutes=1)), _body())
    r2 = _post(client, r1.json()["renewed_token"], _body())
    assert r2.status_code == 200
    assert "renewed_token" in r2.json()


# ---------- b) failed syncs carry no token ----------

def test_invalid_payload_422_carries_no_renewed_token(client):
    body = _body()
    body.pop("heartRate")                                # missing canonical stream
    body["steps"] = [{"count": "not-a-number"}]
    r = _post(client, _token(datetime.now(timezone.utc) + timedelta(hours=1)), body)
    assert r.status_code == 422
    assert "renewed_token" not in r.text


def test_expired_token_401_carries_no_renewed_token(client):
    r = _post(client, _token(datetime.now(timezone.utc) - timedelta(minutes=1)), _body())
    assert r.status_code == 401
    assert "renewed_token" not in r.text


def test_unknown_subject_401_carries_no_renewed_token(client):
    r = _post(client, _token(datetime.now(timezone.utc) + timedelta(hours=1),
                             sub="nobody@example.com"), _body())
    assert r.status_code == 401
    assert "renewed_token" not in r.text
