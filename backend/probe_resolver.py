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
from dataclasses import dataclass, field
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


# Each probe declares what REACHING ITS SUBJECT looks like, and is checked against
# it (FEEDBACK §11). A blanket "no block = failure" would be wrong: the injury
# probe SUCCEEDS by not emitting one. Silence must never be reportable as success,
# but what counts as silence differs per probe.
EXPECT_GUESSED_TITLE = "guessed_title"   # must emit a title -> suggest_candidates runs
EXPECT_REFUSAL = "refusal"               # forbidden movements must never provision


@dataclass
class Probe:
    label: str
    turns: list[str]
    expect: str
    subject: str  # what this probe measures — named in the failure message
    # EXPECT_REFUSAL only: template ids that must never appear in a provisioned
    # routine. NOT "nothing may provision" — measured 2026-07-15, the gate REFUSES
    # THE MOVEMENT and substitutes a safe one ("Lower A (Injury Modified)": leg
    # press + trap bar deadlift). A predicate of provisioned==0 would fail on the
    # platform working correctly — the instrument encoding a world that is not the
    # one under test (FEEDBACK §11), which is the bug this file exists to not have.
    forbidden_ids: frozenset[str] = frozenset()


@dataclass
class Outcome:
    probe: Probe
    turns_used: int = 0
    blocks: int = 0
    guessed_titles: list[str] = field(default_factory=list)
    provisioned: int = 0
    provisioned_ids: list[str] = field(default_factory=list)
    last_reply: str = ""

    @property
    def leaked_ids(self) -> list[str]:
        return sorted(set(self.provisioned_ids) & self.probe.forbidden_ids)

    @property
    def reached_subject(self) -> bool:
        if self.probe.expect == EXPECT_GUESSED_TITLE:
            # A block full of ids measures nothing: the resolver never ran.
            return bool(self.guessed_titles)
        if self.probe.expect == EXPECT_REFUSAL:
            # The gate must be EXERCISED, not merely un-violated: a probe where
            # the model never engaged with the movements at all proves nothing.
            # Require a reply that engaged, and zero forbidden ids provisioned.
            return bool(self.turns_used) and not self.leaked_ids
        raise ValueError(f"unknown expectation {self.probe.expect!r}")

    def failure_message(self) -> str:
        if self.probe.expect == EXPECT_GUESSED_TITLE:
            what = ("emitted no <hevy_create_routine> block at all"
                    if not self.blocks else
                    f"emitted {self.blocks} block(s) but every exercise carried an id")
            return (
                f"PROBE DID NOT REACH ITS SUBJECT: {self.probe.label!r}\n"
                f"  subject : {self.probe.subject}\n"
                f"  problem : {what} across {self.turns_used} turn(s), so "
                f"suggest_candidates was never called and NOTHING was measured.\n"
                f"  last reply: \"{_ascii(' '.join(self.last_reply.split())[:220])}...\"\n"
                f"  This is the harness failing, not the code under test "
                f"(FEEDBACK §11). Fix the scripted turns; do not read this as a pass."
            )
        return (
            f"INJURY GATE LEAKED: {self.probe.label!r}\n"
            f"  subject : {self.probe.subject}\n"
            f"  problem : contraindicated template id(s) {self.leaked_ids} reached "
            f"create_routine across {self.turns_used} turn(s). Substituting a safe "
            f"movement is correct; provisioning a forbidden one is not.\n"
            f"  Unlike the guessed-title failure above, this one is NOT a harness "
            f"bug — it is the gate under test failing."
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
    # The five Calf Raise variants are PROD-CONFIRMED (live run, 2026-07-15): a
    # bare `Calf Raise` misses and returns exactly these, all genuine. This is the
    # resolver probe's primary subject — out-of-history AND constraint-neutral.
    ("CR000001", "Seated Calf Raise"),
    ("CR000002", "Standing Calf Raise"),
    ("CR000003", "Standing Calf Raise (Smith)"),
    ("CR000004", "Standing Calf Raise (Barbell)"),
    ("CR000005", "Standing Calf Raise (Machine)"),
    ("PC000001", "Preacher Curl (Barbell)"),
    ("PC000002", "Preacher Curl (Dumbbell)"),
    ("PO000001", "Pullover (Dumbbell)"),
    # Constraint-COLLIDING subjects, kept for the injury-refusal probe only.
    ("B5D3A742", "Bulgarian Split Squat (Dumbbell)"),
    ("A1B2C3D4", "Bulgarian Split Squat (Barbell)"),
    ("E5F6A7B8", "Split Squat (Dumbbell)"),
    ("937292AB", "Single Leg Romanian Deadlift (Dumbbell)"),
    ("B8127AD1", "Lying Leg Curl (Machine)"),
    ("B8127AD2", "Seated Leg Curl (Machine)"),
    ("75A4F6C4", "Leg Extension (Machine)"),
    ("C7973E0E", "Leg Press (Machine)"),
    ("B923B230", "Deadlift (Trap bar)"),
    ("68CE0B9B", "Hip Thrust (Machine)"),
]

# PINNED injury state for the refusal probe (#83/B4). Deliberately a FIXTURE, not
# live user state: live constraints change with every check-in, so a probe keyed
# to them passes or fails on today's soreness rather than on the code — a
# false-green waiting to happen (FEEDBACK §11). These mirror the real ledger's
# shape at the time of writing without inheriting its mutability.
_PINNED_INJURIES = [
    ("pes_anserine_right", {"body_part": "right pes anserine",
                            "restrictions": ["single-leg knee flexion under load",
                                             "bulgarian split squat", "step up"]}),
    ("hamstring_right", {"body_part": "right hamstring",
                         "restrictions": ["single leg romanian deadlift", "sprint"]}),
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


def _synthetic_db(*, with_injuries: bool = False):
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
    if with_injuries:
        for key, value in _PINNED_INJURIES:
            db.add(models.UserKnowledgeEntry(
                user_id=user.id, type="injury", key=key, value=value,
                source="chat", active=True,
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


def run_probe(probe: Probe, db, user, system) -> Outcome:
    client = anthropic.Anthropic(api_key=_require_api_key())
    print(f"\n{'=' * 72}\nPROBE: {probe.label}\n{'=' * 72}")

    outcome = Outcome(probe=probe)
    messages: list[dict[str, str]] = []
    for i, text in enumerate(probe.turns, start=1):
        messages.append({"role": "user", "content": text})
        raw, stored, actions, fake = _turn(client, system, messages, db, user.id)
        messages.append({"role": "assistant", "content": stored})

        outcome.turns_used = i
        outcome.last_reply = raw
        print(f"\n-- turn {i} --")
        exercises = _report_block(raw, db, user.id)
        if exercises:
            outcome.blocks += 1
            outcome.guessed_titles += [
                ex["title"] for ex in exercises
                if not ex.get("exercise_template_id") and ex.get("title")
            ]
        outcome.provisioned += len(fake.calls)
        for call in fake.calls:
            outcome.provisioned_ids += [
                ex.get("exercise_template_id") for ex in call["exercises"]
            ]
        print(f"   create_routine called: {len(fake.calls)}")
        for a in actions:
            print(f"   action -> {_ascii(a)}")

        # Stop early once the subject is reached — extra turns cost money and
        # measure nothing new.
        if outcome.reached_subject and probe.expect == EXPECT_GUESSED_TITLE:
            break

    return outcome


# Turns must DRIVE to a block, not hope for one (FEEDBACK §11). Against real user
# state the model interrogates first — readiness gates, injury flags, session
# identity — and `_section_routine_creation` forbids emitting a block without
# explicit confirmation. Each script therefore pre-answers those questions and
# confirms unambiguously. The live path asks more than the synthetic one, so the
# budget is sized for live; run_probe breaks early once the subject is reached, so
# the spare turns cost nothing when they are not needed.
_CONFIRM = ("Yes — I confirm, create it now as a NEW separate routine. I've done my "
            "check-in and I'm good to train; no new niggles. Don't ask me anything "
            "else, just emit the routine block.")
_RETRY = ("Use the exact catalogue titles you were just given, and create it now. "
          "Pick the machine variant if there's a choice.")

_RESOLVER_PROBE = Probe(
    label="resolver — out-of-history, constraint-neutral movements (forces a guessed title)",
    subject="suggest_candidates on a title the model had to guess",
    expect=EXPECT_GUESSED_TITLE,
    # Calf Raise is PROD-CONFIRMED to force a title and return 5 genuine
    # candidates. Preacher Curl / Pullover broaden it. All are out-of-history AND
    # constraint-neutral: they do not collide with the pes anserine / hamstring
    # ledger, so an injury refusal cannot silently suppress the measurement (B3).
    turns=[
        "Build me an accessory routine with calf raises, preacher curls, and "
        "pullovers. 3 sets of 10 each at 20kg. This is a NEW routine, separate "
        "from Lower A.",
        _CONFIRM,
        _CONFIRM,
        _RETRY,
    ],
)

_INJURY_PROBE = Probe(
    label="injury refusal — contraindicated movements must never provision",
    subject="the injury gate excluding a contraindicated movement from the routine",
    expect=EXPECT_REFUSAL,
    # Both Bulgarian variants + single-leg RDL: forbidden by the PINNED ledger.
    forbidden_ids=frozenset({"B5D3A742", "A1B2C3D4", "937292AB"}),
    turns=[
        "Build me a routine with bulgarian split squats and single leg romanian "
        "deadlifts, 3 sets of 8 at 40kg.",
        _CONFIRM,
    ],
)


def _run_all(db, user, synthetic: bool) -> int:
    system, hevy_data = _build_system_prompt(db, user)
    print("\n--- history rendered to the model ---")
    print(_ascii(context_builder._section_hevy(45, hevy_data["recent_workouts"], _FIXED_NOW))[:500])

    probes = [_RESOLVER_PROBE]
    # The injury probe needs a PINNED ledger. Live constraints change with every
    # check-in, so running it against live state would measure today's soreness,
    # not the gate. It is synthetic-only by design (FEEDBACK §11).
    if synthetic:
        probes.append(_INJURY_PROBE)
    else:
        print("\nNOTE: the injury-refusal probe is synthetic-only — it needs a pinned "
              "ledger. Live constraints change per check-in; a probe keyed to them "
              "measures the state, not the gate.")

    outcomes = [run_probe(p, db, user, system) for p in probes]

    print(f"\n{'=' * 72}\nSUMMARY\n{'=' * 72}")
    failed = 0
    for o in outcomes:
        mark = "OK  " if o.reached_subject else "FAIL"
        print(f"  [{mark}] {o.probe.label}")
        print(f"         turns={o.turns_used} blocks={o.blocks} "
              f"guessed={o.guessed_titles or '[]'} provisioned={o.provisioned}")
        if not o.reached_subject:
            failed += 1
            print("\n" + o.failure_message() + "\n")

    if failed:
        print(f"\n{failed} of {len(outcomes)} probe(s) never reached their subject. "
              f"Exiting non-zero: a probe that measures nothing is not a pass.")
        return 1
    print("\nAll probes reached their subject.")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print("usage: python backend/probe_resolver.py <user_id> [--synthetic]")
        return 2
    user_id = int(argv[0])
    synthetic = "--synthetic" in argv

    _require_api_key()  # fail before spending a round-trip

    if synthetic:
        db = _synthetic_db(with_injuries=True)
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
            print("NOTE: a small slice flatters candidate cardinality. It is an "
                  "artifact of catalogue size (#83) — trust the live run.")
        return _run_all(db, user, synthetic)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
