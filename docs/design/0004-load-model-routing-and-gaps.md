# 0004 — Load model routing and gaps
**State:** ideation
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#540. Folded questions: Q115, Q121, Q124. The triage placed this as architecture-scale, ideation (extends `load-governor-trajectory-design.md`).

Extends `docs/load-governor-trajectory-design.md`, which stays where it is.

## Proposal

none yet

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q115 | Supramaximal / repeated-sprint work routes Metabolic-only under `#28` — the neuromuscular cost is discarded (supramaximal → NM, the discriminator) | none yet | none recorded | unclassified | open |
| Q121 | Tier-0 load transform modelling gaps — weighted-bodyweight, flat BW fraction, non-rep NM, half-point RIR (Tier-0 gaps) | none yet | none recorded | unclassified | open |
| Q124 | Field-session (Catapult/GPS) ingestion into `aerobic_sessions` (Catapult external load) | none yet | none recorded | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q115 — Supramaximal / repeated-sprint work routes Metabolic-only under `#28` — the neuromuscular cost is discarded</summary>

````
## Q115. Supramaximal / repeated-sprint work routes Metabolic-only under `#28` — the neuromuscular cost is discarded

`#28` fixes the four-window load routing:

> strength volume-load → Mechanical + Neuromuscular · HR/zone-derived load → **Metabolic** ·
> sRPE / subjective-vs-objective divergence → Psychological

Strength dual-routes. Nothing else does. So an all-out interval session — 6 × 30 s, or a rugby
match's repeated accelerations — is HR/zone-derived and lands in **Metabolic alone**, in the same
channel as steady-state aerobic work.

Two consequences, both from `#32`'s per-window τ pairs:

| | Assigned | Plausible |
|---|---|---|
| Sprint session recovery constant | Metabolic τ ≈ 4 d | Neuromuscular τ ≈ 6 d, or longer |
| Neuromuscular fatigue accrued | **zero** | substantial |

The cost is not merely mis-weighted, it is **absent from the channel that should carry it**, and
what does get recorded is assigned a faster recovery constant than the tissue takes. **Likely** —
first-principles from the routing rule and the declared τ priors, not measured.

**This is discoverable pre-implementation.** `#32` confirms no Banister/four-window code exists;
the only load computation is `get_training_load()` (ACWR) in `backend/mcp_server.py`, already
recorded as tech-debt retiring on Tier 0. Correcting the routing now costs a spec amendment.
Correcting it after Tier 0 lands costs a migration of computed history.

### What this is not

**Not a fifth window.** `#32`'s revisit clause orders the levers: τ is tuned first, and the
four-window split is reconsidered only after — governed by `#28`'s own revisit clause. This
question proposes a **routing amendment** in the existing taxonomy, mirroring the dual-route
strength already uses. It does not touch the split.

**Not a weighting claim from the proteomics.** The prompting evidence (Olsen et al.,
Cell Rep Med 2026;102988 · PMID 42594877 — 714 of 2,884 plasma proteins moved by three minutes of
sprinting vs 7 by 90 minutes of moderate cycling) is a **stimulus-quality** finding, not a cost
finding, and it confounds intensity with modality, duration, and sampling window — the moderate
session was slower rather than inert, with fatty-acid and liver-derived responses appearing hours
later. Load is a cost currency. Importing an adaptation finding into a fatigue model is the same
category error as conflating `hard` with `expected_load`. The proteomics motivated the look; it is
not the argument. **Source not independently verified — supplied to chat, not retrieved.**

The load argument stands on the routing rule and the τ priors alone.

### The hard part — the discriminator

Correcting the routing requires the ingestion path to distinguish supramaximal/intermittent work
from continuous work. **Average HR cannot do it.** Six 30-second efforts with recovery produce an
unremarkable session mean — which is the same blindness `get_training_load()`'s `hr_avg` has today,
and the reason the defect is invisible in the current metric.

Candidate discriminators, unranked:

- **Catapult SPT3** (`.gt`; 100 Hz IMU, 10 Hz GNSS) — resolves individual accelerations and sprint
  efforts. The only currently-owned instrument that measures the thing directly. Strengthens the
  case for the `.gt` ingestion path independent of field-session capture.
- **Polar zone-time distribution** rather than mean HR — time above a high zone as a proxy for
  intermittency. Cheaper, coarser, already retrievable per `#17` (AccessLink v4) and `#46`
  (per-second exercise-HR).
- **Session-type declaration** at ingestion — honest, zero-inference, but pushes the judgement onto
  the user and is exactly the kind of self-report the platform prefers to instrument around.

*Cross-ref defect, recorded here because this is where the design pass hits it:* `#28`'s Status line
cites **"Polar zone retrieval (#10)"**, but `#10` is *Annotate confounds, don't discount scores* —
Polar retrieval is `#17` / `#46`. The draft of this question inherited the wrong pointer and it was
corrected here before landing; `#28`'s own line is locked append-only text, so **the correction
rides with the routing amendment this question schedules** rather than costing a decision entry of
its own.

No recommendation. The discriminator choice is the substance of the design pass.

### Live impact

The operator plays rugby union in contact and coaches/attends conditioning built on repeated
running efforts. Match play and Tuesday conditioning are both intermittent by nature, so under the
current routing **most of his high-intensity exposure would accrue no neuromuscular fatigue at
all** while carrying a right proximal semimembranosus rupture (full-thickness, partial-width),
a left hamstring provoked specifically by striding and sprinting, and bilateral L5 pars defects.

Neuromuscular is the channel that would otherwise flag accumulating sprint exposure against a
hamstring that is known to fail at exactly that stimulus. That is the concrete cost of the gap.

### Related

- `#28` — four-window taxonomy and routing. This question targets the routing clause only.
- `#32` — per-window independent τ pairs; revisit ordering (τ before split).
- ΔLoad primitive — per-window acute spike detection, carved out to survive ACWR's retirement.
  Sprint work is the spike-prone stimulus that justifies it; a Metabolic-only route sends the
  spike to the wrong window too.

**State:** OPEN — **NOT blocking.** No Banister code exists, so nothing is currently computing a
wrong number; this is a correction to a spec before it is built. **Next action:** design pass on
the discriminator, then a routing amendment to `#28` (supersede-not-amend, per the append-only
rule). Do not open it as part of the Banister implementation itself — the amendment should land
first so the implementation is built to a corrected spec. **That amendment also carries the `#10`
cross-ref correction recorded above** — it is the reason no separate entry was minted for it. Per
`#123` closed questions leave the scan surface, so if this question closes *before*
the routing amendment lands, the cross-ref correction loses its only live home and needs relocating
at that moment. Owner: Luke.

**Annotation (2026-08-25) — D-B removes the migration-cost urgency, not the substance.** This
question's urgency framing was "correct the routing now or pay a migration of computed history
later." The two-level store settled this lane (D-B: `load_events` append-only → `load_metrics`
derived and recomputable) removes that cost: a routing amendment after Tier 0 lands is a recompute
against `load_events`, not a migration. So the *when* relaxes — the amendment no longer has to beat
the transform to master. What does NOT relax is the **substance**: the discriminator that
distinguishes supramaximal/intermittent from continuous work (average HR cannot do it) still has to
be designed, and the routing amendment to `#28` still has to be authored. Recompute-cheap is not
built-for-free. Still OPEN; still owned by the discriminator design pass.
````

</details>

<details><summary>Q121 — Tier-0 load transform modelling gaps — weighted-bodyweight, flat BW fraction, non-rep NM, half-point RIR</summary>

````
## Q121. Tier-0 load transform modelling gaps — weighted-bodyweight, flat BW fraction, non-rep NM, half-point RIR

The gate-2 `load_events` transform (`formula_version 'tier0-v1'`, DECISIONS_LOG #241)
shipped four deliberate Tier-0 simplifications. Each is **surfaced, not hidden** — none is a
defect in the landed transform. (Distinct from `#243`, a genuine defect — the bodyweight coalesce
leaking into the non-rep branch — already fixed in-version.) **Gap 4 (flat bodyweight fraction) is
now RESOLVED — built as `#245` (`bw_fraction`), promoted build-now ahead of gate 3.** Three honest
priors remain below.

- **Weighted-bodyweight undercount.** `effective_weight = weight_kg` when a plate is logged, else
  `BODYWEIGHT_KG` (102). A weighted pull-up (+20 kg) therefore scores on 20 kg, not ~122 kg — the
  body is the load and the plate is the increment, but Tier 0 has no per-template bodyweight-movement
  flag to know that. A pure-bodyweight set (no plate) correctly uses `BODYWEIGHT_KG`; a barbell lift
  correctly uses the bar load. Only the *weighted-bodyweight* case undercounts. Fix needs a
  per-template "adds bodyweight" tag (a template annotation, like `laterality`).
- **Flat bodyweight fraction — RESOLVED `#245` (2026-08-26).** Built as `hevy_exercise_templates.bw_fraction`:
  a rep set with `weight_kg` NULL/0 scores `BODYWEIGHT_KG × COALESCE(bw_fraction, 1.0)`; a logged weight
  is never scaled. **Tagging amendments (2026-08-26, operator):** Weighted Dead Bug `bw_fraction` revised
  **0.25 → 0.1** (undercount-preferred for the unweighted pattern; logged-weight sets unchanged — that load
  is the overhead hold). Effective at the next recompute; no recompute forced now. The 13 Jul reconciliation
  fixture is **unaffected** — it embeds `0.25` as a test convention to guard the formula, not a prod tag.
  Data provenance: the 13 Jul `0kg×60` / `0kg×50` dead-bug sets are **confirmed genuine reps** (operator),
  so the fixture's rep interpretation is confirmed, not assumed. The additive weighted-bodyweight case (bodyweight + plate) is NOT covered by `#245` and
  remains the **weighted-bodyweight** gap above (it needs the e1RM fit to read the same coalesced load —
  a `formula_version` consideration, and the Hevy assisted-set sign is still UNVERIFIED). Original note
  kept for provenance: `_effective_weight` priced every pure-bodyweight
  REP set at `BODYWEIGHT_KG × 1.0`, but the loaded fraction is class-dependent: force-plate data puts
  it at ~0.65 for horizontal push/row (push-up ~0.64 top / ~0.75 bottom; the coaching "85%" is not
  supported), ~0.9 lower-body BW (shanks unloaded), ~0.95 hanging (pull-up/dip), ~0.5
  kneeling/regressed. So Mechanical **over**counts push-up-class work by ~45%, lower-body BW by
  ~10–15%, hanging by ~5%. **NM is unaffected** — the per-template e1RM is fitted from the same
  coalesce, so the fraction cancels in `I = effective_weight / e1RM`. Within-class precision sits
  inside `m()`/`K_dist`/`K_time` prior noise once smoothed through the ~10 d Mechanical τ (`#32`); the
  *class-level* 1.0-vs-0.65 gap does not. **Shares the weighted-bodyweight remedy:** one per-template
  annotation carrying both "adds bodyweight" and a `bw_fraction` (3–4 class defaults,
  operator-overridable; no separate leverage axis — Hevy already splits elevated/decline/ring
  variants into distinct templates). Weighted: `BW × fraction + weight_kg`; assisted:
  `BW × fraction − weight_kg` (the sign convention on Hevy's assisted set types is **UNVERIFIED** —
  read it off `hevy_workouts.raw` before coding). `#243` already scoped the coalesce to REP sets only
  (weight-NULL non-rep skips), so a `bw_fraction` added to `_effective_weight` touches only rep-based
  bodyweight — confirmed this session.
- **Non-rep NM = 0.** Carries/sleds and timed holds bridge into Mechanical (D-D `K_dist`/`K_time`)
  but contribute **zero** Neuromuscular. Flagged arguable in D-D for maximal sled efforts, which
  carry a real velocity/RFD demand a flat 0 discards.
- **Half-point RIR banding.** RIR = **`floor`(10 − RPE)** (pinned `#244`; RPE 8.5 → RIR 1 → m 1.30) —
  a half point bands DOWN to the harder tier. The m()/f() tables are integer-keyed, so a half point is
  banded rather than interpolated. Deterministic and documented, but a Tier-1 transform may interpolate
  f/m across the half instead (a `formula_version` bump).

**State:** OPEN — not blocking; the transform is correct and honest at Tier 0, and `provenance`
records where each gap bit. **Next action:** none until Tier 1; the per-template annotation carrying
both "adds bodyweight" and `bw_fraction` is the first candidate — it resolves the weighted-bodyweight
undercount and the flat-fraction overcount in one operator-annotation path (like `laterality`), and
verify the Hevy assisted-type sign against `hevy_workouts.raw` before coding it. Owner: Luke.
Cross-refs `#241` (the gate-2 entry), `#243` (the coalesce non-rep-leak fix — scoped it to rep sets),
`#28`/`#32` (D-A/D-C/D-D), `#74`/`#76` (template tags).
````

</details>

<details><summary>Q124 — Field-session (Catapult/GPS) ingestion into `aerobic_sessions`</summary>

````
## Q124. Field-session (Catapult/GPS) ingestion into `aerobic_sessions`

`#251`'s transform scores whatever rows exist in `aerobic_sessions`, today seeded from Polar Flow export
(HR-zone based) and provisioned for Health Connect. Field sessions instrumented by GPS/accelerometer
units (e.g. Catapult) carry an external-load model (PlayerLoad, high-speed-running distance) that is NOT
HR-zone based and would not populate `z*_seconds`, so an Edwards TRIMP cannot see them. Open: is field-
session external load a fourth ingestion into `aerobic_sessions` (with a distinct sub-formula and its own
`formula_version`), a separate source table, or out of the Metabolic window entirely (a different load
axis)? Out of S1 scope — recorded so the ledger gap is named, not silently narrowed to HR-only aerobic
work.

**State:** OPEN

**Cross-reference (#365, Q203).** #365 makes the Catapult SPT3 the preferred field source, optional and not guaranteed. The missing-data side of that (an expected SPT absent) is Q203.
````

</details>
