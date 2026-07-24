# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-24 · Settling period instrumented on every cycle verdict, deliberately not gated (#124)

## 1. Real commits this session

Session-open ref: `d84a98e` (the prior close-out ritual). Two commits on
`feat/cbti-settling-instrument`, ff-merged to **master @ `69ad909`**, pushed; branch deleted.

```
69ad909 governance: DECISIONS_LOG #124 (settling instrumented not gated) + OPEN_QUESTIONS Q48
74d2ae1 feat(cbti): instrument nights_since_effective_from on every cycle verdict — not gated (#124)
```

DECISIONS max **#124**; questions max **Q48**. Backend deploy settled SUCCESS. The change is
engine-internal (`cbti/engine.py`, `cbti/replay.py`) — not reachable by any deployed endpoint (the
caller is the unbuilt trigger), so there is no served-surface probe; the test suite is the
discriminating verification (**401 passed**, was 394). No migration, no prod write, no frontend.

## 2. Pending-queue reconciliation

No `;cc` queue carried in. Nothing decided is uncommitted. `evaluate_cycle` now accepts
`nights_since_effective_from` and records it on all four verdict paths; **nothing branches on it**
(Gate-6 grep: dataclass / signature / `base` only, never in a conditional). The earlier
settling-*gate* proposal is **withdrawn, not deferred** — #124 supersedes it by recording why the
gate is not built, so it is not re-proposed a third time.

## 3. Cold-resume handoff

**Branch:** `master @ 69ad909`, level with origin. **Branch gate — passes.**
`feat/cbti-settling-instrument` merged + deleted. Four parked branches, untouched this session, all
rowed in `BRANCHES.md`: `feat/checkin-injury-probe` (+2), `feat/feedback-ledger` (+4),
`feat/interpretation-view-skeleton` (+3), `feat/recovery-metrics-rhr` (+1). None in limbo.

### CBT-I is capture-complete and now instrumented — one build-piece left

Block 3 runs live in the app: AM diary + Samsung prefill + 4h gate, PM prescription display + nap
capture, ISI baseline, and now the settling instrument (`nights_since_effective_from`, #124). The one
remaining piece to **close** a titration cycle in-app is the **manual evaluation trigger** (#118's
PM-offer half). It is a dependency, not a deferral — it cannot fire before ~31 Jul (needs a full cycle;
block opened 24 Jul). When built, it is also the caller that populates `nights_since_effective_from`
(#124 left the parameter; the trigger supplies the value).

### ROADMAP is date-anchored (#123) — read NOW top-to-bottom

NOW (6 rows, ordered by date): **Q45 nap attribution** (contaminating capture now) · **manual
evaluation trigger** (~31 Jul) · **lab pipeline** · **interpretation 4b + Q36–Q41** · **appointment
brief** (both early-Aug TRT panel) · **cross-repo propagation** (undated, pinned to NOW by #112).
Undated live work is in NEXT (19 rows); LATER unchanged (6).

**Single clearest next action:** the **manual evaluation trigger** — the first dated Code build, due
~31 Jul; there is **no NOW build ready before then** (today is 24 Jul; lab/interpretation are early-Aug).
It folds in #124's trigger-side computation (compute nights-since-`effective_from` and pass it). Running
in parallel and not a Code task: **Q45** — Luke resolves the nap day-attribution from the VA CBT-I
protocol docs or the administering clinician (not the workbook). Q45 contaminates every nap-excluded
night until closed and validates the `date − 1` read PM capture now feeds.

### Open questions — 34 live (14 DONE in `## CLOSED`, #123)

- **OWED (5):** Q4 (HC date-off-by-one), Q6 (strength volume-load), Q13 (HC `hrv_rmssd` structural),
  Q15 (`3497ab483935` prod-drift), Q18 (`samsung_hrv_readings` out-of-range sweep).
- **BLOCKED (2):** Q24 (`laterality` consumer), Q29 (HRV phantom-stale reconciliation).
- **UNSTARTED (27):** incl. **Q45** (nap attribution — gates CBT-I validity), **Q46/Q47** (basis
  provenance; adherence Samsung-bedtime lag), **Q48** (settling period — the #124 instrument's dataset
  is block 3; sibling to `MIN_VALID_NIGHTS` undeterminability at #114/#115), the **Q36–Q41 interpretation
  4b package**, **Q42** (12h-clock scrape — re-scoped: 4h gate covers prefill only, source is HCA's).

### OWED, carried across sessions

FEEDBACK **§18** stands (state-inferred-from-adjacent-attestation). Cross-repo: HCA still greps 0 for
#111's secret-rendering rule — propagate the shared block byte-identically from an HCA-rooted session
(ROADMAP NOW, pinned by #112). `9688f2…` co-occurrence test, the canonical-surface consistency guard,
and the `total_`/`actual_` semantic field-swap all sit in NEXT. Block 3's 24–25 Jul nights predate PM
nap capture (`naps_min = NULL`, un-gateable for naps without a memory backfill — #122).
