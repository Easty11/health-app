"""Which source's per-session RPE wins when more than one rated the same counted session.

THE one place the order is declared, and the one place the operator edits it. `reads.srpe_reads` reads it;
nothing else holds a copy.

    highest rung                                                                          lowest rung
    in_app  >  garmin  >  [future adapters, slotted here when each is added]  >  day_fill

  * `in_app` is RESERVED: the app's own per-session capture. It has no writer yet (the contract refuses a
    write naming it, `srpe_store.SOURCE_SCALES`), so today its rung is empty. Q189 names it as the natural
    surface for H10-only sessions.
  * A new adapter is added to `srpe_store.SOURCE_SCALES` (after a read-only probe, Q209 pattern, FEEDBACK
    section 17) AND slotted into `SOURCE_HIERARCHY` below, in the rank the operator chooses. A source that is
    stored but not listed here is IGNORED by the read (fail closed: an unranked rating is never guessed into
    the order), so its session counts as unrated and the question is asked.
  * `day_fill` is always the lowest rung and is not editable: `daily_records.session_rpe`, the one
    whole-day rating from the nightly close-out, fills only counted sessions that no source rated.

Within ONE source the latest `captured_at` wins. Ratings are never averaged.
"""
from __future__ import annotations

DAY_FILL = "day_fill"

# Highest rung first. Edit this tuple to re-rank; every name must be unique and none may be `day_fill`.
SOURCE_HIERARCHY: tuple[str, ...] = (
    "in_app",
    "garmin",
)

assert len(set(SOURCE_HIERARCHY)) == len(SOURCE_HIERARCHY) and DAY_FILL not in SOURCE_HIERARCHY, \
    "SOURCE_HIERARCHY must list each source once and must not name day_fill"


def rung_of(source: str) -> int | None:
    """0 for the highest rung; `len(SOURCE_HIERARCHY)` for `day_fill`; None for a source that is not ranked."""
    if source == DAY_FILL:
        return len(SOURCE_HIERARCHY)
    try:
        return SOURCE_HIERARCHY.index(source)
    except ValueError:
        return None
