# Capability Taxonomy v1 — the ratio layer (Q27)

**What this is.** The v1 companion text for `backend/engine/taxonomy.py` (`TAXONOMY_VERSION = "v1"`).
`Capability_Taxonomy_v0.md` lives in project knowledge, not in this tree, so Code cannot edit it in
place: this file carries the v1 sections in full and the reframed §F, for chat to fold into that
document (transport per CLAUDE.md "Chat→Code file transport", in reverse). Where the two disagree on
the axis list, `taxonomy.py` wins; this file records why it says what it says.

The expectations below are FLAGS, not verdicts, as in v0. **No number fires a verdict** (G3, amended
from "no numeric norm in code"): published norms are DATA in `backend/reference/capability_norms_v1.json`,
displayed as a band only when an observation's provenance matches the norm's protocol, and never compared
to produce a pass, a fail, a grade or a clearance. The section 7 boundary is unchanged.

---

## §F (reframed) — the ratio layer

v0 §F was the symmetry layer: a per-side region read as a limb symmetry index (LSI), lower side over
higher side. v1 keeps that and names the family it belongs to. A **ratio** is a read DERIVED from two
observations, computed at read time, never stored. There are two kinds:

| Kind | Compares | Example | Declared as |
|------|----------|---------|-------------|
| Inter-limb (LSI) | the same measure, left vs right | single-leg hop distance L/R | `observations.symmetry()`; not a `Ratio` (unchanged) |
| Intra-joint agonist:antagonist | two measures on one joint, same side | ER:IR; adductor:abductor | `taxonomy.Ratio` (`er_ir`, `add_abd`) |

A Ratio is **a new taxonomy type: not a Region, not a Measure.** A Region is something you can load or
test; a Measure is a quantity recorded on a region; a Ratio is `numerator / denominator` across two
declared `(region, measure)` pairs. It has no row of its own, so it cannot drift from the observations
it came from.

### Axes of a Ratio

| Axis | Meaning | Enforced? |
|------|---------|-----------|
| `numerator`, `denominator` | `(region_key, measure_key)`; both must resolve and share a unit | yes, `validate_ratio` at import |
| `same_side` | pairs left with left, never across limbs; needs both measures per-side | yes |
| `same_protocol` | both readings must come from the same protocol | yes: `engine/reference.py` treats a mismatch as `internal` |
| `reference_kind` | `internal` or `literature`, below | closed vocabulary, yes |
| `expectation`, `confidence` | text flag (no number in it); confidence GUESSING | text only |

### `reference_kind`

Declared on every `Measure` and every `Ratio`. The rule:

> A **literature** band applies as a threshold ONLY when the observation's instrument and protocol
> match the norm's. Otherwise the **internal** baseline / trend governs, and the literature gives
> DIRECTION only.

**The gate fails closed.** An observation with no provenance is evaluated as `internal`, whatever the
declaration says. Provenance is `administered_by` + `instrument` + `protocol` on `capability_observations`
(migration `705a17c84d9a`), **all-or-nothing**: all three or none, `instrument` equal to the protocol's
declared instrument, and the observed measure a target of that protocol. A legacy row with none stays
`internal` forever. `engine/reference.py::evaluate_reference` returns `literature` only when the declaration
is `literature`, every observation has complete and consistent provenance, a ratio's two halves share one
protocol, and a norm is cited for `(target, protocol)`; otherwise `internal` with the reason named
("declaration internal", "no provenance", "protocol mismatch", "no norm for protocol"). It returns the band for
display and never a comparison, a flag or a grade.

**When a measure flips to `literature`.** Only when a norm matching its instrument AND protocol is cited in
the norms registry; a test pins the pairing both ways (every `literature` declaration has a cited norm, every
`internal` one has none), so a later admission flips the declaration and adds the norm in one change.

| Declared `literature` | Norm (protocols) |
|---|---|
| ratio `er_ir` | Riemann 2010: ratio 0.86-0.99 (seated neutral, seated 30-30-30, prone 90-90) |
| `shoulder_er` / `shoulder_ir` `hhd_force_n` | Westrick 2013, per body weight (seated neutral, supine 45 deg) |
| ratio `add_abd` | Mosler 2016: 1.2 +/- 0.2 (side-lying eccentric) |
| `hip_adduction` / `squeeze_hhd_n` | Mosler 2016: 3.6 +/- 0.8 N/kg (supine 45 deg squeeze) |
| `hip_adduction` / `squeeze_mmhg` | Delahunt 2011: 236.8 +/- 47.3 mmHg (supine 45 deg cuff squeeze); **cuff ceiling caveat below** |
| `ankle_plantarflexion` / `sl_heel_raise_reps` | Hebert-Losier 2017: median 24 (10 deg incline to fatigue) |

Stay `internal`, no norm admitted: `hhd_force_n` on `hip_adduction`, `hip_abduction` and `knee_flexion`
(Mosler's absolute adduction and abduction are Nm/kg torque, not force), and `slhb_reps`.

---

## Group H — joint-action strength

One region per joint action, so a ratio can be declared across two of them. All six are `STRENGTH`,
per-side, `queue_eligible=False`, `probe_priority=False`, `needs_norm=True`, confidence GUESSING.
Admitted under #335 (tested as a ratio denominator, or trained and tested).

| Region | Plane | Measures | Role |
|--------|-------|----------|------|
| `shoulder_er` | transverse | `hhd_force_n` (N, literature) | numerator of `er_ir` |
| `shoulder_ir` | transverse | `hhd_force_n` (N, literature) | denominator of `er_ir` |
| `hip_adduction` | frontal | `hhd_force_n` (N, internal); `squeeze_hhd_n` (N, literature, bilateral); `squeeze_mmhg` (mmHg, literature, bilateral) | numerator of `add_abd` |
| `hip_abduction` | frontal | `hhd_force_n` (N, internal) | denominator of `add_abd` |
| `ankle_plantarflexion` | sagittal | `sl_heel_raise_reps` (count, literature) | absolute + internal baseline; no ratio |
| `knee_flexion` | sagittal | `hhd_force_n` (N, internal); `slhb_reps` (count, internal) | hamstring strain-risk profile (below); **no H:Q ratio** |

Notes:

- `shoulder_er_ir` is retired (split into `shoulder_er` + `shoulder_ir`, R1). The old `gates=("dip",)` was
  dropped from both halves by the operator's ruling: dip is ungated (it is probe-inert, so nothing changes).
- `knee_extension` is not admitted (R3). Leg extension stays adjudicated no-pattern.
- Copenhagen plank is tagged `hip_adduction` as exposure only. It does not feed `add_abd`.
- `ankle_plantarflexion` is plantarflexion STRENGTH, never `ankle_df` (dorsiflexion MOBILITY).

### `knee_flexion` — declared outcome (R3 amended by R7, R7a)

R3 said "absolute eccentric + LSI". With the EP's instrument unconfirmed, that is amended to: **absolute
eccentric + LSI where an eccentric instrument exists (NordBord / isokinetic, pending the EP); until then,
isometric HHD gives absolute + LSI and the single-leg hamstring bridge gives functional endurance + LSI.**

The region answers a **hamstring strain-risk profile** with three parts:

| Part | Served by |
|------|-----------|
| (a) absolute capacity | `hhd_force_n` (isometric proxy); a NordBord eccentrically, when one exists |
| (b) left/right symmetry (LSI) | `slhb_reps`, `hhd_force_n`; a NordBord when one exists |
| (c) endurance in the hip-extended / knee-flexed position | `slhb_reps` (a FUNCTIONAL read; needs no analogue instrument) |

An analogue output is needed only for (a) against a literature band, and a NordBord is the only instrument
with a strain-risk band behind it (Jeanguyot 2023: professional footballers 297 N, 4.2 N/kg; it becomes a
norm only when a NordBord protocol is declared). No NordBord measure is declared until the EP confirms the
instrument. Neither declared measure has an admitted norm, so both read `internal`.

---

## Measurement routes

| Route | What | Reference | Equipment | Status |
|-------|------|-----------|-----------|--------|
| (i) log-derived | Same setup both sides from the training log, e1RM-normalised | INTERNAL baseline and trend; no norm shares the instrument | none | **built** (`engine/log_strength.py`, `engine/ratios.py`) |
| (ii) protocol probe | Handheld dynamometry (HHD), squeeze, single-leg heel raise, single-leg bridge | literature band, where instrument and protocol match | HHD is **EP-administered** at the clinic (R4); no HHD purchase. A BP cuff for the adductor squeeze is an optional operator buy | **built**: measures, protocols (`engine/protocols.py`), provenance and the gate |

**Route (i).** Per region, the templates are the `exercise_region_tags` rows with `role="primary"`; a
template's side is the tag's declared `side` (NULL reads as bilateral; never derived from a title). Per
session-day and per side the value is the best e1RM across that side's templates, using the shared
strength-read primitives (`reads/strength_reads.py`: same Epley, working-set rule and AEST day as the
See-test series). The **rep ceiling** is route (i)'s own: a set scores an e1RM only up to the ratio's
`log_rep_ceiling` (15, declared on the `Ratio`, 1 to 30), where the See-test series keeps its cap of 10.
When both halves are logged at the same rep count the Epley factor (1 + reps/30) cancels out of the ratio
exactly; for mismatched counts the distortion is the ratio of the two factors (under 6% within 2 reps, 12.5%
at 10 against 15). A ratio pairs numerator and denominator on the **same session-day only** (no window), per
side with sets in BOTH regions (left, right, or bilateral when both are bilateral; never mixed). A day that
does not pair is accounted for, in three counts per side: `paired_days`; `half_not_logged_days` (one region
has sets that day, the other has none); and `no_eligible_e1rm_days` (both have sets, at least one has none
scorable), each listed with the reason: `all_warmup` (every set flagged warm-up), `reps_over_ceiling` (a
working set above the ceiling) or `no_weight` (no working set with a weight above zero and reps in range; a
0 kg set never scores). A day with no sets is "not logged", not ineligible. `unpaired_days` is the sum of the
last two, deprecated for one release. `baseline` is the median of the first three
pairs, `current` the median of the last three pairs within 42 days of today (null when fewer than three are
that recent), `delta_pct` the move between them. There is no label, band or threshold. It never writes
`capability_observations`. Surfaces: `GET /engine/ratios`, `GET /engine/ratios/{key}`,
`GET /engine/log-strength?region_key=`, MCP `get_capability_ratios`.

**Route (ii).** The latest numerator and denominator that share a protocol and were taken within 14 days of
each other (two clinic visits are not one read), per side, with `evaluate_reference` deciding whether a band
may be shown beside the ratio.

Route (i) is why the logged ER:IR (a cable-load ratio, 6.25 : 11.25 kg = 0.56) is not sized against an HHD band:
unlike instruments, so a gap between them is not a deficit. The retired "~0.66-0.75" figure was an
isokinetic-torque reference; the HHD norms run 0.74-0.99 depending on position and are shown only on a
protocol match.

---

## Grounding

Pulled from PubMed 2026-10-11; the quoted figures are the abstracts' own words.

- **Adductor:abductor and groin strain.** Tyler TF, Nicholas SJ, Campbell RJ, McHugh MP. The association
  of hip strength and flexibility with the incidence of adductor muscle strains in professional ice
  hockey players. *Am J Sports Med* 2001;29(2):124-8. PMID 11292035,
  [doi:10.1177/03635465010290020301](https://doi.org/10.1177/03635465010290020301). Prospective, NHL
  players (81 measured, 47 followed, 8 with adductor strains). The abstract reports adduction strength
  95% of abduction strength in uninjured players against 78% in injured players, and a player "17 times
  more likely to sustain an adductor muscle strain if his adductor strength was less than 80% of his
  abductor strength". **Not asserted here as a risk multiplier for this athlete or sport**: it is one
  small cohort of professional ice hockey players on that study's own dynamometry, and it is cited as
  grounding for the direction of the read, not as a threshold. It enters no code.
- **HAGOS is a PROM.** Thorborg K, Tijssen M, Habets B, et al. Patient-Reported Outcome (PRO)
  questionnaires for young to middle-aged adults with hip and groin disability: a systematic review of
  the clinimetric evidence. *Br J Sports Med* 2015;49(12):812. PMID 25586913,
  [doi:10.1136/bjsports-2014-094224](https://doi.org/10.1136/bjsports-2014-094224). Cite HAGOS for groin
  **symptoms and function**; it is not a strength norm and supplies no band for any Ratio here.
- **The Copenhagen five-second squeeze is a pain test.** Thorborg K, Branci S, Nielsen MP, et al.
  *Br J Sports Med* 2017;51(7):594-599. PMID 27935487,
  [doi:10.1136/bjsports-2016-096675](https://doi.org/10.1136/bjsports-2016-096675). Validated as a
  pain-rating indicator (NRS 0-10) against HAGOS Sport in football players. It does not establish a
  squeeze-pressure (mmHg) norm. (The cuff squeeze admitted below, Delahunt 2011, is a different test: an
  absolute pressure on healthy athletes.)

### Norms admitted (R6) — values read 2026-10-19

Each is a record in `capability_norms_v1.json` with `verified_against` = what was actually read.

- **ER:IR ratio.** Riemann BL et al. *J Shoulder Elbow Surg* 2010;19(8):1175-83. PMID 20850997,
  [doi:10.1016/j.jse.2010.05.021](https://doi.org/10.1016/j.jse.2010.05.021). Adults, n=181. The abstract gives
  the unilateral ER/IR ratio as 86% to 99% across limb, position and sex cells (**abstract only**; a
  per-position table was not reachable). Riemann recommends the 30-30-30 position.
- **Shoulder ER and IR force per body weight.** Westrick RB et al. *Sports Health* 2013;5(1):17-21. PMID 24381696,
  [doi:10.1177/1941738112456280](https://doi.org/10.1177/1941738112456280). 546 physically active males, 18.8 +/- 1.0 y
  (**full text**). ER 0.20 +/- 0.04 (neutral) and 0.22 +/- 0.05 (45 deg supine); IR 0.27 +/- 0.06 and 0.26 +/- 0.05.
  **The paper does not state the unit** (Table 3: "computed relative to body weight"); recorded as a dimensionless
  force / body-weight fraction, not N/kg, because 0.20 N/kg would be an implausible 15 N. A young cohort: direction
  only for a 45-year-old.
- **Adductor:abductor ratio and squeeze.** Mosler AB et al. *J Sci Med Sport* 2016;20(4):339-343. PMID 28185809,
  [doi:10.1016/j.jsams.2016.05.010](https://doi.org/10.1016/j.jsams.2016.05.010). 394 male professional footballers
  18-40 (**abstract only**). Ratio 1.2 +/- 0.2; squeeze 3.6 +/- 0.8 N/kg. Absolute adduction 3.0 +/- 0.6 and abduction
  2.6 +/- 0.4 are **Nm/kg torque, not force**, and are not admitted for `hhd_force_n`.
- **Cuff squeeze.** Delahunt E et al. *Man Ther* 2011;16(5):476-80. PMID 21429785,
  [doi:10.1016/j.math.2011.02.014](https://doi.org/10.1016/j.math.2011.02.014). 18 healthy male Gaelic athletes
  (**abstract only**): 236.8 +/- 47.3 mmHg at 45 deg hip flexion. Companion: Nevin & Delahunt 2013, controls
  269 +/- 25 mmHg (PMID 23684372, [doi:10.1016/j.jsams.2013.04.008](https://doi.org/10.1016/j.jsams.2013.04.008)).
  **Ceiling caveat (R9):** Toohey LA et al. 2017 found 16 of 32 community AFL players reached the maximal
  sphygmomanometer reading (PMID 28891759,
  [doi:10.1080/09593985.2017.1374492](https://doi.org/10.1080/09593985.2017.1374492)); the cuff maxes at about
  300 mmHg, so a reading at the maximum is censored, not a value. The cuff stays an optional operator buy.
- **Single-leg heel raise.** Hebert-Losier K et al. *Physiotherapy* 2017;103(4):446-452. PMID 28886865,
  [doi:10.1016/j.physio.2017.03.002](https://doi.org/10.1016/j.physio.2017.03.002). Healthy adults 20-81 y, BMI at
  most 30 (566 of 600 recruited); 10 deg incline, **metronome 60 cycles/min**, fingertip wall support, test ends when the
  heel cannot be lifted or the pace/posture cannot be held (read from the **accepted manuscript**, not the published
  PDF). Median 24 for males (abstract; females 21); the paper's quantile model makes the male median fall from 37.5
  at 20 to 24 at 50, so 24 is the figure for the stated protocol, not an age-matched one.

### Grounding only (no norm admitted)

- Cools AM et al. 2016, HHD database of overhead athletes. PMID 26294055,
  [doi:10.1007/s00167-015-3755-9](https://doi.org/10.1007/s00167-015-3755-9) (abstract: 201 athletes, 18-50 y, ER/IR
  isometric and eccentric normalised to body weight; numeric values not read).
- Jeanguyot E et al. 2023, NordBord, professional footballers 297 N / 4.2 N/kg. PMID 37867754,
  [doi:10.5114/biolsport.2023.125585](https://doi.org/10.5114/biolsport.2023.125585) (**full text**). Becomes a norm
  only when a NordBord protocol is declared.
- Freckleton G, Cook J, Pizzari T. 2014, single-leg hamstring bridge predictive validity. PMID 23918443,
  [doi:10.1136/bjsports-2013-092356](https://doi.org/10.1136/bjsports-2013-092356) (**full text**): 482 players, 28
  hamstring injuries; the protocol is a 60 cm box, knee at about 20 deg, arms crossed, repetitions to failure, no metronome.

---

## Open items

- **NordBord / eccentric measure for `knee_flexion`.** Pending the EP's instrument. No NordBord measure or
  protocol is declared until they confirm what they can test and what, if anything, they would use instead.
- **Cuff ceiling.** The sphygmomanometer squeeze reads at most about 300 mmHg (Toohey 2017); a reading at the
  maximum is censored and is recorded with `confidence="guessing"`. The cuff is an optional operator buy.
- **Westrick's unit.** Recorded as a dimensionless force / body-weight fraction (the paper never states it); awaiting
  operator ratification, as is the inference that the paper's "neutral" test is the seated protocol.
- **Abstract-only norms** (Riemann, Mosler, Delahunt): values taken from the PubMed abstract; the Methods (the
  Thorborg-protocol attribution, Delahunt's best-versus-mean) were not reachable. Marked `abstract_only` in the registry.
- **EP ask list** (open, non-leading): which shoulder rotation test position and protocol they use (so the matching
  `protocol` key is recorded); whether they test hip adduction / abduction eccentrically in side-lying; whether they can
  test eccentric hamstring strength (NordBord or isokinetic) and what they would use instead.
- **Silent skip of an unknown region key** in the constraint engine (`selection.py`): OPEN_QUESTIONS.
