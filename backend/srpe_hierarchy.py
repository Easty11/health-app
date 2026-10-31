"""Which source's per-session RPE wins when more than one rated the same counted session.

THE one place the order is declared, and the one place the operator edits it. `reads.srpe_reads` reads it;
nothing else holds a copy.

    highest rung                                                                          lowest rung
    in_app  >  garmin  >  [future adapters, slotted here when each is added]

  * `in_app` is the app's own per-session capture (`srpe_in_app`: the close-out, the AM catch-up, the backfill).
    It is the only route for a Hevy workout, which records no session RPE, and it outranks the device's own
    rating for the same session.
  * A new adapter is added to `srpe_store.SOURCE_SCALES` (after a read-only probe, Q209 pattern, FEEDBACK
    section 17) AND slotted into `SOURCE_HIERARCHY` below, in the rank the operator chooses. A source that is
    stored but not listed here is IGNORED by the read (fail closed: an unranked rating is never guessed into
    the order), so its session counts as unrated and the question is asked.
  * There is no whole-day rung. The day fill (`daily_records.session_rpe` filling every unrated session of its
    day) was RETIRED by operator ruling: a session no source rated reads UNRATED and never borrows the day.
    `daily_records.session_rpe` is still a column; it is written by nothing and read by nothing.

Within ONE source the latest `captured_at` wins. Ratings are never averaged.
"""
from __future__ import annotations

# Highest rung first. Edit this tuple to re-rank; every name must be unique.
SOURCE_HIERARCHY: tuple[str, ...] = (
    "in_app",
    "garmin",
)

assert len(set(SOURCE_HIERARCHY)) == len(SOURCE_HIERARCHY), "SOURCE_HIERARCHY must list each source once"


def rung_of(source: str) -> int | None:
    """0 for the highest rung; None for a source that is not ranked."""
    try:
        return SOURCE_HIERARCHY.index(source)
    except ValueError:
        return None
