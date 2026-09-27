"""Injury sweep against the REAL `user_knowledge` Injury History lines (operator-run prod read,
G0 addendum), plus the restriction audit's G1 case.

The prod ledger: both hamstring rows resolved — id 18 left (2026-08-19), id 29 right
(2026-08-25). The lines below are verbatim from `user_knowledge` row 2 (Injury History). They
carry the shapes a synthetic fixture would miss: mixed-injury lines (hamstring + shoulder),
lines naming both sides, a resolved-history line next to a live one, and a live lumbar line
the hamstring sweep must NOT hit.

Restriction audit G1 case: the right hamstring's end-range stretching restriction is a neural,
lumbar-origin limiter recorded on a tissue row. Its resolution basis does not address it, so it
is an ORPHAN until re-homed — which the operator did, to id 94 `injury_lumbar_spine`
(mechanical). Both resolution bases and the id 94 row are VERBATIM prod values.

UNCONFIRMED: id 29's `restrictions` array is still the seed value (`ASSUMED_29_RESTRICTIONS`),
pending the operator's prod read (`SELECT value->'restrictions' FROM user_knowledge_entries
WHERE id = 29`). Replace it with the prod array; do not treat the seed as prod.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import hevy_routine_cache
import models
from auth import get_current_user
from database import get_db
from routers import knowledge as knowledge_router

LINES = [
    # (A) mixed-injury line: hamstring + right shoulder
    "(A) Hamstring tweak 04 Jun 2026 at training (minor grade 1), played through 06 Jun — "
    "RESOLVED Aug 2026. Right shoulder setback in the 06 Jun game (upper trap tear "
    "hypothesised ~May 2026, never imaged).",
    # (B) both sides named, historical
    "(B) HISTORICAL (Jul 2026; both hamstrings resolved Aug 2026): single-leg RDL used as "
    "hamstring rehab. Right SLRDL discomfort behind knee at 32kg RPE 9 vs left 32kg clean "
    "(12.5% gap at the time). Left knee click noted in trailing-leg BSS 10 Jul — painless, "
    "monitoring.",
    # (C) the right semimembranosus — no word "hamstring"; hit via "sprint"
    "(C) RIGHT PROXIMAL SEMIMEMBRANOSUS RUPTURE — full-thickness partial-width 3.3 x 1.6cm "
    "(Aug 2025, rugby). RESOLVED in injury ledger 25 Aug 2026. Not a constraint; no sprint or "
    "velocity gating.",
    # (D) left calf — no hamstring term
    "(D) LEFT CALF — medial gastrocnemius tear 14 Jul 2026 (catching a ball, near-zero load). "
    "RESOLVED: no longer a training restriction as of Sep 2026.",
    # (E) both sides, left hamstring named
    "(E) LATERALITY PARADOX (15 Jul 2026): structural/neurological findings are RIGHT (CT right "
    "L5 root, right foraminal narrowing, slump positive right); tissue failures were LEFT (left "
    "hamstring velocity provocation and left gastrocnemius, both since resolved; left pes "
    "anserine). Five explanatory models built and failed — do not generate new hypotheses "
    "without new data.",
    # (F) LIVE lumbar line — must not be hit by a hamstring sweep
    "(F) LUMBAR SPINE — L5-S1 bilateral pars defects, anterolisthesis ~2.3mm, central disc "
    "herniation, right foraminal narrowing; L4-5 retrolisthesis; slump positive right (S1). "
    "Injury vector: loaded end-range lumbar shear with loss of neutral. Painless at slip, sore "
    "hours later; recurrence declining. Scrummaging protective (braced, neutral). CURRENT "
    "CLEARANCE (Dr Aubrey, Sep 2026): all back movements cleared except end-range flexion "
    "combined with twisting; extension may not be provocative and is introduced progressively "
    "(showing promise in pilates); start small, pain gates progression. Heavy hinge, especially "
    "end of range, remains gated. No chiropractic manipulation without current neural imaging. "
    "Hard stops: right-leg radicular signs past the knee → escalate; cauda equina signs → ED "
    "immediately. Goal: earn back bottom of squat via graded re-exposure.",
]

STRETCH = "static end-range hamstring stretching"
# UNCONFIRMED — the seed array, not a prod read (see module docstring).
ASSUMED_29_RESTRICTIONS = ["striding", "sprinting", STRETCH]

# Verbatim prod (operator-supplied).
BASIS_18 = "Velocity provocation cleared - striding and sprinting symptom-free."
BASIS_29 = ("Right hamstring tear is resolved, really has been for sometime, no issues running "
            "due to the tear. ")
LUMBAR_94 = {
    "body_part": "lumbar", "signal_type": "mechanical",
    "restrictions": [
        "static hamstring stretching \u2014 neural (S1 tract from lumbar lesion); flossing, "
        "sliders and dynamic mobility only",
        "end-range lumbar flexion combined with twisting",
        "heavy hinge at end of range",
    ],
}


def _user(db):
    u = models.User(email="prodfix@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client(db, user):
    app = FastAPI()
    app.include_router(knowledge_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _row(db, **kw):
    row = models.UserKnowledgeEntry(type="injury", source="system", **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture(autouse=True)
def _clear_cache():
    hevy_routine_cache._CACHE.clear()
    yield
    hevy_routine_cache._CACHE.clear()


@pytest.fixture
def prod(db_session):
    u = _user(db_session)
    left = _row(db_session, id=18, user_id=u.id, key="injury_hamstring_left", active=False,
                value={"body_part": "hamstring", "side": "left", "signal_type": "mechanical",
                       "restrictions": ["striding", "sprinting"],
                       "resolution": {"resolved_on": "2026-08-19", "resolved_by": "user",
                                      "basis": BASIS_18}})
    right = _row(db_session, id=29, user_id=u.id, key="injury_hamstring_right", active=False,
                 value={"body_part": "hamstring", "side": "right", "signal_type": "mechanical",
                        "restrictions": ASSUMED_29_RESTRICTIONS,
                        "resolution": {"resolved_on": "2026-08-25", "resolved_by": "user",
                                       "basis": BASIS_29}})
    row2 = models.UserKnowledge(id=2, user_id=u.id, category="Injury History",
                                content="\n".join(LINES))
    db_session.add(row2)
    db_session.commit()
    return {"db": db_session, "user": u, "left": left, "right": right,
            "client": _client(db_session, u)}


def _sweep(prod, entry_id, **params):
    r = prod["client"].get(f"/knowledge/injuries/{entry_id}/sweep", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _uk_hits(body):
    return {h["line_index"]: h for h in body["hits"] if h["store"] == "user_knowledge"}


# ── the real lines ───────────────────────────────────────────────────────────

def test_right_hamstring_hits_the_hamstring_lines_and_not_calf_or_lumbar(prod):
    hits = _uk_hits(_sweep(prod, 29))
    assert sorted(hits) == [0, 1, 2, 4]           # A B C E; not D (calf) nor F (live lumbar)
    assert all(h["row_id"] == 2 and h["action"] == "edit" for h in hits.values())
    assert hits[2]["matched_terms"] == ["sprint"]  # (C) never says "hamstring"
    assert not any(h["opposite_side"] for h in hits.values())


def test_left_hamstring_flags_right_only_lines(prod):
    hits = _uk_hits(_sweep(prod, 18))
    assert sorted(hits) == [0, 1, 2, 4]
    # (C) is the RIGHT semimembranosus — correctly flagged for the left sweep.
    assert hits[2]["opposite_side"] is True
    # (A) is flagged too, but its only side word belongs to the SHOULDER in a mixed-injury
    # line — a known limit of line-level side detection. Flagged, never dropped: the operator
    # still sees it.
    assert hits[0]["opposite_side"] is True and hits[0]["sides_mentioned"] == ["right"]
    assert hits[1]["opposite_side"] is False and hits[4]["opposite_side"] is False


def test_operator_term_reaches_the_semimembranosus_line_by_name(prod):
    hits = _uk_hits(_sweep(prod, 29, terms="semimembranosus"))
    assert "semimembranosus" in hits[2]["matched_terms"]


# ── restriction audit (G1 case) ─────────────────────────────────────────────

def _audit(body):
    return {a["restriction"]: a for a in body["restriction_audit"]}


def _lumbar_94(db, user_id, **over):
    value = {**LUMBAR_94, **over}
    return _row(db, id=94, user_id=user_id, key="injury_lumbar_spine", active=True,
                value=value)


def test_left_basis_covers_both_velocity_restrictions(prod):
    a = _audit(_sweep(prod, 18))
    assert a["striding"]["status"] == "covered"
    assert a["sprinting"]["status"] == "covered"


def test_right_basis_addresses_none_of_its_restrictions(prod):
    """The real id 29 basis speaks to the tear and to running. "running" is not "sprint" or
    "stride" — no synonym expansion, deliberately: the audit surfaces, the operator judges."""
    body = _sweep(prod, 29)
    a = _audit(body)
    assert {r: x["status"] for r, x in a.items()} == {
        "striding": "orphan", "sprinting": "orphan", STRETCH: "orphan"}
    # Naming the hamstring is not addressing the stretch: body-part words are not evidence.
    assert a[STRETCH]["match_stems"] == ["stretch"]
    assert "chat-rendered only" in body["restrictions_note"]


def test_stretch_rehomed_to_prod_row_94_with_no_warning(prod):
    _lumbar_94(prod["db"], prod["user"].id)
    a = _audit(_sweep(prod, 29))
    assert a[STRETCH]["status"] == "rehomed" and a[STRETCH]["covered_by_basis"] is False
    [dest] = a[STRETCH]["rehomed_to"]
    assert (dest["entry_id"], dest["key"], dest["body_part"], dest["signal_type"]) == (
        94, "injury_lumbar_spine", "lumbar", "mechanical")
    assert dest["radicular_warning"] is None
    # Striding/sprinting are carried by no active row — still orphans for the operator to judge.
    assert a["striding"]["status"] == "orphan" and a["sprinting"]["status"] == "orphan"


@pytest.mark.parametrize("signal", ["neural", "radicular"])
def test_row_94_typed_neural_would_warn_radicular_blocks(prod, signal):
    """`body_part: lumbar` is spinal to `_is_spinal`, so the same row typed neural/radicular
    would hard-stop hinge/rotation/carry/gait. The audit says so; it never retypes."""
    _lumbar_94(prod["db"], prod["user"].id, signal_type=signal)
    w = _audit(_sweep(prod, 29))[STRETCH]["rehomed_to"][0]["radicular_warning"]
    assert w is not None and w["signal_type"] == signal
    assert {"hinge", "rotation", "carry", "gait_load_carriage"} <= set(w["fires"])


def test_inactive_destination_is_not_a_rehome(prod):
    _row(prod["db"], id=94, user_id=prod["user"].id, key="injury_lumbar_spine", active=False,
         value=LUMBAR_94)
    assert _audit(_sweep(prod, 29))[STRETCH]["status"] == "orphan"


def test_audit_never_writes(prod):
    db = prod["db"]
    db.expire_all()
    before = [(r.id, r.active, r.value) for r in db.query(models.UserKnowledgeEntry)
              .order_by(models.UserKnowledgeEntry.id)]
    _sweep(prod, 29)
    _sweep(prod, 18)
    db.expire_all()
    after = [(r.id, r.active, r.value) for r in db.query(models.UserKnowledgeEntry)
             .order_by(models.UserKnowledgeEntry.id)]
    assert after == before
