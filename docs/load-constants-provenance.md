# Load-constants provenance

**Standing rule (gate).** Every module-level numeric constant, coefficient table, and
formula coefficient in `backend/load_events.py`, `backend/load_events_metabolic.py`, and
`backend/load_metrics.py` has exactly one row here. **A PR that adds or changes a coefficient
in those three modules adds or changes its row in the same PR** — enforced by
`backend/tests/test_load_constants_provenance.py` (set-equality drift guard) and gated in
DECISIONS_LOG #305. No new coefficient lands in these modules unlabelled.

**Provenance classes.**

- **cited** — a source backs the value: a citation already in the module docstring, a standard
  formula, or a chat-verified anchor (marked "chat-verified 17 Sep 2026, Consensus"). The
  source column names it. A weak citation (practitioner convention, n=1) is still *cited*, but
  its weakness is recorded in the revisit column.
- **derived** — computed from another row or a unit conversion, not an independent choice
  (e.g. the banister-v4 seed window IS `ACUTE_DAYS`; the TRIMP minute divisor is s→min).
- **operator input** — a fact about the user, not a modelling choice (`BODYWEIGHT_KG`).
- **operator prior (uncited)** — a modelling choice with no verified source. An honest
  "uncited" beats an unverified reference; citations enter only when verified. **The majority
  of the load coefficients are here** — that is the point of the table, and the input list for
  the Q156 criterion/sensitivity harness.

**Not in this table (deliberately).** `FORMULA_VERSION` / `FORMULA_VERSION_METABOLIC` /
`METRICS_VERSION` and the `WINDOW_*` / `UNIT_*` strings are version keys and labels, not
coefficients — they are the keys this table is versioned *under*, not entries in it. HR-zone
boundaries and any HRmax derivation are set upstream in aerobic ingestion (the metabolic lane
consumes pre-computed `z*_seconds`), so there are no HR-zone rows here. The EWMA decay
`decay_x = e^(−1/τ_x)` is a formula fully determined by the τ rows, not an independent prior,
so it carries no row of its own.

## Table

| constant | module | value | role | class | source | introduced | revisit trigger |
|---|---|---|---|---|---|---|---|
| `BODYWEIGHT_KG` | load_events | 102.0 | kg used to bridge non-rep / bodyweight work into kg·reps | operator input | user 1's bodyweight — a fact about the user, not a modelling choice | #32 | per-user de-hardcode pending (#245 `bw_fraction`, design §8.1) |
| `K_DIST` | load_events | 0.3 | rep-equivalents per metre (distance→kg·reps bridge) | operator prior (uncited) | — | #32 | Q156 |
| `K_TIME` | load_events | 0.05 | rep-equivalents per second (time→kg·reps bridge) | operator prior (uncited) | — | #32 | Q156 |
| `E1RM_WINDOW_DAYS` | load_events | 60 | rolling window (days) for the per-template e1RM fit | operator prior (uncited) | — | #32 | Q156 |
| `H_NO_E1RM` | load_events | 0.5 | h(I) fallback when a template has no in-window e1RM fit | operator prior (uncited) | — | #32 | Q156 |
| `_mech_mult (bands)` | load_events | 1.0 / 1.15 / 1.30 | mechanical band multiplier at RIR ≥4 / 2–3 / 0–1 | operator prior (uncited) | — | #32 | Q156 |
| `_f_rir (table)` | load_events | {0:1.0, 1:0.9, 2:0.75, 3:0.5, 4:0.25, ≥5:0.0} | NM proximity-to-failure factor by RIR | operator prior (uncited) | — | #32 | Q156 |
| `_nm_reps_prior (bands)` | load_events | 0.6 / 0.35 / 0.15 | RPE-absent NM reps-band prior at reps ≤5 / 6–11 / ≥12 | operator prior (uncited) | — | #32 (imputation path #302) | Q156 |
| `_h_intensity.base` | load_events | 0.25 | h(I) floor | operator prior (uncited) | — | #32 | Q156 |
| `_h_intensity.span` | load_events | 0.75 | h(I) span above the floor | operator prior (uncited) | — | #32 | Q156 |
| `_h_intensity.I0` | load_events | 0.40 | h(I) intensity onset (I below which h stays at the floor) | operator prior (uncited) | — | #32 | Q156 |
| `_h_intensity.width` | load_events | 0.45 | h(I) ramp width in intensity units | operator prior (uncited) | — | #32 | Q156 |
| `Epley divisor` | load_events | 30 | Epley e1RM: `w·(1 + (reps + RIR)/30)` | cited | Epley 1985 — standard 1RM formula (cite as such; no verification needed) | standard formula | — |
| `ZONES` | load_events_metabolic | (1, 2, 3, 4, 5) | the five HR-zone indices (structural; weights in `EDWARDS_WEIGHTS`) | derived | structural — zone labels, not a tunable weight | #251 | — |
| `EDWARDS_WEIGHTS` | load_events_metabolic | {1:1, 2:2, 3:3, 4:4, 5:5} | zone weight `z` for Σ (minutes in zone z)·z TRIMP | cited | Edwards 1993 (module docstring) | #251 | a per-zone weighting validated for this athlete |
| `TRIMP minute divisor` | load_events_metabolic | 60 | seconds→minutes in the Edwards TRIMP sum | derived | unit conversion (s→min) | #251 | — |
| `TAU_FITNESS_DAYS` | load_metrics | 42 | fitness EWMA time constant (channel-invariant) | cited | Coggan & Allen (practitioner convention, not peer-reviewed); McGregor 2007 MSSE (abstract, n=1 elite runner: τ_fit 42 best) — chat-verified 17 Sep 2026, Consensus | #18 | Q156; τ does not transfer across TL methods (Vermeire 2021 IJSPP) |
| `TAU_FATIGUE_DAYS` | load_metrics | {mechanical:10, neuromuscular:6, metabolic:4} | per-window fatigue EWMA time constant | operator prior (uncited) | strength-window priors, NOT the 42/7 aerobic convention; τ_metabolic=4 sits against McGregor 2007 (τ_fat 3 uncorrelated, 14 best) and Vermeire 2021 (τ must be fitted per TL method) | #18 | **Q156 — τ_metabolic=4 is the first harness item**; mech 10 / nm 6 follow |
| `FORM_K` | load_metrics | 1 | `form = fitness − k·fatigue` (Coggan/Allen TSB = CTL − ATL) | cited | k=1 is the Coggan/Allen TSB convention; Banister-family models are descriptive, not predictive — Busso 2023 MSSE (chat-verified 17 Sep 2026, Consensus). Display, not authority. | #18 | a criterion fit preferring k≠1 (Q156) |
| `ACUTE_DAYS` | load_metrics | 7 | ΔLoad acute window; also the banister-v4 first-week seed window | operator prior (uncited) | 7-in-28 spike primitive | #33 (windows #249) | descriptive reclassification (#306, WP-B); Q156 |
| `CHRONIC_DAYS` | load_metrics | 28 | ΔLoad chronic window (coupled trailing mean per #249) | operator prior (uncited) | 7-in-28 spike primitive; coupling effect small in practice (Coyne 2019, WP-B) | #33 (windows #249) | uncoupled-chronic OQ (WP-B) |
| `MATURITY_DAYS` | load_metrics | 42 | a window's curve reads 'low' confidence until this much continuous history (≈ one fitness τ) | operator prior (uncited) | chosen ≈ 1·τ_fit; coincides numerically with `TAU_FITNESS_DAYS` but is a separate literal | #18 | Q156 |
| `seed_window (banister-v4)` | load_metrics | = `ACUTE_DAYS` (7) | first-week-mean stock seed window | derived | = `ACUTE_DAYS` (#304); motivated by the EWMA initial-load problem — Wang 2020 Sports Med (chat-verified 17 Sep 2026, Consensus) | #304 | window length on a series restart (Q156) |

_23 rows. 13 module-level `UPPER_CASE` constants (auto-collected by the drift guard) + 10
function-embedded / derived coefficients (the guard's explicit allow-list). See
`backend/tests/test_load_constants_provenance.py`._
