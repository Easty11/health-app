# Session close-out — Q6 tier0-v1 load refinements (#243 / #244 / #245), all landed + live

## 1. Real commits this session

`git log --oneline 7a31068..HEAD` (session-open ref `7a31068`, the prior close-out). Four PRs,
all merged with merge commits, branch remote-deleted after each:

```
4198f0f Merge pull request #112 from Easty11/claude/q6-gate2-load-events-9kejqs
c34e8d5 gov: resolve #NEXT->#245 at land; BRANCHES DONE, Recent-landings
c682545 gov: #245 bw_fraction — decision, Q121 gap-4 resolved, roadmap, branches
3abea06 feat(load): bw_fraction — per-template bodyweight fraction (#245)
ab2157d Merge pull request #111 from Easty11/claude/q6-gate2-load-events-9kejqs
4c9ee2c test(load): 13 Jul reconciliation fixture — the class-closer (#244)
768c233 fix(load): mint RIR banding as floor(10-RPE) — convention, not defect (#244)
ec02436 Merge pull request #110 from Easty11/claude/q6-gate2-load-events-9kejqs
cf273df gov: Q121 — add the flat-bodyweight-fraction Tier-0 gap (fourth)
4509a98 Merge pull request #109 from Easty11/claude/q6-gate2-load-events-9kejqs
6065db5 gov: #243 — record the non-rep bodyweight-COALESCE defect + window
2dc23e1 fix(load): weight-NULL non-rep sets score zero (exclude Hevy cardio)
```
Plus this close-out commit (`chore: session close-out`) on the restarted branch → a new
docs-only governance PR (merge-on-green; no schema).

- **#109** `4509a98` — `#243` non-rep bodyweight-COALESCE fix (weight-NULL non-rep scores zero →
  excludes Hevy cardio); no schema, merge-on-green. Deploy verified; corrected the inflated
  Mechanical from the `#242` recompute.
- **#110** `ec02436` — Q121 gap 4 (flat bodyweight fraction) recorded; docs-only.
- **#111** `ab2157d` — `#244`: the reported "fourth defect" **disconfirmed at the line** (mechanical
  was already `eff_w × reps × m`); RIR banding pinned to `floor(10 − RPE)` as a minted convention;
  the 13 Jul reconciliation fixture (56 real sets, hand-derived oracle) added; no schema.
- **#112** `4198f0f` — `#245`: `hevy_exercise_templates.bw_fraction` (schema migration `d4a1f8c609e2`),
  transform scales only 0/NULL-weight rep sets, worklist `audit_bodyweight_templates.py`; opened
  **HELD per `#238`**, merged on operator release. Backend deploy `34ea588f` SUCCESS, migration
  `c7d9e2f14a86 -> d4a1f8c609e2` applied clean, no dual-head signature.

## 2. Pending-queue reconciliation

No `;cc` pending-commit queue was carried in — the session ran from operator defect reports and a
build directive, not a chat close-out. Nothing provisional is outstanding. Every decision reached
landed:
- `#243` cardio-exclusion fix → `2dc23e1`/`6065db5` (#109). Q121 gap 4 → `cf273df` (#110).
- `#244` floor convention + reconciliation fixture → `768c233`/`4c9ee2c` (#111).
- `#245` bw_fraction (code + schema + worklist + governance) → `3abea06`/`c682545`/`c34e8d5` (#112).
- This close-out (`closeout.md`) → this commit.

**Operator-side follow-ups, NOT yet done (named so they are not lost):** the `bw_fraction` **tagging
pass** (`python backend/audit_bodyweight_templates.py` → assign live fractions per template) and the
**post-`#245` recompute + ranking re-read**. These are the operator's prod-credentialed residue; the
`load_events` rows are stale-at-×1.0 for bodyweight-class movements until that recompute runs.

## 3. Cold-resume handoff

### What landed and is live
Three tier0-v1 load refinements, all deployed:
- **`#243`** — a weight-NULL non-rep set scores zero (the cardio-exclusion mechanism; a leaked
  bodyweight COALESCE had priced treadmill/bike/row distance as mechanical work).
- **`#244`** — the reported "fourth defect" was **not one** (verified three ways: line, git history,
  runtime probe); RIR banding minted as `floor(10 − RPE)`; the **13 Jul reconciliation fixture** is
  now the standing guard — real 56-set session, Mechanical/NM asserted to the cent against a
  hand-derived arithmetic oracle, so a spec-vs-code gap can no longer pass a green suite.
- **`#245`** — per-template `bw_fraction`: a rep set with `weight_kg` NULL/0 scores
  `BODYWEIGHT_KG × COALESCE(bw_fraction, 1.0)`; a logged weight is never scaled. Promoted build-now
  ahead of gate 3 so the ×1.0 distortion never enters the EWMA history.

`formula_version` stays **`tier0-v1`** throughout (recompute, not migration — D-B). Post-`#244`
rankings passed operator **face-validity 5/5** (2026-08-26); the tier0-v1 constants are **frozen**
under the `#244` conventions (floor RIR, 0-falsy bodyweight, load-sums-as-logged, non-rep skip). Q6
itself is DONE (`#242`).

### Current sprint / NOW
1. **Operator (prod-credentialed):** run the `bw_fraction` tagging pass from
   `audit_bodyweight_templates.py`, then the recompute + ranking re-read. Until then the bodyweight-
   class rows are priced at ×1.0.
2. **Then Gate 3 — `load_metrics` daily rollup + the Banister fitness-fatigue model** (per `#32`):
   four independent Fitness/Fatigue channels, per-window τ (Mechanical ~10 d slowest, Neuromuscular
   ~6 d, Metabolic ~4 d, Fitness ~42 d), no global fatigue term, Neuromuscular fed by velocity/RFD
   never raw CMJ. Recomputable from `load_events` (D-B). This wires the strength term into a
   **consumed** metric and retires the aerobic-only ACWR of `#8`. **Contains a schema migration →
   its PR opens HELD for release per `#238`/`#242`.**

### Open questions by status
- **DONE this arc:** Q6 → `#242`; Q121 **gap 4** → `#245`.
- **OPEN, load-adjacent (not blocking gate 3):** `Q121` — three Tier-0 gaps remain: the **additive**
  weighted-bodyweight case (bodyweight + plate; needs the e1RM fit on the coalesced load, and the
  Hevy assisted-set sign is UNVERIFIED), non-rep NM = 0, half-point RIR banding (now `floor`). `Q117`
  (three `expected_load` levels enough?).
- **OPEN, unrelated to load:** `Q120` (injury onset field), `Q118` (Health Connect record metadata
  dropped), `Q116` (`schedule_item` validator backfill).

### Single clearest next action
Operator: run `python backend/audit_bodyweight_templates.py`, tag the bodyweight-class templates,
recompute, re-read rankings. Then Code builds **gate 3** (`load_metrics` + Banister, `#32`).

### What was NOT touched this session (name the standing lanes)
This session — like the three before it — went entirely to the **load instrument** (Q6). Four
consecutive sessions have now built, corrected, and re-corrected the strength-load substrate
(gate 1, gate 2, then the `#243`/`#244`/`#245` refinements); **no user-facing product has moved in
that span.** Standing still, explicitly:
- **CBT-I user surface (interim)** — the titration engine (`cbti/`) is built but invisible in the
  app: no route/page/nav. Gated on `#47` (show engine state vs the MOVE/REVERSE verdict) + the
  diary-capture fork. Untouched.
- **The `#116`/`#121` frontend deploy probe** — the served-bundle grep that would confirm a frontend
  deploy remains owed from earlier sessions; never run.
- **Medical Protocol and Decision Support modules** — the other two of the three platform modules;
  no work this arc (Fitness/load lane only).
- **`Q120` injury-onset** and the ROADMAP injury reframe / edit-supersede lane — untouched.
- **Parked latent hazard:** the pre-existing second alembic head `e2d5c7a1b9f3` (predates the Q6
  lane) — deploys boot clean with both heads, but a future single-linear-head migration or an
  `alembic upgrade head` (singular) path trips `Multiple head revisions`. Resolve with a merge
  migration when that lane is picked up (`#242`/`#245`). Not this lane's to fix.
