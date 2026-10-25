"""Context-bundle PR1 (a–g): the system prompt's precedence fixes after the 7 Oct incident, where the in-app
/chat held the live phase in its prompt and followed a stale legacy note and a stale plan of record instead.

  (a) the authoritative state header opens the prompt: date, open phase, folder, probe posture, the
      precedence instruction
  (b) the plan of record is STALE when revised before the open phase was entered
  (c) the legacy knowledge rows render AFTER every live section, under a legacy header, dated per row
  (d) a hevy.com/workout/<uuid> link auto-focuses the session when none is pinned; a workout missing from
      `hevy_workouts` is fetched live by id (faked at the TRANSPORT layer, #166)
  (e) the focus block carries same-day aerobic, the previous two same-routine workouts and constraint flags
  (f) the derived-arithmetic instruction line is in the header
  (g) each Anthropic call in a /chat turn logs input/output tokens to stdout

Fixtures are synthetic placeholders.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import context_builder
import models
import session_focus
from auth import get_current_user
from current_state import CurrentState
from database import get_db
from routers import chat as chat_router

AEST = context_builder.AEST
NOW = datetime(2026, 10, 26, 12, 0, tzinfo=AEST)


class _U:
    full_name = "Bundle Tester"
    email = "bundle@example.com"


PHASE = {
    "id": 1, "label": "Aerobic base", "intent": "rebuild", "probe_posture": "held",
    "entered_on": "2026-10-01", "review_on": "2026-11-16", "review_due": False,
}


def _prompt(*, phase=PHASE, plan=None, phase_folders=None, hevy_routines=None, legacy=None):
    state = CurrentState(training_phase=phase, training_plan=plan, phase_folders=phase_folders,
                         resolver_position=None)
    return context_builder.build_system_prompt(
        _U(), [], state, knowledge_entries=legacy, hevy_routines=hevy_routines,
    )


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    monkeypatch.setattr(context_builder, "_now_aest", lambda: NOW)


# ── (a) + (f) the authoritative state header ─────────────────────────────────

def test_a_the_prompt_opens_with_the_state_header_naming_date_phase_and_posture():
    prompt = _prompt()
    assert prompt.startswith(context_builder.STATE_HEADER_HEADING)
    header = prompt.split("\n\n")[0]
    assert "Today: Monday, 26 October 2026 (AEST)" in header
    assert "Open phase: Aerobic base — entered 2026-10-01, review on 2026-11-16." in header
    assert "Probe posture: held." in header
    assert "review is DUE" not in header


def test_a_header_flags_a_due_review_and_a_missing_phase():
    assert "review is DUE" in _prompt(phase={**PHASE, "review_due": True}).split("\n\n")[0]
    baseline = _prompt(phase=None).split("\n\n")[0]
    assert "Open phase: none (baseline" in baseline
    assert "Hevy folder" not in baseline


def test_a_header_names_the_declared_folder_by_name_and_id_when_the_folder_list_is_to_hand():
    routines = {"routines": [], "folders": [{"id": 3789956, "title": "Aerobic base"}]}
    header = _prompt(phase_folders={"Aerobic base": 3789956}, hevy_routines=routines).split("\n\n")[0]
    assert "Hevy folder for this phase: Aerobic base (id 3789956)." in header


def test_a_header_falls_back_to_the_bare_id_then_to_none_declared():
    assert "Hevy folder for this phase: id 3789956." in _prompt(
        phase_folders={"Aerobic base": 3789956}).split("\n\n")[0]
    assert "Hevy folder for this phase: none declared." in _prompt(
        phase_folders={"Some other phase": 1}).split("\n\n")[0]


def test_a_header_carries_the_precedence_instruction_once_and_f_the_arithmetic_line():
    prompt = _prompt()
    header = prompt.split("\n\n")[0]
    assert "outrank the Plan of Record and the legacy notes" in header
    assert "name the conflict" in header and "do not resolve it silently" in header
    assert prompt.count("outrank the Plan of Record") == 1
    assert "Derived arithmetic (pace, effective load, unit conversions) is always shown with its inputs" in header


# ── (b) plan-of-record staleness: revised before the open phase was entered ──

def _plan(revised_on):
    return {"macro": "MACRO-TOKEN base then build.", "revised_on": revised_on, "revised_by": "coach"}


def test_b_stale_when_revised_before_the_open_phase_was_entered_even_with_no_review_due():
    reason = context_builder.plan_of_record_stale_reason(_plan("2026-09-30"), PHASE)
    assert reason == context_builder.PLAN_STALE_PHASE_ENTERED
    assert context_builder.plan_of_record_stale(_plan("2026-09-30"), PHASE) is True
    # revised ON the entry day is not before it
    assert context_builder.plan_of_record_stale(_plan("2026-10-01"), PHASE) is False
    assert context_builder.plan_of_record_stale(_plan("2026-10-20"), PHASE) is False


def test_b_the_existing_review_rule_still_applies_and_keeps_its_wording():
    phase = {**PHASE, "entered_on": "2026-08-01", "review_on": "2026-09-01", "review_due": True}
    assert context_builder.plan_of_record_stale_reason(_plan("2026-08-15"), phase) == context_builder.PLAN_STALE_REVIEW
    out = context_builder._section_training_plan(_plan("2026-08-15"), phase)
    assert "STALE — plan not revised since before the last phase review" in out


def test_b_unparseable_or_absent_inputs_are_not_stale():
    assert context_builder.plan_of_record_stale(_plan("nonsense"), PHASE) is False
    assert context_builder.plan_of_record_stale(_plan("2026-09-30"), None) is False
    assert context_builder.plan_of_record_stale(None, PHASE) is False
    # an unparseable entered_on drops only that rule
    assert context_builder.plan_of_record_stale(_plan("2026-09-30"), {**PHASE, "entered_on": "x"}) is False


def test_b_the_chat_plan_section_names_the_phase_and_date_in_the_stale_line():
    out = context_builder._section_training_plan(_plan("2026-09-30"), PHASE)
    assert "STALE — plan last revised before the open phase (Aerobic base) was entered on 2026-10-01" in out
    assert "MACRO-TOKEN" in out                       # shown as stale, never silently dropped
    assert "STALE" not in context_builder._section_training_plan(_plan("2026-10-05"), PHASE)


# ── (c) legacy knowledge: after live state, marked, dated ────────────────────

def _legacy(content, *, updated, category="Training Background", created=None):
    return SimpleNamespace(category=category, content=content, updated_at=updated,
                           created_at=created or updated)


def test_c_legacy_notes_render_after_every_live_section_under_the_legacy_header():
    legacy = [_legacy("LEGACY-TOKEN decompression week", updated=datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc))]
    routines = {"routines": [{"id": "r1", "title": "R1", "folder_id": 1}], "folders": [{"id": 1, "title": "F"}]}
    prompt = _prompt(plan=_plan("2026-10-05"), phase_folders={"Aerobic base": 1}, hevy_routines=routines,
                     legacy=legacy)
    at = prompt.index(context_builder.LEGACY_NOTES_HEADING)
    for live in ("## Authoritative state", "## Plan of Record", "## Training Phase", "## Hevy routines"):
        assert prompt.index(live) < at, live
    assert "## Athlete Knowledge Base" not in prompt
    legacy_block = prompt[at:]
    assert "superseded by the live sections above" in legacy_block.split("\n")[0]
    assert "the live section wins" in legacy_block
    assert "- [2026-09-12] LEGACY-TOKEN decompression week" in legacy_block   # verbatim content, dated


def test_c_row_date_is_the_aest_day_falls_back_to_created_and_is_omitted_when_absent():
    # 2026-09-11 20:00 UTC is 2026-09-12 06:00 in Brisbane
    late = _legacy("A", updated=datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc))
    assert "- [2026-09-12] A" in context_builder._section_knowledge([late])
    created_only = SimpleNamespace(category="Goals", content="B", updated_at=None,
                                   created_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc))
    assert "- [2026-08-01] B" in context_builder._section_knowledge([created_only])
    assert "- C\n" + "" in context_builder._section_knowledge([{"category": "Goals", "content": "C"}]) + "\n"


def test_c_no_legacy_rows_renders_nothing():
    assert context_builder._section_knowledge([]) == ""
    assert context_builder.LEGACY_NOTES_HEADING not in _prompt(legacy=None)


# ── the chat world: (d) (e) (g) ──────────────────────────────────────────────

class _Usage:
    def __init__(self, i, o):
        self.input_tokens, self.output_tokens = i, o


class _FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Draft.")],
                               stop_reason="end_turn", usage=_Usage(1234, 56))


@pytest.fixture
def world(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    me = models.User(email="me@example.com", hashed_password="x")
    other = models.User(email="other@example.com", hashed_password="x")
    db_session.add_all([me, other])
    db_session.commit()
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: me
    client = TestClient(app)
    fake = SimpleNamespace(messages=_FakeMessages())
    monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)

    def send(message="hello", focus=None):
        body = {"message": message, "conversation_history": []}
        if focus is not None:
            body["focus_session"] = focus
        r = client.post("/chat", json=body)
        assert r.status_code == 200, r.text
        return fake.messages.calls[-1]["system"]

    return SimpleNamespace(db=db_session, me=me, other=other, send=send, monkeypatch=monkeypatch, fake=fake)


def _connect_hevy(world, live=None, calls=None):
    """Hevy connected; the standing history empty; `HevyClient.get_workout` faked at the transport layer."""
    world.db.add(models.UserIntegration(user_id=world.me.id, provider="hevy", api_key_encrypted="enc"))
    world.db.commit()

    async def _gather(_key):
        return {"workout_count": 0, "recent_workouts": []}

    async def _routines(_client, _uid):
        return None

    class _Client:
        def __init__(self, _key):
            pass

        async def get_workout(self, wid):
            if calls is not None:
                calls.append(wid)
            if live is None:
                raise RuntimeError("404")
            return live

    m = world.monkeypatch
    m.setattr(chat_router, "decrypt", lambda _v: "k")
    m.setattr(chat_router, "_gather_hevy_context", _gather)
    m.setattr(chat_router.hevy_routine_cache, "get_routines_cached", _routines)
    m.setattr(chat_router, "HevyClient", _Client)


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def _hevy(db, user, hevy_id, start, *, title="Lower", exercises=None, routine_id=None):
    raw = {"id": hevy_id, "title": title, "start_time": start.isoformat(),
           "end_time": (start + timedelta(minutes=60)).isoformat(), "exercises": exercises or []}
    if routine_id:
        raw["routine_id"] = routine_id
    db.add(models.HevyWorkout(hevy_id=hevy_id, user_id=user.id, start_time=start,
                              end_time=start + timedelta(minutes=60), title=title, raw=raw))
    db.commit()
    return raw


def _aerobic(db, user, day, *, start, sport="Pilates", minutes=45, hr=112, source="polar_v4", sid=None):
    row = models.AerobicSession(
        user_id=user.id, source=source, source_session_id=sid or f"{source}-{day}-{sport}", session_date=day,
        start_time=start, stop_time=start + timedelta(minutes=minutes), sport_name=sport,
        duration_minutes=minutes, hr_avg=hr, hr_max=150, z1_seconds=0, z2_seconds=600, z3_seconds=0,
        z4_seconds=0, z5_seconds=0)
    db.add(row)
    db.commit()
    return row


def _pinned(prompt):
    assert "## Session under review" in prompt
    return prompt[prompt.index("## Session under review"):]


UUID = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"
LIVE = {"id": UUID, "title": "LIVE-FETCHED SESSION", "start_time": "2026-10-25T21:00:00+00:00",
        "end_time": "2026-10-25T22:00:00+00:00", "routine_id": "RT-1",
        "exercises": [{"title": "Face Pull", "exercise_template_id": "T9", "notes": "",
                       "sets": [{"type": "normal", "weight_kg": 9, "reps": 12}]}]}


# ── (d) share-URL auto-focus ──────────────────────────────────────────────────

@pytest.mark.parametrize("msg, expected", [
    (f"review https://hevy.com/workout/{UUID} please", UUID),
    (f"HTTPS://WWW.HEVY.COM/WORKOUT/{UUID.upper()}?x=1", UUID),
    ("https://hevy.com/workout/not-a-uuid", None),
    ("no link here", None),
    ("", None),
])
def test_d_share_url_is_detected_as_a_session_scope_hevy_focus(msg, expected):
    focus = session_focus.focus_from_share_url(msg)
    if expected is None:
        assert focus is None
    else:
        assert (focus.kind, focus.id, focus.scope) == ("hevy", expected, "session")


def test_d_a_share_link_in_the_message_pins_the_stored_session_with_no_focus_sent(world):
    _hevy(world.db, world.me, UUID, _utc(2026, 10, 25, 21), title="STORED SESSION")
    prompt = world.send(f"how did this go? https://hevy.com/workout/{UUID}")
    assert "STORED SESSION" in _pinned(prompt)
    assert "review of THIS session's execution" in _pinned(prompt)      # scope=session


def test_d_a_pinned_focus_wins_over_a_link_in_the_message(world):
    _hevy(world.db, world.me, UUID, _utc(2026, 10, 25, 21), title="LINKED SESSION")
    _hevy(world.db, world.me, "hv-pinned", _utc(2026, 10, 20, 21), title="PINNED SESSION")
    pinned = _pinned(world.send(f"https://hevy.com/workout/{UUID}",
                                focus={"kind": "hevy", "id": "hv-pinned", "scope": "session"}))
    assert "PINNED SESSION" in pinned and "LINKED SESSION" not in pinned


def test_d_a_workout_missing_locally_is_fetched_live_by_id_and_rendered(world):
    calls = []
    _connect_hevy(world, live=LIVE, calls=calls)
    pinned = _pinned(world.send(f"https://hevy.com/workout/{UUID}"))
    assert calls == [UUID]
    assert "LIVE-FETCHED SESSION" in pinned and "Face Pull" in pinned
    assert "was not found" not in pinned


def test_d_the_live_fallback_also_serves_a_button_pinned_focus(world):
    calls = []
    _connect_hevy(world, live=LIVE, calls=calls)
    pinned = _pinned(world.send("review", focus={"kind": "hevy", "id": UUID, "scope": "session"}))
    assert calls == [UUID] and "LIVE-FETCHED SESSION" in pinned


def test_d_a_stored_workout_is_not_fetched_live(world):
    calls = []
    _connect_hevy(world, live=LIVE, calls=calls)
    _hevy(world.db, world.me, UUID, _utc(2026, 10, 25, 21), title="STORED SESSION")
    pinned = _pinned(world.send(f"https://hevy.com/workout/{UUID}"))
    assert calls == [] and "STORED SESSION" in pinned and "LIVE-FETCHED" not in pinned


def test_d_a_failed_live_fetch_says_not_found_and_the_turn_proceeds(world):
    _connect_hevy(world, live=None)                       # get_workout raises
    pinned = _pinned(world.send(f"https://hevy.com/workout/{UUID}"))
    assert "was not found" in pinned and "do not describe or invent a session" in pinned


def test_d_no_hevy_integration_means_no_live_fetch_and_a_clean_not_found(world):
    pinned = _pinned(world.send(f"https://hevy.com/workout/{UUID}"))
    assert "was not found" in pinned


def test_d_another_users_stored_workout_is_not_served(world):
    _hevy(world.db, world.other, UUID, _utc(2026, 10, 25, 21), title="FOREIGN SESSION")
    pinned = _pinned(world.send(f"https://hevy.com/workout/{UUID}"))
    assert "FOREIGN SESSION" not in pinned and "was not found" in pinned


def test_d_get_workout_unwraps_hevys_wrapper_and_is_timeout_bounded(monkeypatch):
    import asyncio
    import httpx
    from connectors import hevy as hevy_mod

    seen = {}

    class _Resp:
        status_code = 200
        is_error = False
        text = ""

        def json(self):
            return {"workout": {"id": "w1", "title": "T"}}

    class _AC:
        def __init__(self, **kw):
            seen["timeout"] = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            seen["url"] = url
            return _Resp()

    monkeypatch.setattr(hevy_mod.httpx, "AsyncClient", _AC)
    out = asyncio.run(hevy_mod.HevyClient("k").get_workout("w1"))
    assert out == {"id": "w1", "title": "T"}
    assert seen["url"].endswith("/workouts/w1") and isinstance(seen["timeout"], httpx.Timeout)
    # an id is one path segment: a client-named focus id cannot reach another endpoint
    asyncio.run(hevy_mod.HevyClient("k").get_workout("../routines/x?y=1"))
    assert seen["url"].endswith("/workouts/..%2Froutines%2Fx%3Fy%3D1")


# ── (e) focus extras ──────────────────────────────────────────────────────────

FOCUS_START = _utc(2026, 10, 25, 21)          # Mon 26 Oct 07:00 AEST
FOCUS_DAY = date(2026, 10, 26)


def _upper(title="Face Pull"):
    return [{"title": title, "exercise_template_id": "T1", "notes": "",
             "sets": [{"type": "normal", "weight_kg": 9, "reps": 12}]}]


def test_e_session_scope_lists_same_aest_day_canonical_aerobic_with_the_five_fields(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START, exercises=_upper())
    # 06:00 AEST the same local day == previous UTC day
    _aerobic(world.db, world.me, FOCUS_DAY, start=_utc(2026, 10, 25, 20), sport="Walk", minutes=30, hr=98)
    # previous / next local day: excluded
    _aerobic(world.db, world.me, date(2026, 10, 25), start=_utc(2026, 10, 24, 22), sport="PREV-DAY RIDE")
    _aerobic(world.db, world.me, date(2026, 10, 27), start=_utc(2026, 10, 26, 22), sport="NEXT-DAY RIDE")
    pinned = _pinned(world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "session"}))
    assert "## Same day — canonical aerobic sessions on 2026-10-26" in pinned
    assert "- Walk, start 06:00, 30 min, avg HR 98, source polar_v4" in pinned
    assert "PREV-DAY RIDE" not in pinned and "NEXT-DAY RIDE" not in pinned


def test_e_same_day_block_says_none_when_empty_and_leaves_out_the_focused_aerobic_session(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START)
    assert "None recorded on this day." in _pinned(
        world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "session"}))
    row = _aerobic(world.db, world.me, FOCUS_DAY, start=_utc(2026, 10, 25, 20), sport="FOCUSED WALK")
    _aerobic(world.db, world.me, FOCUS_DAY, start=_utc(2026, 10, 26, 3), sport="LATER PILATES")
    same_day = _pinned(world.send(focus={"kind": "aerobic", "id": str(row.id), "scope": "session"}))
    block = same_day.split("## Same day")[1]
    assert "LATER PILATES" in block and "FOCUSED WALK" not in block


def test_e_non_canonical_twins_are_not_listed_in_the_same_day_block(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START)
    _aerobic(world.db, world.me, FOCUS_DAY, start=_utc(2026, 10, 26, 3), sport="REAL PILATES", source="polar_v4")
    _aerobic(world.db, world.me, FOCUS_DAY, start=_utc(2026, 10, 26, 3, 2), sport="HC TWIN",
             source="health_connect", sid="hc1")
    block = _pinned(world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "session"})).split("## Same day")[1]
    assert "REAL PILATES" in block and "HC TWIN" not in block


def test_e_context_scope_does_not_repeat_the_same_day_block_the_window_already_carries(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START)
    _aerobic(world.db, world.me, FOCUS_DAY, start=_utc(2026, 10, 26, 3), sport="LATER PILATES")
    pinned = _pinned(world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "context"}))
    assert "## Same day" not in pinned and pinned.count("LATER PILATES") == 1


def test_e_previous_two_workouts_of_the_same_routine_newest_first_and_only_that_routine(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START, title="FOCUS", routine_id="RT-1", exercises=_upper())
    _hevy(world.db, world.me, "hv-a", _utc(2026, 10, 1, 21), title="OLDEST SAME", routine_id="RT-1")
    _hevy(world.db, world.me, "hv-b", _utc(2026, 10, 8, 21), title="MIDDLE SAME", routine_id="RT-1")
    _hevy(world.db, world.me, "hv-c", _utc(2026, 10, 15, 21), title="NEWEST SAME", routine_id="RT-1")
    _hevy(world.db, world.me, "hv-d", _utc(2026, 10, 20, 21), title="OTHER ROUTINE", routine_id="RT-2")
    _hevy(world.db, world.me, "hv-e", _utc(2026, 10, 27, 21), title="LATER SAME", routine_id="RT-1")  # after the focus
    pinned = _pinned(world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "session"}))
    block = pinned.split("## Previous 2 workouts of the same routine")[1].split("\n\n")[0]
    assert block.index("NEWEST SAME") < block.index("MIDDLE SAME")
    for absent in ("OLDEST SAME", "OTHER ROUTINE", "LATER SAME", "FOCUS"):
        assert absent not in block


def test_e_no_routine_id_means_no_routine_block_and_none_recorded_is_said(world):
    _hevy(world.db, world.me, "hv-n", FOCUS_START)
    assert "same routine" not in _pinned(world.send(focus={"kind": "hevy", "id": "hv-n", "scope": "session"}))
    _hevy(world.db, world.me, "hv-r", FOCUS_START + timedelta(days=1), routine_id="RT-9")
    assert "No earlier workout of this routine recorded." in _pinned(
        world.send(focus={"kind": "hevy", "id": "hv-r", "scope": "session"}))


def _constraint(db, user, key, text, *, status="confirmed", active=True, tier="advisory", detail=None):
    scope = {"tier": tier, "text": text} if tier == "advisory" else {"tier": "engine", "region_keys": ["shoulder_er"]}
    value = {"kind": "cap", "scope": scope, "exit": {"on_condition": "cleared by physio"},
             "review_by": "2026-12-01", "status": status, "asserted_by": "user"}
    if detail:
        value["detail"] = detail
    db.add(models.UserKnowledgeEntry(user_id=user.id, type="constraint", key=key, value=value,
                                     source="api", active=active))
    db.commit()


def test_e_a_confirmed_constraint_naming_a_session_exercise_is_flagged_inline_case_insensitively(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START, exercises=_upper("Face Pull"))
    _constraint(world.db, world.me, "constraint_shoulder_right_er_load_cap",
                "right shoulder ER loading — face pull, external rotation", detail="cap 9.5 kg")
    pinned = _pinned(world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "session"}))
    flags = pinned.split("## Constraint flags")[1]
    assert "names Face Pull in this session" in flags
    assert "[constraint_shoulder_right_er_load_cap]" in flags and "cap 9.5 kg" in flags
    assert "set by you" in flags                                   # authority travels with the flag


def test_e_constraint_flags_skip_unrelated_unconfirmed_inactive_engine_tier_and_substring_matches(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START, exercises=_upper("Face Pull") + _upper("Row"))
    _constraint(world.db, world.me, "c_unrelated", "left knee deep flexion")
    _constraint(world.db, world.me, "c_proposed", "face pull volume", status="proposed")
    _constraint(world.db, world.me, "c_inactive", "face pull volume", active=False)
    _constraint(world.db, world.me, "c_engine", "", tier="engine")
    _constraint(world.db, world.me, "c_substring", "interface pulley work")          # 'face pull' is not a whole phrase
    _constraint(world.db, world.me, "c_short_title", "rowing machine intervals")      # 'Row' < 4 chars: skipped
    pinned = _pinned(world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "session"}))
    assert "## Constraint flags" not in pinned


def test_e_flags_ride_in_context_scope_too_and_an_aerobic_focus_gets_none(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START, exercises=_upper("Face Pull"))
    _constraint(world.db, world.me, "c1", "face pull loading")
    assert "## Constraint flags" in _pinned(
        world.send(focus={"kind": "hevy", "id": "hv-f", "scope": "context"}))
    row = _aerobic(world.db, world.me, FOCUS_DAY, start=_utc(2026, 10, 25, 20))
    assert "## Constraint flags" not in _pinned(
        world.send(focus={"kind": "aerobic", "id": str(row.id), "scope": "session"}))


def test_e_the_focus_extras_are_absent_with_no_focus_and_the_prompt_is_otherwise_unchanged(world):
    _hevy(world.db, world.me, "hv-f", FOCUS_START, exercises=_upper())
    plain = world.send()
    assert "## Session under review" not in plain and "## Same day" not in plain


# ── (g) usage logging ─────────────────────────────────────────────────────────

def test_g_each_chat_turn_logs_input_and_output_tokens_to_stdout(world, capsys):
    prompt = world.send("hello")
    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("chat usage: call=main"))
    assert "input_tokens=1234" in line and "output_tokens=56" in line
    assert f"system_chars={len(prompt)}" in line


def test_g_a_response_without_usage_logs_n_a_and_never_raises(capsys):
    chat_router.log_usage("main", SimpleNamespace(content=[]), 10)
    assert "input_tokens=n/a output_tokens=n/a system_chars=10" in capsys.readouterr().out


def test_g_the_usage_line_carries_no_prompt_or_reply_text(world, capsys):
    world.send("MY-PRIVATE-MESSAGE")
    assert "MY-PRIVATE-MESSAGE" not in capsys.readouterr().out
