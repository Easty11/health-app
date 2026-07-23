"""Clock arithmetic for the CBT-I module — one definition of the midnight wrap.

Extracted from `import_cbti_block.py` (phase 1), where the conditional wrap was
the defect the Gate-4 reconciliation caught: an unconditional +24h under-read a
night whose bedtime fell after midnight by 0.445 SE. The engine, the prefill
sanity gate and any TIB display all need this arithmetic, and a second local
copy is how the two drift apart — so it lives here once.

The wrap is CONDITIONAL. A span wraps to the next day only when the end clock
time is strictly earlier than the start clock time:

    22:36 -> 05:00   end < start   -> wraps   -> 384 min
    00:05 -> 08:45   end > start   -> no wrap -> 520 min

All functions take and return minutes-since-midnight or "HH:MM" strings; none
of them know about dates, and none of them read the database.
"""
from __future__ import annotations

MINUTES_PER_DAY = 1440


def clock_to_minutes(hhmm: str | None) -> int | None:
    """"22:36" -> 1356. None/blank/malformed -> None (never raises)."""
    if not hhmm or not isinstance(hhmm, str):
        return None
    parts = hhmm.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def minutes_to_clock(minutes: int | None) -> str | None:
    """1356 -> "22:36". Wraps modulo a day so 1500 -> "01:00"."""
    if minutes is None:
        return None
    minutes %= MINUTES_PER_DAY
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def minutes_between(start_min: int | None, end_min: int | None) -> int | None:
    """Elapsed minutes from start to end, wrapping past midnight only when the
    end clock time is earlier than the start. Returns None if either is None."""
    if start_min is None or end_min is None:
        return None
    return (end_min - start_min) if end_min >= start_min else (end_min + MINUTES_PER_DAY - start_min)


def tib_minutes(lights_out_min: int | None, out_of_bed_min: int | None) -> int | None:
    """Time in bed = the SE denominator: lights-out (attempted sleep) to out-of-bed.

    Named separately from `minutes_between` because the SE window is a specific
    contract — it opens at "tried to sleep", not at "got into bed" — and callers
    should say which span they mean.
    """
    return minutes_between(lights_out_min, out_of_bed_min)


def window_minutes(lights_out_hhmm: str, wake_hhmm: str) -> int | None:
    """Prescribed window length from an "HH:MM" lights-out to an "HH:MM" wake
    anchor, e.g. 22:36 -> 05:00 = 384. Uses the same conditional wrap, so a
    post-midnight prescription (00:30 -> 05:00 = 270) is not inflated by a day."""
    return minutes_between(clock_to_minutes(lights_out_hhmm), clock_to_minutes(wake_hhmm))


def signed_offset_minutes(from_min: int | None, to_min: int | None) -> int | None:
    """Signed shortest distance between two minutes-since-midnight values, in
    [-720, +720]. The single definition of "how far apart are two clock times",
    used for adherence deltas, the prefill sanity gate, and for centring a set of
    clock times before taking their standard deviation.

    Kept here rather than inline at each call site for the same reason the wrap
    is: two copies of clock arithmetic drift, and the drift is silent.
    """
    if from_min is None or to_min is None:
        return None
    d = (to_min - from_min) % MINUTES_PER_DAY
    return d - MINUTES_PER_DAY if d > MINUTES_PER_DAY // 2 else d


def clock_delta_minutes(a_hhmm: str | None, b_hhmm: str | None) -> int | None:
    """Signed shortest distance from a to b in minutes, in [-720, +720].

    For adherence ("how far is actual bedtime from prescribed?") and for the
    prefill sanity gate ("is this device value implausibly far from the
    prescription?"), where 23:50 and 00:10 are 20 minutes apart, not 1420.
    """
    return signed_offset_minutes(clock_to_minutes(a_hhmm), clock_to_minutes(b_hhmm))
