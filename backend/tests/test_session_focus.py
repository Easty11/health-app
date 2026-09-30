"""Brief A / A1–A4 — session focus on chat: a session review sees the full session, as the backend renders it.

`ChatRequest.focus_session = {kind, id, scope}` is a reference; the server loads the session for the
calling user, renders it with the shared renderers, and pins it on that turn regardless of the
ten-workout window. Exercised end to end through the real `/chat` endpoint, the model faked at the
TRANSPORT layer (#166) so what is asserted is the system prompt the model would actually have received.

Gates covered (Brief A):
  G1  a Hevy workout OLDER than the ten most recent is pinned with RPE, notes, set types and a
      distance-only set; aerobic focus renders zones; context scope includes a 6-day-old session and a
      next-day scheduled item; an unknown / foreign id is graceful (200); no focus → context unchanged.
  G2  MCP `get_training_sessions` output is byte-identical across the A2 extraction.
  A4  `session_analysis` knowledge entries do NOT reach chat context (so the analyse-session call stays
      out of the feedback path only if it ever did — here it never did; this pins the fact).
Fixtures are synthetic placeholders.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import context_builder
import models
from aerobic_format import format_aerobic_session
from auth import get_current_user
from database import get_db
from routers import chat as chat_router


class _FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Draft.")], stop_reason="end_turn")


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# The session under review: Tue 29 Sep 2026, 07:00 AEST == Mon 28 Sep 21:00 UTC — the UTC calendar day
# is the PREVIOUS day, so a UTC-sliced date would land a day early (the A5(b) hazard, here on the server).
FOCUS_START = _utc(2026, 9, 28, 21, 0)
FOCUS_DAY = date(2026, 9, 29)


@pytest.fixture
def world(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    # Freeze the prompt's clock so two requests' standing prompts are comparable.
    monkeypatch.setattr(
        context_builder, "_now_aest",
        lambda: datetime(2026, 9, 29, 12, 0, tzinfo=context_builder.AEST),
    )
    me = models.User(email="me@example.com", hashed_password="x")
    other = models.User(email="other@example.com", hashed_password="x")
    db_session.add_all([me, other])
    db_session.commit()

    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: me
    client = TestClient(app)
    fake = _FakeClient()
    monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)

    def send(focus=None, message="Session review: x"):
        body = {"message": message, "conversation_history": []}
        if focus is not None:
            body["focus_session"] = focus
        r = client.post("/chat", json=body)
        assert r.status_code == 200, r.text
        return fake.messages.calls[-1]["system"]

    return SimpleNamespace(db=db_session, me=me, other=other, send=send, monkeypatch=monkeypatch,
                           client=client, fake=fake)


def _hevy(db, user, hevy_id, start, *, title="Lower", exercises=None, description="", end_after_min=70):
    raw = {
        "id": hevy_id, "title": title, "description": description,
        "start_time": start.isoformat(), "end_time": (start + timedelta(minutes=end_after_min)).isoformat(),
        "exercises": exercises or [],
    }
    db.add(models.HevyWorkout(hevy_id=hevy_id, user_id=user.id, start_time=start,
                              end_time=start + timedelta(minutes=end_after_min), title=title, raw=raw))
    db.commit()
    return raw


LOWER_EXERCISES = [
    {"title": "Hip Thrust (Barbell)", "exercise_template_id": "T1", "notes": "L side tight on the last rep",
     "sets": [
         {"type": "warmup", "weight_kg": 40, "reps": 10},
         {"type": "normal", "weight_kg": 100, "reps": 8, "rpe": 7.5},
         {"type": "normal", "weight_kg": 100, "reps": 8, "rpe": 8},
         {"type": "failure", "weight_kg": 100, "reps": 6, "rpe": 9},
     ]},
    {"title": "Suitcase Carry", "exercise_template_id": "T2", "notes": "",
     "sets": [{"type": "normal", "weight_kg": 24, "distance_meters": 40},
              {"type": "normal", "distance_meters": 100}]},
    {"title": "Dead Bug", "exercise_template_id": "T3", "notes": "",
     "sets": [{"type": "normal", "duration_seconds": 45}, {"type": "dropset", "reps": 12}]},
]


def _aerobic(db, user, source, day, *, start=None, minutes=45, sport="Pilates", hr=(112, 150),
             zones=(0, 600, 1800, 300, 0), cal=210, sid=None, package=None):
    row = models.AerobicSession(
        user_id=user.id, source=source, source_session_id=sid or f"{source}-{day}-{sport}",
        session_date=day, start_time=start, stop_time=(start + timedelta(minutes=minutes)) if start else None,
        sport_name=sport, duration_minutes=minutes, hr_avg=hr[0] if hr else None, hr_max=hr[1] if hr else None,
        calories=cal, z1_seconds=zones[0] if zones else None, z2_seconds=zones[1] if zones else None,
        z3_seconds=zones[2] if zones else None, z4_seconds=zones[3] if zones else None,
        z5_seconds=zones[4] if zones else None, source_package=package,
    )
    db.add(row)
    db.commit()
    return row


def _schedule(db, user, key, value):
    db.add(models.UserKnowledgeEntry(user_id=user.id, type="schedule_item", key=key, value=value,
                                     source="chat", active=True))
    db.commit()


def _pinned(prompt: str) -> str:
    """The pinned block only: from its heading to the end of the prompt."""
    assert "## Session under review" in prompt
    return prompt[prompt.index("## Session under review"):]


# ── G1 — Hevy: an older-than-window workout is pinned at full fidelity ───────

def test_older_than_window_hevy_is_pinned_with_rpe_notes_types_and_distance_sets(world, monkeypatch):
    db = world.db
    # 12 workouts; the focus is the OLDEST, so it is outside the ten-workout window the standing
    # history carries. The standing window is faked (transport layer) as the ten newest.
    focus_raw = _hevy(db, world.me, "hv-old", _utc(2026, 9, 1, 0), title="OLD LOWER SESSION",
                      exercises=LOWER_EXERCISES, description="felt flat, slept badly")
    recent = [_hevy(db, world.me, f"hv-{i}", _utc(2026, 9, 10 + i, 0), title=f"Recent {i}") for i in range(11)]
    window = sorted(recent, key=lambda w: w["start_time"], reverse=True)[:10]

    integ = models.UserIntegration(user_id=world.me.id, provider="hevy", api_key_encrypted="enc")
    db.add(integ)
    db.commit()

    async def _fake_gather(_key):
        return {"workout_count": 12, "recent_workouts": window}

    async def _fake_routines(_client, _uid):
        return None

    monkeypatch.setattr(chat_router, "decrypt", lambda _v: "k")
    monkeypatch.setattr(chat_router, "_gather_hevy_context", _fake_gather)
    monkeypatch.setattr(chat_router.hevy_routine_cache, "get_routines_cached", _fake_routines)

    prompt = world.send({"kind": "hevy", "id": "hv-old", "scope": "session"})

    standing, pinned = prompt.split("## Session under review")
    assert "OLD LOWER SESSION" not in standing      # outside the ten-workout window — only the pin carries it
    assert "RPE 7.5" in pinned and "RPE 8" in pinned and "RPE 9" in pinned
    assert "L side tight on the last rep" in pinned          # exercise notes
    assert "felt flat, slept badly" in pinned                # workout description
    assert "[warmup]" in pinned and "[failure]" in pinned and "[dropset]" in pinned   # set types
    assert "24kg — 40m" in pinned                            # loaded carry (weight + distance, no reps)
    assert "Set 2: 100m" in pinned                           # a distance-only set
    assert "45s" in pinned and "12 reps" in pinned           # duration-only and reps-only (bodyweight) sets
    assert "review of THIS session's execution" in pinned    # scope=session framing
    assert "## Surrounding load" not in pinned and "## Scheduled next" not in pinned


def test_hevy_focus_renders_the_current_catalogue_title(world):
    """The pinned session goes through the same catalogue annotation as the standing history (#81)."""
    db = world.db
    db.add(models.HevyExerciseTemplate(id="T1", title="Hip Thrust (Renamed In Catalogue)", is_custom=False))
    db.commit()
    _hevy(db, world.me, "hv-1", FOCUS_START, exercises=LOWER_EXERCISES[:1])
    pinned = _pinned(world.send({"kind": "hevy", "id": "hv-1", "scope": "session"}))
    assert "Hip Thrust (Renamed In Catalogue)" in pinned
    assert "UNCATALOGUED" not in pinned.split("Suitcase")[0]


# ── G1 — aerobic focus renders zones ─────────────────────────────────────────

def test_aerobic_focus_renders_zones_through_the_shared_renderer(world):
    row = _aerobic(world.db, world.me, "polar_v4", date(2026, 9, 28), start=_utc(2026, 9, 27, 22, 30),
                   sport="Elliptical", zones=(60, 600, 1500, 300, 0))
    pinned = _pinned(world.send({"kind": "aerobic", "id": str(row.id), "scope": "session"}))
    assert format_aerobic_session(row) in pinned            # exactly the shared renderer's line
    assert "zones=[Z1=1min Z2=10min Z3=25min Z4=5min]" in pinned
    assert "(started 08:30 local)" in pinned                # local, not UTC
    assert "## Surrounding load" not in pinned


# ── G1 — context scope: the guaranteed window ────────────────────────────────

def test_context_scope_pins_the_prior_week_and_the_next_72_hours(world):
    db, me = world.db, world.me
    focus = _hevy(db, me, "hv-focus", FOCUS_START, title="FOCUS LOWER", exercises=LOWER_EXERCISES)
    # performed, inside [22 Sep .. 29 Sep]
    _aerobic(db, me, "polar_v4", date(2026, 9, 23), start=_utc(2026, 9, 22, 22, 0), sport="SIX-DAY-OLD ROW")
    _aerobic(db, me, "polar_v4", FOCUS_DAY, start=_utc(2026, 9, 29, 5, 0), sport="SAME-DAY PILATES")
    _hevy(db, me, "hv-prev", _utc(2026, 9, 26, 22, 0), title="PREV UPPER", exercises=[
        {"title": "Bench Press", "exercise_template_id": "B1", "notes": "",
         "sets": [{"type": "warmup", "weight_kg": 40, "reps": 8},
                  {"type": "normal", "weight_kg": 80, "reps": 5, "rpe": 8.5}]}])
    # performed, OUTSIDE the window
    _aerobic(db, me, "polar_v4", date(2026, 9, 21), start=_utc(2026, 9, 20, 22, 0), sport="EIGHT-DAY-OLD RIDE")
    _aerobic(db, me, "polar_v4", date(2026, 10, 2), start=_utc(2026, 10, 1, 22, 0), sport="AFTER-THE-SESSION RUN")
    # a non-canonical twin of the same-day pilates (HC, no zones) must not appear twice
    _aerobic(db, me, "health_connect", FOCUS_DAY, start=_utc(2026, 9, 29, 5, 2), sport="SAME-DAY PILATES HC TWIN",
             zones=None, package="com.sec.android.app.shealth")
    # scheduled: weekday item next day (Wed 30 Sep), a dated one-off in the window, one outside (+4 days)
    _schedule(db, me, "physio", {"activity": "NEXT-DAY PHYSIO", "days": ["wednesday"], "hard": True,
                                 "expected_load": "none", "time_of_day": "morning"})
    _schedule(db, me, "swim", {"activity": "DATED SWIM", "event_date": "2026-10-02", "hard": False,
                               "expected_load": "light", "time_of_day": "unknown"})
    _schedule(db, me, "far", {"activity": "FOUR-DAYS-OUT CLASS", "event_date": "2026-10-03", "hard": False,
                              "expected_load": "light", "time_of_day": "evening"})
    _schedule(db, me, "same-day", {"activity": "SAME-DAY SCHEDULED", "days": ["tuesday"], "hard": False,
                                   "expected_load": "moderate", "time_of_day": "evening"})

    pinned = _pinned(world.send({"kind": "hevy", "id": "hv-focus", "scope": "context"}))

    assert "review of this session IN CONTEXT" in pinned
    assert "FOCUS LOWER" in pinned and "RPE 9" in pinned                       # the pinned session, full
    window = pinned.split("## Surrounding load")[1].split("## Scheduled next")[0]
    assert "SIX-DAY-OLD ROW" in window                                         # 6 days back — in
    assert "SAME-DAY PILATES" in window                                        # same local day — in
    assert "PREV UPPER" in window and "top 80kg × 5, peak RPE 8.5" in window  # compact Hevy rendering
    assert "EIGHT-DAY-OLD RIDE" not in window and "AFTER-THE-SESSION RUN" not in window
    assert "HC TWIN" not in window                                             # non-canonical twin: once only
    assert "FOCUS LOWER" not in window                                         # the session isn't its own context
    assert "Set 1" not in window                                               # compact, not set-by-set
    nxt = pinned.split("## Scheduled next")[1]
    assert "2026-09-30 (Wed): NEXT-DAY PHYSIO (hard) [morning]" in nxt         # next-day scheduled item
    assert "2026-10-02 (Fri): DATED SWIM (soft, light)" in nxt                 # dated one-off, soft included
    assert "FOUR-DAYS-OUT CLASS" not in nxt and "SAME-DAY SCHEDULED" not in nxt
    assert focus["title"] == "FOCUS LOWER"


def test_context_window_anchors_on_the_session_local_date_not_the_utc_date(world):
    """07:00 AEST on 29 Sep is 21:00 UTC on 28 Sep. The window is [22 Sep..29 Sep] and the schedule
    starts 30 Sep — a UTC anchor would shift both a day early."""
    db, me = world.db, world.me
    _hevy(db, me, "hv-focus", FOCUS_START, exercises=LOWER_EXERCISES[:1])
    _schedule(db, me, "a", {"activity": "ON-THE-29TH", "days": ["tuesday"], "hard": False,
                            "expected_load": "light", "time_of_day": "unknown"})
    _schedule(db, me, "b", {"activity": "ON-THE-2ND", "days": ["friday"], "hard": False,
                            "expected_load": "light", "time_of_day": "unknown"})
    pinned = _pinned(world.send({"kind": "hevy", "id": "hv-focus", "scope": "context"}))
    assert "up to and including 2026-09-29" in pinned
    assert "2026-09-30 to 2026-10-02" in pinned
    nxt = pinned.split("## Scheduled next")[1]
    assert "ON-THE-2ND" in nxt and "ON-THE-29TH" not in nxt


def test_context_scope_with_nothing_around_says_so_explicitly(world):
    row = _aerobic(world.db, world.me, "polar_v4", FOCUS_DAY, start=_utc(2026, 9, 29, 5, 0))
    pinned = _pinned(world.send({"kind": "aerobic", "id": str(row.id), "scope": "context"}))
    assert "None recorded in this window." in pinned
    assert "No schedule items fall on these days." in pinned


# ── G1 — graceful on unknown / foreign ids; no focus = unchanged ─────────────

@pytest.mark.parametrize("kind,ident", [("hevy", "no-such-workout"), ("aerobic", "999999"), ("aerobic", "not-a-number")])
def test_unknown_id_is_graceful_and_the_turn_proceeds(world, kind, ident):
    pinned = _pinned(world.send({"kind": kind, "id": ident, "scope": "session"}))
    assert "was not found" in pinned and "do not describe or invent a session" in pinned


def test_another_users_session_is_not_found_and_never_leaks(world):
    _hevy(world.db, world.other, "hv-theirs", FOCUS_START, title="THEIR SECRET LOWER", exercises=LOWER_EXERCISES)
    row = _aerobic(world.db, world.other, "polar_v4", FOCUS_DAY, start=_utc(2026, 9, 29, 5, 0), sport="THEIR RUN")
    for focus in ({"kind": "hevy", "id": "hv-theirs", "scope": "context"},
                  {"kind": "aerobic", "id": str(row.id), "scope": "context"}):
        prompt = world.send(focus)
        assert "was not found" in _pinned(prompt)
        assert "THEIR SECRET LOWER" not in prompt and "THEIR RUN" not in prompt


def test_no_focus_leaves_the_context_unchanged(world):
    """No `focus_session` → no pinned block, and the standing prompt is byte-identical to the one
    sent WITH a focus minus the appended block (the pin is appended, never woven in)."""
    _hevy(world.db, world.me, "hv-1", FOCUS_START, exercises=LOWER_EXERCISES)
    without = world.send()
    assert "Session under review" not in without
    with_focus = world.send({"kind": "hevy", "id": "hv-1", "scope": "session"})
    assert with_focus.startswith(without + "\n\n## Session under review")
    assert world.send(None) == without


@pytest.mark.parametrize("bad", [
    {"kind": "strava", "id": "1", "scope": "session"},
    {"kind": "hevy", "id": "1", "scope": "everything"},
    {"kind": "hevy", "id": "", "scope": "session"},
])
def test_malformed_focus_is_rejected_by_the_schema(world, bad):
    r = world.client.post("/chat", json={"message": "x", "conversation_history": [], "focus_session": bad})
    assert r.status_code == 422


def test_an_unexpected_loader_failure_still_lets_the_turn_proceed(world, monkeypatch):
    import session_focus

    def _boom(*_a, **_k):
        raise RuntimeError("db down")
    monkeypatch.setattr(session_focus, "_load_hevy", _boom)
    pinned = _pinned(world.send({"kind": "hevy", "id": "x", "scope": "session"}))
    assert "loading it failed on the server" in pinned


# ── A4 — session_analysis entries do not reach chat context ──────────────────

def test_session_analysis_entries_do_not_reach_the_chat_prompt(world):
    """Established for Brief A A4: no section of the chat prompt renders a `session_analysis` knowledge
    entry (the renderers filter by type, and this type has no renderer). So the client's
    /health/analyse-session call fed nothing the model reads; removing it from the feedback path loses
    no context. If a renderer for this type is ever added this test fails and A4 must be re-decided."""
    world.db.add(models.UserKnowledgeEntry(
        user_id=world.me.id, type="session_analysis", key="session_hv-1", source="system", active=True,
        value={"workout_id": "hv-1", "workout_title": "SENTINEL-ANALYSIS-TITLE", "total_volume_kg": 987654,
               "top_1rm": {"Squat": 123456}}))
    world.db.commit()
    prompt = world.send()
    assert "SENTINEL-ANALYSIS-TITLE" not in prompt and "987654" not in prompt and "123456" not in prompt


# ── G2 — MCP get_training_sessions is byte-identical across the A2 extraction ─

def _legacy_line(s):
    """The per-session rendering exactly as it stood inline in `mcp_server.get_training_sessions`
    before A2 (frozen copy — the reference the extraction must reproduce)."""
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
    return (f"{s.session_date} [{s.source}] {s.sport_name or 'unknown'}: "
            f"{dur_min} HR={avg_hr}/{max_hr} dist=— cal={cal}{zone_summary}")


def test_mcp_get_training_sessions_output_is_byte_identical(world, monkeypatch):
    import mcp_server

    today = datetime.now(timezone.utc).date()
    db, me = world.db, world.me
    rows = [
        _aerobic(db, me, "polar_v4", today - timedelta(days=1), sport="Elliptical", zones=(60, 600, 1500, 300, 0)),
        _aerobic(db, me, "polar_flow_export", today - timedelta(days=2), sport=None, minutes=0, hr=None,
                 cal=None, zones=None),
        _aerobic(db, me, "polar_v4", today - timedelta(days=3), sport="Row", zones=(0, 0, 0, 0, 0), hr=(0, 0)),
        _aerobic(db, me, "polar_v4", today - timedelta(days=4), sport="Ride", zones=(29, 31, 89, 0, 0), minutes=61.6),
    ]
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: me.id)

    out = mcp_server.get_training_sessions(days=28)

    ordered = sorted(rows, key=lambda s: s.session_date, reverse=True)
    for s in ordered:
        assert _legacy_line(s) in out.split("\n")
        assert format_aerobic_session(s) == _legacy_line(s)
    body = [ln for ln in out.split("\n") if ln.startswith(str(today.year))]
    assert body == [_legacy_line(s) for s in ordered]
