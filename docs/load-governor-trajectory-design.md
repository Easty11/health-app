# Load Governor + Trajectory Layer — Design Spec (PROPOSED)

**Status:** PROPOSED — chat-drafted design, unadjudicated. Nothing here is repo state.
**Provenance:** Chat session 2026-08-27. Grounded against `Easty11/health-app` master via
codeload tarball on that date; all `file:line` references are as of that read and MUST be
re-verified by Code at implementation (sessions span days; landed ≠ live).

---

## Code verification record (landing this doc)

Re-verified against master on **2026-08-28** (master through DECISIONS_LOG `#247`,
OPEN_QUESTIONS `Q121`), per the doc's own instruction and the unseeable-surface rule. This
record covers only the in-tree anchors; the chat-log evidence anchors (§12) are not
repo-readable and are left as cited.

**Verified exact / correct:**
- #18 — `engine/__init__.py:22` ("references the Banister fitness-fatigue model … never ACWR"); dosing seam `engine/selection.py:436–464` (`_dosing`, `_WINDOWS_BY_CAPACITY`, `_DOSING_NOTE` — "ACWR is not used").
- #8 — `engine/__init__.py:19` (nothing gates on the suppressed readiness composite).
- #161 — `engine/__init__.py:24–31` (invariant scopes to the verdict, not measurement).
- #221 — `engine/selection.py` `select_next` docstring ("this function only ever REMOVES candidates").
- #28/#32 — `load_events.py` header (two-level store; recompute-not-migrate; reasoned priors tagged `FORMULA_VERSION = "tier0-v1"`).
- Criterion: `rolling_e1rm` + `E1RM_WINDOW_DAYS = 60`, per-template, RPE-usable only.
- `aerobic_sessions` migration `e3b2d1c4a5f6_add_aerobic_sessions.py` present.
- Metabolic **absent** from `load_events` emission — only `WINDOW_MECHANICAL` (`kg_reps`) and `WINDOW_NEUROMUSCULAR` (`nm_au`) rows are written; no `WINDOW_METABOLIC`.
- Training-engine `expected_load` **absent** from master (`backend/engine/` + `load_events.py` grep empty); the token is used only by the CBT-I / check-in knowledge subsystem (`context_builder.py`, `routers/knowledge.py`).
- Decision **#75** = "The Plan layer WRAPS the Adaptive Exposure Engine; it does not supersede it" (matches §1/§5.1's proposed Trajectory home).
- `_WINDOWS_BY_CAPACITY` routes `stability → [Neuromuscular, Psychological]` (INV-8 routing-into-Psychological premise holds).

**Corrected line drift (values/semantics unchanged, line numbers advanced since the 2026-08-27 read):**
- §8.1 `BODYWEIGHT_KG = 102.0` — **`load_events.py:73`** (doc had `:63`).
- §8.1 `EPOCH_RPE_COMPLETE = date(2026, 5, 11)` — **`load_events.py:67`** (doc had `:58`).

**Governance status of this landing:** this is an orientation/design doc only. No decision
numbers or Q-numbers are minted; the canonical stores (`DECISIONS_LOG`, `OPEN_QUESTIONS`,
`ROADMAP`) are untouched. The §11 candidates resolve to numbers only when adjudicated and
landed per the standing number-at-merge rule.

---

**Authority constraints (verified in-tree, dates as above):**
- #18 — quantitative dosing references Banister fitness-fatigue, **never ACWR** (`engine/__init__.py:22`, `engine/selection.py:436–464`).
- #8 — the readiness composite is suppressed; nothing gates on it (`engine/__init__.py:19`).
- #161 — the wearable-metric invariant scopes to the **verdict**, not to measurement (`engine/__init__.py:24–31`).
- #28/#32 — two-level load store; computed history is a recompute, never a migration; all coefficients are reasoned priors tagged `FORMULA_VERSION` (`load_events.py` header).
- #221 — the weekly-template slot filter only ever REMOVES candidates; it never overrides a stop (`engine/selection.py` `select_next` docstring).
**Governance discipline:** no decision numbers or Q-numbers are minted here. §11 lists
*candidate* entries for the stores; numbers resolve at merge per standing rule.

---

## §1 Objective and non-goals

**Objective.** Fill the dosing seam (`engine/selection.py:436–464`): a quantitative load
model behind `_dosing()` that (a) regulates acute and chronic load per physiological
window, and (b) regulates it **against a planned trajectory**, so the same trace state
reads differently in September (planned decay), November (build), and February (protect
availability). Two objects, one currency:

1. **Governor** — per-user, per-window Banister-form traces + acute guards over
   `load_events` (the `load_metrics` rollup the Tier-0 header already names as gate 3).
2. **Trajectory** — the imposed plan: phase-structured per-window target bands the
   Governor regulates against. The natural home is the plan layer (recorded as
   Decision #75, verified in-tree at landing).

**Non-goals.** This spec does not touch the capability engine (gate), the taxonomy, the
adaptation loop, or the explore/exploit split. It does not re-architect selection; it
plugs into the seam selection already reserves. It does not build schedule search (v2).

**Why both objects are structurally necessary (not a style choice).** Optimising a raw
Banister model does not produce periodisation — its "optimal" plan is maximal loading
then cessation (Ceddia 2025/26). The plan cannot be derived from the Governor; it must be
imposed on it. Conversely, the gate cannot see systemic accumulation (response tags are
per-exposure and lag), and the Governor cannot see untestedness. Gate → direction,
Governor → magnitude, Trajectory → context. See INV-1.

---

## §2 Invariants

- **INV-1 Gate precedes Governor.** The Governor operates only on sessions/patterns the
  capability gate has admitted. Like the #221 slot filter, the Governor only ever
  REMOVES or SCALES — it never re-admits a stopped pattern and never adds eligibility.
  Structural, not an ordering convention.
- **INV-2 Unit-lock.** Window traces are meaningful only against their own history
  (`kg_reps`, `nm_au`, and the Metabolic unit are not commensurable, and different load
  quantifications evolve differently through time — Vermeire 2021). All cross-window
  logic (substitution, display, flags) runs on **within-window normalised position**
  (z-score / minimal-detectable-change bands against the user's own trailing
  distribution), never on absolute values.
- **INV-3 Constants are reasoned priors.** Every time constant, ramp cap, and threshold
  below is a population/reasoned prior (#32 idiom), tagged `FORMULA_VERSION`,
  recompute-not-migrate on correction. Fitted or prior values are **never surfaced to a
  user as facts** ("your time constant is X" is overclaiming by construction — Hellard
  2006 CIs; ill-conditioning literature). Verdicts carry bands, not point estimates.
- **INV-4 Verdict shape (#161-compliant).** Governor outputs are decision-support
  advisories: flags, bands, proposed scalings. They are never the verdict on capability,
  and they never gate the adaptation loop. Self-report and operator override retain
  primacy (§8.4).
- **INV-5 Exogenous guardrails.** Trajectory shapes (phase structure, ramp caps, floors)
  are practice-derived priors imposed from outside the model. The Governor is never
  asked to optimise or bless its own plan (Ceddia).
- **INV-6 No ACWR (#18).** No acute:chronic ratio appears anywhere in dosing logic.
  Acute safety is enforced by ramp-rate caps and monotony/strain guards (§4.2), which
  require no fitted constants.
- **INV-7 Fail-closed on thin coverage.** Every trace carries a coverage/confidence tag.
  Missing inputs (unworn device, unlogged sessions, window not yet derived) WIDEN
  conservatism and are said aloud in the advisory; they never fake precision.
- **INV-8 Psychological is modulator-in / accrual-out.** Ambient life-stress modulates
  thresholds on the three physical windows (a capacity discount); acute session
  cognitive demand accrues into the Psychological trace. Psychological is never a
  governed dose target. (Session-established; consistent with `_WINDOWS_BY_CAPACITY`
  routing stability INTO Psychological.)

---

## §3 Windows, inputs, and criterion series

### §3.1 Ledger state (as of grounding read)

| Window        | `load_events` derivation | Source | Status |
|---------------|--------------------------|--------|--------|
| Mechanical    | LIVE — `kg_reps` per strength session | Hevy (`load_events.py`) | Tier-0 |
| Neuromuscular | LIVE — `nm_au` per strength session   | Hevy (`load_events.py`) | Tier-0 |
| Metabolic     | **ABSENT** — named in enum/seam only  | `aerobic_sessions` exists (migration `e3b2d1c4a5f6`); Polar/Catapult upstream | **Precondition S1** |
| Psychological | **ABSENT** — named in enum/seam only  | check-in life-load exists; session RPE-T not yet captured | Sequenced S6 |

The Governor over two strength windows is blind to the largest in-season chronic-tax
vector (rugby + aerobic). **Metabolic derivation into `load_events` is the first
precondition** (§10 S1), not an enhancement.

### §3.2 Criterion series (falsifiability requirement)

The fitting literature's core failure is traces trusted without an observable: models
fit history and still predict individual futures poorly (Busso 2023). Each window
therefore carries a **criterion series** — a window-native observable the fitness trace
must eventually agree with. Trace-vs-criterion divergence is a first-class flag (the
expected-vs-observed residual discipline, applied to the Governor itself).

| Window        | Criterion (v1) | State |
|---------------|----------------|-------|
| Mechanical/NM | rolling per-template e1RM — **already computed** (`rolling_e1rm`, `load_events.py`, 60 d window) | wire-up only |
| Metabolic     | pace@HR or submax HR-drift from existing Polar sessions (passive) — data-shape **VERIFY**; periodic submax protocol as fallback (standard elite practice, Akenhead) | build |
| Psychological | none in v1; PVT spot-check remains the on-demand probe (session-established, off the daily path) | deferred |

A Governor without criteria is unfalsifiable; ship no window's *authority* (§6) before
its criterion is wired. Display may precede authority.

---

## §4 The Governor (`load_metrics` rollup)

Daily, per user × window, computed from `load_events` (never raw payloads — #28):

### §4.1 Traces
- `load_raw` — day's summed window-native load.
- `chronic` — exponentially-weighted trace, time-constant prior **τ_c = 42 d** (aerobic
  convention; whether strength windows want a different τ is a candidate OQ, §11).
  This is the **fitness trace** and the load-bearing chronic object.
- `acute` — EW trace, prior **τ_a = 7 d**. v1 role: display + guard inputs.
- `fatigue` / `form` — **computed, displayed, NOT authoritative in v1.** The fatigue
  component is the model's statistically weakest part (adds no predictive value across
  two datasets — Marchal 2025). Promotion to veto authority is a v2 decision with
  explicit evidence criteria (§11).

### §4.2 Acute guards (no fitted constants; the #18-compliant acute safety layer)
- `ramp_rate` — week-over-week % change in `chronic`. Cap is a **phase-indexed prior**
  from the Trajectory (§5.3); starting prior ~5–10%/wk build phases (Guessing-grade
  prior — tune from calibration).
- `monotony` = mean(daily load)/SD over 7 d; `strain` = weekly load × monotony (Foster).
  Flag priors: monotony > 2.0, strain > user-trailing 90th percentile (z-based per INV-2).

### §4.3 Outputs
Per window: normalised position (z vs trailing distribution), guard flags,
coverage/confidence tag, criterion-divergence flag. All advisory-shaped (INV-4).

---

## §5 The Trajectory object

### §5.1 Structure
`trajectory` = ordered `phase[]` per user. Each phase: date range; objective weight
(mega tier — for the operator: availability/games-played 2027, not peak capacity);
per-window **target chronic band** (floor + ceiling as % of reference or z-band) and
**ramp cap**; error-asymmetry setting (§5.3). Tiers are views of this one object:
mega = the objective it is solved against; macro = phase shapes; meso = ramp steps;
micro = the weekly resolver distributing sessions against the current phase
(`weekly_template` slot machinery, #221 — resolver/`schedule_item` linkage per
governance memory, **VERIFY at implementation**).

### §5.2 Phase context changes verdicts
The Governor evaluates traces **against the active phase band**, not against static
norms: September decay inside a recovery phase = on-plan (no detraining flag);
November `chronic` under the build band = **up-scale advisory** (behind the base the
plan needs); February high chronic inside band = plan succeeding. The detraining floor
is the phase band, not a global constant.

### §5.3 Phase-indexed error asymmetry
Flag thresholds are set per phase by which error the phase can afford (Type I/II
framing, Rebelo 2026): early offseason tolerates missed overreach (wide bands —
recovery time is cheap); from ~February, tolerates false holds (tight bands — an
interrupted March costs games, the actual mega objective). One parameter per phase.

### §5.4 Exogeneity
Phase shapes and caps come from practice priors and operator intent (INV-5). The
Governor checks feasibility (e.g., a requested ramp exceeding cap) but never generates
the plan.

---

## §6 Control actions (the Governor's contract — the three ways it earns existence)

- **CA-1 Cap today (acute).** Scale factor / hold advisory on today's already-gated
  session, per window, from guard flags + phase band. Never re-admits (INV-1).
- **CA-2 Shape forward (chronic).** Project `expected_load` (§7) over the horizon;
  flag phase-band breaches and behind-trajectory deficits; propose redistribution.
  v1 = flag + nudge against the template; v2 = search.
- **CA-3 Substitute across windows.** When one window's normalised position is high and
  another's has room *relative to its own phase band* (INV-2), propose a session-type
  swap rather than a shrink. This is the entire payoff of four windows over one scalar;
  without CA-3 the multi-window design is ornamentation.

If none of CA-1..3 ships, the monitor fails the operator's own investment test and
should not be built.

---

## §7 `expected_load` — the shared currency

Per scheduled item × window: prescribed external work → expected window deposit, via
per-user transfer priors (strength: the existing set-load formulas run prospectively;
metabolic: TRIMP-class mapping — candidate OQ). Written by the plan/resolver layer;
read by CA-2 (forward integral), by the residual machinery (observed − expected →
psychological/stress signal and criterion checks), and by calibration (§9). One object
serves Governor, Trajectory, and the psychological modulator — build it once.
(Training-engine `expected_load` confirmed absent from master this session; only the
CBT-I subsystem uses the token.)

---

## §8 Multi-user and cold start

- **§8.1 De-hardcode operator priors.** `BODYWEIGHT_KG = 102.0` (`load_events.py:73`)
  → per-user profile attribute (existing bodyweight source — VERIFY; else prompt at
  onboarding). `EPOCH_RPE_COMPLETE = date(2026,5,11)` (`load_events.py:67`) → per-user
  integration attribute (nullable = diagnostic off). e1RM window stays a global prior.
- **§8.2 Priors + partial pooling.** New users start on population priors (τ, guards,
  transfer priors); per-user distributions take over as history accrues. Bayesian
  informative-prior fitting is the sanctioned v2 path (Peng 2023) — never
  unconstrained least squares.
- **§8.3 Coverage heterogeneity.** Arbitrary device subsets are the norm. INV-7
  applies: traces compute from whatever exists, tagged; advisories widen and disclose.
- **§8.4 Override-with-annotation.** Coach/user perception is the most-used monitoring
  input in practice and buy-in the top adoption barrier (Weston 2018; Akenhead 2016).
  Any advisory is overridable with a required one-line annotation; overrides are
  logged as data (they are calibration signal), never fought. Consistent with #161
  self-report primacy. This is the adoption surface, not a concession.

---

## §9 Calibration (Nov 2026 – Feb 2027 offseason ramp)

The build phase is the best controlled ramp available before the 2027 season. Capture:
planned trajectory, `expected_load`, actual `load_events`, criterion series, check-in,
HRV. **Deliverable expectations are deliberately modest:** prior-tempered coarse
constants and validated guard thresholds — *data-informed, not data-driven* (Vermeire
2022). Individual FFM fitting is ill-conditioned with wide CIs and weak out-of-sample
prediction (Hellard 2006; Busso 2023); v1 runs fixed priors regardless, and the
calibration dataset is the option on a careful v2, not a promise of personal constants.

---

## §10 Sequencing (each step usable alone; later steps depend on earlier)

- **S1** Metabolic derivation → `load_events` (from `aerobic_sessions`/Polar).
  Blocks everything; a two-window Governor is blind to the dominant tax vector.
- **S2** `load_metrics` rollup: traces + guards + normalisation + coverage tags
  (display only).
- **S3** Criterion wiring (e1RM hook-up; metabolic criterion build). Authority gate
  for S5.
- **S4** Trajectory object + phase context; encode the current offseason plan as its
  first instance (capture window is NOW — the offseason has already started).
- **S5** Control actions v1 (CA-1..3 as flags/advisories against the seam).
- **S6** Psychological: RPE-T capture (one field, post-session), accrual into
  Psychological trace; life-load modulator onto thresholds.
- **S7** Multi-user de-hardcoding + population priors (§8.1–8.2).
  S7 may run parallel to S2+; S4 may precede S3.
- Calibration capture (§9) runs continuously from S2.

---

## §11 Governance interface (candidates only — numbers mint at merge)

**Candidate decisions (if adopted):** two-object architecture + INV set; fatigue-trace
demotion in v1 with named promotion criteria; per-window criterion requirement as the
authority gate; ACWR readout boundary — the MCP monitoring surface currently reports
ACWR sweet-spot language while #18 forbids ACWR in dosing; one sentence formalising
"readout ≠ dosing input" (or retiring the readout) when this work starts.

**Candidate open questions:** strength-window τ priors vs the 42/7 aerobic convention;
Metabolic unit + TRIMP-class transfer prior and criterion definition from actual Polar
data shape; RPE-T capture surface in Hevy vs check-in; fatigue-trace promotion
evidence bar; substitution equivalence priors (how much Metabolic session "replaces" an
NM session for CA-3).

---

## §12 Evidence anchors (session-verified links held in chat log 2026-08-27)

Practice: Akenhead & Nassis 2016; Weston 2018; Houtmeyers 2021; Dello Iacono 2025;
West 2020; Rebelo 2026; Afonso 2025 (integration absent — 5/46 multivariate).
Model: Hellard 2006 (ill-conditioning); Busso 2023 (predictive inadequacy);
Marchal 2025 (fatigue-component flaw); Vermeire 2021 (methods not interchangeable),
2022 (data-informed); Peng 2023 (Bayesian priors); Ceddia 2025/26 (no periodisation
from raw FFM). Differential RPE: McLaren 2017. Stress–injury: Ivarsson 2017 meta.
