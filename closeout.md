# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-24 · CBT-I loop brought to capture-complete (block 3 live), then the backlog re-tiered to external dates

## 1. Real commits this session

Session-open ref: `a2ecef9` (the prior close-out ritual). Four briefs landed since, all on
**master @ `acc94d1`**, pushed; no intervening full ritual (handoffs were true-upped in place).

```
acc94d1 governance: DECISIONS_LOG #123 — ROADMAP anchored to dates, closed questions below the fold
2e0bcf8 chore: re-tier ROADMAP to external dates; move closed questions below the fold
8c265c8 governance: retire feat/cbti-pm-naps; only the evaluation trigger remains
802ddd6 governance: CLAUDE.md recent-landings — prepend #122
22a5c8a governance: DECISIONS_LOG #122 — naps captured PM as 0-not-null, engine exclusion goes live
9ea4a44 feat(cbti): capture naps_min at PM so the engine's nap exclusion goes live
e1c9f79 governance: DECISIONS_LOG #121 — a deploy check must cover every service that changed
3bf3fb9 governance: retire feat/cbti-isi-pm; true up the handoff (PM display + ISI now done)
9331c31 governance: DECISIONS_LOG #120 — ISI stored item-level, canonical total derived
7bc0fc9 feat(cbti): show tonight's prescribed window on the PM close-out
b7ca8e1 docs: correct the false "block 3 opened without ISI" claim in closeout and ROADMAP
8588464 feat(cbti): backfill script for block 3's baseline ISI (run post-deploy)
7c62840 feat(cbti): cbti_isi table — ISI stored as items, canonical total derived
```

Grouped by brief: **ISI + PM display** (`7c62840`→`3bf3fb9`, #120) · **deploy-coverage rule**
(`e1c9f79`, #121) · **PM nap capture** (`9ea4a44`→`8c265c8`, #122) · **backlog triage**
(`2e0bcf8`,`acc94d1`, #123). DECISIONS max **#123**; questions max **Q47**. Prod at
`d3f7a1908c62` (backend) with both services deploy-verified per #121. No open code changes.

## 2. Pending-queue reconciliation

No `;cc` queue carried in — Code-driven briefs throughout. Nothing decided is uncommitted.
Two prod writes this session, both verified by read-back: block 3's opening block/prescription
(`cbti_blocks` id=2, `cbti_prescriptions` id=10) and its baseline ISI (`cbti_isi` id=1). One
carried data note (#122): block 3's nights logged 24–25 Jul predate PM nap capture and keep
`naps_min = NULL` — un-gateable for naps without a memory backfill (two nights).

## 3. Cold-resume handoff

**Branch:** `master @ acc94d1`, level with origin. **Branch gate — passes.** `chore/backlog-triage`
merged + deleted. Four parked branches, untouched this session, all rowed in `BRANCHES.md`:
`feat/checkin-injury-probe` (+2), `feat/feedback-ledger` (+4), `feat/interpretation-view-skeleton`
(+3), `feat/recovery-metrics-rhr` (+1). None in limbo.

### The CBT-I module is capture-complete for block 3 — one build-piece left

Block 3 is open and running live in the app: AM diary capture + Samsung prefill + 4h gate, PM
prescription display + nap capture, and the baseline ISI are all in and deploy-verified. The one
remaining piece to **close** a titration cycle in-app is the **manual evaluation trigger** (#118's
PM-offer half). It is a dependency, not a deferral: it cannot fire before ~31 Jul (needs a full
cycle of nights; block opened 24 Jul).

### ROADMAP is now date-anchored (#123) — read NOW top-to-bottom

NOW holds only date-anchored work, ordered by date (6 rows): **Q45 nap attribution** (contaminating
capture now) · **manual evaluation trigger** (~31 Jul) · **lab upload pipeline** · **interpretation
4b + Q36–Q41** · **appointment brief** (both against the early-Aug TRT panel) · **cross-repo
propagation** (undated, pinned to NOW by #112). Undated live work is in NEXT (19 rows); LATER
unchanged (6).

**Single clearest next action:** the **manual evaluation trigger** — the first dated Code build, due
~31 Jul; there is **no NOW build ready before then** (today is 24 Jul, lab/interpretation are
early-Aug). Running in parallel and not a Code task: **Q45** — Luke resolves the nap day-attribution
from the VA CBT-I protocol docs or the administering clinician (not the workbook, searched to
exhaustion). Q45 contaminates every nap-excluded night until closed and validates the engine's
`date − 1` read that PM capture now feeds.

### Open questions — 33 live (14 DONE moved to `## CLOSED`, #123)

- **OWED (5):** Q4 (HC date-off-by-one), Q6 (strength volume-load), Q13 (HC `hrv_rmssd` structural),
  Q15 (`3497ab483935` prod-drift), Q18 (`samsung_hrv_readings` out-of-range sweep).
- **BLOCKED (2):** Q24 (`laterality` consumer), Q29 (HRV phantom-stale reconciliation).
- **UNSTARTED (26):** incl. **Q45** (nap attribution — gates CBT-I validity), **Q46/Q47** (basis
  provenance; adherence Samsung-bedtime lag), the **Q36–Q41 interpretation 4b package**, **Q42**
  (12h-clock scrape — re-scoped: 4h gate covers prefill only, source parse is HCA's), and the
  cross-repo/loop-hygiene set (Q30–Q33).

### OWED, carried across sessions

FEEDBACK **§18** stands (state-inferred-from-adjacent-attestation). Cross-repo: HCA still greps 0
for #111's secret-rendering rule — propagate the shared block byte-identically from an HCA-rooted
session (ROADMAP NOW, pinned by #112). `9688f2…` co-occurrence test, the canonical-surface
consistency guard, and the `total_`/`actual_` semantic field-swap all sit in NEXT.
