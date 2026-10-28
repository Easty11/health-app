"""Read-only probe: does a fresh Personal API token exchange invalidate the previous token? (Q239 item 4)

    railway ssh --service health-app-backend
    cd /app
    /opt/venv/bin/python -m scripts.garmin_token_probe --user-id 1

The nightly sweep and the on-read refresh each exchange the user's key for a bearer token. If a new exchange
kills the token an older holder still has, those two can race. This answers it with the user's own key, in order:

  1. exchange token A and make one data request with it (the CONTROL: if A is not accepted, nothing below means anything);
  2. exchange token B from a second client (a fresh exchange, as a second process would make);
  3. make one data request with A, then one with B, then, after `--settle` seconds, A again.

A still accepted after B was issued -> a fresh exchange does NOT invalidate the previous token. A refused -> it does.
The data request is the HR-zone config (one small GET). Requests are paced 2 s apart (the host answers 429 to a burst).

No writes: it reads the key and writes nothing, not even the cached token. If the answer is that exchanges DO
invalidate, B replaces the token the user's cached copy holds, and the next real call self-heals with one 401 and one
re-exchange (the client's own retry). Output is ASCII: HTTP status codes and a verdict. No key, token or body is printed.
Exit 0 = a verdict was reached (NO_INVALIDATION or INVALIDATES), 1 = inconclusive.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Callable, Optional

import httpx

import garmin_personal_lanes as gpl
from connectors import garmin_personal as gp
from database import SessionLocal
from encryption import decrypt

PACE_S = gpl.PACE_S
SETTLE_S = 15.0


def _status(http: httpx.Client, token: str) -> int:
    """One data request with exactly this token; the raw status, no retry and no re-exchange (the client's own
    401 retry would hide the very answer being measured)."""
    try:
        return http.get(gp.HR_ZONES_PATH, headers={"Authorization": f"Bearer {token}"}).status_code
    except httpx.HTTPError as exc:
        raise gp.PersonalTransientError(f"GET: {type(exc).__name__}") from None


def probe(api_key: str, *, transport: Optional[httpx.BaseTransport] = None, pace_s: float = PACE_S,
          settle_s: float = SETTLE_S, sleep: Callable[[float], None] = time.sleep) -> dict:
    out: dict = {"verdict": "INCONCLUSIVE", "reason": None, "a_control": None, "a_after_b": None,
                 "b": None, "a_after_settle": None, "tokens_differ": None}
    with gp.PersonalClient(api_key, transport=transport) as ca, gp.PersonalClient(api_key, transport=transport) as cb, \
            httpx.Client(base_url=gp.BASE_URL, timeout=gp.TIMEOUT_S, transport=transport) as http:
        token_a = ca.exchange()
        sleep(pace_s)
        out["a_control"] = _status(http, token_a)
        if out["a_control"] != 200:
            out["reason"] = f"control request with token A answered HTTP {out['a_control']}, not 200"
            return out
        sleep(pace_s)
        token_b = cb.exchange()
        out["tokens_differ"] = token_a != token_b
        sleep(pace_s)
        out["a_after_b"] = _status(http, token_a)
        sleep(pace_s)
        out["b"] = _status(http, token_b)
        sleep(settle_s)
        out["a_after_settle"] = _status(http, token_a)
    if out["b"] != 200:
        out["reason"] = f"the new token B answered HTTP {out['b']}, not 200"
    elif not out["tokens_differ"]:
        out["verdict"], out["reason"] = "SAME_TOKEN", "the second exchange returned the same token; nothing to invalidate"
    elif 200 == out["a_after_b"] == out["a_after_settle"]:
        out["verdict"] = "NO_INVALIDATION"
    elif out["a_after_b"] == 401 or out["a_after_settle"] == 401:
        out["verdict"] = "INVALIDATES"
    else:
        out["reason"] = f"token A answered HTTP {out['a_after_b']} then {out['a_after_settle']}; neither a clean 200 nor a 401"
    return out


def main(argv: list[str] | None = None, *, db_factory=SessionLocal, transport: Optional[httpx.BaseTransport] = None,
         sleep: Callable[[float], None] = time.sleep) -> int:
    p = argparse.ArgumentParser(description="Does a fresh token exchange invalidate the previous token? (read-only)")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--settle", type=float, default=SETTLE_S, help="seconds before the second check of token A")
    args = p.parse_args(argv)

    db = db_factory()
    try:
        row = gpl.get_row(db, args.user_id)
        api_key = decrypt(row.api_key_encrypted) if row is not None else None
    finally:
        db.close()
    if api_key is None:
        print(f"user {args.user_id} has no garmin_personal key", file=sys.stderr)
        return 1
    try:
        res = probe(api_key, transport=transport, settle_s=args.settle,
                    pace_s=0.0 if transport is not None else PACE_S, sleep=sleep)
    except gp.PersonalApiError as exc:
        print(f"STOPPED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        del api_key
    print(f"user {args.user_id}: tokens_differ={res['tokens_differ']} A_control={res['a_control']} "
          f"A_after_B={res['a_after_b']} B={res['b']} A_after_settle={res['a_after_settle']}")
    print(f"VERDICT: {res['verdict']}" + (f" ({res['reason']})" if res["reason"] else ""))
    return 0 if res["verdict"] in ("NO_INVALIDATION", "INVALIDATES", "SAME_TOKEN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
