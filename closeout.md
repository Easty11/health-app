# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-03. Branch at close: `feat/cbti-hunting-titration` (pushed, **not merged**).
Session-open ref: `f7901fd`. Session-open `DECISIONS_LOG` max on master: **164** (counted
`^### [0-9]+`, period-agnostic) — matching the brief, no re-aim needed.

**The titration is now a perpetual 4-night hunting search.** The window dithers ±15 min, the block
never auto-closes, and the reported sleep-need estimate is the centre of the dither rather than the
bouncing window. Nothing is deployed; both `#121` probes are owed.

## 1. Real commits this session

`git log --oneline f7901fd..HEAD`:

```
4b247f4 feat(cbti): perpetual 4-night hunting titration — no auto-close, centre-as-estimate
```

Plus this close-out commit. Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-08-03 feat(cbti): perpetual 4-night hunting titration — no auto-close, centre-as-estimate
2026-08-03 governance: #164 landed — BRANCHES row DONE, step 2 loop closed
2026-08-03 governance: resolve #NEXT -> #164, Q#NEXT -> Q76, Q#NEXT+1 -> Q77 (on-branch, pre-ff)
2026-08-03 feat(hevy): #NEXT wire <hevy_create_exercise> — the model-facing custom-exercise path
2026-08-03 governance: close #163's prod population gate — catalogue proven populated by the app
2026-08-03 governance: record the #163 merge + post-merge deploy verification
2026-08-03 governance: resolve #NEXT -> #163, Q#NEXT -> Q75 (on-branch, pre-ff)
2026-08-02 chore: session close-out
2026-08-02 governance: #NEXT (sync wiring), Q#NEXT (recurring-sync fork), BRANCHES row
2026-08-02 feat(hevy): #NEXT wire the exercise-template sync — operator endpoint + connect-time seed
```

## 2. Pending-queue reconciliation

No `;cc` queue was carried in. The input was a **code-ready brief** (4-night hunting titration),
reconciled step by step.

| Brief step | Outcome |
|---|---|
| 0 — cut branch, report max | **Landed.** `git cherry origin/master` empty at cut. Max **#164**. |
| 1 — four constants | **Landed.** `CYCLE_NIGHTS` 4, `MIN_VALID_NIGHTS` 3, `MAX_MOVE_MIN` 15, `ADHERENCE_FAIL_N` 2, each with an extended CHOSEN-not-derived note. The `MIN_VALID < CYCLE` cascade is now **asserted at import**, not just commented. |
| 2 — remove auto-close | **Landed, with a correction** — there was no engine-close to remove. See below. |
| 3 — centre-as-estimate | **Landed.** `CENTRE_CYCLES = 4` + pure `centre_estimate()`; surfaced on `/checkin-v2/today` (`centre_minutes`, `centre_cycles_n`, `dither_minutes`) and rendered in `PrescriptionCard` with a convergence band. |
| 4 — nap over-exclusion guard | **Landed.** The sufficiency HOLD now carries a per-reason tally. `NAP_EXCLUDE_MIN` untouched; Q45 stays OPEN. |
| 5 — deep-sleep-lever framing | **Landed** as `#47`-bounded education: five levers, evidence-ranked, identical for every reader, never scored or reordered by anyone's data. |
| LOG | **Entry minted** as `### #NEXT`. |
| New question (multi-user nap attribution) | **Minted** as `## Q#NEXT`. |

**Provisional, not done:** `#NEXT` and `Q#NEXT` are unresolved because the branch is **not merged**.
Integers are claimed at the fast-forward — master max was **#164** / **Q77** at authoring; re-read at
that instant rather than reusing these.

## 3. Cold-resume handoff

### The correction that matters — there was no engine-close to remove

The brief framed step 2 as removing the engine-driven block close `#118` established, and warned to
enumerate consumers first. Enumerated against master **before** editing:

- **Nothing writes `cbti_blocks.closed_on` from an engine decision.** The only writers are
  `import_cbti_block.py` (the historical block-1 import) and a read in `correct_cbti_block3_rx.py`.
- The engine's `close` was consumed **only** by `replay.py`'s advisory `#107` exit-too-early report
  (which prints) and by tests.

So `#118`'s "close is engine-driven" half was **specified and never built**. What this session removes
is a *recommendation*, not a mechanism — a materially smaller change than the brief supposed, and one
that touches no write path. `close` is **retained** in the `Decision` Literal and the DB CHECK
constraint: block 1 was imported carrying it and the ledger is append-only, so retiring the value
would invalidate history. The engine simply never emits it again, which is asserted parametrically.

### Gate evidence

- **Step 1** — `test_cbti_replay.py` green. Every changed replay decision traced to an intended
  constant, nothing flipped for another reason:

  | Change | Cause |
  |---|---|
  | 3-night stub `insufficient hold` → `extend` | `MIN_VALID_NIGHTS` 5→3 (3 now suffices) |
  | a 7-night span splits 1 → 2 cycles | `CYCLE_NIGHTS` 7→4 |
  | moves cap at 15, not 30 | `MAX_MOVE_MIN` 30→15 |
  | plateau `close` → `hold` + `converged` | step 2 |

- **Step 2** — full `close`/`closed_on` enumeration above. On 28 flat nights the walk yields 7
  cycles, cycles 3–7 all `hold`/`converged`, and the block never ends. `no input shape makes the
  engine emit close` is parametrised across five `prior_basis_tst` shapes × four TST/SE combinations.
- **Step 3 worked example** — windows `[405, 420, 435, 420]` → centre **420 min (7h00)**. A pure ±15
  dither `[405, 435, 405, 435]` → centre **420** while the latest window reads **435**: probe and
  estimate are demonstrably different numbers. Ageing-out proven: `[300]×10 + [450]×4` → **450**.
- **Step 4** — synthetic 4-night cycle with 2 nap nights:
  `insufficient_nights: 2 valid of 4, need 3 (2 excluded: nap x2)`, with per-night detail retained in
  `excluded_nights`. Non-vacuity: one nap night still leaves a decidable cycle.
- **Suite** — backend **674 passed** (master baseline **655**, measured by stashing; **+19** new).
  Frontend `npm run build` clean; eslint **5 errors, unchanged from the master baseline**.
- **Copy** — no frontend test runner exists, so `leverContent.js` / `centreCopy.js` are pure modules
  evaluated in node; assertions recorded OWED, not faked. Verified output: `7h 00m` ·
  `6h 45m–7h 15m` · `centre of the last 4 cycles` · `from the last cycle only`.

### Judgement calls beyond the brief

1. **Existing tests were retuned to derive from the constants, not repatched to new literals.**
   `week()` became `cycle()` sized from `CYCLE_NIGHTS`, and assertions now read `CYCLE_NIGHTS`,
   `MIN_VALID_NIGHTS`, `ADHERENCE_FAIL_N` rather than 7/5/3. A suite that hardcodes the cadence stops
   testing a full cycle the moment the constant moves — silently, not red. 17 tests were touched.
2. **A real bug caught by the build, not by review.** `DeepSleepLevers.jsx` beside a data module named
   `deepSleepLevers.js` differ only by leading case. On Windows the import resolved to the `.js` data
   module (no default export) and the build failed; on Railway's case-sensitive filesystem it would
   have resolved to the `.jsx` and built fine. Renamed to `leverContent.js` — a same-name-different-case
   pair is a platform-dependent footgun regardless of which side happens to win.
3. **The stale hub `#NEXT` was resolved to `#162` here too.** Master still carried the unresolved
   `### #NEXT` heading from the `feat/hub-shell` merge, with `#163`/`#164` minted on top — so `#162`
   was a hole and a placeholder sat mid-log. Left alone, this branch would have carried **two**
   `### #NEXT` headings and the pre-ff resolution could have hit the wrong one. Resolved in
   `DECISIONS_LOG` / `OPEN_QUESTIONS` Q63 / `CLAUDE.md`. `feat/cbti-eval-trigger` resolves it to the
   same `#162`, so the two branches agree — expect a trivial textual conflict, take either side.
4. **Two stale `CLAUDE.md` landings lines corrected.** `#163` read "not master" when it is on master
   and its prod gate is closed; `#164` was absent. Block trimmed back to its 3-line cap.

### Open questions touched

- **`Q#NEXT` (new)** — exclude-all starves a frequent napper at the 4-night cadence. **OPEN**, blocked
  by Q45, blocks any second user on the CBT-I module. Four candidates recorded, none costed, with an
  explicit "do not resolve by loosening `NAP_EXCLUDE_MIN` for the single user".
- **`Q45`** — unchanged, still OPEN. Exclude-all stands; the over-exclusion is now *legible* (the HOLD
  names the tally) but not fixed.
- **`Q48`** — still OPEN, and deliberately so: the dither generates the SE-recovery data its curve-fit
  would need, so this advances it rather than pre-empting it.
- **`Q55`** — the cadence constants now carry a recorded rationale, still chosen-not-derived.
- **`Q63`** — `DONE → #162` (was `DONE → #NEXT`).

### Branch state

- `feat/cbti-hunting-titration` — this session's work. Pushed, rowed in `BRANCHES.md`, **OWED**.
- `feat/cbti-eval-trigger` — from the prior session, still **unmerged and pushed**. Its `BRANCHES.md`
  row lives on that branch, so master cannot see it; cross-referenced from this session's row and from
  `ROADMAP.md` instead of duplicating it (duplicating would guarantee a second conflict). Its
  eligibility gate reads `CYCLE_NIGHTS`, so it inherits the 4-night cadence automatically once both
  land — no edit needed there for this change.

### Outstanding (owner: Luke)

1. **Merge decision on `feat/cbti-hunting-titration`.** On merge: resolve `#NEXT` and `Q#NEXT`
   on-branch pre-ff — re-read master max at that instant, do **not** reuse #164/Q77.
2. **Deploy probes, both services, post-merge** (`#116` timing + `#121` coverage). Backend:
   `railway deployment list --service health-app-backend` SUCCESS and `/checkin-v2/today` returns
   `centre_minutes`. Frontend: `railway service health-app-frontend` SUCCESS and grep the live
   `assets/index-*.js` for `What drives deep sleep`.
3. **Decide `feat/cbti-eval-trigger`'s fate.** It is the `#118` PM trigger and has been held two
   sessions. Merging it after this branch gives the 4-night cadence a surface; abandoning it loses the
   witnessed-accept path *and* the duplicate `#162` fix.
4. **No prod verification of the new cadence.** Nothing here was run against block 3's live data —
   this session was synthetic-only by design, but the first real 4-night cycle is the watch-point.
   Specifically: whether the dither converges, or the centre wanders (the decision's revisit clause
   names the Q45 nap exclusion and `SE_FLOOR_PCT` as first suspects).
5. **No frontend test runner.** Lever content and centre copy are inspection-and-node-backed.

### Single next action

Review `feat/cbti-hunting-titration` (`4b247f4`, pushed). If merging: resolve `#NEXT`/`Q#NEXT` pre-ff,
`git land feat/cbti-hunting-titration`, then run both deploy probes in item 2.

### Governance stores changed this session

`DECISIONS_LOG.md` · `OPEN_QUESTIONS.md` · `ROADMAP.md` · `BRANCHES.md` · `CLAUDE.md`
(`FEEDBACK.md` and `Ideas.md` unchanged.)
