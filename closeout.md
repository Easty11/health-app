# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-23 · CBT-I Step 5 begun: two canonical docs corrected on master, SCHEMA-lag guard recorded owed

## 1. Real commits this session

Session-open ref: `f54f60c`. Both commits **merged to master at `8771a19`**, pushed.

```
8771a19 governance: record the SCHEMA-lag guard as owed; note the corrected-doc audit shape
7442bb5 docs: correct two stale claims in checkin-schema.md, and a real SCHEMA.md lag
```

```
2026-07-23 governance: record the SCHEMA-lag guard as owed; note the corrected-doc audit shape
2026-07-23 docs: correct two stale claims in checkin-schema.md, and a real SCHEMA.md lag
2026-07-23 governance: DECISIONS_LOG #116 — verify a deploy after it settles
2026-07-23 chore: session close-out — phase 2 merged, prod reconciled
2026-07-23 chore: session close-out
2026-07-23 governance: DECISIONS_LOG #114/#115 (CBT-I titration engine)
2026-07-23 feat(cbti): instrument TIB over-run; record two rejected gates and one dead end
2026-07-23 fix(cbti): admit unknown-alcohol nights with provenance; exit-condition tests
2026-07-23 feat(cbti): titration engine + replay harness (phase 2, Step 3-4)
2026-07-22 feat(cbti): extract midnight-wrap primitives + got_into_bed (phase 2, Steps 1-2)
```

Maxima: **DECISIONS #116 · questions Q45 · FEEDBACK §17.** No new decision entries this session —
#117/#118 remain provisional for the surfaces branch. No code, no migration, no test delta.

## 2. Pending-queue reconciliation

No `;cc` queue carried in. The surfaces brief drove Step 1 only; Steps 2–9 are not started.

| Brief step | Outcome |
|---|---|
| 1 — correct `docs/checkin-schema.md`; check SCHEMA.md | **DONE**, merged `7442bb5` |
| 2–9 — endpoints, prefill gate, AM/PM, components, trigger, block-open | **NOT STARTED** — session boundary |

Nothing decided this session is uncommitted.

### Step 1 found a second, real lag — and it was mine

`docs/checkin-schema.md` carried two claims, **both verified stale before editing** rather than taken
from the brief:

- *"This is the target spec — not yet implemented."* The check-in **is** implemented: `checkin_v2.py`
  serves `/prefill` `/am` `/pm` `/today` `/history`, wired at `main.py`; `CheckInAM.jsx` (`/checkin-am`)
  and `NightlyCloseOut.jsx` (`/nightly`) are live surfaces behind `RequireAuth`. Stale by roughly a
  year, and it **mis-scoped the CBT-I surfaces work as construction rather than extension** until
  checked — the reconnaissance that caught it is the reason Step 5 is a smaller build than briefed.
- *"Soreness items are hardcoded for now. **Future:** drive from the active injury list."* That future
  arrived: `derive_soreness_items` is called at `checkin_v2.py:218` and consumed by `CheckInAM.jsx`.

**The VERIFY then found a lag in SCHEMA.md, which is the repo-canonical one.** Four columns from
migration `c4e8a2019bd7` — `basis_n_samsung`, `basis_n_diary`, `basis_n_alcohol_unknown`,
`basis_tib_over_run_min` — were in `models.py` and absent from SCHEMA.md. **An omission when that
migration was folded in during phase 2, not an anomaly of `checkin-schema.md`.** That reframes the
problem from "one doc is unreliable" to "the never-lag rule has no enforcement", which is why the
guard is now recorded as owed rather than treated as fixed.

### Two audit shapes worth carrying forward

- **A corrected document produces a grep false positive by design.** `not yet implemented` greps **1**
  in `checkin-schema.md` *immediately after* the correction landed — the hit is the correction note
  quoting the superseded text. Correct-don't-delete and audit-by-grep are each right and they
  interact. Recorded as a clause on #113 in `CLAUDE.md`; read the line, not the count.
- **The models-vs-SCHEMA detector was demonstrated with a negative control** — a fabricated column
  name reports LAG, proving the check can detect absence rather than always passing. That control is
  what makes it worth promoting to a test rather than re-deriving.

## 3. Cold-resume handoff

**Branch:** `feat/cbti-surfaces` @ `8771a19`, pushed, **0 commits ahead of master**. Master is also at
`8771a19`. Untracked stray: `.claude/launch.json` (known).

**Branch terminal-state gate — passes.** Five branches, all rowed in `BRANCHES.md` and all on origin:

```
feat/cbti-surfaces                 0 +   rowed UNSTARTED, on origin   (Step 5, resume at Step 2)
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin
feat/recovery-metrics-rhr          1 +   rowed, on origin
```

**Why the branch is empty and re-cut.** Step 1 corrected a *canonical surface*, and a fix for a
canonical-surface defect only counts once it is on the canonical surface — until it merged, master
still told the next reader the check-in was unimplemented, which is the exact wire the correction
exists to remove. It was docs-only (no migration, no code, no dormancy question), so it merged at
near-zero cost and the branch was re-cut from the new master under the **same name**, keeping the
brief's ANCHOR valid verbatim.

**NEXT — resume the surfaces brief at Step 2, unchanged.** Known before starting: AM/PM capture is
implemented and routed, so Step 5 is extension, not construction. Three VERIFYs carry the risk, all
recorded in full on the `BRANCHES.md` row:

1. **The Samsung `bedtime` → `got_into_bed` mapping may be untestable.** Clock times live on
   `samsung_hrv_readings`; `sleep_duration_minutes` lives on `health_connect_syncs`. The arithmetic
   needs a join that may lack per-night correspondence. If untestable, map as the brief specifies but
   record the mapping as **UNVERIFIED** — an unverified prefill *default* is recoverable (the operator
   edits `lights_out` when the two diverge, so the diary self-corrects and the SE denominator stays
   honest); an unverified *stored* value would not be.
2. **Step 4 deliberately ends the engine's dormancy.** `checkin_v2.py` becomes the first non-test
   consumer of `cbti/`, so a `timeutil` bug stops being latent and becomes a live capture-path bug.
   The freeze contract is the branch's highest-risk assertion and needs a **mutation control**: write
   a value, mutate the inputs it was derived from, re-read, assert the frozen value did not move. A
   write-then-read test proves storage, not freezing.
3. **Step 3's negative control is the gate.** A synthetic `10:12`-for-`22:12` must be *demonstrated*
   rejected and a valid value shown to pass. Frontend test infrastructure existence is unestablished;
   if absent, assert backend-side and say so rather than standing a framework up inside a feature brief.

**Standing caution for Steps 6–7:** read `CheckInAM.jsx` and `NightlyCloseOut.jsx` properly before
designing against them. Every structural claim in the brief about those files traces to greps of call
sites and line counts, **not to their render logic**. "Follow the existing soreness-from-`/prefill`
pattern" is an inference from a call site; if it does not match, report rather than force it.

**Then:** ISI capture — a separate brief, and it **must land before block 3 opens**, since a block-open
ISI cannot be retrofitted once the block has started.

**OWED, newly recorded:** the **SCHEMA.md-vs-`models.py` guard** (ROADMAP NOW, per #112) — turn the
demonstrated one-off detector into a test so the never-lag rule is enforced rather than aspirational.
Separate concern from surfaces, deliberately not that branch.

**OWED, carried:** the `health-connect-app` shared-block propagation and the `9688f2…` co-occurrence
test (both ROADMAP NOW). `FEEDBACK` **§18**/**§19** need a brief to land them. **Q45** (nap
attribution — close from the VA protocol documentation, not the workbook). **Q42** belongs to HCA's
store. **Q41**, **Q37**, **Q33**. HCA **Q11** should close `DONE → #93`; HCA **Q9 item 1** and **Q10**
remain open there.

**Single clearest next action:** resume the surfaces brief at Step 2 on `feat/cbti-surfaces`. The
branch is empty and current; nothing needs rewriting.
