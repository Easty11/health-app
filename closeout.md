# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

2026-07-23 · CBT-I Step 5 opened at Step 1 only — docs corrected, consistency guard recorded owed

## 1. Real commits this session

Session-open ref: `f54f60c`. All six on **master @ `157df9f`**, pushed.

```
157df9f governance: generalise the owed guard to both canonical-surface comparisons
869e1fe docs: mark the corrected-doc clause as postdating #113, not part of it
bf5a4ed chore: close-out artifacts belong on master, not the feature branch
ba80eb4 chore: session close-out
8771a19 governance: record the SCHEMA-lag guard as owed; note the corrected-doc audit shape
7442bb5 docs: correct two stale claims in checkin-schema.md, and a real SCHEMA.md lag
```

```
2026-07-23 governance: generalise the owed guard to both canonical-surface comparisons
2026-07-23 docs: mark the corrected-doc clause as postdating #113, not part of it
2026-07-23 chore: close-out artifacts belong on master, not the feature branch
2026-07-23 chore: session close-out
2026-07-23 governance: record the SCHEMA-lag guard as owed; note the corrected-doc audit shape
2026-07-23 docs: correct two stale claims in checkin-schema.md, and a real SCHEMA.md lag
2026-07-23 governance: DECISIONS_LOG #116 — verify a deploy after it settles
2026-07-23 chore: session close-out — phase 2 merged, prod reconciled
2026-07-23 chore: session close-out
2026-07-23 governance: DECISIONS_LOG #114/#115 (CBT-I titration engine)
```

Maxima unchanged: **DECISIONS #116 · questions Q45 · FEEDBACK §17.** `DECISIONS_LOG.md` was **not
touched this session** — no new entry landed, so the CLAUDE.md recent-landings block is unchanged
(nothing new to point at). No code, no migration, no test delta. Backend suite last measured **352
passed**; prod at `c4e8a2019bd7`, level with master.

## 2. Pending-queue reconciliation

No `;cc` queue carried in. The surfaces brief drove **Step 1 only**.

| Brief step | Outcome |
|---|---|
| 1 — correct `docs/checkin-schema.md`; check SCHEMA.md | **DONE** `7442bb5`, merged to master |
| 2–9 — endpoints, prefill gate, AM/PM, components, trigger, block-open | **NOT STARTED** |
| LOG #117/#118 | **NOT WRITTEN** — numbers still free |

Nothing decided this session is uncommitted.

### What Step 1 found

`docs/checkin-schema.md` carried two claims, both verified stale before editing: the check-in is
**implemented and routed** (`checkin_v2.py` at `main.py`; `CheckInAM.jsx` `/checkin-am`,
`NightlyCloseOut.jsx` `/nightly`, both behind `RequireAuth`), and soreness items **are** driven from the
active injury list (`derive_soreness_items`, `checkin_v2.py:218`). The first claim had already
mis-scoped Step 5 as construction rather than extension until reconnaissance caught it.

**The VERIFY then found a lag in SCHEMA.md, the repo-canonical one** — four columns from migration
`c4e8a2019bd7` present in `models.py` and absent from SCHEMA.md. An omission when that migration was
folded in during phase 2, not an anomaly of `checkin-schema.md`. That reframed the problem from "one
doc is unreliable" to "the never-lag rule has no enforcement".

### THIS SESSION'S SHAPE IS ITSELF THE FINDING — read before planning the next one

**1 docs commit, 5 governance/close-out commits, ZERO CBT-I functionality.** Step 1 was a doc
correction and every turn after it concerned how that correction was recorded. Each governance item was
individually justified and several were genuinely worth having; the accumulation is the defect. It is
the same shape recorded twice in this repo — correct at each step, wrong in aggregate (see #113's
corrected-doc clause, and the self-describing-document problem noted below).

**The mechanism is an asymmetry, not carelessness.** Governance work is bounded, safe and always
available: no state to establish, no unknown to surface, nothing that turns out larger than expected.
The surfaces work has a bedtime mapping that may be untestable, a dormancy transition that turns latent
bugs live, and two frontend files still unread. **Safe work displaces unsafe work precisely because it
is safe**, and each displacement is individually defensible, which is what stops it registering.

**The cost is concrete.** The module exists to run block 3 and currently cannot: no AM capture, no
prescription display, no trigger, no ISI. If block 3 becomes necessary before the surfaces land, it
runs on the VA app again and this entire build sits unused for another cycle.

### Two smaller findings, recorded and not to be re-derived

- **A document that states its own repo position invalidates that statement by being committed.**
  `closeout.md` claimed "0 ahead" and the act of committing it made that false; the `BRANCHES.md` row
  had the same property. Not a rule — the practical form is *describe state as of the commit before,
  or do not state it*. Both now say "level with master" rather than a SHA.
- **The close-out belongs on master.** It was committed to the feature branch first, leaving master's
  copy stale — a cold session reads master, so the handoff would not have been where it is looked for.
  Fixed at `bf5a4ed`.

## 3. Cold-resume handoff

**Branch:** `feat/cbti-surfaces`, pushed, **level with master**, 0 commits ahead. Untracked stray:
`.claude/launch.json` (known).

**Branch terminal-state gate — passes.** Five branches, all rowed in `BRANCHES.md`, all on origin:

```
feat/cbti-surfaces                 0 +   rowed UNSTARTED, on origin   (Step 5, resume at Step 2)
feat/checkin-injury-probe          2 +   rowed, on origin
feat/feedback-ledger               4 +   rowed, on origin
feat/interpretation-view-skeleton  3 +   rowed, on origin
feat/recovery-metrics-rhr          1 +   rowed, on origin
```

### NEXT SESSION: Step 2. Not the owed list.

**Resume the surfaces brief at Step 2 — block status on `/prefill` and `/today` — then Steps 3–9, then
ISI.** The brief stands unchanged and its ANCHOR (`feat/cbti-surfaces`) passes verbatim.

**Of the four owed items, only ISI blocks block 3.** The consistency guard, the `9688f2…` co-occurrence
test and the cross-repo propagation queue indefinitely at no cost. They are bounded, safe and always
available — which is exactly why they displace work that is not. **Do not pick them up before the
surfaces land.**

**Hold unplanned governance during the surfaces build.** The bar: a defect producing incorrect
behaviour or an unrecoverable record — not an improvement to how something is recorded. Findings below
that bar go in the close-out and wait. This does **not** cover the brief's own LOG: #117/#118 are part
of the deliverable and land with the build, at the end, not as their own turns.

**Three VERIFYs carry the risk**, recorded in full on the `BRANCHES.md` row:

1. **The Samsung `bedtime` → `got_into_bed` mapping may be untestable.** Clock times are on
   `samsung_hrv_readings`; `sleep_duration_minutes` is on `health_connect_syncs`. The arithmetic needs
   a join that may lack per-night correspondence. If untestable, map as the brief specifies but record
   the mapping as **UNVERIFIED** — an unverified prefill *default* is recoverable (the operator edits
   `lights_out` when the two diverge, so the diary self-corrects and the SE denominator stays honest);
   an unverified *stored* value would not be.
2. **Step 4 deliberately ends the engine's dormancy.** `checkin_v2.py` becomes the first non-test
   consumer of `cbti/`, so a `timeutil` bug stops being latent and becomes a live capture-path bug. The
   freeze contract is the branch's highest-risk assertion and needs a **mutation control**: write a
   value, mutate the inputs it was derived from, re-read, assert the frozen value did not move. A
   write-then-read test proves storage, not freezing.
3. **Step 3's negative control IS the gate.** A synthetic `10:12`-for-`22:12` must be *demonstrated*
   rejected and a valid value shown to pass. Frontend test infrastructure existence is unestablished;
   if absent, assert backend-side and say so rather than standing a framework up inside a feature brief.

**Standing caution for Steps 6–7:** read `CheckInAM.jsx` and `NightlyCloseOut.jsx` properly before
designing against them. Every structural claim in the brief about those files traces to greps of call
sites and line counts, **not their render logic**. "Follow the existing soreness-from-`/prefill`
pattern" is an inference from a call site; if it does not match, report rather than force it.

**OWED — queued, and deliberately not next:** the generalised **canonical-surface consistency guard**
(ROADMAP NOW — SCHEMA.md vs `models.py`, and CLAUDE.md conventions vs `DECISIONS_LOG` entries; the
detector exists and its negative control is the load-bearing part). The **`9688f2…` co-occurrence
test**. The **`health-connect-app` shared-block propagation**. **ISI capture** — a separate brief, and
the only owed item that blocks, since a block-open ISI cannot be retrofitted once the block has started.

**OWED, carried:** `FEEDBACK` **§18**/**§19** need a brief. **Q45** (nap attribution — close from the VA
protocol documentation, not the workbook, which is searched to exhaustion). **Q42** belongs to HCA's
store. **Q41**, **Q37**, **Q33**. HCA **Q11** should close `DONE → #93`; HCA **Q9 item 1** and **Q10**
remain open there.

**Single clearest next action:** Step 2 of the surfaces brief on `feat/cbti-surfaces`. The module
exists to run block 3 and currently cannot — that is the thing to fix.
