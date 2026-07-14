"""LIVE PROBE — the model-facing contract for routine provisioning (#83).

Operator-run. NOT a test, NOT in CI: it calls the real Anthropic API (costs
money) and the model is non-deterministic, so it can never be a pass/fail gate.
It is a MEASUREMENT instrument. `pytest` does not collect it (no `test_` prefix,
not under `tests/`).

Why it exists: every other test in this repo fakes the model — and the model is
where #82 failed. Provisioning is a contract stated in English in
`_section_routine_creation` and honoured (or not) by a model at runtime. Nothing
else here exercises that. This does.

What it measures: for a movement OUTSIDE recent history the model has no id for,
what TITLE does it emit, does that title resolve, and — given the candidate
warning (#83) — does it recover on the next turn?

    python backend/probe_resolver.py <user_id>              # real catalogue (Railway)
    python backend/probe_resolver.py <user_id> --synthetic  # in-memory 10-row slice

Safety, non-negotiable:
  * FakeHevyClient — `create_routine` is never called against Hevy. Nothing can
    be written to a real account.
  * READ-ONLY on the DB: no db.add, no db.commit (the --synthetic path builds a
    throwaway in-memory SQLite; it never touches the configured DB).
  * The API key is NEVER printed, logged, or echoed — presence is checked, the
    value is not materialised.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from typing import Any

import anthropic
import pytz
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import context_builder
import database
import models  # noqa: F401 — registers tables on Base.metadata
from current_state import current_state as compute_current_state
from hevy_templates import resolve_exercise, suggest_candidates
from routers import chat as chat_mod

AEST = pytz.timezone("Australia/Brisbane")
_FIXED_NOW = AEST.localize(datetime(2026, 7, 14, 9, 30, 0))

_BLOCK_RE = re.compile(
    r"<hevy_create_routine>\s*(\{.*?\})\s*</hevy_create_routine>", re.S
)


class EmptyCatalogueError(Exception):
    """`hevy_exercise_templates` is empty — a PRECONDITION failure, not a result
    (mirrors #77). Every title would miss and the probe would report a 0%
    hit-rate over an empty catalogue, which is a lie. Run
    `sync_hevy_templates.py` first, or pass --synthetic."""


class MissingApiKeyError(Exception):
    """No ANTHROPIC_API_KEY. Presence only — the value is never read into output."""


# A prod-real slice (2026-07-14). Only used by --synthetic, for machines with no
# populated catalogue. The Leg Curl pair is deliberate: it is what proves
# candidate cardinality is an artifact of catalogue SIZE (#83).
_SYNTHETIC_CATALOGUE = [
    ("B5D3A742", "Bulgarian Split Squat (Dumbbell)"),
    ("A1B2C3D4", "Bulgarian Split Squat (Barbell)"),
    ("E5F6A7B8", "Split Squat (Dumbbell)"),
    ("B8127AD1", "Lying Leg Curl (Machine)"),
    ("B8127AD2", "Seated Leg Curl (Machine)"),
    ("75A4F6C4", "Leg Extension (Machine)"),
    ("937292AB", "Single Leg Romanian Deadlift (Dumbbell)"),
    ("C7973E0E", "Leg Press (Machine)"),
    ("B923B230", "Deadlift (Trap bar)"),
    ("68CE0B9B", "Hip Thrust (Machine)"),
]

# Rendered as "recent history" so the model HAS ids for these. Everything the
# probes ask for is deliberately absent, forcing the #82 title path.
_HISTORY_TITLES = ["Leg Press (Machine)", "Deadlift (Trap bar)", "Hip Thrust (Machine)"]


def _require_api_key() -> str:
    """Presence check. The value is returned to the SDK and never printed."""
    load_dotenv()
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise MissingApiKeyError(
            "ANTHROPIC_API_KEY is not set — the probe measures a live model and "
            "cannot run without it."
        )
    return key


def _synthetic_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for tid, title in _SYNTHETIC_CATALOGUE:
        db.add(models.HevyExerciseTemplate(
            id=tid, title=title, type="weight_reps", is_custom=False, owner_user_id=None,
        ))
    user = models.User(email="probe@example.com", hashed_password="x", full_name="Probe")
    db.add(user)
    db.commit()
    db.refresh(user)
    # One knowledge entry so `_section_onboarding_interview` does NOT fire. Without
    # it the model spends its turns on profile questions and the probe measures
    # onboarding instead of the resolver contract — observed, not theorised.
    db.add(models.UserKnowledgeEntry(
        user_id=user.id, type="preference", key="device_profile",
        value={"hrv_source": "galaxy_ring"}, source="chat", active=True,
    ))
    db.commit()
    return db


def _catalogue_size(db) -> int:
    return db.query(models.HevyExerciseTemplate).count()


def _history_rows(db, user_id: int) -> list[tuple[str, str]]:
    """Real catalogue rows for the movements we render as recent history."""
    Template = models.HevyExerciseTemplate
    rows = db.execute(
        select(Template.id, Template.title).where(Template.title.in_(_HISTORY_TITLES))
    ).all()
    return [(r[0], r[1]) for r in rows]


def _build_system_prompt(db, user) -> tuple[str, dict[str, Any]]:
    hevy_data = {
        "workout_count": 45,
        "recent_workouts": [{
            "title": "Lower A",
            "start_time": "2026-07-10T08:00:00Z",
            "end_time": "2026-07-10T09:00:00Z",
            "exercises": [
                {"exercise_template_id": tid, "title": title,
                 "sets": [{"type": "normal", "weight_kg": 60, "reps": 8}]}
                for tid, title in _history_rows(db, user.id)
            ],
        }],
    }
    chat_mod._annotate_canonical_titles(hevy_data, db)
    state = compute_current_state(user.id, db, today=_FIXED_NOW.date())
    context_builder._now_aest = lambda: _FIXED_NOW
    prompt = context_builder.build_system_prompt(
        user=user, connected_integrations=["hevy"], state=state, hevy_data=hevy_data,
        knowledge_entries=None, today_checkin=None, health_connect_records=None,
        samsung_hrv=None, daily_record=None, engine_selection=None,
    )
    return prompt, hevy_data


class FakeHevyClient:
    """Nothing reaches Hevy. A real routine is never created."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_routine(self, title, exercises, folder_id=None):
        self.calls.append({"title": title, "exercises": exercises})
        return {"routine": {"id": "probe-fake"}}


def _ascii(s: str) -> str:
    """Windows consoles are cp1252; the action strings carry emoji."""
    return s.encode("ascii", "replace").decode("ascii")


def _turn(client, system, messages, db, user_id):
    """One faithful round-trip.

    MIRRORS routers/chat.py:529-540 — model reply, then action processing, then
    the actions appended to the reply. That append is what the frontend stores as
    the assistant message (ChatPanel.jsx:82) and echoes back as history
    (ChatPanel.jsx:77-80), so the model reads its own failure next turn. If the
    probe appended the RAW reply instead, turn 2 would never see the candidate
    warning and any "it recovered" result would be fiction.
    """
    resp = client.messages.create(
        model=chat_mod.MODEL, max_tokens=1500, system=system, messages=messages
    )
    raw = "".join(b.text for b in resp.content if b.type == "text")
    fake = FakeHevyClient()
    cleaned, actions = asyncio.run(
        chat_mod._process_routine_actions(raw, fake, user_id, db)
    )
    stored = cleaned + ("\n\n" + "\n".join(actions) if actions else "")
    return raw, stored, actions, fake


def _report_block(raw: str, db, user_id: int) -> list[dict]:
    m = _BLOCK_RE.search(raw)
    if not m:
        # No block is a RESULT, not a non-event: the model may be asking the user
        # to disambiguate rather than guessing — which is the #83 design working.
        # Show what it said, or the operator cannot tell refusal from confusion.
        print("   (no <hevy_create_routine> block emitted this turn — model said:)")
        snippet = " ".join(raw.split())[:320]
        print(f"     \"{_ascii(snippet)}...\"")
        return []
    try:
        payload = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        print(f"   (block emitted but unparseable: {exc})")
        return []

    exercises = payload.get("exercises", [])
    for ex in exercises:
        tid, title = ex.get("exercise_template_id"), ex.get("title")
        if tid:
            print(f"   [ID ]  {tid}")
            continue
        got = resolve_exercise(db, title, user_id)
        verdict = f"RESOLVED -> {got}" if got else "*** MISS ***"
        print(f"   [TTL]  {title!r}  {verdict}")
        if not got:
            cands = [t for _, t in suggest_candidates(db, title, user_id)]
            print(f"          candidates: {cands or '(none)'}")
    return exercises


def run_probe(label: str, turns: list[str], db, user, system) -> None:
    client = anthropic.Anthropic(api_key=_require_api_key())
    print(f"\n{'=' * 72}\nPROBE: {label}\n{'=' * 72}")

    messages: list[dict[str, str]] = []
    for i, text in enumerate(turns, start=1):
        messages.append({"role": "user", "content": text})
        raw, stored, actions, fake = _turn(client, system, messages, db, user.id)
        messages.append({"role": "assistant", "content": stored})

        print(f"\n-- turn {i} --")
        _report_block(raw, db, user.id)
        print(f"   create_routine called: {len(fake.calls)}")
        for a in actions:
            print(f"   action -> {_ascii(a)}")


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print("usage: python backend/probe_resolver.py <user_id> [--synthetic]")
        return 2
    user_id = int(argv[0])
    synthetic = "--synthetic" in argv

    _require_api_key()  # fail before spending a round-trip

    if synthetic:
        db = _synthetic_db()
        user = db.query(models.User).first()
    else:
        from database import SessionLocal
        db = SessionLocal()
        user = db.get(models.User, user_id)
        if user is None:
            print(f"No user {user_id}.")
            return 1

    try:
        size = _catalogue_size(db)
        if not size:
            raise EmptyCatalogueError(
                "hevy_exercise_templates is empty — run sync_hevy_templates.py, "
                "or pass --synthetic for an in-memory slice."
            )
        print(f"catalogue: {size} templates ({'SYNTHETIC' if synthetic else 'live DB'})")
        if synthetic:
            print("NOTE: a 10-row slice flatters candidate uniqueness. Cardinality "
                  "is an artifact of catalogue size (#83) — trust the live run.")

        system, hevy_data = _build_system_prompt(db, user)
        print("\n--- history rendered to the model ---")
        print(_ascii(context_builder._section_hevy(45, hevy_data["recent_workouts"], _FIXED_NOW))[:500])

        # PROBE 1 — movement outside history. Forces a guessed title. Turn 3 tests
        # whether the candidate warning (#83) closes the loop.
        run_probe(
            "1 — out-of-history movement (forces a guessed title)",
            ["Build me a lower body routine with bulgarian split squats, leg press, "
             "and hip thrusts. 3 sets of 8 each at 60kg.",
             "Yes, go ahead and create it.",
             "Please try again."],
            db, user, system,
        )

        # PROBE 3 — generality: is the miss systematic across movements?
        run_probe(
            "3 — generality: three other out-of-history movements",
            ["Add leg curls, leg extensions, and single leg romanian deadlifts to a "
             "routine. 3 sets of 10 each at 20kg.",
             "Yes, go ahead and create it.",
             "Please try again."],
            db, user, system,
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
