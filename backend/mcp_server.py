import functools
import inspect
import json
import re
from datetime import date, datetime, timezone, timedelta

import httpx
import pytz

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from injury_trajectory import evaluate as evaluate_injury_trajectories
from connectors.hevy import HevyClient
from hevy_format import format_set, format_workout_compact
from hevy_routine_format import (  # shared renderers (#314) — one home, also used by context_builder
    format_routine_compact,
    format_routine_full,
)
from hevy_templates import (
    _visible_to,
    catalogue_titles_by_id,
    refresh_catalogue_if_stale,
    sync_exercise_templates,
)
from encryption import decrypt
from oauth_provider import PersonalOAuthProvider
import appointment_brief
import clinical_documents
import models
import typed_entries
from routers.knowledge import FINDING_DOMAINS
from routers.labs import get_lab_results as _read_lab_results, StoredResultOut
from routers.clinical_documents import document_out as _clinical_document_out, parse_filters as _parse_document_filters
from reads.labs_reads import latest_lab_results
from aerobic_format import format_aerobic_session, format_also_recorded_by, format_day_ratings, format_selfeval   # one aerobic renderer, shared with the in-app chat (A2)
from reads.srpe_reads import aerobic_bout, hevy_bout, observed_ratings, session_ratings   # per-session RPE/feel for a session, any source (Q209)
from reads.aerobic_reads import arbitrated_sessions, overlap_fraction, overlaps_workout, twins_by_canonical   # the canonical read-door (#Q161) and the ONE Hevy-overlap predicate (#309/A3.2)
from reads.hevy_reads import counted_workouts   # the counted-Hevy read-door (#309)
from sport_classes import is_strength_sport
from reads.recovery_reads import hrv_deviation, representative_source
from reads.recovery_night import recovery_text   # per-field recovery resolution (get_recovery_metrics)
from reads.freshness_reads import freshness, freshness_footer_line, freshness_snapshot_lines
from reads.snapshot_reads import hrv_continuity, hrv_continuity_line, latest_sleep_night, sleep_snapshot_lines
from engine.training_phase import current_training_phase
from engine import week_plan as week_plan_mod   # the plan's derivations (#316), incl. the uncounted-item day lookup
from context_builder import CONCURRENT_STRENGTH_PHRASE, _uncounted_phrase, plan_of_record_stale   # the ONE plan-of-record STALE definition (#312/#319); the ONE `concurrent_strength` wording
from current_state import current_state as _current_state   # plan, phase, phase_folders, week plan: one read
from load_metrics import _local_day   # the single operator-local-day source

_SERVER_ROOT = "https://health-app-backend-production-760e.up.railway.app"
_MCP_URL = f"{_SERVER_ROOT}/mcp"

# Held at module level (not anonymous) so routers/mcp_auth.py's login form
# can call complete_login()/get_user_id() on the same instance FastMCP uses.
_oauth_provider = PersonalOAuthProvider()

mcp = FastMCP(
    "Health Intelligence",
    auth_server_provider=_oauth_provider,
    auth=AuthSettings(
        issuer_url=_SERVER_ROOT,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        resource_server_url=_MCP_URL,
    ),
    # Disable DNS-rebinding protection: deployed behind Railway's reverse proxy,
    # Host header is the public domain — not localhost — so the auto-enabled
    # protection (triggered when host defaults to 127.0.0.1) would reject every
    # request with 421. Setting transport_security explicitly disables it.
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


def _request_access_token() -> AccessToken | None:
    """The access token that authenticated THIS request.

    The SDK's `get_access_token()` reads a contextvar that tool handlers inherit from the task
    which started the MCP session, i.e. the FIRST request of the session. Once access tokens
    expire (Q196) that is the wrong token: a client that refreshes keeps its Mcp-Session-Id and
    sends the new token, the middleware accepts it, but the handler would still see the token
    that created the session, by then expired. The current request's own token is on its
    `scope["user"]`, which the bearer middleware set for this request. Outside an HTTP request
    (no request context) the contextvar is the only source, so it is the fallback."""
    try:
        request = mcp.get_context().request_context.request
    except (LookupError, ValueError):
        request = None
    if request is None:
        return get_access_token()
    user = request.scope.get("user")
    return user.access_token if isinstance(user, AuthenticatedUser) else None


def _current_user_id() -> int:
    """Resolve the caller's user_id from the bearer token of the current request. Raises
    rather than falling back to any default — every tool call must be bound
    to a real, logged-in user (see oauth_provider.PersonalOAuthProvider)."""
    token = _request_access_token()
    if token is None:
        raise ValueError("No authenticated MCP session — sign in via /mcp/login first")
    user_id = _oauth_provider.get_user_id(token.token)
    if user_id is None:
        raise ValueError("MCP token is not bound to a user")
    return user_id


def _db_rows(sql: str, params: dict) -> list[dict]:
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        cols = result.keys()
        return [dict(zip(cols, row)) for row in result.fetchall()]


def _as_date(v) -> date:
    """A raw-SQL `date` column as a `date` (SQLite hands back an ISO string; Postgres a date)."""
    return v if isinstance(v, date) and not isinstance(v, datetime) else date.fromisoformat(str(v)[:10])


def _epley_1rm(weight_kg: float, reps: int) -> float:
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + reps / 30)


# ---------------------------------------------------------------------------
# Temporal anchoring — every tool output carries a visible `as_of` (WS3 / #281)
# ---------------------------------------------------------------------------

# Australia/Brisbane, no DST — the operator-local day the rest of the codebase
# anchors on (context_builder, load_metrics). An MCP thread can persist across
# calendar days; without a per-output stamp the client reasons off whatever "today"
# it last cached (the Q140 skew family). The data itself is already emit-time fresh
# (every query resolves `CURRENT_DATE` server-side per call); this makes the anchor
# the data was computed against VISIBLE, so a re-run on a later day is legible as later.
_AS_OF_TZ = pytz.timezone("Australia/Brisbane")


def _as_of(now: datetime | None = None) -> str:
    """ISO-8601 Brisbane-local instant this response was generated (seconds grain)."""
    dt = now.astimezone(_AS_OF_TZ) if now is not None else datetime.now(_AS_OF_TZ)
    return dt.isoformat(timespec="seconds")


def _aest_wake_day(now: datetime | None = None) -> date:
    """The Brisbane-local wake-day for `now` (default: the wall clock). The HRV readiness
    read keys on this, not the UTC date: at 07:00 AEST the UTC date is still YESTERDAY,
    and under the same-wake-day recency gate (#327) a UTC `for_date` would read
    yesterday's night as today's."""
    dt = now.astimezone(_AS_OF_TZ) if now is not None else datetime.now(_AS_OF_TZ)
    return dt.date()


def _stamp(body: str, now: datetime | None = None) -> str:
    """Prepend the generation-time anchor to a tool's text output."""
    return f"as_of: {_as_of(now)} (Australia/Brisbane)\n\n{body}"


def _stamped(fn):
    """Decorator: stamp a tool's string return with `as_of` at the call boundary, once.

    Applied UNDER `@mcp.tool()` (so the tool the client sees is the stamped one) and
    ABOVE the body, so it wraps every exit path -- including the no-data early returns
    -- without editing each `return`. `functools.wraps` preserves the signature and
    docstring FastMCP introspects. Handles the one async tool (`get_hevy_workouts`)."""
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def _async_wrapper(*args, **kwargs):
            return _stamp(await fn(*args, **kwargs))
        return _async_wrapper

    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        return _stamp(fn(*args, **kwargs))
    return _wrapper


# ---------------------------------------------------------------------------
# Tool 1 — Recovery metrics
# ---------------------------------------------------------------------------

@mcp.tool()
@_stamped
def get_recovery_metrics(days: int = 7) -> str:
    """Get recent recovery biometrics, one line per wake-day, each value tagged with the
    source that supplied it, including the Garmin transport ([garmin/api] the Personal API,
    [garmin/HC] Health Connect, [garmin/di] the epoch SpO2 lane). Every field resolves on its
    own to its best available source (HRV, TST and sleep stages, efficiency, SpO2, respiratory
    rate, heart rate), so a source that carries only some fields never blanks the others. HRV is
    never ranked or blended across instruments: each source's reading is shown. Sleep stages
    come from one writer, never mixed. Eff is derived from the device's own sleep window (no
    pre-sleep time), so it reads higher than the diary efficiency. RHR= is the daily resting
    rate and nothing else; the sleep nadir and the ring's sleep HR are separate, labelled
    figures. A sleep night that cannot be one night is withheld and the reason printed. A field
    no source carries prints '—'."""
    user_id = _current_user_id()
    since = _aest_wake_day() - timedelta(days=days)
    with SessionLocal() as _db:
        return recovery_text(_db, user_id, since, days)


# ---------------------------------------------------------------------------
# Tool 2 — Check-in history
# ---------------------------------------------------------------------------

@mcp.tool()
@_stamped
def get_checkin_history(days: int = 30) -> str:
    """Get morning check-in history. Unions legacy and new tables for
    continuous history. Returns sleep quality, fatigue, soreness, life load,
    alcohol context, each day's per-session RPE with its source, and readiness scores."""
    user_id = _current_user_id()

    rows = _db_rows(
        """
        SELECT date, sleep_quality, fatigue, soreness::text, motivation,
               life_load, alcohol_units,
               -- #327: HRV read live from hrv_readings by wake-day equality (garmin
               -- headlines a same-day pair, as select_wakeday_hrv); the retained
               -- passive_hrv_ms denorm is a fallback ONLY for a day with no canonical row.
               COALESCE(
                   (SELECT h.rmssd_ms FROM hrv_readings h
                    WHERE h.user_id = dr.user_id AND h.captured_at = dr.date
                      AND h.rmssd_ms IS NOT NULL
                    ORDER BY CASE h.source WHEN 'garmin' THEN 2 WHEN 'samsung' THEN 1
                             ELSE 0 END DESC, h.id DESC
                    LIMIT 1),
                   dr.passive_hrv_ms   -- reached only when no value-bearing row exists
               ) AS hrv_ms,
               morning_readiness, 'daily_records' AS source
        FROM daily_records dr
        WHERE user_id = :user_id
          AND am_timestamp IS NOT NULL
          AND date >= CURRENT_DATE - :days

        UNION ALL

        SELECT date, sleep_quality, fatigue, NULL AS soreness,
               motivation, NULL AS life_load, NULL AS alcohol_units,
               NULL AS hrv_ms,
               readiness_score AS morning_readiness, 'legacy' AS source
        FROM daily_check_ins
        WHERE user_id = :user_id
          AND date >= CURRENT_DATE - :days

        ORDER BY date DESC
        """,
        {"user_id": user_id, "days": days},
    )

    if not rows:
        return f"No check-in data found in the last {days} days."

    # Each day's counted sessions with the rating and source the read door resolves for each. The whole-day
    # RPE this line used to print is retired: it was never a rating OF a session.
    with SessionLocal() as _rdb:
        _by_day: dict = {}
        for _rs in session_ratings(_rdb, user_id, since=_as_date(rows[-1]["date"]), until=_as_date(rows[0]["date"])):
            _by_day.setdefault(_rs.bout.day, []).append(_rs)

    lines = [f"Check-in history — last {days} days"]
    lines.append(f"Data window: {rows[-1]['date']} → {rows[0]['date']}\n")

    for r in rows:
        src_tag = f"[{r['source']}]"
        sleep_q = r["sleep_quality"] if r["sleep_quality"] is not None else "—"
        fatigue = r["fatigue"] if r["fatigue"] is not None else "—"
        soreness = r["soreness"] if r.get("soreness") is not None else "—"
        motivation = r["motivation"] if r["motivation"] is not None else "—"
        life_load = r["life_load"] if r.get("life_load") is not None else "—"
        alcohol = r["alcohol_units"] if r.get("alcohol_units") is not None else "—"
        rpe = format_day_ratings(_by_day.get(_as_date(r["date"]), []))
        readiness = r["morning_readiness"] if r["morning_readiness"] is not None else "—"
        hrv = f"{r['hrv_ms']:.0f}ms" if r.get("hrv_ms") is not None else "—"
        lines.append(
            f"{r['date']} {src_tag}: sleep={sleep_q} fatigue={fatigue} soreness={soreness} "
            f"motivation={motivation} life_load={life_load} alcohol={alcohol} "
            f"session_rpe=[{rpe}] hrv={hrv} readiness={readiness}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2b — CBT-I sleep diary + prescription ledger + ISI (read-only, #330)
# ---------------------------------------------------------------------------

# The diary columns served, in output order. I1 sensor firewall: CBT-I reads the recall
# diary and its ledger ONLY — never passive_*, health_connect_syncs, samsung_* or
# hrv_readings. This tuple IS the whole daily_records projection (the SELECT is built
# from it), so a sensor column can only arrive by being named here.
_CBTI_DIARY_COLS = (
    "got_into_bed", "lights_out", "sleep_latency_min", "waso_min",
    "night_wakings_n", "wakings_nocturia_n", "wakings_pain_n", "wakings_spontaneous_n",
    "final_wake", "out_of_bed", "naps_min", "alcohol_units",
    "diary_tst_min", "diary_se_pct",
)

# Output labels where the column name misstates the unit. The waking-cause columns hold
# MINUTES of waso_min by cause, not counts (#332); the rename is owed as a migration, so
# the served header says what the value is.
_CBTI_DIARY_LABELS = {
    "wakings_nocturia_n": "waso_nocturia_min",
    "wakings_pain_n": "waso_pain_min",
    "wakings_spontaneous_n": "waso_spontaneous_min",
}

_CBTI_DIARY_SQL = (
    "SELECT date, " + ", ".join(_CBTI_DIARY_COLS) + " FROM daily_records "
    "WHERE user_id = :user_id AND date >= :since ORDER BY date"
)
_CBTI_BLOCKS_SQL = (
    "SELECT id, opened_on, closed_on, wake_anchor, open_reason, close_reason, "
    "exit_tst_min, exit_se_pct FROM cbti_blocks WHERE user_id = :user_id "
    "ORDER BY opened_on, id"
)
# cbti_prescriptions / cbti_isi carry no user_id — scoped through their block. A screening
# ISI with block_id NULL is therefore unattributable and not served (said in the output).
_CBTI_RX_SQL = (
    "SELECT p.id, p.block_id, p.effective_from, p.effective_to, p.prescribed_lights_out, "
    "p.wake_anchor, p.window_minutes, p.decision, p.basis_tst_min, p.basis_se_pct, "
    "p.basis_nights_n, p.basis_n_diary, p.basis_n_samsung, p.rationale "
    "FROM cbti_prescriptions p JOIN cbti_blocks b ON b.id = p.block_id "
    "WHERE b.user_id = :user_id ORDER BY p.effective_from, p.id"
)
_CBTI_ISI_SQL = (
    "SELECT i.block_id, i.administered_at, i.timepoint, i.item_1, i.item_2, i.item_3, "
    "i.item_4, i.item_5, i.item_6, i.item_7, i.total_reported, i.administered_via "
    "FROM cbti_isi i JOIN cbti_blocks b ON b.id = i.block_id "
    "WHERE b.user_id = :user_id ORDER BY i.administered_at"
)


def _as_date_val(v) -> date | None:
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _load_cbti_diary(conn, user_id: int, since: date) -> dict[str, list[dict]]:
    """Run the four read-only CBT-I queries on `conn`. Fetches from `since - 1` so the
    formatter can attribute the previous afternoon's nap to the first night served."""
    def rows(sql, **params):
        result = conn.execute(text(sql), {"user_id": user_id, **params})
        cols = list(result.keys())
        return [dict(zip(cols, r)) for r in result.fetchall()]

    return {
        "nights": rows(_CBTI_DIARY_SQL, since=since - timedelta(days=1)),
        "blocks": rows(_CBTI_BLOCKS_SQL),
        "prescriptions": rows(_CBTI_RX_SQL),
        "isi": rows(_CBTI_ISI_SQL),
    }


def _rx_in_force(night: date, rxs: list[dict]) -> dict | None:
    """The prescription governing the night that ends on wake-date `night`: the latest
    `effective_from <= night`, unless its `effective_to` has already passed (a gap between
    blocks has no prescription). Same span rule as cbti.replay: a successor's
    effective_from is a hard wall."""
    live = None
    for rx in sorted(rxs, key=lambda r: (_as_date_val(r["effective_from"]), r["id"])):
        if _as_date_val(rx["effective_from"]) <= night:
            live = rx
    if live is None:
        return None
    to = _as_date_val(live["effective_to"])
    return None if to is not None and night > to else live


def _fmt(v, spec: str = "") -> str:
    if v is None:
        return "—"
    return format(v, spec) if spec else str(v)


def _one_line(s) -> str:
    return " ".join(str(s).split()) if s else "—"


def _format_cbti_diary(data: dict[str, list[dict]], since: date, days: int) -> str:
    """Render the diary, ledger and ISI (pure; testable). Only `_CBTI_DIARY_COLS` are
    rendered from a night row — any other key is ignored, so the I1 firewall holds at the
    formatter too, not only at the SELECT.

    Night = wake date (the AM record's date). `naps_min` on night D is the value logged at
    PM on D-1 (it belongs to the night terminating D; #219, the same read cbti.replay does)."""
    nights = data.get("nights") or []
    rxs = data.get("prescriptions") or []
    blocks = data.get("blocks") or []
    isi = data.get("isi") or []

    naps_by_date = {_as_date_val(n["date"]): n.get("naps_min") for n in nights}
    lines = [
        f"CBT-I sleep diary — nights since {since} (last {days} days)",
        "Source: daily_records recall-diary columns + cbti_blocks / cbti_prescriptions / "
        "cbti_isi ledger. No sensor-derived fields (I1).",
        "Night = wake date. naps_min = nap logged the previous afternoon (belongs to this "
        "night, #219). Diary clocks may have been accepted from a prefill (final_wake from "
        "HC sleep_end since #328); prefill provenance is not stored. waso_*_min = minutes "
        "of waso_min by cause (not counts; night_wakings_n is the count).",
        "",
        "== Nightly diary ==",
    ]
    header = ["date", "rx_id", "rx_lights_out", "rx_wake_anchor"] + [
        _CBTI_DIARY_LABELS.get(c, c) for c in _CBTI_DIARY_COLS]
    lines.append(" | ".join(header))

    served = 0
    for n in nights:
        d = _as_date_val(n["date"])
        if d < since:
            continue
        vals = {c: n.get(c) for c in _CBTI_DIARY_COLS}
        vals["naps_min"] = naps_by_date.get(d - timedelta(days=1))
        # A daily_records row with no diary entry at all (ratings-only day) is not a night.
        if all(vals[c] is None for c in _CBTI_DIARY_COLS if c != "naps_min"):
            continue
        rx = _rx_in_force(d, rxs)
        cells = [
            str(d),
            _fmt(rx["id"]) if rx else "—",
            _fmt(rx["prescribed_lights_out"]) if rx else "—",
            _fmt(rx["wake_anchor"]) if rx else "—",
        ] + [
            _fmt(vals[c], ".1f") if c == "diary_se_pct" and vals[c] is not None else _fmt(vals[c])
            for c in _CBTI_DIARY_COLS
        ]
        lines.append(" | ".join(cells))
        served += 1
    if served == 0:
        lines.append(f"(no diary nights since {since})")

    lines += ["", "== Blocks =="]
    for b in blocks:
        exit_se = _fmt(b["exit_se_pct"], ".1f")
        lines.append(
            f"block {b['id']}: {b['opened_on']} → {b['closed_on'] or 'open'} "
            f"wake_anchor={b['wake_anchor']} exit_tst_min={_fmt(b['exit_tst_min'])} "
            f"exit_se_pct={exit_se}"
        )
        lines.append(f"  open_reason: {_one_line(b['open_reason'])}")
        if b["closed_on"]:
            lines.append(f"  close_reason: {_one_line(b['close_reason'])}")
    if not blocks:
        lines.append("(no CBT-I blocks)")

    lines += ["", "== Prescriptions =="]
    for p in rxs:
        lines.append(
            f"rx {p['id']} [block {p['block_id']}] {p['effective_from']} → "
            f"{p['effective_to'] or 'live'}: lights_out={p['prescribed_lights_out']} "
            f"wake_anchor={p['wake_anchor']} window_min={p['window_minutes']} "
            f"decision={p['decision']} basis_tst_min={_fmt(p['basis_tst_min'])} "
            f"basis_se_pct={_fmt(p['basis_se_pct'], '.1f')} "
            f"basis_nights={_fmt(p['basis_nights_n'])} "
            f"(diary {_fmt(p['basis_n_diary'])}, device {_fmt(p['basis_n_samsung'])})"
        )
        lines.append(f"  rationale: {_one_line(p['rationale'])}")
    if not rxs:
        lines.append("(no prescriptions)")

    lines += ["", "== ISI (Insomnia Severity Index) =="]
    for i in isi:
        items = [i[f"item_{k}"] for k in range(1, 8)]
        at = i["administered_at"]
        if isinstance(at, str):          # SQLite returns the timestamp as text
            at = datetime.fromisoformat(at)
        if isinstance(at, datetime):
            at = (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(_AS_OF_TZ)
            at = at.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"{at} [block {i['block_id']}, {i['timepoint']}] total={sum(items)} "
            f"(reported {_fmt(i['total_reported'])}) items={items} "
            f"via={_fmt(i['administered_via'])}"
        )
    if not isi:
        lines.append("(no block-linked ISI administrations)")
    lines.append("ISI total is the canonical item sum; screening ISIs not linked to a "
                 "block are not served (no user scope).")

    return "\n".join(lines)


@mcp.tool()
@_stamped
def get_cbti_diary(days: int = 42) -> str:
    """CBT-I sleep diary for the last N nights, read-only: per night (wake date) the
    prescription in force (prescribed lights-out + wake anchor), got_into_bed, lights_out,
    sleep latency, WASO and its minutes by cause (nocturia / pain / spontaneous), wakings count,
    final wake, out of bed, naps, alcohol units, and the diary's own TST and SE. Also the
    full block + prescription ledger and ISI history. Recall-diary and ledger columns
    only — no sensor-derived sleep data (I1)."""
    user_id = _current_user_id()
    since = _aest_wake_day() - timedelta(days=days)
    with engine.connect() as conn:
        data = _load_cbti_diary(conn, user_id, since)
    return _format_cbti_diary(data, since, days)


# ---------------------------------------------------------------------------
# Tool 3 — Training sessions (aerobic/cardio)
# ---------------------------------------------------------------------------

def _session_selfevals(db, user_id: int, sessions: list) -> dict[int, object]:
    """`{aerobic_session.id: Rating}` for the given canonical sessions: the per-session rating the read
    door resolves (any source, by the declared hierarchy). Per-session only: the whole-day `session_rpe`
    is not a rating OF a session and is never shown on its line. Sessions the felt-load count leaves out
    (Pilates, say) are rated here too, so their rating still shows."""
    ratings = observed_ratings(db, user_id, [aerobic_bout(s) for s in sessions])
    return {key[1]: r for key, r in ratings.items()}


@mcp.tool()
@_stamped
def get_training_sessions(days: int = 28) -> str:
    """Get aerobic/cardio sessions from all connected sources (Polar, etc).
    Returns sport type, duration, average/max HR, distance, calories, HR zones.
    A session that is the HR trace of a Hevy gym workout (at least half of it inside that workout)
    is marked as overlapping it by title; the training plan does not count it as conditioning.
    A session that other devices also recorded carries also_recorded_by=[{source, source_package}]:
    identity only, those recordings are not extra training and add no load.
    For aerobic sessions and Hevy workouts merged into one list, use get_recent_sessions."""
    user_id = _current_user_id()
    since = _aest_wake_day() - timedelta(days=days)

    # Read-door (#Q161): list CANONICAL sessions only — a same-bout Polar/HC twin must not
    # appear twice. arbitrated_sessions marks exactly one row per bout canonical; day is the
    # local `session_date` (untimed sessions, which the old `start_time >=` filter dropped,
    # are now included). Rendered inside the session so attributes are materialised.
    with SessionLocal() as _db:
        arbitrated = arbitrated_sessions(user_id, _db, since=since)
        twins = twins_by_canonical(arbitrated)   # Q201(b): who each canonical row suppressed, before the filter drops them
        sessions = [s for s in arbitrated if getattr(s, "canonical", True)]
        selfevals = _session_selfevals(_db, user_id, sessions)   # a rating is placed by overlap, so a lost twin's value lands on the winner

        if not sessions:
            return (
                f"No aerobic sessions found in the last {days} days. "
                "Note: Polar data accumulates from June 2026 onward."
            )

        gym = _gym_trace_marks(_db, user_id, sessions)   # concurrent_strength, as the resolver tests it

        lines = [f"Training sessions — last {days} days"]
        lines.append(f"Data window: {sessions[-1].session_date} → {sessions[0].session_date}")
        lines.append("Note: Polar data accumulates from June 2026 onward.\n")

        for s in sessions:
            line = format_aerobic_session(s)
            if s.id in selfevals:
                line += format_selfeval(selfevals[s.id])
            line += format_also_recorded_by(twins.get(s.id))
            if s.id in gym:
                line += _gym_trace_note(gym[s.id])
            lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4 — Hevy strength workouts (async — HevyClient is async)
# ---------------------------------------------------------------------------

@mcp.tool()
@_stamped
async def get_hevy_workouts(days: int = 14) -> str:
    """Get strength training workouts from Hevy. Returns exercises, sets,
    weights, reps, and estimated 1RM (Epley formula) per movement.
    For Hevy workouts matched to their device recordings in one list, use get_recent_sessions."""
    user_id = _current_user_id()

    db: Session = SessionLocal()
    try:
        row = (
            db.query(models.UserIntegration)
            .filter_by(user_id=user_id, provider="hevy")
            .first()
        )
        if row is None:
            return "Hevy integration not connected for this user."
        api_key = decrypt(row.api_key_encrypted)
    finally:
        db.close()

    client = HevyClient(api_key)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    all_workouts = []
    page = 1
    while True:
        data = await client.get_workouts(page=page, page_size=10)
        workouts = data.get("workouts", [])
        if not workouts:
            break
        for w in workouts:
            start = w.get("start_time", "")
            try:
                wdt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except Exception:
                continue
            if wdt < cutoff:
                # workouts are newest-first; once we go past cutoff we're done
                all_workouts_done = True
                break
            all_workouts.append(w)
        else:
            page += 1
            continue
        break

    if not all_workouts:
        return f"No Hevy workouts found in the last {days} days."

    lines = [f"Hevy workouts — last {days} days"]
    lines.append(f"Data window: {all_workouts[-1]['start_time'][:10]} → {all_workouts[0]['start_time'][:10]}\n")

    for w in all_workouts:
        lines.append(f"## {w.get('title', 'Workout')} — {w['start_time'][:10]}")

        description = (w.get("description") or "").strip()
        if description:
            lines.append(f"   Description: {description}")

        for ex in w.get("exercises", []):
            title = ex.get("title", "Unknown exercise")
            lines.append(f"  {title}")

            # Exercise notes carry the L/R tags and injury flags — preserve line
            # breaks (tag on line 1, observation on line 2).
            notes = (ex.get("notes") or "").strip()
            if notes:
                for note_line in notes.split("\n"):
                    note_line = note_line.strip()
                    if note_line:
                        lines.append(f"     note: {note_line}")

            sets = ex.get("sets", [])
            best_1rm = 0.0
            for set_idx, s in enumerate(sets):
                # Render every set (warmups included, labelled by format_set) so
                # activation / all-warmup movements no longer vanish.
                lines.append(format_set(s, set_idx))
                # e1RM from non-warmup sets only.
                if s.get("type") != "warmup":
                    wkg = s.get("weight_kg")
                    reps = s.get("reps")
                    if wkg is not None and reps is not None:
                        est = _epley_1rm(wkg, reps)
                        if est > best_1rm:
                            best_1rm = est

            if best_1rm > 0:
                lines.append(f"       e1RM≈{best_1rm:.1f}kg")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool — recent sessions, aerobic and Hevy in one list (read-only formatter)
#
# Nothing here arbitrates, matches by a rule of its own, or counts. The sessions are
# `arbitrated_sessions` (canonical only, as `get_training_sessions`); the workouts are
# `counted_workouts`; a workout is the SAME BOUT as a session when the shared
# `overlaps_workout` predicate (>= HEVY_MIRROR_OVERLAP_FRACTION of the session's own duration
# inside one workout; the resolver's `concurrent_strength` guard and the mirror read-door use the
# same one) says so. That predicate is applied here to every canonical session, Polar included:
# the mirror MARK is Health Connect only, but the overlap TEST is package-agnostic.
# ---------------------------------------------------------------------------

def _local_midnight_utc(d: date) -> datetime:
    return _AS_OF_TZ.localize(datetime.combine(d, datetime.min.time())).astimezone(timezone.utc)


def _concurrent_strength_sessions(sessions: list, counted: list) -> dict[int, object]:
    """{session.id: workout} for each canonical session the resolver would uncount as
    `concurrent_strength` (#307): `overlaps_workout(session, counted)`, the same call at
    engine/resolver.py. The mapped workout is the one covering most of the session, for its title.

    Not a one-to-one pairing (a workout used once): a second trace over the same gym bout would
    lose its mark. The resolver tests every session on its own against the whole set, and so does
    this. `get_recent_sessions` links through the same function (#415). An untimed session has no
    interval and is never marked (the resolver files it as `untimed` before the overlap test)."""
    out: dict[int, object] = {}
    for s in sessions:
        if not overlaps_workout(s, counted):
            continue
        out[s.id] = max(counted, key=lambda w: (overlap_fraction(s, [w]), w.hevy_id))
    return out


def _counted_workouts_near(db: Session, user_id: int, sessions: list) -> list:
    """The workout set the resolver tests `concurrent_strength` against: non-excluded Hevy workouts
    through the `counted_workouts` door (an excluded workout, and both members of an unadjudicated
    duplicate pair, are out). The resolver clips that set to its quota window; here the fetch is
    the sessions' span padded a day either side, so a bout straddling an edge still counts."""
    days = [s.session_date for s in sessions if s.session_date is not None]
    if not days:
        return []
    candidates = (
        db.query(models.HevyWorkout)
        .filter(models.HevyWorkout.user_id == user_id,
                models.HevyWorkout.excluded_at.is_(None),
                models.HevyWorkout.start_time.isnot(None),
                models.HevyWorkout.start_time >= _local_midnight_utc(min(days)) - timedelta(days=1),
                models.HevyWorkout.start_time < _local_midnight_utc(max(days) + timedelta(days=1)) + timedelta(days=1))
        .all()
    )
    counted, _unadjudicated = counted_workouts(db, user_id, candidates)
    return counted


def _gym_trace_marks(db: Session, user_id: int, sessions: list) -> dict[int, object]:
    """The `concurrent_strength` marks for canonical `sessions`, fetched against the resolver's set."""
    return _concurrent_strength_sessions(sessions, _counted_workouts_near(db, user_id, sessions))


def _gym_trace_note(w) -> str:
    """The suffix on a marked session's line: the resolver's own wording, then the workout title."""
    return f" — {CONCURRENT_STRENGTH_PHRASE} ({w.title or 'Workout'})"


def _hevy_detail(w) -> str:
    """The attached Hevy line: exercise count, then the shared compact renderer (top sets)."""
    started = w.start_time
    if started is not None:
        started = (started if started.tzinfo else started.replace(tzinfo=timezone.utc)).astimezone(_AS_OF_TZ)
    n = len((w.raw or {}).get("exercises") or [])
    return f"  ↳ {n} exercise{'' if n == 1 else 's'} · " + format_workout_compact(
        w.raw or {}, started.strftime("%H:%M") if started is not None else "")


def _format_recent_sessions(sessions, selfevals, counted, unadjudicated, fresh, days: int, since: date,
                            twins=None, hevy_ratings=None) -> str:
    """Newest first: one line per canonical aerobic session; a session that overlaps a counted
    workout (`_concurrent_strength_sessions`, the #414 test: each session on its own) is a SEGMENT of
    that workout, so a workout's segments are listed in start-time order with its Hevy detail once
    beneath them. `Hevy only` for a counted workout with no segment, `HR only` for a strength-named
    session with no overlapping workout, then the freshness footer. Pure.

    RATINGS. `selfevals` is `{aerobic id: Rating}` and `hevy_ratings` is `{hevy_id: Rating}`, both the read
    door's answer. A counted Hevy workout is ONE bout with ONE rating, rendered ONCE on the workout's own line
    (the `Hevy only` header, or the detail line under its segments), never on a segment: a device row that is
    a segment of a workout is not a separate counted session."""
    linked = _concurrent_strength_sessions(sessions, counted)
    matched = {w.hevy_id for w in linked.values()}
    items: list[tuple[float, list[str]]] = []

    def _ts_of(dt, day):
        if dt is not None:
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
        return _local_midnight_utc(day).timestamp()

    def _session_line(s, *, segment: bool = False) -> str:
        line = format_aerobic_session(s)
        if s.id in selfevals and not segment:       # a segment carries no rating of its own: the workout does
            line += format_selfeval(selfevals[s.id])
        return line + format_also_recorded_by((twins or {}).get(s.id))

    def _workout_rating(w) -> str:
        r = (hevy_ratings or {}).get(w.hevy_id)
        return "" if r is None else format_selfeval(r)

    segments: dict[str, tuple[object, list]] = {}      # hevy_id -> (workout, its segments)
    for s in sessions:
        w = linked.get(s.id)
        if w is not None:
            segments.setdefault(w.hevy_id, (w, []))[1].append(s)

    emitted: set[str] = set()
    for s in sessions:
        w = linked.get(s.id)
        if w is None:
            line = _session_line(s)
            if is_strength_sport(s.sport_name):
                line += " — HR only (no Hevy workout matches)"
            items.append((_ts_of(s.start_time, s.session_date), [line]))
        elif w.hevy_id not in emitted:
            emitted.add(w.hevy_id)
            segs = sorted(segments[w.hevy_id][1], key=lambda x: (_ts_of(x.start_time, x.session_date), x.id))
            items.append((_ts_of(segs[0].start_time, segs[0].session_date),
                          [_session_line(x, segment=True) for x in segs] + [_hevy_detail(w) + _workout_rating(w)]))

    def _hevy_line(w, note: str) -> list[str]:
        started = w.start_time
        day = (started if started.tzinfo else started.replace(tzinfo=timezone.utc)).astimezone(_AS_OF_TZ).date() \
            if started is not None else None
        dur = (f"{(w.end_time - w.start_time).total_seconds() / 60:.0f} min"
               if w.start_time is not None and w.end_time is not None else "—")
        rating = _workout_rating(w) if note == "Hevy only" else ""      # an uncounted duplicate is rated by nothing
        return [f"{day or 'undated'} [hevy] {w.title or 'Workout'}: {dur} — {note}{rating}", _hevy_detail(w)]

    def _in_window(w) -> bool:
        return w.start_time is not None and _local_day(w.start_time) >= since

    for w in counted:
        if w.hevy_id not in matched and _in_window(w):
            items.append((_ts_of(w.start_time, since), _hevy_line(w, "Hevy only")))
    for w in unadjudicated:
        if _in_window(w):
            items.append((_ts_of(w.start_time, since), _hevy_line(w, "Hevy only, unadjudicated duplicate (not counted)")))

    items.sort(key=lambda t: -t[0])
    out = [f"Recent sessions — last {days} days (from {since})"]
    if not items:
        out.append(f"No sessions or Hevy workouts in the last {days} days.")
    for _ts, lines in items:
        out.extend(lines)
    out.append("")
    out.append(freshness_footer_line(fresh))
    return "\n".join(out)


@mcp.tool()
@_stamped
def get_recent_sessions(days: int = 7) -> str:
    """Get recent training in one list, newest first: each aerobic session from all sources
    (date, sport, duration, source, HR avg/max, zones, self-evaluation). A device session that
    overlaps a Hevy workout is listed as a segment of it: a workout's segments in start order, the
    workout's exercises and top sets once beneath them. Hevy workouts with no device recording
    are marked 'Hevy only', strength-named device sessions with no Hevy workout 'HR only'. A
    session's per-session RPE and its source (in_app, garmin) follow the line as selfeval=[...]; a Hevy
    workout carries its rating once, on its own line, never on a device segment. Ends
    with how long ago Health Connect and Polar last delivered. A session that other devices also
    recorded carries also_recorded_by=[{source, source_package}] (identity only, no extra load)."""
    user_id = _current_user_id()
    since = _local_day() - timedelta(days=days)
    with SessionLocal() as _db:
        arbitrated = arbitrated_sessions(user_id, _db, since=since)
        twins = twins_by_canonical(arbitrated)   # Q201(b), as get_training_sessions
        sessions = [s for s in arbitrated if getattr(s, "canonical", True)]
        # Candidate fetch, padded a day before the window so a bout started just before it still
        # links; the formatter applies the in-window cut on the LOCAL day. Partitioned by the
        # counted-Hevy door.
        candidates = [
            w for w in _db.query(models.HevyWorkout)
            .filter(models.HevyWorkout.user_id == user_id,
                    models.HevyWorkout.start_time >= _local_midnight_utc(since) - timedelta(days=1))
            .all()
        ]
        counted, unadjudicated = counted_workouts(_db, user_id, candidates)
        # Ratings are placed against the bouts the read door counts: each counted Hevy workout, and each
        # device row that is NOT a segment of one (a segment is folded into its workout). So a workout
        # carries exactly one rating and a segment none, and a rating made on the workout never lands twice.
        linked = _concurrent_strength_sessions(sessions, counted)
        ratings = observed_ratings(
            _db, user_id,
            [aerobic_bout(s) for s in sessions if s.id not in linked] + [hevy_bout(w) for w in counted])
        selfevals = {k[1]: r for k, r in ratings.items() if k[0] == "aerobic"}
        hevy_ratings = {k[1]: r for k, r in ratings.items() if k[0] == "hevy"}
        return _format_recent_sessions(
            sessions, selfevals, counted, unadjudicated, freshness(_db, user_id), days, since, twins, hevy_ratings)


# ---------------------------------------------------------------------------
# Tool 5 — Today's readiness snapshot
# ---------------------------------------------------------------------------

def _readiness_hrv_line(rep: dict | None, dev: dict, wake_day: date) -> str:
    """The readiness snapshot's HRV line: the representative source's current-day ms WITH
    its source and date, or "—" plus the stale sources' last dates when no source read
    today (#327 recency gate). Never prints a prior-day number as today's."""
    if rep is not None:
        return f"  HRV: {rep['rmssd']:.0f} ms ({rep['source']}, {wake_day})"
    stale = dev.get("stale_sources") or []
    if stale:
        last = ", ".join(f"{s['source']} {s['last_captured_at']}" for s in stale)
        return f"  HRV: — (no current-day reading; last: {last})"
    return "  HRV: —"


@mcp.tool()
@_stamped
def get_readiness_snapshot() -> str:
    """Today's readiness snapshot. Latest biometrics, most recent check-in,
    7-day training summary, and current injury constraints. The resting and sleep heart-rate
    figures are withheld, with the reason printed, when their night is more than 48 hours old."""
    user_id = _current_user_id()

    # Q130 → #292: the readiness HRV reads the per-source-normalised deviation model
    # (source-agnostic over hrv_readings), NOT `.canonical` arbitration. This is a rich
    # LLM readout (not the device-attributed `get_recovery_metrics`, which stays wholly
    # Samsung), so it surfaces BOTH the representative single ms figure and the full
    # deviation object (combined z, direction, cross-source confidence). Sleep is ONE writer
    # per night by fixed priority (Garmin > Samsung Health > Samsung scraper), named on every
    # value and never blended (`reads/snapshot_reads.py`, shared with the card).
    with SessionLocal() as _db:
        # #294: feed the active training-phase change date so a mid-deload / regime
        # change surfaces as baseline_state="settling" with capped confidence here (this
        # readout surfaces both), instead of crying wolf. No open phase → None → off.
        _phase = current_training_phase(_db, user_id)
        _wake_day = _aest_wake_day()
        _dev = hrv_deviation(
            user_id, _db, for_date=_wake_day,
            phase_change_date=_phase.entered_on if _phase is not None else None,
        )
        _sleep = latest_sleep_night(_db, user_id)
        _continuity = hrv_continuity(_db, user_id, _wake_day)
        _fresh = freshness(_db, user_id)
    _rep = representative_source(_dev)

    checkin_rows = _db_rows(
        """
        SELECT date, sleep_quality, fatigue, soreness::text,
               motivation, life_load, morning_readiness
        FROM daily_records
        WHERE user_id = :user_id
          AND am_timestamp IS NOT NULL
        ORDER BY date DESC
        LIMIT 1
        """,
        {"user_id": user_id},
    )

    # Read-door (#Q161): count CANONICAL sessions only, so a same-bout Polar/HC twin does not
    # inflate the readiness training summary (session_date is the local day).
    with SessionLocal() as _sdb:
        _canonical = [s for s in arbitrated_sessions(
                          user_id, _sdb, since=_aest_wake_day() - timedelta(days=7))
                      if getattr(s, "canonical", True)]
        _gym = _gym_trace_marks(_sdb, user_id, _canonical)
    # A gym session's HR trace is that strength session, not conditioning (`concurrent_strength`,
    # #307): out of the aerobic count and minutes, reported on its own line below.
    _week = [s for s in _canonical if s.id not in _gym]
    _traces = [s for s in _canonical if s.id in _gym]
    session_count = len(_week)
    session_total_min = sum(float(s.duration_minutes) for s in _week
                            if s.duration_minutes is not None)
    trace_total_min = sum(float(s.duration_minutes) for s in _traces
                          if s.duration_minutes is not None)

    lines = ["=== TODAY'S READINESS SNAPSHOT ===\n"]

    if _sleep is not None or _rep is not None or _dev["n_contributing"] or _continuity["nights"]:
        lines.append(f"Latest biometrics (wake-day {_wake_day}):")
        lines.append(_readiness_hrv_line(_rep, _dev, _wake_day))
        if _dev["n_contributing"]:
            lines.append(
                f"  HRV deviation: {_dev['combined_z']:+.2f}σ {_dev['direction']} "
                f"(confidence {_dev['confidence']}, {_dev['n_contributing']} source(s), "
                f"baseline {_dev['baseline_state']})"
            )
        lines.extend(sleep_snapshot_lines(_sleep, today=_wake_day))
        lines.append(hrv_continuity_line(_continuity) + "\n")
    else:
        lines.append("Latest biometrics: no sleep or HRV data found.\n")

    lines.extend(freshness_snapshot_lines(_fresh))
    lines.append("")

    if checkin_rows:
        c = checkin_rows[0]
        lines.append(f"Most recent check-in ({c['date']}):")
        lines.append(f"  Sleep quality={c['sleep_quality']} Fatigue={c['fatigue']} Soreness={c.get('soreness') or '—'}")
        lines.append(f"  Motivation={c['motivation']} Life load={c.get('life_load') or '—'}")
        with SessionLocal() as _cdb:
            _day_sessions = session_ratings(_cdb, user_id, since=_as_date(c["date"]), until=_as_date(c["date"]))
        lines.append(f"  Session RPE=[{format_day_ratings(_day_sessions)}] Readiness={c['morning_readiness'] or '—'}\n")
    else:
        lines.append("Most recent check-in: none found.\n")

    if session_count:
        lines.append(f"Aerobic sessions (last 7 days): {session_count} sessions, "
                     f"{session_total_min:.0f} total minutes" + ("" if _traces else "\n"))
    if _traces:
        lines.append(f"Gym HR traces (last 7 days): {len(_traces)} sessions, "
                     f"{trace_total_min:.0f} min, not counted as aerobic\n")

    injury_rows = _db_rows(
        """
        SELECT value FROM user_knowledge_entries
        WHERE user_id = :user_id AND type = 'injury' AND active = true
        ORDER BY added_at DESC
        """,
        {"user_id": user_id},
    )

    lines.append("---")
    if injury_rows:
        lines.append("Active injury constraints:")
        for r in injury_rows:
            val = r["value"] or {}
            body_part = val.get("body_part", "unknown")
            restrictions = val.get("restrictions", [])
            r_str = f" (avoid: {', '.join(restrictions)})" if restrictions else ""
            lines.append(f"- {body_part}{r_str}")
    else:
        lines.append("Active injury constraints: none recorded.")

    # Typed constraints (#342): active CONFIRMED rows through the shared lift and line formatter
    # (the chat section renders the same lines). Input-gated — no confirmed constraint → nothing
    # appended, so the snapshot is unchanged for a user without one.
    constraints, _findings, live_keys = _typed_entries_read(user_id)
    if constraints:
        lines.append("")
        lines.append("Active constraints (confirmed):")
        today = _aest_wake_day()
        lines.extend(typed_entries.constraint_line(c, live_keys, today) for c in constraints)

    # Plan-review flags — trajectory divergence + symptom-gated review (Step 3).
    # Surfacing only: these never alter restrictions or gate selection.
    with SessionLocal() as sess:
        flags = evaluate_injury_trajectories(user_id, sess)
    if flags["divergences"] or flags["reviews"]:
        lines.append("")
        lines.append("Plan review flags:")
        for f in flags["divergences"]:
            lines.append(f"- [DIVERGENCE] {f['label']}: {f['message']}")
        for f in flags["reviews"]:
            lines.append(f"- [REVIEW] {f['label']}: {f['message']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 6 — Metabolic training load (Banister)
# ---------------------------------------------------------------------------

# The metabolic lane of load_metrics: the Metabolic→load_events transform (#251,
# `metab-v1`, Edwards zone-weighted TRIMP) rolled up under the Banister τ-set
# (`banister-v4`, the normalised EWMA — #18 restored — on a per-user calendar start (P3) with
# the first-week-mean stock seed (P1.1)). This pin FOLLOWS the metrics_version bump (the
# revisit trigger the banister-v2 entry named, re-invoked by P3 then P1.1): the rollup writes
# only banister-v4 now, so this readout must select it. This readout replaced the legacy
# aerobic acute:chronic ratio (ACWR) surface, retired in #255 once that transform landed —
# the trigger #249 named. `_METAB_FORMULA_VERSION` is the metabolic events version and is
# UNCHANGED by P3/P1.1 (only the strength lane went tier0-v2; the seed is version-shared).
_METAB_FORMULA_VERSION = "metab-v1"
_METAB_METRICS_VERSION = "banister-v4"
_METAB_WINDOW = "metabolic"


def _typed_entries_read(user_id: int, rows_filter=None):
    """ONE query of the user's active entries, lifted through `typed_entries` — the same lifts
    `current_state` applies, so the MCP reads exactly what the chat reads (G0 ruling D3) without
    running the whole `current_state()` (resolver, week plan, HRV). `rows_filter` narrows the rows
    BEFORE the finding lift, so a filtered read still counts only its own withheld rows."""
    with SessionLocal() as sess:
        entries = (
            sess.query(models.UserKnowledgeEntry)
            .filter_by(user_id=user_id, active=True)
            .order_by(models.UserKnowledgeEntry.added_at.desc(), models.UserKnowledgeEntry.id.desc())
            .all()
        )
        live = typed_entries.active_keys(entries)
        constraints = typed_entries.lift_constraints(entries)
        findings = typed_entries.lift_findings([e for e in entries if rows_filter is None or rows_filter(e)])
    return constraints, findings, live


def _format_training_load(rows: list[dict]) -> str:
    """Format the metabolic-window load readout from `load_metrics` rows (latest day
    first). Serves the Banister metabolic lane — window-native Edwards TRIMP plus the
    acute/chronic trace values — with NO acute:chronic ratio and NO sweet-spot band
    verdict. The legacy aerobic ACWR readout was retired (#255) after the
    Metabolic→load_events transform landed (#251); dosing never used ACWR (#18) and the
    readout no longer does — the readout≠dosing boundary closes with the readout gone."""
    if not rows:
        return "\n".join([
            "=== METABOLIC TRAINING LOAD (Banister) ===\n",
            "No metabolic load metrics yet.",
            "The metabolic window lights up once zone-tagged aerobic sessions are ingested",
            f"and the load_events → load_metrics rollup runs ({_METAB_FORMULA_VERSION} / {_METAB_METRICS_VERSION}).",
        ])
    latest = rows[0]
    unit = latest["unit"]
    return "\n".join([
        "=== METABOLIC TRAINING LOAD (Banister) ===\n",
        f"As of:              {latest['day']}",
        f"Daily load (TRIMP): {latest['daily_load']:.1f} {unit}",
        f"Fitness (τ42):      {latest['fitness']:.1f} {unit}",
        f"Fatigue (τ4):       {latest['fatigue']:.1f} {unit}",
        f"Form:               {latest['form']:.1f} {unit}",
        f"Acute (7d mean):    {latest['acute_load']:.1f} {unit}",
        f"Chronic (28d mean): {latest['chronic_load']:.1f} {unit}",
        f"Maturity:           {latest['maturity']}",
        "",
        f"Source: load_metrics metabolic lane ({_METAB_FORMULA_VERSION} / {_METAB_METRICS_VERSION}),",
        "Edwards zone-weighted TRIMP. Acute/chronic are trace values, not a dosing ratio (#18/#255).",
    ])


@mcp.tool()
@_stamped
def get_training_load() -> str:
    """Metabolic training-load readout: the Banister fitness/fatigue/form curves and the
    acute/chronic trace over the metabolic window (Edwards zone-weighted TRIMP), read from
    the `load_metrics` metabolic lane (metab-v1 / banister-v4). No acute:chronic ratio and
    no sweet-spot verdict — the legacy aerobic ACWR readout was retired (#255) after the
    Metabolic→load_events transform landed (#251)."""
    user_id = _current_user_id()

    rows = _db_rows(
        """
        SELECT day, daily_load, fitness, fatigue, form,
               acute_load, chronic_load, maturity, unit
        FROM load_metrics
        WHERE user_id = :user_id
          AND formula_version = :fv
          AND metrics_version = :mv
          AND load_window = :win
        ORDER BY day DESC
        LIMIT 1
        """,
        {"user_id": user_id, "fv": _METAB_FORMULA_VERSION,
         "mv": _METAB_METRICS_VERSION, "win": _METAB_WINDOW},
    )

    return _format_training_load(rows)


# ---------------------------------------------------------------------------
# Tool 7 — Lab results (raw read-back)
# ---------------------------------------------------------------------------

def _marker_matches(query: str, r) -> bool:
    """Does `query` name this row's marker?

    Mirrors `labs_reads.find_marker`'s RULE — word-boundary, case-insensitive,
    matched against the raw name OR the canonical id with underscores read as spaces
    — but in the FILTER direction. `find_marker` searches a row-name within a user
    MESSAGE (mention-detection over a sentence); here the query IS the marker term and
    is searched within each candidate, so "creatinine" matches "R U-Creatinine" and
    "creatinine_urine". Same tokenisation rule, opposite subject: calling `find_marker`
    directly would treat the query as the message, return first-match-only, and miss
    every marker whose name is longer than the query."""
    q = query.strip().lower()
    if not q:
        return False
    candidates = {r.marker_name_raw.lower()}
    if r.marker_canonical:
        candidates.add(r.marker_canonical.replace("_", " ").lower())
    return any(re.search(rf"\b{re.escape(q)}\b", c) for c in candidates)


def _format_result_line(r) -> str:
    """One marker line — RAW fields only, exactly the `StoredResultOut` projection (#47).
    No `computed_flag`/`confidence` (not on the projection, and not surfaced here);
    exclusivity flags are carried on the model but not decorated, for parity with the
    REST read-back."""
    if r.value_num is not None:
        value = f"{r.value_operator + ' ' if r.value_operator else ''}{r.value_num}"
    elif r.value_qualitative:
        value = r.value_qualitative
    else:
        value = "—"

    unit = f" {r.unit_canonical}" if r.unit_canonical else ""

    if r.ref_low is not None and r.ref_high is not None:
        ref = f" (ref {r.ref_low}–{r.ref_high})"
    elif r.ref_high is not None:
        ref = f" (ref < {r.ref_high})"
    elif r.ref_low is not None:
        ref = f" (ref > {r.ref_low})"
    else:
        ref = ""

    # LAB-asserted flag only — never computed_flag (withheld-computed, #47).
    flag = f" [{r.lab_flag}]" if r.lab_flag else ""

    return f"{r.marker_name_raw}: {value}{unit}{ref}{flag}"


def _format_lab_results(reports, marker: str | None = None, limit: int | None = None) -> str:
    """Pure text formatter over the `StoredReportOut` list from `routers.labs.get_lab_results`.

    Filtering happens HERE over the returned Pydantic snapshots — no second query. `marker`
    keeps only rows whose name matches (dropping any report left with no rows); `limit` then
    keeps the most-recent N of the surviving reports (the list arrives newest-first). Filter
    precedes limit so `marker=x, limit=3` reads as "my last 3 x reports", not "x within my
    last 3 reports of anything"."""
    if marker is not None:
        filtered = []
        for rep in reports:
            hits = [r for r in rep.results if _marker_matches(marker, r)]
            if hits:
                # A shallow copy carrying only the matching rows — the read is not re-run.
                filtered.append(rep.model_copy(update={"results": hits}))
        reports = filtered

    # De-noise the chat read-back of hollow re-confirm shells: an `all_markers_declined`
    # report with no rows is a duplicate-upload record the upload-history surface owns, not a
    # result. Dropped HERE, before `limit`, so a phantom never spends a most-recent-N slot; and
    # before the header is emitted (a bare `continue` at the render loop would leave the
    # `===`/`source:` lines behind — an empty headed block, worse than the shell). Presentation
    # only: the shared REST projection and its upload-history feed are untouched, nothing is
    # deleted. A `no_values_extracted` shell is a genuine extraction fault and is KEPT — it
    # renders its one-line fault below.
    reports = [
        rep for rep in reports
        if not (not rep.results and rep.zero_row_reason == "all_markers_declined")
    ]

    if limit is not None:
        reports = reports[:limit]

    if not reports:
        return "No lab results on file."

    lines: list[str] = []
    for rep in reports:
        if lines:
            lines.append("")
        lines.append(f"=== {rep.panel_name_raw} — {rep.collected_date} ({rep.lab_name}) ===")
        lines.append(f"source: {rep.source_doc_filename or '—'}")
        if rep.zero_row_reason and not rep.results:
            lines.append(f"(no rows ingested: {rep.zero_row_reason})")
            continue
        for r in rep.results:
            lines.append(_format_result_line(r))

    return "\n".join(lines)


def _format_latest_levels(rows, marker: str | None = None, limit: int | None = None) -> str:
    """Flat one-line-per-marker "current levels" view over `labs_reads.latest_lab_results`
    (the sanctioned one-row-per-marker-latest read — reused so "latest" is defined in ONE
    place, not re-derived by walking report-grouped rows).

    SECOND #47 ENFORCEMENT POINT. `latest_lab_results` returns `LabRow`, which carries
    `computed_flag`/`is_derived` for its context_builder consumer — the withhold that
    `StoredReportOut` gives the report path for free is NOT inherited here. Each row is
    re-projected to `StoredResultOut` (the #47 field set) before rendering, dropping those two
    fields structurally. The withhold test covers BOTH this path and the report path, or a
    field added to one could silently ride the other.

    `all_markers_declined` shells contribute no `LabResult` rows, so this view is naturally
    shell-free — no interaction with the report path's suppression filter."""
    if marker is not None:
        rows = [r for r in rows if _marker_matches(marker, r)]
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        return "No lab results on file."

    lines = ["=== CURRENT LEVELS (latest per marker) ==="]
    for r in rows:
        projected = StoredResultOut(
            marker_name_raw=r.marker_name_raw,
            marker_canonical=r.marker_canonical,
            value_num=r.value_num,
            value_operator=r.value_operator,
            value_qualitative=r.value_qualitative,
            unit_canonical=r.unit_canonical,
            ref_low=r.ref_low,
            ref_high=r.ref_high,
            ref_low_exclusive=r.ref_low_exclusive,
            ref_high_exclusive=r.ref_high_exclusive,
            lab_flag=r.lab_flag,
        )
        # Per-line collection date: in a deduped view markers genuinely differ in draw date,
        # and a stale marker's date is the signal.
        lines.append(f"{_format_result_line(projected)} (collected {r.collected_date})")
    return "\n".join(lines)


@mcp.tool()
@_stamped
def get_lab_results(marker: str | None = None, limit: int | None = None,
                    latest_only: bool = False) -> str:
    """Raw stored lab values, ranges, and lab-asserted flags, grouped by report, newest
    first. Not interpreted — no deltas, mechanisms, or judgements.

    Optional `marker` filters to one analyte (word-boundary, case-insensitive, matched on
    the printed name or canonical id, e.g. "creatinine"). Optional `limit` keeps the most
    recent N reports.

    `latest_only=True` returns one row per marker — its most recent draw — flat, with the
    collection date on each line; default is the report-grouped history above."""
    user_id = _current_user_id()
    with SessionLocal() as sess:
        if latest_only:
            return _format_latest_levels(latest_lab_results(user_id, sess),
                                         marker=marker, limit=limit)
        user = sess.get(models.User, user_id)
        # StoredReportOut is a plain Pydantic snapshot and survives session close, but the
        # brief's belt-and-suspenders: read and format inside the session.
        reports = _read_lab_results(current_user=user, db=sess)
        return _format_lab_results(reports, marker=marker, limit=limit)


def _verbatim_block(label: str, text: str) -> list[str]:
    """A verbatim field as a delimited block. The text between `<<<` and `>>>` is the stored
    string exactly -- never indented, wrapped, trimmed or re-encoded -- so a reader can lift it
    byte-for-byte; the delimiters carry the label so the text itself is not touched."""
    return [f"{label}, verbatim:", "<<<", text, ">>>"]


def _num(structured, key):
    """A numeric field of `structured`, or None (a bool is not a number here)."""
    v = (structured or {}).get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _dexa_headline(d) -> str | None:
    """One line for a DXA that has no report comment, read from `structured`: total mass, whole-body
    tissue fat % and the BMD T-score, whichever of the three are present. A DERIVED line, built from
    stored numbers -- never the document's own words -- and it says so; None when none are present."""
    if d.doc_type != "imaging" or d.modality != "DXA":
        return None
    mass, fat, t = (_num(d.structured, k) for k in ("total_mass_kg", "tissue_fat_pct", "t_score"))
    parts = []
    if mass is not None:
        parts.append(f"total mass {mass:g} kg")
    if fat is not None:
        parts.append(f"tissue fat {fat:g}%")
    if t is not None:
        parts.append(f"BMD T-score {t:+g}")
    return " · ".join(parts) or None


def _no_conclusion_lines(d, letter) -> tuple[list[str], bool]:
    """What stands in the conclusion slot when a document has no `conclusion_verbatim` and no
    `diagnosis_verbatim`: a referral's / letter's `reason`, or a DXA's `structured` headline, each
    labelled as NOT word-for-word; else the plain "no conclusion" line. Returns the lines and whether
    `reason` was used (the full view then does not print it a second time)."""
    reason = letter.get("reason")
    if isinstance(reason, str) and reason.strip():
        what = "reason for referral" if d.subtype == "referral" else "reason"
        return [f"{what} (as extracted, NOT word-for-word):", reason], True
    headline = _dexa_headline(d)
    if headline is not None:
        return [f"headline (from structured data, NOT a report comment): {headline}"], False
    return ["(no conclusion on the document)"], False


def _document_headline(d) -> str:
    kind = d.modality if d.doc_type == "imaging" else d.subtype
    parts = [str(d.service_date), kind, d.study if d.doc_type == "imaging" else None, d.region]
    return " · ".join(p for p in parts if p) + f"  [{d.doc_key}]"


def _format_clinical_documents(docs, *, full: bool = False) -> str:
    """Pure text formatter over `ClinicalDocumentOut` snapshots (oldest `service_date` first, as
    the read returns them). LIST view: date · modality-or-subtype · study · region, then the
    conclusion in full. A letter has no `conclusion_verbatim`; its `diagnosis_verbatim` (a
    different verbatim field, labelled as such) stands in; failing that, a referral's `reason` or a
    DXA's `structured` headline stands in, each labelled NOT word-for-word. FULL view (one `doc_key`): every
    stored field, the condensed summaries marked as not verbatim. Verbatim fields are emitted
    through `_verbatim_block` untouched. Stores and reads back; interprets nothing."""
    if not docs:
        return "No clinical documents on file."
    lines: list[str] = []
    if not full:
        lines.append(f"=== CLINICAL DOCUMENTS ({len(docs)}), oldest first ===")
    for d in docs:
        if lines:
            lines.append("")
        lines.append(_document_headline(d))
        letter = d.letter or {}
        reason_used = False
        if d.conclusion_verbatim is not None:
            label = f"conclusion ({d.conclusion_label})" if d.conclusion_label else "conclusion"
            lines.extend(_verbatim_block(label, d.conclusion_verbatim))
        elif letter.get("diagnosis_verbatim") is not None:
            lines.extend(_verbatim_block("diagnosis", letter["diagnosis_verbatim"]))
        else:
            fallback, reason_used = _no_conclusion_lines(d, letter)
            lines.extend(fallback)
        if not full:
            continue
        for label, value in (
            ("type", d.doc_type), ("modality", d.modality), ("subtype", d.subtype),
            ("laterality", d.laterality), ("reported", d.reported_date), ("provider", d.provider),
            ("referrer", d.referrer_name_raw), ("author", d.author_name_raw),
            ("recipient", d.recipient), ("accession", d.accession),
        ):
            if value is not None:
                lines.append(f"{label}: {value}")
        lines.append(f"source files: {', '.join(d.source_doc_filenames)}")
        lines.append(f"extracted: {d.extracted_at or '—'} ({d.schema_version}, {d.source})")
        if d.clinical_history is not None:
            lines.extend(["clinical history:", d.clinical_history])
        if d.findings_summary is not None:
            lines.extend(["findings summary (condensed, NOT verbatim):", d.findings_summary])
        if d.structured:
            lines.extend(["structured:", json.dumps(d.structured, indent=1, ensure_ascii=False)])
        for key, value in letter.items():
            if key == "diagnosis_verbatim" or (key == "reason" and reason_used):
                continue   # already shown above, in the conclusion slot
            if key == "management_plan_verbatim":
                lines.append("management plan, verbatim (one entry per line):")
                lines.extend(["<<<"] + list(value) + [">>>"])
            elif isinstance(value, str):
                note = " (condensed, NOT verbatim)" if key.endswith("_summary") else ""
                lines.extend([f"{key}{note}:", value])
            else:
                lines.extend([f"{key}:", json.dumps(value, indent=1, ensure_ascii=False)])
        if d.extraction_notes:
            lines.extend(["extraction notes:"] + [f"- {n}" for n in d.extraction_notes])
    return "\n".join(lines)


@mcp.tool()
@_stamped
def get_clinical_documents(since: str | None = None, doc_type: str | None = None,
                           modality: str | None = None, region: str | None = None,
                           doc_key: str | None = None) -> str:
    """The user's stored clinical documents -- imaging reports and clinical letters -- oldest
    `service_date` first. Read-back only: nothing here is interpreted, and no finding, constraint
    or injury is derived from a document.

    LIST view (default): date · modality (imaging) or subtype (letter) · study · region, the
    `doc_key`, and the document's own conclusion IN FULL. A conclusion is stored and returned
    verbatim, between `<<<` and `>>>`, exactly as extracted (typos and all); a letter shows its
    `diagnosis_verbatim` in that place. A letter with no diagnosis (a referral) shows its `reason`,
    and a DXA with no report comment shows a one-line headline (total mass, tissue fat %, BMD
    T-score) built from `structured`; both are labelled NOT word-for-word. Summaries are condensed,
    not verbatim, and are marked so.

    Optional filters: `since` (ISO date -- `service_date` on or after it), `doc_type`
    (imaging | correspondence), `modality` (US | CT | MRI | XR | DXA, case-insensitive), `region`
    (case-insensitive substring of the free-text region).

    `doc_key=<key>` returns that ONE document in full instead -- every stored field, including
    `structured` (modality numerics) and the letter body. A finding's `document` evidence ref
    that equals a `doc_key` resolves to this record."""
    since_d = None
    if since is not None:
        try:
            since_d = date.fromisoformat(since)
        except ValueError:
            return f"`since` must be an ISO date (YYYY-MM-DD), got {since!r}."
    try:
        doc_type, modality = _parse_document_filters(doc_type, modality)
    except ValueError as e:
        return str(e) + "."
    with SessionLocal() as sess:
        rows = clinical_documents.read_documents(
            sess, _current_user_id(), since=since_d, doc_type=doc_type, modality=modality,
            region=region, doc_key=doc_key)
        docs = [_clinical_document_out(r) for r in rows]
    if doc_key is not None and not docs:
        return f"No clinical document with doc_key {doc_key!r}."
    return _format_clinical_documents(docs, full=doc_key is not None)


@mcp.tool()
@_stamped
def get_findings(domain: str | None = None, since: str | None = None,
                 status: str | None = None) -> str:
    """The user's recorded findings — interpretations of their data, each with its date
    (`as_of`), status (open | confirmed), basis and evidence, newest first. Full statements
    (the chat's standing section truncates them). Proposals are never included.

    Optional filters: `domain` (injury | clinical | training | analysis), `since` (ISO date —
    `as_of` on or after it), `status` (open | confirmed).

    Findings derived from lab results are withheld and only counted: lab results are never
    interpreted here — see the Labs page."""
    if domain is not None and domain not in FINDING_DOMAINS:
        return f"Unknown domain {domain!r} — one of {', '.join(FINDING_DOMAINS)}."
    if status is not None and status not in typed_entries.FINDING_READ_STATUSES:
        return f"Unknown status {status!r} — one of {', '.join(typed_entries.FINDING_READ_STATUSES)}."
    since_d = None
    if since is not None:
        try:
            since_d = date.fromisoformat(since)
        except ValueError:
            return f"`since` must be an ISO date (YYYY-MM-DD), got {since!r}."

    def _keep(e) -> bool:
        if e.type != "finding":
            return False
        v = e.value or {}
        if domain is not None and v.get("domain") != domain:
            return False
        if status is not None and v.get("status") != status:
            return False
        if since_d is not None:
            as_of = typed_entries.parse_date(v.get("as_of"))
            if as_of is None or as_of < since_d:
                return False
        return True

    _constraints, findings, _live = _typed_entries_read(_current_user_id(), rows_filter=_keep)
    visible, withheld = findings["visible"], findings["withheld_labs"]
    if not visible and not withheld:
        return "No findings recorded" + (" for these filters." if (domain or since or status) else ".")
    lines = [f"Findings ({len(visible)}), newest first:"] if visible else []
    lines += [typed_entries.finding_line(f, full=True) for f in visible]
    if withheld:
        lines.append(typed_entries.withheld_labs_line(withheld, "Labs page"))
    return "\n".join(lines)


@mcp.tool()
@_stamped
def get_appointment_brief(key: str) -> str:
    """The assembled brief for one appointment (by its entry key, e.g. `appt_<yyyymmdd>_<slug>`),
    as JSON — the SAME object the app's /appointments/<key> page renders (one assembly function).

    Sections are listed in reading order by `module` (header, leave_with, asks, since,
    changes_vs_history, current_constraints, …); which appear depends on the appointment's `kind`.
    Asks labelled `"source": "ledger"` are derived from the ledger, not written by the user.
    Each row appears once: `leave_with` items are one-line pointers (`short`) to asks by `id`, capped
    at the five highest priorities (`total` is every ask, `remaining_ids` names the rest; all of them are
    under `asks`), and `since` omits what `changes_vs_history` carries. `resolves.unresolved: true` marks an ask whose
    linked row is not shown (missing, proposed, inactive or out of scope). Scope is the injuries the appointment names plus rows parented directly to them; proposals
    and lab-derived findings are never included.

    Plain-words fields (the print document reads these; `text`/`exit` keep the chat phrasing):
    `patient.name` (the user's full name, null if unset); on a finding `parent_key` and
    `parent_label` (the injury in words); on a constraint `restriction` (advisory: its own text;
    engine: kind, regions and side, without tier boilerplate), `exit_label` (the exits with the
    parent injury named in words) and `parent_key`/`parent_label`; on a derived ask `question` (the template alone, e.g. "Is this
    still appropriate?"); on a `changes_vs_history` injury `change` (`resolved` | `updated`)."""
    with SessionLocal() as sess:
        brief = appointment_brief.load_appointment_brief(sess, _current_user_id(), key)
    if brief is None:
        return f"No active appointment with key {key!r}."
    return json.dumps(brief, indent=1, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool — the training plan and schedule (read-only formatter over `current_state`)
#
# Nothing here derives or recomputes: the plan of record, the open phase, `phase_folders`, the
# resolver position and the week plan are `current_state`'s lifts of the stores the in-app coach
# already reads (`plan_week` is the SAME function behind `GET /engine/week-plan`; `done` is
# `resolve()`'s, `scheduled`/`quota`/`excess`/`unplaced` are `week_plan.consistency_rows`'). The
# STALE flag is `context_builder.plan_of_record_stale`. No verdicts: the stores' contents only.
# ---------------------------------------------------------------------------

_SCHEDULE_DAY_ABBR = {
    "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu",
    "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
}


def _plan_time(v: dict) -> str | None:
    """A schedule item's time as stored: the `time_range` text when present, else `time_of_day`
    (`unknown` is a stored value, not an absence, but it says nothing, so it is dropped)."""
    tod = v.get("time_of_day")
    tod = None if tod in (None, "unknown") else tod
    rng = v.get("time_range")
    return " ".join(x for x in (tod, rng) if x) or None


def _plan_satisfies(sat) -> str | None:
    if isinstance(sat, dict) and sat:
        return ", ".join(f"{k}:{x}" for k, x in sat.items())
    return None


def _plan_slot(slot: dict) -> str:
    """One raw microcycle slot as stored: kind:key, dose, minutes, the aerobic-lane sports."""
    kind = next((k for k in ("capacity", "load_window", "activity") if k in slot), "?")
    parts = [f"{kind}:{slot.get(kind)}", f"{slot.get('sessions_per_cycle')} per cycle",
             f"{slot.get('minutes')} min"]
    if slot.get("device_sports"):
        parts.append("sports " + "/".join(str(x) for x in slot["device_sports"]))
    if slot.get("recorded_via"):
        parts.append(f"recorded via {slot['recorded_via']}")
    return ", ".join(parts)


def _format_plan_of_record(plan: dict | None, phase: dict | None) -> list[str]:
    macro = plan.get("macro") if isinstance(plan, dict) else None
    if not isinstance(macro, str) or not macro.strip():
        return []
    meta = [f"revised {plan['revised_on']}" if plan.get("revised_on") else None,
            f"by {plan['revised_by']}" if plan.get("revised_by") else None]
    lines = ["== Plan of record ==", "Last " + (", ".join(m for m in meta if m) or "revision not recorded")]
    if plan_of_record_stale(plan, phase):
        lines.append(f"STALE: last revised {plan.get('revised_on')}, before the open phase's review date "
                     f"{phase.get('review_on')}, which has passed.")
    lines += ["", macro.strip()]
    return lines


def _format_plan_phase(phase: dict | None, phase_folders, window: dict | None) -> list[str]:
    if not phase:
        return ["== Current phase ==", "No open training phase (baseline)."]
    lines = ["== Current phase ==", f"{phase.get('label')} (entered {phase.get('entered_on')})"]
    if phase.get("intent"):
        lines.append(f"  intent: {phase['intent']}")
    if phase.get("review_on"):
        lines.append(f"  review on: {phase['review_on']}" + (" - review due" if phase.get("review_due") else ""))
    lines.append(f"  probe posture: {phase.get('probe_posture') or 'not set'}")
    lines.append(f"  vehicle ranking: {phase.get('vehicle_ranking') or 'not set'}")
    caps = phase.get("capacities")
    lines.append("  capacities: all live (no phase restriction)" if caps is None
                 else "  capacities: " + (", ".join(caps) if caps else "none"))
    if isinstance(phase_folders, dict):
        folder = phase_folders.get(phase.get("label"))
        lines.append(f"  Hevy folder (phase_folders): {folder}" if folder is not None
                     else "  Hevy folder (phase_folders): none declared for this phase")

    micro = phase.get("microcycle")
    if isinstance(micro, dict) and isinstance(micro.get("sub_cycles"), list):
        subs = micro["sub_cycles"]
        today_label = window.get("label") if isinstance(window, dict) and window.get("source") == "phase" else None
        lines.append(f"  microcycle: {micro.get('sub_cycle_days')}-day sub-cycles, {len(subs)} in rotation")
        for i, sc in enumerate(subs, 1):
            sc = sc if isinstance(sc, dict) else {}
            label = sc.get("label") or "(unlabelled)"
            here = " <- today" if today_label is not None and sc.get("label") == today_label else ""
            lines.append(f"    {i}/{len(subs)} {label}{here}")
            for slot in sc.get("slots") or []:
                lines.append(f"      - {_plan_slot(slot)}")
    if isinstance(window, dict) and window.get("source") == "phase":
        lines.append(f"  today is in leg {window.get('label')} ({window.get('start_date')} -> {window.get('end_date')})")
    return lines


def _format_plan_week(week: dict) -> list[str]:
    win = week.get("window") or {}
    lines = ["== This week ==",
             f"Window {win.get('label')}: {win.get('start_date')} -> {win.get('end_date')} (source {win.get('source')})"]
    for day in week.get("days") or []:
        flags = [] if day.get("available") else ["UNAVAILABLE (a hard item blocks training)"]
        if day.get("caution"):
            flags.append(f"caution: {day['caution']}")
        lines.append(f"{(day.get('weekday') or '').capitalize()} {day.get('date')}"
                     + (f" - {'; '.join(flags)}" if flags else ""))
        for h in day.get("hard") or []:
            bits = [h.get("expected_load"), "same-day training OK" if h.get("same_day_training") else None,
                    " ".join(x for x in (h.get("time_of_day"), h.get("time_range")) if x) or None]
            lines.append(f"  hard: {h.get('activity')}" + (f" ({', '.join(b for b in bits if b)})" if any(bits) else ""))
        for f in day.get("flexible") or []:
            sat = _plan_satisfies(f.get("satisfies"))
            lines.append(f"  flexible (candidate day, {f.get('pool')}/wk across its days): {f.get('activity')}"
                         + (f" [{sat}]" if sat else ""))
        for a in day.get("actual") or []:
            lines.append(f"  counted: {a.get('title') or a.get('sport_name') or a.get('ref')} -> {a.get('kind')}:{a.get('key')}")
    keys = week.get("keys") or []
    if keys:
        lines.append("Per slot key (scheduled = schedule items linked to it; done = the resolver's count):")
        for k in keys:
            lines.append(f"  {k['kind']}:{k['key']} - scheduled {k['scheduled']} / quota {k['quota']} / done {k['done']}"
                         f" - excess {k['excess']}, unplaced {k['unplaced']}")
    lines.append("needs_planning: " + ("yes (a quota is declared and every slot key has scheduled 0)"
                                       if week.get("needs_planning") else "no"))
    if week.get("unlinked_soft"):
        lines.append("Flexible items linked to no slot (listed, never counted): " + ", ".join(week["unlinked_soft"]))
    for n in week.get("one_off_notes") or []:
        lines.append(f"One-off note: {n.get('description')}" + (f" (expires {n['expires_at']})" if n.get("expires_at") else ""))
    return lines


# Why an in-window item is in the resolver's `uncounted[]`, as a fact about the record (no verdict). The
# reason codes are the resolver's, so a line here can be matched to `GET /engine/legs` `uncounted.reasons`.
def _uncounted_why(u: dict) -> str | None:
    reason = u.get("reason")
    if reason == "unclaimed_session":
        if u.get("detail") == "no_sport":
            return "the session has no sport recorded, so no slot's sports list can name it"
        return f"no slot's sports list names \"{u.get('sport_name')}\""
    if reason == "untimed":
        return "no start or stop time, so it cannot be placed or checked against a Hevy workout"
    if reason == "concurrent_strength":
        return "the same bout as a Hevy workout (its heart-rate trace)"
    if reason == "unadjudicated_duplicate":
        return "a possible duplicate Hevy workout, not yet adjudicated"
    if reason == "untagged":
        return "no exercise in it carries a primary region tag"
    if reason == "off_plan":
        return "its dominant capacity has no slot in this leg"
    return None


def _whole_minutes(v) -> str | None:
    """A duration in whole minutes ("59 min"); under a minute reads "<1 min", so a short session is not shown as
    zero. A non-number is None. (A device records fractions; the plan line is for finding the session.)"""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    return "<1 min" if 0 < v < 1 else f"{int(v + 0.5)} min"


def _format_plan_uncounted(uncounted: list[dict], context: dict | None) -> list[str]:
    """Sessions and workouts inside the window that matched no slot, each with its date and the resolver's
    reason. Silence here is how an unmatched sport name went unseen for a week (21 Oct 2026)."""
    if not uncounted:
        return []
    context = context or {}
    lines = ["== Not counted toward any slot this leg ==",
             "In the window, recorded, and not counted (reason code as in the legs read):"]
    for u in uncounted:
        key = ("session", u["session"]) if u.get("session") is not None else ("workout", u.get("workout"))
        meta = context.get(key, {})
        dur = u.get("duration_minutes")
        parts = [meta.get("day"), _uncounted_phrase(u),
                 _whole_minutes(dur),
                 f"Hevy \"{meta['title']}\"" if meta.get("title") else None]
        why = _uncounted_why(u)
        lines.append("- " + " · ".join(str(p) for p in parts if p)
                     + f" - {u.get('reason')}" + (f": {why}" if why else ""))
    return lines


def _format_plan_schedule_items(values: list[dict]) -> list[str]:
    if not values:
        return []
    lines = ["== Schedule items =="]
    for v in sorted(values, key=lambda x: str(x.get("activity") or "").casefold()):
        when = []
        span = v.get("event_date")
        if span:
            when.append(f"on {span}" + (f" -> {v['event_end']}" if v.get("event_end") else ""))
        if v.get("days"):
            when.append("/".join(_SCHEDULE_DAY_ABBR.get(str(d).lower(), str(d)) for d in v["days"]))
        if v.get("sessions_per_week") is not None:
            when.append(f"{v['sessions_per_week']}/wk")
        parts = [str(v.get("activity")), ", ".join(when) or "no days stored",
                 "hard" if v.get("hard") else "flexible", _plan_time(v),
                 f"expected_load {v['expected_load']}" if v.get("expected_load") else None,
                 f"season end {v['season_end']}" if v.get("season_end") else None,
                 f"satisfies {_plan_satisfies(v.get('satisfies'))}" if _plan_satisfies(v.get("satisfies")) else None]
        lines.append("- " + " · ".join(p for p in parts if p))
    return lines


def _format_training_plan(state, uncounted_context: dict | None = None) -> str:
    """The plan, phase, week and schedule as text, from one `CurrentState`. Pure. Each section
    appears only if its store holds something; the phase section always states the baseline."""
    pos = state.resolver_position if isinstance(state.resolver_position, dict) else None
    window = pos.get("window") if pos else None
    sections = [
        _format_plan_of_record(state.training_plan, state.training_phase),
        _format_plan_phase(state.training_phase, state.phase_folders, window),
    ]
    if state.week_plan is not None:
        sections.append(_format_plan_week(state.week_plan))
    elif window:
        # The resolver found a window but plan_week failed (current_state logged it and kept
        # going). Say so: a silent omission would read as "no week".
        sections.append(["== This week ==", "The week plan could not be read (see the server log)."])
    if pos:
        sections.append(_format_plan_uncounted(pos.get("uncounted") or [], uncounted_context))
    sections.append(_format_plan_schedule_items(
        [e.value or {} for e in state.knowledge_entries if getattr(e, "type", None) == "schedule_item"]))
    return "\n\n".join("\n".join(s) for s in sections if s)


@mcp.tool()
@_stamped
def get_training_plan() -> str:
    """Get the training plan and schedule: the plan of record (macro plan, with its STALE flag),
    the open phase (intent, review date, posture, capacities, microcycle and today's leg, Hevy
    folder), this week from the week planner (hard items by day, flexible items on their
    candidate days, scheduled/quota/done per slot key, needs_planning, day-after-heavy cautions),
    the sessions in the window that matched no slot (each with its date and reason), and the active
    schedule items. States what the stores hold; no verdicts."""
    user_id = _current_user_id()
    with SessionLocal() as _db:
        state = _current_state(user_id, _db, _local_day())
        pos = state.resolver_position if isinstance(state.resolver_position, dict) else {}
        return _format_training_plan(state, week_plan_mod.uncounted_context(_db, pos.get("uncounted") or []))


# ---------------------------------------------------------------------------
# Capability ratios (Q27 v1) — both routes per declared ratio, numbers only.
#
# Route (i) is derived from the Hevy log (same session-day pairs; baseline/current medians; the move
# between them); route (ii) is derived from clinic observations (same protocol, within 14 days).
# The governing reference and its reason are printed beside each; a literature band is printed as DATA
# when the reference gate allows it. Nothing here compares a reading to a band or labels a result.
# ---------------------------------------------------------------------------

def _fmt_band_value(value: dict) -> str:
    if "low" in value:
        return f"{value['low']:g} to {value['high']:g}"
    if "median" in value:
        return f"median {value['median']:g}"
    return f"mean {value['mean']:g}, SD {value['sd']:g}"


def _fmt_reference(ref: dict) -> list[str]:
    out = [f"reference: {ref['governing']} - {ref['reason']}"]
    band = ref.get("band")
    if band:
        cit = band["citation"]
        unit = band["unit"] if band["unit"] != "ratio" or band.get("normalisation") is None             else "force / body weight"
        out.append(
            f"band (published reference, for display): {_fmt_band_value(band['value'])} {unit} - "
            f"{band['population']}, n={band['n']} ({cit['authors']} {cit['year']}, PMID {cit['pmid']}; "
            f"read against {band['verified_against'].replace('_', ' ')})"
        )
        if band.get("unit_note"):
            out.append(f"unit note: {band['unit_note']}")
        if "body_mass_kg" in ref:
            out.append(
                f"body mass used: {ref['body_mass_kg']:g} kg ({ref['body_mass_source']}); "
                f"reading per that mass: {ref['value_normalised']:.3g}"
            )
    return out


# Why a logged day has no usable e1RM, in the words of the log (facts about the sets, not judgements).
_INELIGIBLE_REASON_TEXT = {
    "all_warmup": "all sets flagged warm-up",
    "reps_over_ceiling": "working sets above the {ceiling}-rep ceiling",
    "no_weight": "no set with a weight above zero and reps in range",
}


def _fmt_log_day(iso: str) -> str:
    from datetime import date as _date
    d = _date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def _fmt_no_eligible(detail: list[dict], ceiling: int) -> list[str]:
    """One line per day: '15 Oct: Shoulder ER - all sets flagged warm-up; ...'."""
    from engine import taxonomy as _tax
    by_day: dict[str, list[str]] = {}
    for e in detail:
        region = _tax.by_key(e["region"])
        who = region.label if region is not None else e["region"]
        why = _INELIGIBLE_REASON_TEXT[e["reason"]].format(ceiling=ceiling)
        by_day.setdefault(e["day"], []).append(f"{who} - {why}")
    return [f"{_fmt_log_day(day)}: " + "; ".join(parts) for day, parts in sorted(by_day.items())]


def _format_capability_ratios(overviews: list[dict]) -> str:
    blocks = ["CAPABILITY RATIOS (Q27 v1). Numbers and the governing reference only: no verdicts."]
    for ov in overviews:
        ratio, log, observed = ov["ratio"], ov["log_derived"], ov["observed"]
        lines = [f"{ratio['label']} [{ratio['key']}]"]
        lines.append(f"  Route (i) from the Hevy log (e1RM from sets up to {log['rep_ceiling']} reps; "
                     f"same session-day pairs only):")
        if not log["sides"]:
            lines.append("    no side has both halves logged")
        for side, s in log["sides"].items():
            parts = [f"{s['paired_days']} paired day(s), {s['half_not_logged_days']} with only one half logged, "
                     f"{s['no_eligible_e1rm_days']} with both logged but no usable e1RM"]
            parts.append("baseline " + (f"{s['baseline']:.3f}" if s["baseline"] is not None else "n/a (under 3 pairs)"))
            parts.append("current " + (f"{s['current']:.3f}" if s["current"] is not None
                                       else f"n/a (under 3 pairs within {log['currency_days']} days)"))
            if s["delta_pct"] is not None:
                parts.append(f"change {s['delta_pct']:+.1f}%")
            lines.append(f"    {side}: " + "; ".join(parts))
            for day_line in _fmt_no_eligible(s["no_eligible_e1rm"], log["rep_ceiling"]):
                lines.append(f"      no usable e1RM - {day_line}")
            lines.append(f"      reference: {s['reference']['governing']} - {s['reference']['reason']}")
        um = log["unmatched_sides"]
        if um["numerator_only"] or um["denominator_only"]:
            lines.append(f"    unmatched sides (not paired): numerator-only {um['numerator_only'] or '-'}, "
                         f"denominator-only {um['denominator_only'] or '-'}")
        lines.append(f"  Route (ii) from clinic readings (same protocol, within {observed['window_days']} days):")
        if not observed["sides"]:
            lines.append("    no paired readings recorded")
        for side, o in observed["sides"].items():
            n, dn = o["numerator"], o["denominator"]
            ratio_txt = f"{o['ratio']:.3f}" if o["ratio"] is not None else "n/a"
            lines.append(
                f"    {side}: {ratio_txt} = {n['value']:g} {n['unit']} ({n['observed_on']}) / "
                f"{dn['value']:g} {dn['unit']} ({dn['observed_on']}); protocol {o['protocol'] or 'none recorded'}"
            )
            for r in _fmt_reference(o["reference"]):
                lines.append("      " + r)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


@mcp.tool()
@_stamped
def get_capability_ratios() -> str:
    """Get the capability strength ratios (shoulder ER:IR, hip adductor:abductor) by both routes:
    (i) derived from the Hevy log (e1RM per side from sets up to the ratio's rep ceiling, same session-day
    pairs, baseline vs current; days that do not pair are counted as one-half-logged or no-usable-e1RM,
    with the reason and date), and
    (ii) from clinic readings (same protocol, within 14 days), each with its governing reference and
    the reason. A published literature band is shown as data only when the reading's protocol matches
    the norm's. States numbers; no verdicts."""
    user_id = _current_user_id()
    from engine import ratios as _ratios
    with SessionLocal() as _db:
        return _format_capability_ratios(_ratios.all_ratio_overviews(_db, user_id))


# ---------------------------------------------------------------------------
# Exercise catalogue read (Q27 tag pass, STEP 3b)
# ---------------------------------------------------------------------------

def _like_literal(text_: str) -> str:
    """Escape LIKE wildcards so a substring query matches its characters, not a pattern."""
    return text_.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _exercise_catalogue_rows(db: Session, user_id: int, query: str | None) -> list[dict]:
    """The templates visible to `user_id` (`hevy_templates._visible_to`: the global defaults and this
    user's OWN customs, never another user's), narrowed by a case-insensitive title substring, each with
    its tag state. READ-ONLY: nothing is written and no title is resolved.

    The tag state is `selection.classify_coverage`, the one definition the audit and the read path use:
    TAGGED (tag rows), NO-PATTERN (adjudicated, no rows), UNTAGGED (neither). The regions and roles come
    from the tag rows themselves; the side is the DECLARED `side` column, shown only where one exists."""
    from engine import selection as _selection

    T, Tag = models.HevyExerciseTemplate, models.ExerciseRegionTag
    q = db.query(T).filter(_visible_to(user_id))
    if query:
        q = q.filter(T.title.ilike("%" + _like_literal(query) + "%", escape="\\"))
    templates = q.order_by(func.lower(T.title), T.id).all()
    ids = {t.id for t in templates}
    _, classes = _selection.classify_coverage(db, ids)
    tag_rows: dict[str, list] = {}
    if ids:
        for r in db.query(Tag).filter(Tag.hevy_exercise_template_id.in_(ids)).order_by(
                Tag.region_key).all():
            tag_rows.setdefault(r.hevy_exercise_template_id, []).append(r)

    out = []
    for t in templates:
        rows = tag_rows.get(t.id, [])
        out.append({
            "id": t.id, "title": t.title, "custom": bool(t.is_custom), "laterality": t.laterality,
            "state": classes[t.id],
            "regions": [(r.region_key, r.role) for r in rows],
            "sides": sorted({r.side for r in rows if r.side}),
        })
    return out


_CATALOGUE_STATE_TEXT = {"tagged": "TAGGED", "adjudicated_no_pattern": "NO-PATTERN", "untagged": "UNTAGGED"}


def _format_exercise_catalogue(rows: list[dict], query: str | None) -> str:
    scope = f" whose title contains {query!r}" if query else ""
    if not rows:
        return f"No exercise templates visible to you{scope}."
    lines = [
        f"EXERCISE CATALOGUE: {len(rows)} template(s) visible to you{scope}. "
        "Tag state: TAGGED = has region tags; NO-PATTERN = adjudicated with none; UNTAGGED = neither. "
        "Side is shown only where one is declared."
    ]
    for r in rows:
        if r["state"] == "tagged":
            state = "TAGGED " + ", ".join(f"{k}({role})" for k, role in r["regions"])
        else:
            state = _CATALOGUE_STATE_TEXT[r["state"]]
        side = f" | side {'/'.join(r['sides'])}" if r["sides"] else ""
        lines.append(
            f"{r['id']} | {r['title']} | {'custom' if r['custom'] else 'default'} | "
            f"laterality {r['laterality'] or 'unset'} | {state}{side}"
        )
    return "\n".join(lines)


@mcp.tool()
@_stamped
async def get_exercise_catalogue(query: str | None = None) -> str:
    """List the exercise templates in the Hevy catalogue visible to you (the global defaults and your own
    customs), one line each: id, title, custom or default, laterality, and tag state (TAGGED with its
    regions and roles, NO-PATTERN, or UNTAGGED) plus the declared side where there is one. `query` is an
    optional case-insensitive substring of the title. Read-only: it states what is recorded, writes
    nothing, resolves nothing and gives no verdict. The catalogue is refreshed from Hevy first when it
    is stale; a `query` that matches nothing forces one refresh and looks again, so a template made in
    Hevy minutes ago can be found by name."""
    user_id = _current_user_id()
    query = (query or "").strip() or None
    db: Session = SessionLocal()
    try:
        await refresh_catalogue_if_stale(db, user_id)     # the door chat.py uses; a no-op inside its window
        rows = _exercise_catalogue_rows(db, user_id, query)
        if query and not rows:
            # The staleness gate skips the Hevy call inside 24h, and a miss is evidence the local copy is
            # behind Hevy: force one refresh and look again (chat's refresh-on-miss). Never raises.
            try:
                await sync_exercise_templates(db, only_user_id=user_id)
            except Exception:  # noqa: BLE001 -- a refresh problem must not fail a read of the local store
                pass
            rows = _exercise_catalogue_rows(db, user_id, query)
        return _format_exercise_catalogue(rows, query)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tools 8 & 9 — Hevy routine read-back (list + full-by-id)
#
# Routines are read LIVE from Hevy and never persisted (there is no routine
# store to reconcile) — mirroring `get_hevy_workouts`. Two granularities, per
# prior art (`chrisdoc/hevy-mcp` splits `search-routines`/`get-routine`):
#   * search_hevy_routines — compact list (title, id, folder, exercise titles +
#     count, NO set detail) so a title-existence / made-it check stays context-
#     small. This is the surface a create's check-exists-before-create guard reads.
#   * get_hevy_routine — the full config of one routine, INCLUDING superset
#     grouping and per-set detail, so a routine can be verified made-correctly.
# ---------------------------------------------------------------------------


def _current_user_hevy_key() -> str | None:
    """Decrypted Hevy key for the current MCP user, or None if not connected.

    Mirrors `get_hevy_workouts`'s preamble (own SessionLocal, resolve user via
    `_current_user_id`, decrypt the stored token) so the routine tools share one
    connect/decrypt path. Returns None rather than raising on the not-connected
    case, leaving the caller to render the user-facing message."""
    user_id = _current_user_id()
    db: Session = SessionLocal()
    try:
        row = (
            db.query(models.UserIntegration)
            .filter_by(user_id=user_id, provider="hevy")
            .first()
        )
        return decrypt(row.api_key_encrypted) if row is not None else None
    finally:
        db.close()


def _routine_title_fallback(routines: list[dict]) -> dict[str, str]:
    """template_id -> catalogue title, for exercises whose LIVE payload omits a title.

    Payload-first (VERIFY 4): Hevy's routine exercises carry `title`, so the happy
    path needs no lookup — this opens a session and queries the local template
    store ONLY for ids missing a title, and returns {} (no query) when every
    exercise already carries one."""
    missing = {
        ex.get("exercise_template_id")
        for r in routines
        for ex in r.get("exercises", [])
        if not ex.get("title") and ex.get("exercise_template_id")
    }
    if not missing:
        return {}
    db: Session = SessionLocal()
    try:
        return catalogue_titles_by_id(db, missing)
    finally:
        db.close()


@mcp.tool()
@_stamped
async def search_hevy_routines() -> str:
    """List the user's existing Hevy routines — compact. Returns each routine's
    title, id, folder, and its exercise names with a count, but NO set detail.

    Use this to check whether a routine exists (e.g. before creating one) or to
    find a routine's id to inspect in full with get_hevy_routine."""
    api_key = _current_user_hevy_key()
    if api_key is None:
        return "Hevy integration not connected for this user."

    client = HevyClient(api_key)

    all_routines: list[dict] = []
    page = 1
    while True:
        data = await client.get_routines(page=page, page_size=10)
        routines = data.get("routines", []) or []
        all_routines.extend(routines)
        page_count = data.get("page_count", page)
        if page >= page_count or not routines:
            break
        page += 1

    if not all_routines:
        return "No routines found in Hevy."

    fallback = _routine_title_fallback(all_routines)
    lines = [f"Hevy routines ({len(all_routines)})", ""]
    for routine in all_routines:
        lines.extend(format_routine_compact(routine, fallback))
    return "\n".join(lines)


@mcp.tool()
@_stamped
async def get_hevy_routine(routine_id: str) -> str:
    """Inspect one Hevy routine in full by its id: every exercise (in order),
    superset grouping, rest, notes, and every set (type, weight, reps, duration,
    distance, RPE).

    Use this to verify a routine was built correctly. Get the id from
    search_hevy_routines. An unknown id returns a clear not-found message."""
    api_key = _current_user_hevy_key()
    if api_key is None:
        return "Hevy integration not connected for this user."

    client = HevyClient(api_key)

    try:
        data = await client.get_routine(routine_id)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (400, 404):
            return f"No routine found with id '{routine_id}'."
        raise

    # Tolerate both a {"routine": {...}} wrapper and a bare routine object — the
    # connector parses nothing, so neither shape is asserted (VERIFY 2/4).
    routine = data.get("routine", data) if isinstance(data, dict) else None
    if not routine:
        return f"No routine found with id '{routine_id}'."

    fallback = _routine_title_fallback([routine])
    return "\n".join(format_routine_full(routine, fallback))
