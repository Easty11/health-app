"""A fake Garmin Personal API host, at the TRANSPORT layer (`httpx.MockTransport`).

Tests drive the REAL `PersonalClient` against this, so the exchange protocol, the header shape, the token
cache, the 401 retry and the response handling are all exercised, not stubbed (FEEDBACK section 23: code
that interprets a third party's response is tested with the transport faked, not the client).
"""
from __future__ import annotations

import base64
import json
import itertools
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx

from connectors import garmin_personal as gp

FAKE_KEY = "test-personal-api-key-0001"
FAKE_PK = 150823854                       # a stand-in userProfilePk (the real one is never put in a test)
_counter = itertools.count(1)


def make_jwt(exp: datetime, jti: Optional[int] = None) -> str:
    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64({'exp': int(exp.timestamp()), 'jti': jti or next(_counter)})}.sig"


class FakeHost:
    def __init__(self, key: str = FAKE_KEY, *, now: Optional[datetime] = None, ttl: timedelta = timedelta(hours=24)):
        self.key = key
        self.now = now or datetime.now(timezone.utc)
        self.ttl = ttl
        self.issued: set[str] = set()
        self.exchanges = 0
        self.requests: list[tuple[str, str, dict]] = []     # (method, path, params)
        self.routes: dict[tuple[str, Optional[str]], Any] = {}
        self.exchange_status: Optional[int] = None          # force the exchange to fail with this status
        self.reject_next_bearer = False                     # answer the next data call 401 once
        self.status_for: dict[str, int] = {}                # path -> forced status
        self.exchange_body: Optional[str] = None

    def set(self, path: str, payload: Any, date_: Optional[str] = None) -> None:
        self.routes[(path, date_)] = payload

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    @staticmethod
    def _date_of(request: httpx.Request) -> Optional[str]:
        q = dict(request.url.params)
        for k in ("date", "startDate"):
            if k in q:
                return q[k]
        last = request.url.path.rsplit("/", 1)[-1]
        return last if len(last) == 10 and last[4] == "-" else None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == gp.TOKEN_PATH:
            self.exchanges += 1
            if self.exchange_status is not None:
                return httpx.Response(self.exchange_status, text="nope")
            if request.headers.get("Authorization") != f"ApiKey {self.key}":
                return httpx.Response(401, text="bad key")
            token = self.exchange_body or make_jwt(self.now + self.ttl)
            self.issued.add(token)
            return httpx.Response(200, text=token + "\n")
        self.requests.append((request.method, path, dict(request.url.params)))
        auth = request.headers.get("Authorization", "")
        if self.reject_next_bearer:
            self.reject_next_bearer = False
            return httpx.Response(401)
        if not auth.startswith("Bearer ") or auth[7:] not in self.issued:
            return httpx.Response(401)
        if path in self.status_for:
            return httpx.Response(self.status_for[path])
        d = self._date_of(request)
        for key in ((path, d), (path.rsplit("/", 1)[0] if d else path, d), (path, None)):
            if key in self.routes:
                payload = self.routes[key]
                if callable(payload):
                    payload = payload(dict(request.url.params))
                if payload is None:
                    return httpx.Response(204)
                return httpx.Response(200, json=payload)
        return httpx.Response(404)


# -- payload builders (shapes per the 24-25 Oct 2026 probe; values synthetic) -----------------------

def hrv_payload(d: str, avg: float = 55.0, *, samples: int = 3, with_pk: bool = True) -> dict:
    p = {"hrvSummary": {"calendarDate": d, "lastNightAvg": avg, "weeklyAvg": avg + 1, "status": "BALANCED",
                        "baseline": {"balancedLow": 40.0, "balancedUpper": 70.0}},
         "hrvReadings": [{"hrvValue": avg + i, "readingTimeGMT": f"{d}T01:{i:02d}:00.0"} for i in range(samples)]}
    if with_pk:
        p["userProfilePk"] = FAKE_PK
    return p


def sleep_payload(d: str, *, tst: int = 27000, start="2026-10-24T12:00:00.0", end="2026-10-24T20:00:00.0") -> dict:
    return {"dailySleepDTO": {
        "calendarDate": d, "sleepTimeSeconds": tst, "sleepStartTimestampGMT": start, "sleepEndTimestampGMT": end,
        "deepSleepSeconds": 5400, "lightSleepSeconds": 16200, "remSleepSeconds": 5400, "awakeSleepSeconds": 1800,
        "averageRespirationValue": 14.0, "lowestRespirationValue": 10.0, "highestRespirationValue": 19.0,
        "averageSpO2Value": 95.0, "lowestSpO2Value": 88.0, "averageSpO2HRSleep": 51.0,
        "sleepScores": {"overall": {"value": 81, "qualifierKey": "GOOD"}, "totalDuration": {"qualifierKey": "GOOD"}},
        "awakeCount": 3, "avgSleepStress": 17.5, "sleepNeed": {"baseline": 480, "actual": 470},
        "userProfilePk": FAKE_PK}}


def heart_rate_payload(d: str, resting: int = 48) -> dict:
    return {"userProfilePK": FAKE_PK, "calendarDate": d, "restingHeartRate": resting,
            "lastSevenDaysAvgRestingHeartRate": resting + 1,
            "heartRateValues": [[1761264000000 + i * 120000, 55 + i] for i in range(4)] + [[1761264480000, None]]}


def spo2_hourly_payload(d: str) -> dict:
    return {"calendarDate": d, "spO2HourlyAverages": [[1761264000000 + h * 3600000, 94 + (h % 3)] for h in range(24)]}


def body_battery_payload(d: str) -> list:
    return [{"date": d, "charged": 60, "drained": 45,
             "bodyBatteryValuesArray": [[1761264000000, 30], [1761267600000, 85], [1761271200000, 12]]}]


def stress_payload(d: str) -> dict:
    return {"values": [{"calendarDate": d, "values": {"overallStressLevel": 29, "maxStressLevel": 91}}]}


def hr_zones_payload(max_hr: int = 190) -> list:
    return [{"sport": "DEFAULT", "trainingMethod": "HR_RESERVE", "maxHeartRateUsed": max_hr,
             "restingHeartRateUsed": 49, "lactateThresholdHeartRateUsed": 168}]


def populate(host: FakeHost, d: str) -> None:
    host.set(gp.HRV_PATH.format(date=d), hrv_payload(d))
    host.set(gp.SLEEP_PATH, sleep_payload(d), d)
    host.set(gp.HEART_RATE_PATH, heart_rate_payload(d), d)
    host.set(gp.SPO2_HOURLY_PATH.format(date=d), spo2_hourly_payload(d))
    host.set(gp.BODY_BATTERY_PATH, body_battery_payload(d), d)
    host.set(gp.STRESS_PATH.format(start=d, end=d), stress_payload(d))
    host.set(gp.HR_ZONES_PATH, hr_zones_payload())
