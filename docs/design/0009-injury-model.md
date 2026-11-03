# 0009 — Injury model
**State:** discussion
**Owner:** Luke   **Opened:** 2026-11-04   **Last moved:** 2026-11-04

## Context

Opened 2026-11-04 from the operator's question: designed from nothing, what would an injury
system built to influence and control exercise programming include, exclude and output, and
which injury types would it treat rather than note? Pointer issue GH#603. Related: 0002
(plan-log reconciliation — time-loss derivation and the per-session pain capture), 0003
(constraints engine tier — committed; the modifier layer this model extends), 0001 (canonical
exercise layer — regional load needs it). The live ledger is the first cut of this model:
injury rows are episodes, confirmed constraint rows are block modifiers, findings hold clusters,
the AM soreness map is the symptom series.

## Proposal

**Purpose.** Not an injury register. An input layer to prescription: it tells the engine and the
coach what may not be done, what may be done only within a dose, what must be done to earn
capacity back, and when each is re-examined; and it leaves a record good enough for a clinician
and the athlete to see cause and course. What serves none of those outputs is noted, not
modelled.

**Three objects and a series.**
- A *problem* is a standing condition (a structural lumbar spine, a cervical cord contact). It
  has states (quiet, irritable, flare), clinician-governed boundaries and standing modifiers that
  outlive every phase. Problems are reviewed, never resolved. The phase's avoid list derives from
  the standing modifiers; a phase deload is one expression of them (operator, Oct 2026).
- An *episode* is a dated tissue event: onset, mechanism (contact, velocity, load, insidious),
  structure as specifically as known, side, severity, and a diagnosis status honest about
  confidence (suspected, imaged, clinician-confirmed). Episodes resolve, with a basis. An episode
  may belong to a problem or stand alone. Recurrence is a link to an earlier episode, not a new
  unrelated row (Likely: the sports-injury consensus distinction between re-injury at the same
  site and type after return, and a subsequent unrelated injury).
- A *modifier* is what the engine reads: `block`, `cap`, `caution`, and `require` (a positive
  prescription — graded re-exposure of a range, pain-gated). Scope is region, side, capacity, and
  standing-vs-phase-bound; it carries authority, exit and review. `cap` needs a dose seam under
  it so a cap is a number and not a block with a softer name (Q183).
- The *symptom series* — soreness per region per morning, pain during a session, neural signs,
  function markers — monitors and never gates on its own (#72).

**Courses, and treat versus note.**
- Acute episodes: full record; treated, with modifier exits defaulting from the tissue's clock,
  not a flat interval.
- Gradual-onset / overuse: captured weekly in the overuse-questionnaire form (Likely: OSTRC —
  participation reduced, volume modified, performance affected, pain); treated with caps and load
  management, not blocks.
- Chronic problems: standing modifiers; review cadence tied to clinical review; flare detection
  from the symptom series PROPOSES a temporary tightening, never applies one.
- Niggles: note-only; promoted to an episode on a persistence rule (present on about three of
  seven mornings, or an overuse score above threshold).
- Clusters: analysis objects (findings) linking episodes under a hypothesis with its evidence;
  the system holds the link and refuses to speculate ("five models failed — no new hypothesis
  without new data", the operator's ledger).
- Systemic modifiers (RA flare exists as a flag) stay a modifier class; illness and acute sleep
  debt belong to readiness.
- Red flags are their own class with one output — an escalation message — and no programming
  logic.

**Outputs.** To the engine: the modifier set per region and side with kind, reason, authority and
exit. To the coach: the same rendered, plus what changed since last session and what is due. To
the operator: the morning "needs your call", and one timeline per injury (symptoms, regional
load, modifier changes, clinician events, probe results) — also the honest content of a
clinician brief. To the clinician: an export in consensus form (onset, mechanism, time-loss days,
recurrences). To the plan: the return-to-load path, where `require` meets the exposure engine's
probe. To analysis: regional load before onset, recurrence rate by problem, time-loss by phase —
time-loss derivable only once 0002 lands.

**Angles.** Regional load exposure is the covariate a niggle cannot be read without; the Hevy
region tags make it computable (0001). A pain-progression rule (Likely: the tendinopathy
pain-monitoring model — pain up to about 5/10 during work tolerated if settled by next morning
and not rising week on week) operationalises "pain gates progression" over the symptom series
and a per-session pain capture. Confidence to load a region belongs to the psychological window
(#28); noted, not built. Authority extends to episodes, not only modifiers.

## Exclusions

No diagnosis: labels stored at stated confidence, never upgraded. No automatic lifting or
tightening: every exit and flare response is a proposal a human confirms (#223). No prose. No
episode created from device data alone. No pain number as a gate. No medical treatment:
medications, manipulation, injections are recorded as clinician instructions, never recommended.
Concussion: governed by the sport; recorded as a clinician-authority modifier ("stood down until
cleared") and otherwise out.

## Alternatives considered

One object (the current injury row) carrying problem, episode and modifier fields — rejected:
it is why a structural lumbar problem and a resolved hamstring tear share a shape and a resolve
button. A separate injury register outside the engine's read path — rejected: the register would
drift from what the engine enforces, the failure #340 already names.

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| 1 | Shape fields for the model, admitted now as optional | `onset_on`, `course`, `mechanism`, `tissue`, `diagnosis_status`, `problem_key`, `recurrence_of` on `type=injury` | PR-A's tests | two-way | resolved → #493 |
| 2 | Problem vs episode: one type with `problem_key`, or two types | one type now; split only if a problem needs fields an episode cannot carry | the first standing problem that needs its own state machine (flare states) | two-way | open |
| 3 | `cap` and `require` at the engine tier | behind a dose seam; `require` as a positive exposure the probe schedules | the dose seam design (Q106 / GH#489; GH#595) | one-way (cross-module: prescription) | open |
| 4 | Tissue-based review defaults | a small declared table tissue → review interval, used as `review_by` default for engine proposals | the table itself; operator ratification | two-way | open |
| 5 | Note → treat persistence rule for niggles | ~3 of 7 mornings or an overuse score threshold → propose an episode | the first month of symptom-series data under the rule | two-way | open |
| 6 | Regional load exposure as a covariate | derived from Hevy region tags per session; needs 0001 | 0001's state | depends on 0001 | open |
| 7 | Red-flag class | its own type or a `signal_type`; one output (escalate) | operator + clinician wording | one-way (clinical) | open |
| 8 | Per-session pain capture | the PM close-out's pain reason code | 0002 | owed to 0002 | open |
| 9 | Overuse weekly capture (OSTRC-style) | a weekly four-item prompt on a chosen day | operator ruling on cadence | two-way | open |
| 10 | Coach proposals from clinical documents | yes, proposal-gated, clinician authority pre-selected | the operator's fork ruling (GH#608, filed by PR-D) | one-way | open |

## Decisions landed

- #493 — The injury row has a closed shape: a body-part vocabulary, side and signal enums, the seven optional injury-model fields admitted (enum- or existence-checked, read by nothing yet), and no new `restrictions[]` (resolves row 1).
