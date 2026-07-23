# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-23 · CBT-I phase 2 Steps 1–4: titration engine, Gate-4 replay, governance #114/#115

## 1. Real commits this session

Session-open ref: `4e12894` (master tip). Work sits on **`feat/cbti-engine` @ `0e340a7`**, pushed,
**5 ahead / 0 behind master — NOT merged.**

```
0e340a7 governance: DECISIONS_LOG #114/#115 (CBT-I titration engine)
5ce61ed feat(cbti): instrument TIB over-run; record two rejected gates and one dead end
f776813 fix(cbti): admit unknown-alcohol nights with provenance; exit-condition tests
2532e60 feat(cbti): titration engine + replay harness (phase 2, Step 3-4)
8ad304e feat(cbti): extract midnight-wrap primitives + got_into_bed (phase 2, Steps 1-2)
```

```
2026-07-23 governance: DECISIONS_LOG #114/#115 (CBT-I titration engine)
2026-07-23 feat(cbti): instrument TIB over-run; record two rejected gates and one dead end
2026-07-23 fix(cbti): admit unknown-alcohol nights with provenance; exit-condition tests
2026-07-23 feat(cbti): titration engine + replay harness (phase 2, Step 3-4)
2026-07-22 feat(cbti): extract midnight-wrap primitives + got_into_bed (phase 2, Steps 1-2)
2026-07-23 governance: DECISIONS_LOG #113, mint Q45, schedule the co-occurrence test
2026-07-23 chore: session close-out
2026-07-23 governance: DECISIONS_LOG #112, cross-repo debt convention, secrets residuals closed
2026-07-22 governance: DECISIONS_LOG #111, close Q43/Q44, secret-rendering prohibition
2026-07-22 chore: session close-out
```

Maxima on the branch: **DECISIONS #115 · questions Q45 · FEEDBACK §17.** Master is at **#113 / Q45**,
so #114/#115 are claimed at the ff-merge. Backend suite **352 passed** (was 308 at session open).
Migrations `a7b3f1c8d240` (got_into_bed) and `c4e8a2019bd7` (basis provenance) — **single head**.

## 2. Pending-queue reconciliation

No `;cc` queue carried in. Phase 2's standing brief drove Steps 1–4; every item resolved:

| Brief item | Outcome |
|---|---|
| 1a — extract the midnight wrap | **LANDED** `8ad304e`; importer reconciliation still 0/53, `worst_residual` byte-identical |
| 1b — `got_into_bed` | **LANDED** `8ad304e`, migration `a7b3f1c8d240` |
| 1c — alcohol three-state | **WITHDRAWN by chat** — column already nullable; became an engine predicate |
| 1d — nap attribution | **Q45 on master**; engine excludes nap-flagged nights |
| 2 — migration | **LANDED**, single head, up/down/up clean in isolation |
| 3 — engine | **LANDED** `2532e60`; all three VERIFYs pass (one failed first — see below) |
| 4 — replay + divergence | **LANDED**; ran against production, account below |
| 5 — surfaces | **NOT STARTED** — deliberate stopping point |
| LOG #114/#115 | **LANDED** `0e340a7` |

Nothing decided this session is uncommitted.

### Gate 4 — the replay, and what it found

Final series (51 nights in block window, **0 with a Samsung bedtime**, 17 with a constraining session
end, 9 historical prescriptions):

```
cy  window        dec       win     lo   TST     SE   n  sam  dia   a?  exc  ema  tibOver
 1  03-19..03-25  hold      384  22:36   362  85.69   6    0    6    4    1    3    +42.7
 2  03-26..04-01  compress  380  22:40   350  94.63   7    0    7    3    0    1    -14.0
 3  04-02..04-08  hold      380  22:40     -      -   3    0    3    1    4    2     +3.3
 4  04-09..04-15  hold      380  22:40     -      -   3    0    3    0    4    0    +31.7
 5  04-16..04-22  hold      380  22:40   378  85.68   6    0    6    2    0    1    +64.2
 6  04-23..04-29  extend    410  22:10   380  94.02   6    0    6    4    0    0    +25.0
 7  04-30..05-06  extend    425  21:55   395  89.13   6    0    6    4    0    3    +34.2
 8  05-07..05-13  hold      425  21:55     -      -   2    0    2    0    3    1    +42.5
```

**Hard floor holds.** Never closes; ends at 425 min (7h05) **still extending**. No early exit, so
#107's premise survives — the failure mode the floor watches for did not occur.

**Divergence from the VA app's nine prescriptions, which IS the output:** direction agrees, magnitude
lags (425 vs 458, unfinished not stopped). The engine holds on drink clusters where VA titrated
through them (cy3/4/8); compresses at cy2 where VA extended, which is #107 working as designed — high
SE alone does not buy window; and holds twice on adherence, which VA had no gate for.

**Composition: `samsung=0, diary=39, alcohol_unknown=18`.** Every basis night on the diary source
(Samsung `bedtime` begins 2026-06-08; the block closed 2026-05-11), and **18 of 39 basis nights were
admitted as assumed-clean rather than verified-clean.** Recorded per prescription so a later reader
sees that nearly half the basis rests on an inference.

### The alcohol predicate was corrected mid-flight, on evidence

The first replay was **eight straight HOLDs, no titration** — it measured the predicate, not the
engine. Excluding unknown-alcohol nights alongside recorded drinks removed 29 of 53 nights. Three
lines discriminated, one decisively: TST and WASO both place unknowns with recorded-zeros (383/22 vs
370/20, against drink 430/30), SE is noise (2.5 vs 2.1 on SD 6–11), and **0 of 19 blanks sit adjacent
to a drink night where ~3.7 are expected under random placement, p = 0.0033** — active refutation of
"blank means drank and did not log". Unknown is now admitted and flagged.

**The exclusion rationale was also wrong and is corrected in-source:** drink nights carry the block's
**highest** TST (430 vs 370), not suppressed sleep. They are higher-TIB nights run under a different
regime, so the alcohol filter is a **non-adherence proxy that overlaps the adherence gate** rather than
an independent filter.

### Two candidate gates built up and rejected, both recorded

Recorded in #114 and the engine docstring so neither is re-proposed from scratch:

1. **Endpoint adherence arm** (`out_of_bed` vs anchor, ±30, ≥3 of 7) — **tested, fires on nothing**,
   worst cycle 2 of 6. Wake-end failures are few-and-huge; bed-end failures many-and-small.
2. **Direct TIB gate** — discriminates, still withdrawn: SE = TST/TIB and over-run = TIB − window share
   TIB **by construction**; no threshold exists in the data (+3…+64, continuous); and it would starve
   the engine to 2 titrations in 8. `basis_tib_over_run_min` is instrumented instead.

### One VERIFY failed on my own code

VERIFY 3 (nothing re-implements the midnight wrap) **failed against `engine.py`** — two local
re-implementations. The shortest-path offset moved to `cbti.timeutil.signed_offset_minutes`;
`clock_delta_minutes` delegates. Grep now shows zero wrap arithmetic outside `timeutil`.

## 3. Cold-resume handoff

**Branch:** `feat/cbti-engine` @ `0e340a7`, pushed, 5 ahead / 0 behind, `--ff-only` available.
Untracked stray: `.claude/launch.json` (known). **Master is at `4e12894`.**

**Branch terminal-state gate — passes.** All five branches rowed in `BRANCHES.md` and on origin:

```
feat/cbti-engine                   5 +   rowed, on origin   (phase 2, Steps 1-4 done)
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin
feat/recovery-metrics-rhr          1 +   rowed, on origin
```

**Migrations are NOT applied to production, deliberately.** Prod stays at `e5f2a9c7b104`; Railway runs
`alembic upgrade head` on deploy, so `a7b3f1c8d240` and `c4e8a2019bd7` land at merge. Applying them
ahead of the merge is what created the prod-ahead-of-master divergence phase 1 spent a brief undoing.
The replay reads production **column-explicitly** so it works against the pre-migration schema.

**NEXT — CBT-I phase 2 Step 5 (surfaces), not started.** A fresh session with a clean brief. Scope:
AM diary fields render only when an open `cbti_block` exists; prefill `lights_out` / `got_into_bed` /
`out_of_bed` / `final_wake` from Samsung as editable defaults; **never** prefill `sleep_latency_min` or
`waso_min` (the device is systematically wrong on wakefulness magnitude, in the direction that breaks
the protocol); prefill sanity-gate rejecting any device value >~4h from the prescription (the 12-hour
clock failure — see Q42); PM close-out displays the current prescribed lights-out. **This is the first
work in the sequence to touch `frontend/`.**

**Then:** merge `feat/cbti-engine` (`--ff-only`, claiming #114/#115 — re-verify master's max first),
and fold in the `9688f2…` co-occurrence test from ROADMAP NOW.

**Three constants ship unvalidated, recorded not chosen** (#114): `MAX_MOVE_MIN` bound 0 of 8;
`PLATEAU_TOL_MIN` never reached, synthetic coverage only; `MIN_VALID_NIGHTS` undeterminable — failing
cycles at n=3/3/2, so lowering to 4 changes nothing and 3 still leaves one.

**Open, carried:** **Q45** (nap attribution — engine excludes; close it from the VA protocol
documentation, not the workbook, which is searched to exhaustion). **Q42** (12h-clock scrape) belongs
to HCA's store. The `health-connect-app` shared-block propagation is in **ROADMAP NOW** (#112).
`FEEDBACK` **§18**/**§19** still need a brief to land them. **Q41** (haematocrit citation capture),
**Q37**, **Q33**. HCA **Q11** should close `DONE → #93`; HCA **Q9 item 1** and **Q10** remain open there.

**Single clearest next action:** brief and build Step 5 (surfaces) in a fresh session, then merge
`feat/cbti-engine`. The engine is proven against real data and the branch is landable as it stands —
nothing is half-built.
