# Capability Taxonomy v1 — the ratio layer (Q27)

**What this is.** The v1 companion text for `backend/engine/taxonomy.py` (`TAXONOMY_VERSION = "v1"`).
`Capability_Taxonomy_v0.md` lives in project knowledge, not in this tree, so Code cannot edit it in
place: this file carries the v1 sections in full and the reframed §F, for chat to fold into that
document (transport per CLAUDE.md "Chat→Code file transport", in reverse). Where the two disagree on
the axis list, `taxonomy.py` wins; this file records why it says what it says.

The expectations below are FLAGS, not verdicts, as in v0. No numeric norm lives in code.

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
| `same_protocol` | both readings must come from the same protocol | **declarative only** until observations carry protocol provenance |
| `reference_kind` | `internal` or `literature`, below | closed vocabulary, yes |
| `expectation`, `confidence` | text flag; bands marked "to populate"; confidence GUESSING | text only |

### `reference_kind`

Declared on every `Measure` and every `Ratio`. The rule:

> A **literature** band applies as a threshold ONLY when the observation's instrument and protocol
> match the norm's. Otherwise the **internal** baseline / trend governs, and the literature gives
> DIRECTION only.

`Measure.reference_kind` defaults to `internal`, the restrictive reading: a measure that has not
declared a literature reference cannot have one applied. The rule needs the observation's instrument
and protocol, which `capability_observations` does not yet record (see "Provenance" below), so today
it is a statement of intent that nothing can evaluate. That is why no deficit flag fires from a Ratio.

---

## Group H — joint-action strength

One region per joint action, so a ratio can be declared across two of them. All six are `STRENGTH`,
per-side, `queue_eligible=False`, `probe_priority=False`, `needs_norm=True`, confidence GUESSING.
Admitted under #335 (tested as a ratio denominator, or trained and tested).

| Region | Plane | Measures | Role |
|--------|-------|----------|------|
| `shoulder_er` | transverse | `hhd_force_n` (N, literature) | numerator of `er_ir` |
| `shoulder_ir` | transverse | `hhd_force_n` (N, literature) | denominator of `er_ir` |
| `hip_adduction` | frontal | `hhd_force_n` (N, literature); `squeeze_mmhg` (mmHg, literature, bilateral) | numerator of `add_abd` |
| `hip_abduction` | frontal | `hhd_force_n` (N, literature) | denominator of `add_abd` |
| `ankle_plantarflexion` | sagittal | `sl_heel_raise_reps` (count, literature) | absolute + internal baseline; no ratio |
| `knee_flexion` | sagittal | none declared | absolute eccentric + LSI; **no H:Q ratio** |

Notes:

- `shoulder_er_ir` is retired (split into `shoulder_er` + `shoulder_ir`, R1). `gates=("dip",)` is carried
  onto BOTH halves; which action actually gates dip is unruled.
- `knee_extension` is not admitted (R3). Leg extension stays adjudicated no-pattern.
- Copenhagen plank is tagged `hip_adduction` as exposure only. It does not feed `add_abd`.
- `ankle_plantarflexion` is plantarflexion STRENGTH, never `ankle_df` (dorsiflexion MOBILITY).

---

## Measurement routes

| Route | What | Reference | Equipment | Status |
|-------|------|-----------|-----------|--------|
| (i) log-derived | Same setup both sides from the training log, e1RM-normalised | INTERNAL baseline and trend; literature gives direction only | none | declared in the model, **computation not built** |
| (ii) protocol probe | Handheld dynamometry (HHD), squeeze, single-leg heel raise | literature band, where instrument and protocol match | HHD is **EP-administered** at the clinic (R4); no HHD purchase. A BP cuff for the adductor squeeze is an optional operator buy | measures declared; no observation yet |

Route (i) is why the logged ER:IR (a cable-load ratio, 6.25 : 11.25 kg = 0.56) cannot be sized against
the ~0.66-0.75 band (an isokinetic-torque reference): unlike instruments, so a gap between them is not
a deficit. The band quoted in `expectation` text is Q27's citation, unverified, marked "to populate".
An HHD-force ER:IR needs its own HHD-specific reference before it can act as a threshold.

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
  squeeze-pressure (mmHg) norm. `hip_adduction/squeeze_mmhg` is declared `literature` per the brief, but
  no mmHg band has been verified; see Open items.

---

## Open items

- **Route (i) computation** is not built. Declared only.
- **Provenance.** `capability_observations` has `method` (baseline_battery / probe / session / manual)
  and `source` (self_report / catapult / hevy / polar / manual) plus an unqueried free `context` JSON.
  It has no `administered_by`, and no structured instrument or protocol. Until it does, the
  `reference_kind` match rule and `same_protocol` cannot be evaluated. Migration designed and HELD for
  the operator (schema migrations are held).
- **Who gates dip** (`shoulder_er`, `shoulder_ir`, or one of them) is unruled.
- **`knee_flexion` has no declared measure**, so its absolute + LSI read has nothing to be observed on.
- **`squeeze_mmhg` literature basis** is unverified (see Grounding).
