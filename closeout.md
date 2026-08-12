# Close-out — 2026-08-12 (ROADMAP hygiene: strike Hevy step-2, add adaptive-programming lane)

## Real commits this session

Session-open ref: `71880e2` (prior master tip). `git log --oneline 71880e2..HEAD`:

```
2db9b29 Merge pull request #59 from Easty11/chore/roadmap-adaptive-lane
b24b7c9 chore(roadmap): strike discharged Hevy step-2 row; add adaptive-programming lane to NEXT
```

Diff touched **`ROADMAP.md` only** (3 insertions / 2 deletions). Landed via PR #59,
`--merge --delete-branch`, fast-forward to `2db9b29`. Placeholder guard (POSIX) passed.
Both removed lines sat inside declared replacement regions (header date; the struck Hevy
row), so #176(c) guard-gated landing held.

The close-out commit itself follows this write (governance: `CLAUDE.md` Recent-landings
prepend + 3-cap trim, `closeout.md`, and the BRANCHES self-row).

## Pending-queue reconciliation

**PENDING carried in from `;cc`: none.** The chat close-out reported "PENDING — nothing
from this session." Both `;cc` adjudications resolve to **no repo write**, confirmed:

1. **Mint fork → NO MINT.** No DECISIONS_LOG entry was minted for the adaptive-lane
   placement. Provenance is row-carried via the NEXT row's citations (#75 frame, Q27,
   #21, #163/#164/#166). The three-conjunct mint filter fails on conjunct 1 (session
   objective was governance housekeeping, not product/tooling work). Closed unless Luke
   overrides. Nothing provisional — the strike and lane are committed on master.

2. **Precision nit → BATCHED, not spun.** The adaptive-lane NEXT row reads
   "custom-exercise creation live end-to-end (#163/#164/#166)". This overstates #166 by
   exactly the create→list-back round-trip that **Q77 holds open** (the Copenhagen orphan
   is confirmed absent from the store — the create fired, ingestion-side proof owed). It
   does not change the lane's precondition (substantively met either way), so per the
   severity gate it rides the **next** ROADMAP touch: swap to "wired and live-fired;
   round-trip proof owed (Q77)". No write this session; Q77 already tracks the underlying
   debt. **This is the one deliberately-deferred wording correction — apply it on the
   next ROADMAP edit, do not spin a branch for it alone.**

## Cold-resume handoff

**Session class: INSTRUMENT/governance.** This session moved only `ROADMAP.md` (a
re-triage: one discharged lane struck, one future lane placed). No product or feature
code ran. See "What was NOT touched" below — it is the larger part of the state.

### What landed
- Hevy custom-exercise-creation **step-2** lane struck DONE in ROADMAP (orphan table above
  LATER): step-1 prod gate closed #163 (494→499), `<hevy_create_exercise>` #164,
  response-tolerance #166 confirmed a live create. Q75 (catalogue freshness) stays OPEN,
  **not** closed by the strike.
- **Adaptive-programming lane** added to ROADMAP NEXT: Plan schema (steps 2–4 of the
  exercise-catalogue sequence) + capability-taxonomy v1 (Q27), framed by #75 (Plan wraps
  the Adaptive Exposure Engine — cycle/slots/cardinality Plan-owned, probe/fortify region
  selection stays engine-side). Target: offseason Block A (~Sep). Its placement now lives
  on master, closing the memory-only gap.

### Maxima at close
- Decisions max: **#210**. Questions max: **Q99**. (Note for the record: the `;cc`
  open-report claimed #206/Q99 from memory; master read #210/Q99 — the re-read-at-open
  rule caught a four-behind recall. Chat is updating its ledger.)

### Current sprint — ROADMAP NOW (dated, by external date)
1. **CBT-I: resolve Q45 nap day-attribution** — DATED, contaminating capture now
   (`naps_min` date−1 read live for block 3, unverified; now also gates a second user at
   the 4-night cadence, Q78). Close from VA CBT-I protocol docs / clinician, not the
   workbook. Owner: Luke. **This is the dated head of the queue.**
2. **CBT-I: manual witnessed evaluation trigger** — BUILT but SUPERSEDED, needs REWORK
   (`feat/cbti-eval-trigger`, OWED — see below). Do not force-merge.
3. Lab upload pipeline (uploading unpaused; junk-row operator decision owed).
4. Interpretation layer build (1b delivered; increments 2/3/5 remain — see below).
5. Appointment brief (depends on lab pipeline + interpretation).
6–8. Cross-repo shared-block propagations to `health-connect-app` (all OWED, HCA-rooted).

### Open questions (grouped)
- **OPEN, pre-existing, untouched this session:** Q45 (nap attribution — dated head),
  Q75 (Hevy catalogue freshness), Q77 (custom-create round-trip — tracks the batched nit
  above), Q27 (capability-taxonomy v1). None changed.
- Full OPEN set unchanged from prior close; this session opened/closed no questions.

### Single clearest next action
**Resolve Q45** (VA nap day-attribution) — it is the dated head of ROADMAP NOW, gates the
CBT-I eval-trigger rework, and now gates a second user. Owner: Luke; closes from the VA
CBT-I protocol docs or the administering clinician (workbook searched to exhaustion).

### What was NOT touched this session (named explicitly)
This was a governance/instrument session — the second-order risk is that the handoff reads
as governance and the next session does more governance. The **product lanes stood still**
and are the real queue:

- **Interpretation increment 2 (rephrase)** — UNSTARTED, and operator-confirmed *needed*
  by go-live (#194): Luke's O2 said the base text is too complex for a layperson. This is
  the strongest post-go-live product pick. Untouched.
- **Interpretation increment 3 (lever-tap → scoped education thread)** — UNSTARTED.
- **Interpretation small lanes from the go-live census** — `Bilirubin conjugated` + `CK`
  canonical-map, marker display-name polish, selectable-term glossary, `lab_accession`
  persist. All UNSTARTED product work. Untouched.
- **`feat/cbti-eval-trigger`** — OWED/REWORK (obsolete against master's 4-night engine
  after #165). Full rework checklist in BRANCHES.md row. Pushed `fec0324`, unmerged.
  Untouched this session.
- **CBT-I user surface** — invisible in-app; gated on #47 (state-only vs action). Q60.
- **Banister readiness build** — OWED; data path unblocked, model unbuilt. Untouched.
- **#116/#121 frontend deploy probe for the hub shell (#162)** — still never run. Untouched.
- **Cross-repo propagations (health-connect-app)** — three OWED shared-block copies, all
  HCA-rooted, all untouched (correctly — not landable from a health-app-rooted session).

If the next session is free to pick, the product bias points at **interpretation
increment 2 (rephrase)**, which go-live explicitly surfaced as needed.
