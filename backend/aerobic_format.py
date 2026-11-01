"""Shared aerobic-session rendering — the single source of truth for turning one
`aerobic_sessions` row into its one-line text form.

Consumed by both `mcp_server.get_training_sessions` (the external MCP surface) and
`session_focus` (the in-app chat's pinned session block, A1). It is the aerobic twin of
`hevy_format.format_set`: the same one-renderer-per-kind rule (a summariser duplicated across
two surfaces is how one copy drifts — DECISIONS_LOG #68), so a session reads the same wherever
it is reviewed.

The line is the MCP tool's, moved here verbatim — the MCP output is byte-identical across the
extraction (Brief A G2). Pure: takes a row-like object (`session_date`, `source`, `sport_name`,
`duration_minutes`, `hr_avg`, `hr_max`, `calories`, `z1_seconds`…`z5_seconds`), touches no DB.
"""

import json
from typing import Any


def format_aerobic_session(s: Any) -> str:
    """One aerobic session as a compact line: date, source, sport, duration, avg/max HR,
    calories, and the HR-zone minutes when the row carries a zone split.

    `—` marks an absent value. `dist=—` is fixed: `aerobic_sessions` has no distance column.
    Zones render only when `z1_seconds` is non-NULL (the writers set the five zone columns
    together), each zone as whole minutes with empty zones omitted."""
    dur_min = f"{s.duration_minutes:.0f} min" if s.duration_minutes else "—"
    avg_hr = f"{s.hr_avg:.0f}" if s.hr_avg is not None else "—"
    max_hr = f"{s.hr_max:.0f}" if s.hr_max is not None else "—"
    cal = f"{s.calories:.0f} kcal" if s.calories is not None else "—"

    zone_summary = ""
    if s.z1_seconds is not None:
        zones = {
            "1": round((s.z1_seconds or 0) / 60), "2": round((s.z2_seconds or 0) / 60),
            "3": round((s.z3_seconds or 0) / 60), "4": round((s.z4_seconds or 0) / 60),
            "5": round((s.z5_seconds or 0) / 60),
        }
        zone_parts = [f"Z{k}={v}min" for k, v in zones.items() if v]
        zone_summary = " zones=[" + " ".join(zone_parts) + "]"

    return (
        f"{s.session_date} [{s.source}] {s.sport_name or 'unknown'}: "
        f"{dur_min} HR={avg_hr}/{max_hr} dist=— cal={cal}{zone_summary}"
    )


def format_selfeval(row: Any) -> str:
    """The self-evaluation suffix for a session line, e.g. ` selfeval=[RPE 4/10 feel 25/100 garmin]`.

    `row` is the session's per-session rating from the read door (`reads.srpe_reads.Rating`: `rpe_cr10`,
    `feel`, `source`), never the whole-day fill. RPE is CR-10; feel is the source's passthrough (Garmin's
    0-100 as sent, no label: only 25 = "Weak" is verified); the trailing word names the source. The shared `format_aerobic_session` line is NOT changed, so the
    in-app chat's pinned session block reads as before; only `get_training_sessions` appends this."""
    parts = []
    if row.rpe_cr10 is not None:
        parts.append(f"RPE {row.rpe_cr10:g}/10")
    if row.feel is not None:
        parts.append(f"feel {row.feel}/100")
    return f" selfeval=[{' '.join(parts)} {row.source}]"


def format_day_ratings(rated: Any) -> str:
    """One day's per-session ratings, e.g. `Upper body 8/10 in_app; Pilates 3/10 garmin; Walk unrated`, or `—`
    when the day has no counted session.

    `rated` is the read door's `RatedSession` list for the day (`.bout`, `.rating`): each counted session with
    the rating and source the door resolved, never a whole-day value. An unrated session says so."""
    from reads.srpe_reads import session_label
    parts = []
    for rs in rated:
        label = session_label(rs.bout)
        parts.append(f"{label} unrated" if rs.rating is None
                     else f"{label} {rs.rating.rpe_cr10:g}/10 {rs.rating.source}")
    return "; ".join(parts) if parts else "—"


def format_also_recorded_by(twins: Any) -> str:
    """The Q201(b) twin suffix for a canonical session line (#418), e.g.
    ` also_recorded_by=[{"source": "health_connect", "source_package": "com.garmin.android.apps.connectmobile"}]`.

    `twins` are the non-canonical rows the canonical row suppressed. Identity only — source and
    source_package per twin: no ids, no zones, no load, so a twin can never be read as additional
    training. An empty/None `twins` yields "" (the field is omitted, never empty-listed). The shared
    `format_aerobic_session` line is NOT changed, so the in-app chat's pinned session block reads as
    before; only the MCP coach reads append this."""
    if not twins:
        return ""
    entries = [{"source": t.source, "source_package": t.source_package} for t in twins]
    return " also_recorded_by=" + json.dumps(entries)
