# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-25 · Free-text AM/PM notes on the daily record (#125) — both surfaces, deployed and verified

## 1. Real commits this session

Session-open ref: `e47e867` (the prior close-out ritual). Three commits on `feat/daily-notes`,
ff-merged to **master @ `a4bfd39`**, pushed; branch deleted.

```
a4bfd39 governance: CLAUDE.md recent-landings — prepend #125
dcaeed7 governance: DECISIONS_LOG #125 — free-text AM/PM notes on the daily record
7e5372c feat: free-text am_notes / pm_notes on the daily record, both check-in surfaces
```

DECISIONS max **#125**; questions max **Q48**. Migration `f1a4c7e29b83` (two nullable `Text` columns,
`am_notes`/`pm_notes`) chained off the real head `d3f7a1908c62` — the Step-A VERIFY caught that the ISI
migration had superseded the brief's stated `b2d5f9e04a17`. Both services deploy-verified per #121:
backend `alembic current = f1a4c7e29b83` with both columns present in prod, OpenAPI carries the fields;
frontend bundle carries the textarea label — each with a negative control. Suite **406 passed** (was 401).

## 2. Pending-queue reconciliation

No `;cc` queue carried in. Nothing decided is uncommitted. Two columns, not one, because the AM and PM
surfaces submit independently — asserted by a test that a PM submit does not clobber `am_notes`. The
notes are observational: read by no engine code, not block-gated. **Usable tonight** — a note logged in
the AM/PM check-in lands on the daily record.

**Deliberately excluded (next brief, per this brief's GUARD):** the external-disruption boolean and the
`n_alcohol_unknown` retirement — both touch `classify_night` and both have open VERIFYs
(the `TRAINING_RECOVERY_MIN` constrained-night path; whether the alcohol flag is stored or derived).

## 3. Cold-resume handoff

**Branch:** `master @ a4bfd39`, level with origin. **Branch gate — passes.** `feat/daily-notes` merged +
deleted. Four parked branches, untouched this session, all rowed in `BRANCHES.md`:
`feat/checkin-injury-probe` (+2), `feat/feedback-ledger` (+4), `feat/interpretation-view-skeleton` (+3),
`feat/recovery-metrics-rhr` (+1). None in limbo.

### CBT-I is capture-complete + instrumented — one build-piece left

Block 3 runs live: AM diary + prefill + 4h gate, PM prescription display + nap capture, ISI baseline, the
settling instrument (#124), and now free-text notes (#125). The one remaining piece to **close** a cycle
in-app is the **manual evaluation trigger** (#118's PM-offer half) — a dependency, not a deferral: it
cannot fire before ~31 Jul (needs a full cycle; block opened 24 Jul). When built it also supplies #124's
`nights_since_effective_from`.

### ROADMAP is date-anchored (#123) — read NOW top-to-bottom

NOW (6 rows): **Q45 nap attribution** (contaminating capture now) · **manual evaluation trigger**
(~31 Jul) · **lab pipeline** · **interpretation 4b + Q36–Q41** · **appointment brief** (early-Aug TRT
panel) · **cross-repo propagation** (undated, pinned to NOW by #112). NEXT 19; LATER 6.

**Single clearest next action:** the **manual evaluation trigger** — the first dated Code build, due
~31 Jul; nothing in NOW is buildable before then. Running in parallel, not a Code task: **Q45** — Luke
resolves the nap day-attribution from the VA CBT-I protocol docs or the clinician.

### Open questions — 34 live (14 DONE in `## CLOSED`)

- **OWED (5):** Q4, Q6, Q13, Q15, Q18. **BLOCKED (2):** Q24, Q29.
- **UNSTARTED (27):** incl. **Q45** (nap attribution — gates CBT-I validity), **Q46/Q47** (basis
  provenance; adherence lag), **Q48** (settling period — block 3 is the dataset, #124), the **Q36–Q41
  interpretation 4b package**, **Q42** (12h-clock scrape — re-scoped: 4h gate covers prefill only).

### OWED, carried across sessions

FEEDBACK **§18** stands. Cross-repo: HCA still greps 0 for #111's secret-rendering rule — propagate the
shared block byte-identically from an HCA-rooted session (ROADMAP NOW, pinned by #112). The `9688f2…`
co-occurrence test, the canonical-surface consistency guard, and the `total_`/`actual_` semantic
field-swap sit in NEXT. Block 3's 24–25 Jul nights predate PM nap capture (`naps_min = NULL`, #122).
