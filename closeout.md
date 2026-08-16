# Session close-out

## 1. Real commits this session

Session-open ref: `eb71551` (master head at session start; local master clean and level with
origin, 0/0). Two branches, cut in sequence from master, both **merged via PR and deleted**.

```
e536835 gov: Railway prod verification 2026-08-16 closes Q13/Q15/Q18 (#NEXT)
0efa0ba gov: resolve #NEXT -> #215 at merge (master max re-read #214)
b109128 Merge pull request #68 from Easty11/chore/railway-verification-closes
d40499e fix: revise contraindication block sets per the Q23 audit (#NEXT)
29d3941 gov: resolve #NEXT -> #216, Q#NEXT -> Q102 at merge (master max re-read #215/Q101)
d142b09 Merge pull request #69 from Easty11/fix/contra-block-sets
<this commit> chore: session close-out
```

Branch 1 `chore/railway-verification-closes` (docs only, #176 bank-and-land path) → PR #68.
Branch 2 `fix/contra-block-sets` (code + its governance) → PR #69. The `placeholder guard
(POSIX)` check passed on both before merge.

## 2. Pending-queue reconciliation

No `;cc` pending-commit queue was carried in — the session started from a written two-brief
work order, not a chat close-out. Nothing to reconcile.

Both decisions minted this session landed: **#215** and **#216** in `DECISIONS_LOG.md`, with
`#NEXT` resolved at each merge instant against a freshly re-read master max (**#214** then
**#215**; questions **Q101** → new **Q102**). Master did not advance mid-session, so no
re-resolve was forced.

**One process failure worth carrying forward.** The first attempt to resolve `#NEXT` used a
bare substring replace and rewrote **105 historical prose references** to the `#NEXT`
convention across the three stores — the exact false-positive class the guard's own docstring
names (corrected entries quote the token they superseded). Caught immediately by reading the
replacement counts (37/8/63 where 6 were expected), reverted via `git checkout --` before any
commit, and redone with per-site anchors carrying expected-occurrence assertions. The
after-check that makes the redo trustworthy: per-file `#NEXT` counts are byte-identical to
`origin/master` (31 / 4 / 30), so only this session's own six tokens moved. This is
`FEEDBACK` §17 / #113 — *match on anchors, not substrings, especially in an audit* — and it
reproduced on the very store that documents it.

**Not a placeholder, but adjacent debt:** the `Q102` reference in `selection.py`'s
`_SPINAL_PARTS` comment and the `#216` references in the new test module were written as
literals rather than placeholders (`FEEDBACK` §20 renumber debt). Both are confirmed correct
against the maxima re-read immediately before the resolution commit, but they were correct by
luck of a non-advancing master, not by construction.

## 3. Cold-resume handoff

### What landed this session

**(a) Three OWED prod verifications, closed — `#215`.** Q13, Q15 and Q18 had all been blocked
on one surface: production Postgres, unreachable from the dev SQLite `DATABASE_URL`. They had
aged 34–38 days for that single shared reason. One operator session cleared all three,
read-only, **zero prod writes**:

- **Q15** — `alembic_version` = `e2d5c7a1b9f3` = local head. All three `3497ab483935`
  divergences are present in prod with their intended types. The drift was **local behind
  prod**, since reconciled; not an un-migrated delta.
- **Q18** — the full 15-field `_BOUNDS` `NOT BETWEEN` sweep over all 56 `samsung_hrv_readings`
  rows returned **zero violators**; the `2026-06-28` trigger row's `sleep_efficiency_pct` is
  already NULL. `BRANCHES.md` `fix/hrv-sleep-integrity` Task 3 satisfied with no backfill;
  that row moves OWED → DONE.
- **Q13** — `hrv_rmssd` non-null count is **0** all-time and
  `health_connect_record_sources` holds only exercise / heart_rate (47,250 rows) / sleep /
  steps: **no HRV record type has ever arrived**. The 47,250 heart-rate rows are what make
  this positive rather than inconclusive — the pipeline demonstrably reads Samsung-written
  records, so the gap is not a dead ingest path. Absent at source, not unmapped. **Q5's
  unmapped hypothesis is eliminated for HRV** (it stays live for other fields). The scraper
  remains the sole HRV path, so the SPOF is **transferred, not closed**, to HCA issue #9.

`FEEDBACK` gains **§29** (essay in `FEEDBACK_ARCHIVE`): Railway's dashboard query editor
executes a multi-statement paste as a **silent 0-row no-op** — even `SELECT
current_database()` returns nothing. Q18's true answer and its false-negative answer were the
same string ("zero rows"), so the clean result was nearly recorded off a measurement that
never reached the subject. One statement per run for any prod check; when an instrument's
clean result is byte-identical to its failure result, it needs a positive control that cannot
return the clean value.

**(b) Contraindication block sets revised — `#216`.** The Q23 audit ran (taxonomy × confirmed
tags × sole-consumer verification, plus a read-only live ledger read). Findings:

- **Over-block direction is clean** against the confirmed tags. The question's stated worry
  does not reproduce.
- **Membership was swept for the A–E vocabulary and never for G**, and each omission
  contradicts the set's own stated reason for existing. `_RADICULAR_BLOCKS` gains
  `hip_flexion_pc_length` (a PC-length screen is functionally an SLR — a neural provocation
  test) and `loaded_carry_capacity_bw`; `_RA_FLARE_BLOCKS` gains `grip_strength` (its
  rationale reads "grip compromised" yet left the grip region probeable mid-flare) and
  `loaded_carry_capacity_bw`. Both sets blocked `carry` while leaving its G-axis twin open.
- **The radicular arm was unscoped by body part** — any entry typed `neural` triggered a
  lumbar-shaped stand-down. Now gated on `_SPINAL_PARTS`, with an empty `body_part` degrading
  to the broader caution rather than to permission.

**Protective, not corrective: neither named set has ever fired in prod** — all five live
ledger entries are typed `mechanical`.

Suite **860 passed** (838 baseline + 22 new). The new tests were shown to **discriminate**,
not merely pass: against master's `selection.py` the four defect cases return the wrong answer
and both preserved behaviours already hold; after the change all six are correct. Deploy
verified per #116/#121 — backend deployment SUCCESS at merge commit `d142b09`, prior
deployment REMOVED, and an **in-container probe** confirms `/app/engine/selection.py` carries
`_SPINAL_PARTS`, `_is_spinal` and all three new members at line numbers matching master
(strings present in no prior image).

### What was NOT touched — the standing lanes

**This was one product-code session and one governance/verification session, and the product
half was defensive plumbing rather than a user-facing capability.** Named explicitly so the
next session does not infer the queue from what happens to be legible here:

- **Interpretation layer inc-3 (lever tap → scoped education thread)** — UNSTARTED, unmoved.
  Inc-2 (rephrase, #202) and inc-5 (go-live, #194) are done; **inc-3 is the sequenced
  continuation and nothing this session touched it.**
- **Lab pipeline small lanes** — `lab_accession` persistence, the `Bilirubin conjugated` + `CK`
  canonical-map additions, marker display-name polish, the glossary/term-definitions feature.
  All queued, all untouched.
- **`SCHEMA.md` is stale for the entire lab family** — still OWED, still documenting a
  superseded design. Unmoved.
- **CBT-I accept-confirm defect (#214)** — the irreversible-write two-step confirm. Still a
  NEXT row; `cbti_prescriptions.id`=12 still stands pending Luke's decision on whether to
  correct it. **Q45** (nap day-attribution) is still the dated NOW blocker and every
  nap-excluded night still rests on an unverified attribution.
- **Q101** (elapsed-vs-sufficient cycle selection) — OPEN, unmoved.
- **Cross-repo propagation debt (four ROADMAP NOW rows)** — all four still OWED, all four
  landable only from an HCA-rooted session. This session could not touch them by rule.
- **Interpretation hub shell (#150/#162)** — the `#116`/`#121` **frontend** deploy probe is
  still never run.

**Consecutive-session pattern, stated rather than left to be noticed:** #211 and #212 were
product code; #213 was product code; #214 was governance; this session was verification plus
defensive engine plumbing. The instrument and governance lanes keep producing legible work
while **interpretation inc-3 and the lab small lanes have not moved in several sessions.**
Those are product lanes with no blocker — they are simply not what gets picked.

### Open questions minted this session

**`Q102` — `restrictions[]` is dead data.** `is_contraindicated` reads `restrictions` for
exactly one thing (the `ra_flare` alias); every other restriction string the ledger carries is
inert. Blocking runs on `signal_type` + set membership + a `body_part` substring, which cannot
express what the entries actually say. Evidence from the live ledger:

- **Entry 29** — a documented neural sign is typed `mechanical` *because* typing it `neural`
  would block its own desensitisation lane (the loaded hinge is tolerated and wanted; the
  aggravator is passive end-range tension). The vocabulary forces a choice between an honest
  `signal_type` and a workable plan. **Any audit trusting `signal_type` as clinical truth is
  reading a field bent to route around the blocker.**
- **Entries 18/29** — a LIVE over-block: `lunge_single_leg` contraindicated bilaterally via
  `_ACUTE_TISSUE_BLOCKS["hamstring"]` against an actively-trained region, with nothing to
  expire it despite the map's docstring promising a "time-limited" exclusion.
- **Entry 30** — `"pes anserine"` does not contain `knee`, so it never reaches the map;
  `"deep-flexion unilateral"` enforces nothing.
- **Entry 16** — `"heavy gripping"` restricts nothing at all.

**The live `lunge_single_leg` over-block was deliberately NOT patched.** Removing it ad hoc
trades a known over-block for an unknown under-protection, and it originates in the very entry
whose typing Q102 argues is unreliable. It belongs to the design pass. Now carries a ROADMAP
NEXT row.

### Single clearest next action

**Interpretation layer increment 3 — lever tap → scoped education thread.** It is the
sequenced continuation of a lane that is otherwise complete (inc-2 done #202, inc-5 done
#194), it has no blocker, and it is the highest-value item that has not moved in several
sessions. If a dated item must come first, it is **Q45** (nap day-attribution) — contaminating
capture is live right now for the CBT-I block, and it closes from the VA protocol docs or the
administering clinician, not the workbook.

### Explicitly out of scope this session

- **Brief B (`health-connect-app` Q2 close)** was NOT executed. It requires the session rooted
  in `health-connect-app`; this session is rooted in `health-app`, and the single-repo scope
  rule forbids editing a second repo's canonical stores from here. Brief B's own anchor
  ("`git rev-parse --show-toplevel` ends in `health-connect-app`. Stop if wrong.") fails.
  **Q2 in HCA remains OWED and needs its own HCA-rooted session** — the close text is written
  and ready in the brief.
- **Q7** (device-bound stash review) and the **Q102 design pass** itself — excluded by the
  brief by design.
