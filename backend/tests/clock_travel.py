"""pytest plugin for the date-fragility pin (`test_clock_pin.py`): travel the WHOLE session, collection
included, to the date in `PIN_TRAVEL_TO` (an ISO UTC datetime), with the clock still ticking.

Session-wide on purpose: several tests capture `_TODAY = datetime.now(...)` at import, so a per-test
travel would leave them on the real date while the code under test sees the travelled one.

`time-machine` (not freezegun): it patches the clock sources and leaves the real `datetime`/`date`
classes and the monotonic clock alone, so routes registered during a test and asyncio sleeps still work.
"""
import datetime as dt
import os

import time_machine

_travel = None


def pytest_configure(config):
    global _travel
    target = os.environ.get("PIN_TRAVEL_TO")
    if not target:
        return
    dest = dt.datetime.fromisoformat(target).replace(tzinfo=dt.timezone.utc)
    _travel = time_machine.travel(dest, tick=True)
    _travel.start()


def pytest_unconfigure(config):
    if _travel is not None:
        _travel.stop()
