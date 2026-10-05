"""Pin: the date-sensitive tests still pass a year from now (the 6 Oct 2026 rollover class).

Two tests failed on the day a hardcoded date stopped being "recent" or "future" (#335, and the HC-sync
and seed-constraints fixes after it), each a day after CI last passed. A fixed date compared with the
clock cannot fail until the day it flips, so this runs the files that mix a date literal with a live
clock under a clock ONE YEAR AHEAD: a new literal that goes stale within a year fails here, now.

Which files: every test file that holds a `2026-`/`2027-` date literal AND reads a live clock (the same
test the sweep used), so a new file with both is covered without anyone remembering to add it, plus the
five files the 15 Oct watch item named. It runs them in a subprocess because the clock must be travelled
before collection (see `clock_travel.py`).
"""
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TESTS = Path(__file__).parent
_BACKEND = _TESTS.parent
_LITERAL = re.compile(r"\b202[67]-\d{2}-\d{2}")   # no trailing \b: also matches 2026-09-28T05:00:00Z
_CLOCK = re.compile(
    r"_local_day\(|date\.today\(|datetime\.now\(|datetime\.utcnow\(|\b_today\(|_today_aest|time\.time\(|utcnow"
)
# The 15 Oct 2026 watch item (hardcoded `review_by`); they match the rule today, named so a refactor
# that drops their clock read does not silently drop them from the pin.
_NAMED = (
    "test_constraint_engine_arm.py", "test_constraint_entries.py", "test_sweep_constraint_rehome.py",
    "test_typed_entries_render.py", "test_typed_write_shape_docs.py",
)
_SELF = Path(__file__).name


def date_sensitive_files() -> list[str]:
    found = set(_NAMED)
    for p in _TESTS.glob("test_*.py"):
        if p.name == _SELF:
            continue
        text = p.read_text(encoding="utf-8")
        if _LITERAL.search(text) and _CLOCK.search(text):
            found.add(p.name)
    return sorted(found)


def test_the_named_files_exist_and_the_rule_finds_them():
    for name in _NAMED:
        assert (_TESTS / name).exists(), name
    found = date_sensitive_files()
    assert set(_NAMED) <= set(found)
    assert len(found) >= 20, found          # the rule is live, not an empty glob


def test_date_sensitive_files_pass_one_year_ahead():
    target = (datetime.now(timezone.utc) + timedelta(days=366)).replace(microsecond=0)
    files = [str(_TESTS / f) for f in date_sensitive_files()]
    env = {**os.environ, "PIN_TRAVEL_TO": target.replace(tzinfo=None).isoformat()}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "tests.clock_travel", "-q", "-p", "no:cacheprovider", *files],
        cwd=_BACKEND, env=env, capture_output=True, text=True, timeout=600,
    )
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-40:])
    assert proc.returncode == 0, (
        f"a date-sensitive test fails with the clock at {target:%Y-%m-%d %H:%M}Z: a fixed date compared "
        f"with the clock. Derive it from _local_day() (today + N days), or travel the clock for a test "
        f"about a fixed date.\n{tail}"
    )
