# Session close-out — Q6 gate 1 (Hevy strength persistence), landed + live-verified

## 1. Real commits this session

`git log --oneline 5ae8a07..HEAD` (session-open ref `5ae8a07`, before the close-out commit):

```
d5875a3 Merge pull request #105 from Easty11/claude/hevy-strength-persistence-24nkkj
cb28231 test(substrate): enforce SQLite FKs suite-wide + seed FK-blind fixtures (#239)
b42e32a Merge pull request #104 from Easty11/claude/hevy-strength-persistence-24nkkj
433a1f2 fix(hevy): flush parent before sets in workout ingest — FK ordering (#239 follow-up)
215435f Merge pull request #103 from Easty11/claude/hevy-strength-persistence-24nkkj
d86aadc gov: resolve #NEXT -> #239 at merge (master max 238 verified this instant)
52db768 gov: Q6 four-window load — record persistence + Tier-0 design (D-A..D-G)
5551c3d feat(hevy): persist Hevy workouts + sets — Q6 four-window load, gate 1
```

Plus this close-out commit (`chore: session close-out`).

Three PRs, all merged with merge commits, branch remote-deleted after each:
- **#103** `215435f` — persistence layer + governance (`#239`, D-A..D-G). Contained the schema
  migration `f9a2c1d40b73`; opened held per `#238`, merged on explicit operator instruction.
- **#104** `b42e32a` — the FK-ordering ingest fix (no schema; merge-on-green).
- **#105** `d5875a3` — suite-wide FK-enforced test substrate + 71 seeded fixtures (tests-only;
  merge-on-green).

## 2. Pending-queue reconciliation

No `;cc` pending-commit queue was carried into this session — it opened from a task brief, not a
chat close-out. Nothing provisional is outstanding. Every decision reached this session landed in
a commit above:
- Q6 four-gate re-scope, D-A..D-G design, Q115 annotation → `52db768`/`d86aadc` (in `#103`).
- FK-ordering fix → `433a1f2` (in `#104`). Test-substrate hardening → `cb28231` (in `#105`).
- Gate-1 DONE mark, `#240`, FEEDBACK §33, ROADMAP transform agenda, BRANCHES DONE row,
  CLAUDE.md Recent-landings → this close-out commit.

## 3. Cold-resume handoff

### What landed and is live
Q6 **gate 1 is DONE and live-verified.** `hevy_workouts` + `hevy_sets` on prod (migration
applied, deploy `9b6ad5de` SUCCESS on `d5875a3`). Backfill re-run on the fixed code:

- 56 workouts / 1710 sets; span **2026-04-05 → 2026-08-24** — the entire Hevy history fits inside
  180 d, so the store is **complete**, not merely a 180-day window.
- Dedup flagged exactly the two known same-day pairs (16/17 Jun VO2+Upper, 01 Jul Upper ×2).
  Operator excluded the planned-routine-artifact copy of each (`excluded_at`, larger set count +
  zero RPE) → **effective store 54 workouts / 1609 sets**.
- RPE coverage is ~100% of RPE-capable sets from the **mid-May 2026 epoch**; April is a bounded
  pre-RPE era. The raw 68.6% conflates that with the now-excluded artifacts (90 sets) and 34
  structurally RPE-incapable non-rep sets — record the corrected reading, not 68.6%.

### Current sprint / NOW
Q6 **gate 2 — the `load_events` transform** (next session; spec review precedes build). Agenda,
chat-settled (full detail in ROADMAP "Banister build"):
1. Missing-RPE rule — rep-based sets before the operator-set mid-May-2026 epoch band by reps
   alone; after it, full (reps, RPE) banding; non-rep sets per D-D. No RPE imputation ever; e1RM
   fitted from RPE-present sets only (RPE-absent sets consume, never update).
2. D-C coefficients + band table; D-D bridging constant (kg·m / kg·s → kg·reps).
3. The transform reads `excluded_at` from day one.
4. **Fix `_rpe_coverage`** — denominator must be `reps IS NOT NULL` + excluded-aware, not
   `type='normal' AND weight_kg NOT NULL`; as-is it misreports every future sync (a real carried
   code defect, deferred here deliberately).
5. Candidate hardening — Hevy planned-vs-performed artifact dedup by signature (0-RPE post-epoch
   rep-based workout, usually a same-day full-RPE partner).

### Open questions by status
- **Q6** — OPEN; gate 1 DONE, gates 2–4 sequenced. Closes `DONE → #28` when gate 2 lands and
  gate 4's query shows strength volume non-zero in per-window `load_metrics`.
- **Q115** — OPEN (supramaximal routing amendment); D-B removed its migration-cost urgency, the
  discriminator design pass remains its substance.
- **Q116 / Q118 / Q119 / Q120** — OPEN, untouched this session (HC-sync backfill/metadata; the
  schedule-item backfill; the injuries edit-supersede lane).

### Single clearest next action
Before the transform can compute load: **operator tags Kneeling Leg Curl laterality and clears the
`audit_laterality_coverage` worklist** (forward operator items, gate the first load computation).
Then open the gate-2 transform session against the ROADMAP agenda.

### NOT touched this session — name the standing lanes
This session and the two before it were **instrument, not product**: persistence + its test
substrate, following `#237` (an operator *view*) and `#234–236` (a sync *contract*). The health
*intelligence* — the thing being instrumented — has not moved in three sessions:
- **The four-window load engine itself** (gates 2–4) is still entirely unbuilt. Gate 1 only
  stores the substrate; no strength load is computed, and `mcp_server.get_training_load` is still
  aerobic-only ACWR (`#8`).
- **The Banister fitness-fatigue model** (this ROADMAP row's original subject) is unbuilt; only
  `naive_baseline` is displayed.
- **CBT-I user surface** (Q60/Q47) — engine built, still invisible in the app; no route/page/nav.
- **Injuries edit-supersede lane** (Q120) and the readiness model behind `model_forecast` remain
  spec-only.
The next session that isn't the gate-2 transform should be a product lane, not another instrument.
