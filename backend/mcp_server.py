from datetime import datetime, timezone, timedelta

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from sqlalchemy import text

from database import engine, SessionLocal
from connectors.hevy import HevyClient
from encryption import decrypt
from oauth_provider import PersonalOAuthProvider
import models

_SERVER_URL = "https://health-app-backend-production-760e.up.railway.app/mcp"

mcp = FastMCP(
    "Health Intelligence",
    auth_server_provider=PersonalOAuthProvider(),
    auth=AuthSettings(
        issuer_url=_SERVER_URL,
        service_documentation_url=None,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        resource_server_url=_SERVER_URL,
    ),
    streamable_http_path="/",
)


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
# Tool 1 — Recovery metrics
# ---------------------------------------------------------------------------

@mcp.tool()
def get_recovery_metrics(user_id: int = 1, days: int = 7) -> str:
    """Get recent recovery biometrics from Samsung Ring.
    Returns HRV (ms), sleep architecture (deep/REM/light/awake minutes),
    SpO2, respiratory rate, sleep efficiency for the last N days."""

    rows = _db_rows(
        """
        SELECT captured_at, hrv_ms, sleep_hr_bpm, respiratory_rate,
               sleep_efficiency_pct, actual_sleep_time_minutes,
               deep_minutes, rem_minutes, light_minutes, awake_minutes,
               spo2_average_pct, bedtime, wake_time
        FROM samsung_hrv_readings
        WHERE user_id = :user_id
          AND captured_at >= CURRENT_DATE - :days
        ORDER BY captured_at DESC
        """,
        {"user_id": user_id, "days": days},
    )

    source = "samsung_hrv_readings"
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
                   NULL AS bedtime, NULL AS wake_time
            FROM health_connect_syncs
            WHERE user_id = :user_id
              AND date >= CURRENT_DATE - :days
            ORDER BY date DESC
            """,
            {"user_id": user_id, "days": days},
        )
        source = "health_connect_syncs"

    if not rows:
        return f"No recovery data found in the last {days} days."

    lines = [f"Recovery metrics — last {days} days (source: {source})"]
    lines.append(f"Data window: {rows[-1]['captured_at']} → {rows[0]['captured_at']}\n")

    for r in rows:
        date = str(r["captured_at"])[:10]
        hrv = f"{r['hrv_ms']:.0f} ms" if r["hrv_ms"] is not None else "—"
        spo2 = f"{r['spo2_average_pct']:.1f}%" if r["spo2_average_pct"] is not None else "—"
        rr = f"{r['respiratory_rate']:.1f} br/min" if r["respiratory_rate"] is not None else "—"
        eff = f"{r['sleep_efficiency_pct']:.0f}%" if r["sleep_efficiency_pct"] is not None else "—"
        tst = f"{r['actual_sleep_time_minutes']:.0f} min" if r["actual_sleep_time_minutes"] is not None else "—"
        deep = f"{r['deep_minutes']:.0f}" if r["deep_minutes"] is not None else "—"
        rem = f"{r['rem_minutes']:.0f}" if r["rem_minutes"] is not None else "—"
        light = f"{r['light_minutes']:.0f}" if r.get("light_minutes") is not None else "—"
        awake = f"{r['awake_minutes']:.0f}" if r.get("awake_minutes") is not None else "—"
        lines.append(
            f"{date}: HRV={hrv} SpO2={spo2} RR={rr} Eff={eff} "
            f"TST={tst} Deep={deep}m REM={rem}m Light={light}m Awake={awake}m"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2 — Check-in history
# ---------------------------------------------------------------------------

@mcp.tool()
def get_checkin_history(user_id: int = 1, days: int = 30) -> str:
    """Get morning check-in history. Unions legacy and new tables for
    continuous history. Returns sleep quality, fatigue, soreness, life load,
    alcohol context, session RPE, and readiness scores."""

    rows = _db_rows(
        """
        SELECT date, sleep_quality, fatigue, soreness::text, motivation,
               life_load, alcohol_units, session_rpe, passive_hrv_ms,
               morning_readiness, 'daily_records' AS source
        FROM daily_records
        WHERE user_id = :user_id
          AND am_timestamp IS NOT NULL
          AND date >= CURRENT_DATE - :days

        UNION ALL

        SELECT date, sleep_quality, fatigue, NULL AS soreness,
               motivation, NULL AS life_load, NULL AS alcohol_units,
               NULL AS session_rpe, NULL AS passive_hrv_ms,
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
        lines.append(
            f"{r['date']} {src_tag}: sleep={sleep_q} fatigue={fatigue} soreness={soreness} "
            f"motivation={motivation} life_load={life_load} alcohol={alcohol} "
            f"session_rpe={rpe} readiness={readiness}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 3 — Training sessions (aerobic/cardio)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_training_sessions(user_id: int = 1, days: int = 28) -> str:
    """Get aerobic/cardio sessions from all connected sources (Polar, etc).
    Returns sport type, duration, average/max HR, distance, calories, HR zones."""

    rows = _db_rows(
        """
        SELECT source, sport, start_time, end_time, duration_seconds,
               avg_hr, max_hr, distance_meters, calories, hr_zones
        FROM exercise_sessions
        WHERE user_id = :user_id
          AND start_time >= CURRENT_DATE - :days
        ORDER BY start_time DESC
        """,
        {"user_id": user_id, "days": days},
    )

    if not rows:
        return (
            f"No aerobic sessions found in the last {days} days. "
            "Note: Polar data accumulates from June 2026 onward."
        )

    lines = [f"Training sessions — last {days} days"]
    lines.append(f"Data window: {rows[-1]['start_time']} → {rows[0]['start_time']}")
    lines.append("Note: Polar data accumulates from June 2026 onward.\n")

    for r in rows:
        date = str(r["start_time"])[:10]
        dur_min = f"{r['duration_seconds'] / 60:.0f} min" if r["duration_seconds"] else "—"
        avg_hr = f"{r['avg_hr']:.0f}" if r["avg_hr"] is not None else "—"
        max_hr = f"{r['max_hr']:.0f}" if r["max_hr"] is not None else "—"
        dist = f"{r['distance_meters'] / 1000:.2f} km" if r["distance_meters"] else "—"
        cal = f"{r['calories']:.0f} kcal" if r["calories"] is not None else "—"

        zone_summary = ""
        if r.get("hr_zones"):
            try:
                zones = r["hr_zones"] if isinstance(r["hr_zones"], dict) else {}
                zone_parts = [f"Z{k}={v}min" for k, v in zones.items() if v]
                zone_summary = " zones=[" + " ".join(zone_parts) + "]"
            except Exception:
                pass

        lines.append(
            f"{date} [{r['source']}] {r['sport'] or 'unknown'}: "
            f"{dur_min} HR={avg_hr}/{max_hr} dist={dist} cal={cal}{zone_summary}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 4 — Hevy strength workouts (async — HevyClient is async)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_hevy_workouts(user_id: int = 1, days: int = 14) -> str:
    """Get strength training workouts from Hevy. Returns exercises, sets,
    weights, reps, and estimated 1RM (Epley formula) per movement."""

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
        for ex in w.get("exercises", []):
            title = ex.get("title", "Unknown exercise")
            normal_sets = [s for s in ex.get("sets", []) if s.get("set_type") != "warmup"]
            if not normal_sets:
                continue

            set_strs = []
            best_1rm = 0.0
            for s in normal_sets:
                wkg = s.get("weight_kg")
                reps = s.get("reps")
                if wkg is not None and reps is not None:
                    set_strs.append(f"{wkg}kg x {reps}")
                    est = _epley_1rm(wkg, reps)
                    if est > best_1rm:
                        best_1rm = est
                elif reps is not None:
                    set_strs.append(f"BW x {reps}")

            sets_summary = f"{len(normal_sets)} sets: " + ", ".join(set_strs)
            orm_line = f" | e1RM≈{best_1rm:.1f}kg" if best_1rm > 0 else ""
            lines.append(f"  {title}: {sets_summary}{orm_line}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 5 — Today's readiness snapshot
# ---------------------------------------------------------------------------

@mcp.tool()
def get_readiness_snapshot(user_id: int = 1) -> str:
    """Today's readiness snapshot. Latest biometrics, most recent check-in,
    7-day training summary, and current injury constraints."""

    hrv_rows = _db_rows(
        """
        SELECT captured_at, hrv_ms, sleep_efficiency_pct,
               actual_sleep_time_minutes, deep_minutes, rem_minutes,
               spo2_average_pct, respiratory_rate, sleep_hr_bpm
        FROM samsung_hrv_readings
        WHERE user_id = :user_id
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        {"user_id": user_id},
    )

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

    session_stats = _db_rows(
        """
        SELECT COUNT(*) AS session_count,
               SUM(duration_seconds) AS total_seconds
        FROM exercise_sessions
        WHERE user_id = :user_id
          AND start_time >= CURRENT_DATE - 7
        """,
        {"user_id": user_id},
    )

    hrv_continuity = _db_rows(
        """
        SELECT COUNT(*) AS reading_count
        FROM samsung_hrv_readings
        WHERE user_id = :user_id
          AND captured_at >= CURRENT_DATE - 7
        """,
        {"user_id": user_id},
    )

    lines = ["=== TODAY'S READINESS SNAPSHOT ===\n"]

    if hrv_rows:
        r = hrv_rows[0]
        lines.append(f"Latest biometrics ({str(r['captured_at'])[:10]}):")
        lines.append(f"  HRV: {r['hrv_ms']:.0f} ms" if r["hrv_ms"] is not None else "  HRV: —")
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

    if session_stats:
        s = session_stats[0]
        count = s["session_count"] or 0
        total_min = (s["total_seconds"] or 0) / 60
        lines.append(f"Aerobic sessions (last 7 days): {count} sessions, {total_min:.0f} total minutes\n")

    lines.append("---")
    lines.append("Active injury constraints (as of June 2026):")
    lines.append("- Left little finger: provocative — wrenched, bruising. No load progression until cleared.")
    lines.append("- Right shoulder: horizontal adduction provocative unloaded; load amplifies.")
    lines.append("  Overhead: caution. Pressing: untested.")
    lines.append("- Left hamstring: clear below jogging pace. Provoked by striding/sprinting.")
    lines.append("  Velocity is the gate.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 6 — Training load / ACWR
# ---------------------------------------------------------------------------

@mcp.tool()
def get_training_load(user_id: int = 1) -> str:
    """Calculate acute:chronic workload ratio (ACWR) from 28 days of sessions.
    Acute = last 7 days. Chronic = 28-day rolling daily average.
    ACWR sweet spot: 0.8–1.3. Above 1.5 = elevated injury risk."""

    rows = _db_rows(
        """
        SELECT start_time, duration_seconds, avg_hr
        FROM exercise_sessions
        WHERE user_id = :user_id
          AND start_time >= CURRENT_DATE - 28
        ORDER BY start_time DESC
        """,
        {"user_id": user_id},
    )

    first_row = _db_rows(
        """
        SELECT MIN(start_time) AS first_session
        FROM exercise_sessions
        WHERE user_id = :user_id
        """,
        {"user_id": user_id},
    )

    data_from = first_row[0]["first_session"] if first_row and first_row[0]["first_session"] else "unknown"

    now = datetime.now(timezone.utc)
    cutoff_7 = now - timedelta(days=7)

    acute_load = 0.0
    chronic_load = 0.0
    count_7 = 0
    count_28 = len(rows)

    for r in rows:
        dur_min = (r["duration_seconds"] or 0) / 60
        avg_hr = r["avg_hr"]
        load = (dur_min * avg_hr) if avg_hr is not None else dur_min

        chronic_load += load
        try:
            st = datetime.fromisoformat(str(r["start_time"]).replace("Z", "+00:00"))
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
        except Exception:
            st = now - timedelta(days=14)

        if st >= cutoff_7:
            acute_load += load
            count_7 += 1

    chronic_weekly_avg = chronic_load / 4

    if chronic_weekly_avg > 0:
        acwr = acute_load / chronic_weekly_avg
        acwr_str = f"{acwr:.2f}"
        if acwr < 0.8:
            interpretation = "Underloading — below stimulus threshold"
        elif acwr <= 1.3:
            interpretation = "Sweet spot — proceed with planned training"
        elif acwr <= 1.5:
            interpretation = "Caution — consider load reduction"
        else:
            interpretation = "Elevated injury risk — reduce load"
    else:
        acwr_str = "N/A (no chronic baseline)"
        interpretation = "Insufficient data for ACWR calculation"

    lines = [
        "=== TRAINING LOAD / ACWR ===\n",
        f"Acute load (7 days):    {acute_load:.0f} load units ({count_7} sessions)",
        f"Chronic weekly avg:     {chronic_weekly_avg:.0f} load units/week ({count_28} sessions over 28 days)",
        f"ACWR:                   {acwr_str}",
        f"Interpretation:         {interpretation}",
        f"\nLoad metric: TRIMP proxy (duration_min × avg_hr) where HR available; duration_min otherwise.",
        f"Data from: {data_from}",
        f"Note: Hevy volume load is NOT yet integrated into this calculation (exercise_sessions only).",
    ]

    return "\n".join(lines)
