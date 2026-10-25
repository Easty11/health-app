"""Sleep-night helpers shared by the two sleep readers (`recovery_night`, `snapshot_reads`).

Read-side only. Split out of `snapshot_reads` so that module can consume `recovery_night`'s
per-field resolution without an import cycle; `snapshot_reads` re-exports every name below, so
existing imports from it keep working.

WRITER IDENTITY. Health Connect names the app that wrote each record
(`health_connect_record_sources.source_package`); the maps here turn those packages into the
friendly keys the rank tuples use. The Garmin Personal API is a different TRANSPORT of the same
`garmin` source (#449), not a Health Connect writer, and does not appear here.

PLAUSIBILITY (`night_implausibility`). A sleep night read off a wearable is withheld, with its
reason, when it cannot be one night. The first case: user 1's 25 Oct 2026 Health Connect night read
TST 1151 min (light 1067) because one Garmin session started exactly 12 hours before the Personal
API's start for the same night (01:35:00Z against 13:35:00Z); deep and REM matched the API to the
minute, the light stage absorbed the extra 719 minutes, and the aggregate's span ran 20 hours. The
aggregate stores no per-stage segments, so the corruption cannot be undone on read, only refused.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models

# Health Connect writer package → friendly source, as the packages actually arrive in
# health_connect_record_sources.source_package. Withings is a real HC sleep writer historically
# (Q83) even though it is disabled on live nights, so a Samsung+Withings night is recognised as
# multi-source rather than misattributed to Samsung.
SLEEP_SOURCE_BY_PACKAGE = {
    "com.garmin.android.apps.connectmobile": "garmin",
    "com.sec.android.app.shealth": "samsung",
    "com.withings.wiscale2": "withings",
}
SLEEP_SOURCE_LABELS = {"garmin": "Garmin", "samsung": "Samsung", "withings": "Withings"}
# Names for the value itself. The Samsung Health relay and the Samsung scraper are different
# writers with different data, so the snapshot never calls either of them just "Samsung".
SLEEP_WRITER_NAMES = {"garmin": "Garmin", "samsung": "Samsung Health", "withings": "Withings"}
SCRAPER_WRITER_NAME = "Samsung scraper"
# Writer priority, highest first, for the sources this module can name. The scraper is not an
# HC writer; it sits below every HC writer by the ruling in snapshot_reads.
SLEEP_WRITER_PRIORITY = ("garmin", "samsung", "withings")

# A night longer than this is not one night. PROPOSED, pending the operator's ruling (Q243 brief,
# S3): 12 h catches the 12-hour start-time shift above whatever the true night was (the shift adds
# ~720 min), and sits 1.7 h above the longest night read in prod (10.3 h, user 4, Personal API).
MAX_PLAUSIBLE_TST_MIN = 12 * 60
# Stage minutes are floored per stage, so allow a minute of rounding against the session span.
_SPAN_TOLERANCE_MIN = 1.0


def hc_sleep_writers(db: Session, user_id: int, night: date) -> set[str]:
    """The distinct REAL writer packages of a Health Connect sleep night.

    JOIN WINDOW: a sleep session's `record_start` is its START timestamp, whose local date is
    normally the calendar day BEFORE the wake-date `health_connect_syncs` is keyed on, so match
    `record_start` on {night, night-1}. The 'unknown' pre-cutover sentinel is not a source."""
    days = [night.isoformat(), (night - timedelta(days=1)).isoformat()]
    rows = db.execute(
        select(models.HealthConnectRecordSource.source_package)
        .where(
            models.HealthConnectRecordSource.user_id == user_id,
            models.HealthConnectRecordSource.record_type == "sleep",
            func.substr(models.HealthConnectRecordSource.record_start, 1, 10).in_(days),
        )
        .distinct()
    ).all()
    return {pkg for (pkg,) in rows if pkg and pkg != "unknown"}


def night_implausibility(
    tst_min: float | None,
    stage_min: float | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> str | None:
    """Why a sleep night cannot be one night, or None when it can.

    Refuses (a) a total sleep time above `MAX_PLAUSIBLE_TST_MIN`, and (b) more asleep minutes, in
    total or in the stage sum, than the night's own start-to-end span. Pure: the caller decides
    what to do with the reason (the readers withhold the night and print it)."""
    if tst_min is not None and tst_min > MAX_PLAUSIBLE_TST_MIN:
        return (f"TST {tst_min:.0f} min exceeds {MAX_PLAUSIBLE_TST_MIN / 60:.0f} h "
                f"({tst_min / 60:.1f} h is not one night)")
    if start is not None and end is not None and end > start:
        span = (end - start).total_seconds() / 60
        for name, v in (("TST", tst_min), ("stage sum", stage_min)):
            if v is not None and v > span + _SPAN_TOLERANCE_MIN:
                return f"{name} {v:.0f} min exceeds the night's own span of {span:.0f} min"
    return None
