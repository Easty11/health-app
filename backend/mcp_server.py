import functools
import inspect
import re
from datetime import date, datetime, timezone, timedelta

import httpx
import pytz

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import engine, SessionLocal
from injury_trajectory import evaluate as evaluate_injury_trajectories
from connectors.hevy import HevyClient
from hevy_format import format_set
from hevy_routine_format import (  # shared renderers (#314) — one home, also used by context_builder
    format_routine_compact,
    format_routine_full,
)
from hevy_templates import catalogue_titles_by_id
from encryption import decrypt
from oauth_provider import PersonalOAuthProvider
import models
from routers.labs import get_lab_results as _read_lab_results, StoredResultOut
from reads.labs_reads import latest_lab_results
from reads.aerobic_reads import arbitrated_sessions   # the canonical read-door (#Q161)
from reads.recovery_reads import hrv_deviation, representative_source
from engine.training_phase import current_training_phase

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


def _current_user_id() -> int:
    """Resolve the caller's user_id from their MCP bearer token. Raises
    rather than falling back to any default — every tool call must be bound
    to a real, logged-in user (see oauth_provider.PersonalOAuthProvider)."""
    token = get_access_token()
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

def _format_recovery_metrics(rows: list, days: int) -> str:
    """Render source-tagged recovery rows into the tool's text table (pure; testable).

    Each row is a mapping carrying `source` plus HRV/sleep fields; rows are already
    ordered captured_at DESC. Every line is prefixed with its `[source]` so provenance is
    never silent and a night carried by two sources shows as two labelled lines — neither
    collapsed nor dropped (Garmin lines carry HRV only; Samsung supplies the sleep
    architecture, so a Garmin line renders the sleep fields as '—')."""
    if not rows:
        return f"No recovery data found in the last {days} days."

    sources = ", ".join(sorted({str(r["source"]) for r in rows}))
    lines = [f"Recovery metrics — last {days} days (sources: {sources})"]
    lines.append(f"Data window: {rows[-1]['captured_at']} → {rows[0]['captured_at']}\n")

    for r in rows:
        date = str(r["captured_at"])[:10]
        src = r["source"]
        hrv = f"{r['hrv_ms']:.0f} ms" if r["hrv_ms"] is not None else "—"
        rhr = f"{r['sleep_hr_bpm']:.0f} bpm" if r["sleep_hr_bpm"] is not None else "—"
        spo2 = f"{r['spo2_average_pct']:.1f}%" if r["spo2_average_pct"] is not None else "—"
        rr = f"{r['respiratory_rate']:.1f} br/min" if r["respiratory_rate"] is not None else "—"
        eff = f"{r['sleep_efficiency_pct']:.0f}%" if r["sleep_efficiency_pct"] is not None else "—"
        tst = f"{r['actual_sleep_time_minutes']:.0f} min" if r["actual_sleep_time_minutes"] is not None else "—"
        deep = f"{r['deep_minutes']:.0f}" if r["deep_minutes"] is not None else "—"
        rem = f"{r['rem_minutes']:.0f}" if r["rem_minutes"] is not None else "—"
        light = f"{r['light_minutes']:.0f}" if r.get("light_minutes") is not None else "—"
        awake = f"{r['awake_minutes']:.0f}" if r.get("awake_minutes") is not None else "—"
        lines.append(
            f"{date} [{src}]: HRV={hrv} RHR={rhr} SpO2={spo2} RR={rr} Eff={eff} "
            f"TST={tst} Deep={deep}m REM={rem}m Light={light}m Awake={awake}m"
        )

    return "\n".join(lines)


@mcp.tool()
@_stamped
def get_recovery_metrics(days: int = 7) -> str:
    """Get recent recovery biometrics across connected sources (Samsung Ring + Garmin).
    Returns HRV (ms) source-tagged per night, plus sleep architecture (deep/REM/light/
    awake minutes), SpO2, respiratory rate, sleep efficiency for the last N days. Sleep
    architecture is Samsung-only; a Garmin night carries HRV and shows sleep fields as
    '—'. A night measured by both sources shows as two labelled lines — never collapsed,
    never silently preferring one source."""
    user_id = _current_user_id()

    # Union the source-native stores: Samsung device rows carry HRV + full sleep
    # architecture (and pre-mirror history the held backfill hasn't copied), Garmin HRV
    # comes from the source-agnostic `hrv_readings`. Neither is dropped; each row is
    # source-tagged for the formatter. Raw ms is never blended (cross-instrument offset is
    # non-constant, #292) — the two sources are shown side by side, labelled.
    rows = _db_rows(
        """
        SELECT captured_at, hrv_ms, sleep_hr_bpm, respiratory_rate,
               sleep_efficiency_pct, actual_sleep_time_minutes,
               deep_minutes, rem_minutes, light_minutes, awake_minutes,
               spo2_average_pct, bedtime, wake_time, 'samsung' AS source
        FROM samsung_hrv_readings
        WHERE user_id = :user_id
          AND captured_at >= CURRENT_DATE - :days
          AND context = 'passive_overnight'
        UNION ALL
        SELECT captured_at, rmssd_ms AS hrv_ms, NULL AS sleep_hr_bpm,
               NULL AS respiratory_rate, NULL AS sleep_efficiency_pct,
               NULL AS actual_sleep_time_minutes, NULL AS deep_minutes,
               NULL AS rem_minutes, NULL AS light_minutes, NULL AS awake_minutes,
               NULL AS spo2_average_pct, NULL AS bedtime, NULL AS wake_time,
               'garmin' AS source
        FROM hrv_readings
        WHERE user_id = :user_id
          AND captured_at >= CURRENT_DATE - :days
          AND source = 'garmin'
        ORDER BY captured_at DESC, source
        """,
        {"user_id": user_id, "days": days},
    )

    if not rows:
        rows = _db_rows(
            """
            SELECT date AS captured_at, hrv_rmssd AS hrv_ms,
                   resting_heart_rate AS sleep_hr_bpm,
                   respiratory_rate, NULL AS sleep_efficiency_pct,
                   sleep_duration_minutes AS actual_sleep_time_minutes,
                   deep_sleep_minutes AS deep_minutes,
                   rem_sleep_minutes AS rem_minutes,
                   NULL AS light_minutes, NULL AS awake_minutes,
                   oxygen_saturation AS spo2_average_pct,
                   NULL AS bedtime, NULL AS wake_time, 'health_connect_syncs' AS source
            FROM health_connect_syncs
            WHERE user_id = :user_id
              AND date >= CURRENT_DATE - :days
            ORDER BY date DESC
            """,
            {"user_id": user_id, "days": days},
        )

    return _format_recovery_metrics(rows, days)


# ---------------------------------------------------------------------------
# Tool 2 — Check-in history
# ---------------------------------------------------------------------------

@mcp.tool()
@_stamped
def get_checkin_history(days: int = 30) -> str:
    """Get morning check-in history. Unions legacy and new tables for
    continuous history. Returns sleep quality, fatigue, soreness, life load,
    alcohol context, session RPE, and readiness scores."""
    user_id = _current_user_id()

    rows = _db_rows(
        """
        SELECT date, sleep_quality, fatigue, soreness::text, motivation,
               life_load, alcohol_units, session_rpe,
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
               NULL AS session_rpe, NULL AS hrv_ms,
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
        rpe = r["session_rpe"] if r.get("session_rpe") is not None else "—"
        readiness = r["morning_readiness"] if r["morning_readiness"] is not None else "—"
        hrv = f"{r['hrv_ms']:.0f}ms" if r.get("hrv_ms") is not None else "—"
        lines.append(
            f"{r['date']} {src_tag}: sleep={sleep_q} fatigue={fatigue} soreness={soreness} "
            f"motivation={motivation} life_load={life_load} alcohol={alcohol} "
            f"session_rpe={rpe} hrv={hrv} readiness={readiness}"
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
        "HC sleep_end since #328); prefill provenance is not stored.",
        "",
        "== Nightly diary ==",
    ]
    header = ["date", "rx_id", "rx_lights_out", "rx_wake_anchor"] + list(_CBTI_DIARY_COLS)
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
    sleep latency, WASO, night wakings split by cause (nocturia / pain / spontaneous),
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

@mcp.tool()
@_stamped
def get_training_sessions(days: int = 28) -> str:
    """Get aerobic/cardio sessions from all connected sources (Polar, etc).
    Returns sport type, duration, average/max HR, distance, calories, HR zones."""
    user_id = _current_user_id()
    since = datetime.now(timezone.utc).date() - timedelta(days=days)

    # Read-door (#Q161): list CANONICAL sessions only — a same-bout Polar/HC twin must not
    # appear twice. arbitrated_sessions marks exactly one row per bout canonical; day is the
    # local `session_date` (untimed sessions, which the old `start_time >=` filter dropped,
    # are now included). Rendered inside the session so attributes are materialised.
    with SessionLocal() as _db:
        sessions = [s for s in arbitrated_sessions(user_id, _db, since=since)
                    if getattr(s, "canonical", True)]

        if not sessions:
            return (
                f"No aerobic sessions found in the last {days} days. "
                "Note: Polar data accumulates from June 2026 onward."
            )

        lines = [f"Training sessions — last {days} days"]
        lines.append(f"Data window: {sessions[-1].session_date} → {sessions[0].session_date}")
        lines.append("Note: Polar data accumulates from June 2026 onward.\n")

        for s in sessions:
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

            lines.append(
                f"{s.session_date} [{s.source}] {s.sport_name or 'unknown'}: "
                f"{dur_min} HR={avg_hr}/{max_hr} dist=— cal={cal}{zone_summary}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4 — Hevy strength workouts (async — HevyClient is async)
# ---------------------------------------------------------------------------

@mcp.tool()
@_stamped
async def get_hevy_workouts(days: int = 14) -> str:
    """Get strength training workouts from Hevy. Returns exercises, sets,
    weights, reps, and estimated 1RM (Epley formula) per movement."""
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
    7-day training summary, and current injury constraints."""
    user_id = _current_user_id()

    hrv_rows = _db_rows(
        """
        SELECT captured_at, hrv_ms, sleep_efficiency_pct,
               actual_sleep_time_minutes, deep_minutes, rem_minutes,
               spo2_average_pct, respiratory_rate, sleep_hr_bpm
        FROM samsung_hrv_readings
        WHERE user_id = :user_id
          AND context = 'passive_overnight'
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        {"user_id": user_id},
    )

    # Q130 → #292: the readiness HRV reads the per-source-normalised deviation model
    # (source-agnostic over hrv_readings), NOT `.canonical` arbitration. This is a rich
    # LLM readout (not the device-attributed `get_recovery_metrics`, which stays wholly
    # Samsung), so it surfaces BOTH the representative single ms figure and the full
    # deviation object (combined z, direction, cross-source confidence). Sleep/SpO2/
    # architecture below stay on the Samsung device row (Garmin supplies none).
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
    _rep = representative_source(_dev)

    checkin_rows = _db_rows(
        """
        SELECT date, sleep_quality, fatigue, soreness::text,
               motivation, life_load, session_rpe, morning_readiness
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
        _week = [s for s in arbitrated_sessions(
                     user_id, _sdb, since=datetime.now(timezone.utc).date() - timedelta(days=7))
                 if getattr(s, "canonical", True)]
    session_count = len(_week)
    session_total_min = sum(float(s.duration_minutes) for s in _week
                            if s.duration_minutes is not None)

    hrv_continuity = _db_rows(
        """
        SELECT COUNT(*) AS reading_count
        FROM samsung_hrv_readings
        WHERE user_id = :user_id
          AND captured_at >= CURRENT_DATE - 6
          AND context = 'passive_overnight'
        """,
        {"user_id": user_id},
    )

    lines = ["=== TODAY'S READINESS SNAPSHOT ===\n"]

    if hrv_rows:
        r = hrv_rows[0]
        lines.append(f"Latest biometrics ({str(r['captured_at'])[:10]}):")
        lines.append(_readiness_hrv_line(_rep, _dev, _wake_day))
        if _dev["n_contributing"]:
            lines.append(
                f"  HRV deviation: {_dev['combined_z']:+.2f}σ {_dev['direction']} "
                f"(confidence {_dev['confidence']}, {_dev['n_contributing']} source(s), "
                f"baseline {_dev['baseline_state']})"
            )
        lines.append(f"  Sleep efficiency: {r['sleep_efficiency_pct']:.0f}%" if r["sleep_efficiency_pct"] is not None else "  Sleep efficiency: —")
        lines.append(f"  Sleep duration: {r['actual_sleep_time_minutes']:.0f} min" if r["actual_sleep_time_minutes"] is not None else "  Sleep duration: —")
        lines.append(f"  Deep: {r['deep_minutes']:.0f} min  REM: {r['rem_minutes']:.0f} min" if (r.get("deep_minutes") is not None and r.get("rem_minutes") is not None) else "  Sleep stages: —")
        lines.append(f"  SpO2: {r['spo2_average_pct']:.1f}%" if r["spo2_average_pct"] is not None else "  SpO2: —")
        lines.append(f"  Resp rate: {r['respiratory_rate']:.1f} br/min" if r["respiratory_rate"] is not None else "  Resp rate: —")
        lines.append(f"  Resting HR: {r['sleep_hr_bpm']:.0f} bpm\n" if r["sleep_hr_bpm"] is not None else "  Resting HR: —\n")
        hrv_count = hrv_continuity[0]["reading_count"] if hrv_continuity else 0
        lines.append(f"  HRV data continuity: {hrv_count}/7 days in last week\n")
    else:
        lines.append("Latest biometrics: no Samsung Ring data found.\n")

    if checkin_rows:
        c = checkin_rows[0]
        lines.append(f"Most recent check-in ({c['date']}):")
        lines.append(f"  Sleep quality={c['sleep_quality']} Fatigue={c['fatigue']} Soreness={c.get('soreness') or '—'}")
        lines.append(f"  Motivation={c['motivation']} Life load={c.get('life_load') or '—'}")
        lines.append(f"  Session RPE={c.get('session_rpe') or '—'} Readiness={c['morning_readiness'] or '—'}\n")
    else:
        lines.append("Most recent check-in: none found.\n")

    if session_count:
        lines.append(f"Aerobic sessions (last 7 days): {session_count} sessions, "
                     f"{session_total_min:.0f} total minutes\n")

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
