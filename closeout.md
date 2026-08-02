# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-02 (second session that day; the prior close-out is `d11b2b8`).
Branch at close: `feat/cbti-eval-trigger` (pushed, **not merged**). Session-open ref: `d11b2b8`.

**`#118`'s owed PM half is built.** The engine's cycle decision is offered at nightly close-out with
its full basis, and the successor prescription is minted only on an explicit accept. One gate was
NOT met — live prod verification — and it is owed, not claimed.

## 1. Real commits this session

`git log --oneline d11b2b8..HEAD`:

```
f30dd49 feat(cbti): #118 PM evaluation trigger — witnessed offer + accept, reusing #128's ledger read
```

Plus this close-out commit. Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-08-02 feat(cbti): #118 PM evaluation trigger — witnessed offer + accept, reusing #128's ledger read
2026-08-02 chore: session close-out
2026-08-02 feat(frontend): #150 hub shell — tile grid on /dashboard, chat docked, panels relocated
2026-08-02 governance: question-state vocab (carve+sweep), Q65 collapse, Q73/Q74, FEEDBACK §22, CLAUDE accretion compress, ROADMAP NEXT reconcile
2026-08-02 governance: renumber #NEXT -> #161 and land; Q72 carries the owner's position
2026-08-02 governance: #NEXT (verdict-vs-measurement scoping), Q72, BRANCHES row
2026-08-02 feat(engine): capability_observations — graded, timestamped measurement
2026-08-01 chore: session close-out
2026-08-01 governance: resolve #NEXT -> #160 (on-branch, pre-ff)
2026-08-01 governance: #NEXT — the group as-of derivation, and the label #159 actually asked for
```

## 2. Pending-queue reconciliation

No `;cc` queue was carried in. The input was a **code-ready brief** (CBT-I PM evaluation trigger,
`#118`), reconciled step by step. Nothing in it is silently dropped.

| Brief step | Outcome |
|---|---|
| 0 — cut branch, report max decision number | **Landed.** Cut clean from master. Max is **#161** numbered — but master also carried an unresolved `### #NEXT`; see "Inherited defect" below. |
| 1 — extract the shared cycle read/eval | **Landed.** `load_ledger_rxs` + `evaluate_live_cycle` in `cbti/replay.py`. `test_cbti_replay.py` green (6 passed) **before** the endpoints were added — the extraction is proven decision-neutral for the replay. |
| 2 — read-only offer endpoint | **Landed** as `GET /checkin-v2/cbti/evaluation`. Writes nothing. **Gate NOT fully met** — the live prod verification could not run; see "Outstanding". |
| 3 — witnessed-accept mint endpoint | **Landed** as `POST /checkin-v2/cbti/evaluation/accept`. Append-only invariant asserted by column diff; double-accept guarded; block row untouched; `close` refused. |
| 4 — PM offer surface | **Landed** in `NightlyCloseOut.jsx`. Integration point reported below. |
| 5 — Q45 caveat surfaced, not resolved | **Landed.** `nights_excluded` renders as a dated list with reasons, not a count. `Q45` gains a note recording that the exposure is now legible and still unresolved. |
| LOG | **Entry minted** as `### #NEXT`, against the brief's "Likely None". Adjudication below. |

**Provisional, not done:** this branch's `#NEXT` is unresolved because it is **not merged**. The
integer is claimed at the fast-forward.

### Inherited defect, fixed here

Master carried an **unresolved `### #NEXT`**: `feat/hub-shell` fast-forwarded last session while its
heading still read `#NEXT`, so number-at-merge did not happen. Left alone, this session's entry would
have been a second `#NEXT` in the same file — exactly the collision the rule exists to kill. Resolved
to **#162** here, with the miss recorded in the entry, `BRANCHES.md` and `ROADMAP.md` rather than
quietly corrected. Renumber scope was classified, not counted (`#148`): five live tokens
(`DECISIONS_LOG` heading + Status, `OPEN_QUESTIONS` Q63, `CLAUDE.md` landings, `BRANCHES.md` row,
`ROADMAP.md` row); every other `#NEXT` in the tree is pre-existing prose *about* the convention and
was left untouched.

## 3. Cold-resume handoff

### What exists now

`feat/cbti-eval-trigger` at `f30dd49`, pushed, **not merged**.

- `backend/cbti/replay.py` — `load_ledger_rxs` (the `#128` prescription read, extracted from `main`),
  `evaluate_live_cycle` (+ `LiveCycleEval`), and `_as_date`.
- `backend/routers/checkin_v2.py` — the offer and accept endpoints, their schemas, and helpers.
- `backend/tests/test_cbti_eval_trigger.py` — 11 tests.
- `frontend/src/components/cbti/{EvaluationOffer.jsx,evaluationCopy.js}`; `NightlyCloseOut.jsx` +6 lines.

### Adjudications made (corrections are the expected output)

1. **Eligibility is calendar DAYS elapsed, not logged nights** — the brief specified
   `nights_since_effective_from >= 7`; `#118` says "7 days". Days wins, and the difference has teeth:
   gating the offer on logged nights strands the operator, because cycle 1 can never reach 7 logged
   nights once one of its 7 calendar days goes unlogged and that span is already past. Night count
   still governs the decision through the engine's existing sufficiency gate, which HOLDs and names
   the shortfall. Both quantities are reported. Pinned by a test.
2. **`close` is surfaced but not acceptable** — block close stays engine-driven (`#118`) and no close
   path is built, so the offer renders with no accept control and accept returns 409 rather than
   minting a terminal-looking prescription that leaves the block open.
3. **The trigger replays the whole block** — `prior_basis_tst` needs two prior cycles for the plateau
   exit, so evaluating the live cycle alone would make `close` structurally unreachable.
4. **Reuse target named wrongly in the brief** — the constant is `_PRESCRIPTIONS_SQL`, not `_RX_SQL`.
   No `_RX_SQL` exists on master.
5. **LOG is not "None".** The brief predicted no entry. Calls 1–3 are settled by neither `#118` nor
   `#128` and each has a live consequence, so one entry was minted. The brief's own two candidate
   triggers were both declined: the `#47`/`Q60` boundary was already drawn by `#118` (building to it
   is application, not a new call), and nothing here settles `Q48`, which stays open.

### Gate evidence

- **Step 1** — `test_cbti_replay.py` **6 passed** after the extraction, run before any endpoint
  existed. `main()` now calls `load_ledger_rxs` with the same query and construction it had inline.
- **Step 2 / Step 3** — 11 new tests, full backend suite **589 passed** (578 baseline **+11**), no
  regressions. Append-only proven by re-reading the prior row after accept and asserting the changed
  column set `== {effective_to, superseded_by}`; successor count asserted `== 2` rows on the block;
  block `closed_on` asserted still null; double-accept asserts 409 **and** still 2 rows.
- **`#128` reuse** — a test reproduces block 3's shape (a correction superseding the seed mid-block)
  and asserts the basis reports the correction's `22:30`/390, not the seed's `23:45`/360.
- **Step 4 integration point** — `NightlyCloseOut.jsx` fetches `GET /checkin-v2/today` on mount and
  posts `POST /checkin-v2/pm` from `handleSubmit`. `<EvaluationOffer />` is slotted immediately after
  `<PrescriptionCard />` in both render branches, **outside** the `<form>`: it carries its own submit
  button, and nesting it would have made that button submit the close-out. It self-fetches, so the PM
  payload and submit path are untouched (`git diff` on the page is +6 lines, all render/import).
- **Copy** — extracted to a pure module and evaluated in node (no runner exists; the assertion is
  OWED, not faked). This caught a real bug: `close` rendered as `"Close the block by +30 min"`. The
  delta phrase is now restricted to `extend`/`compress`. Verified output:
  `Extend the window by +30 min` · `Compress the window by -30 min` · `Hold the window` ·
  `Close the block` · `1 night excluded from the basis` · `Next evaluation in 4 nights`.
- **Build/lint** — `npm run build` clean; eslint **5 errors, unchanged from the master baseline**.

### Not verified — the one gate not met

**Live prod verification (step 2's gate) did not run.** Two independent blockers, neither worked around:

1. `railway run` injects `DATABASE_URL` pointing at `postgres-*.railway.internal`, which does not
   resolve off-network. The backend service exposes **no** public URL variable (checked by listing
   env var **names** only — no value was rendered), and the Postgres service cannot be enumerated
   without the Railway agent tooling (`railway setup agent`).
2. `railway ssh` was **blocked by this session's permission classifier**.

A local server was also deliberately **not** started: `database.py` calls `load_dotenv()`, so a
mis-set `DATABASE_URL` would point a **write** endpoint (`accept` mints a ledger row) at production
health data. Not worth a screenshot. Consequently the populated offer card has not been seen
rendered with live data — the component's states are exercised only by construction and by the pure
copy functions.

### Open questions touched

- `Q45` — still **OPEN**. Gains a note: exclusions are now rendered dated-with-reasons at the moment
  a decision is witnessed, so the exposure is legible; the attribution is unchanged and still closes
  from VA protocol docs or the clinician.
- `Q48` — untouched, still OPEN. The trigger settles nothing about the settling window.
- `Q63` — **DONE → #162** (was `DONE → #NEXT`; see "Inherited defect").

### Outstanding (owner: Luke)

1. **Merge decision on `feat/cbti-eval-trigger`.** On merge: resolve `#NEXT` on-branch pre-ff
   (re-read master max at that instant — it is **#162** now, do not reuse), then
   `git land feat/cbti-eval-trigger`.
2. **Live prod verification, owed from step 2.** Either run `railway setup agent` and re-probe, or
   run the read-only check from an environment with DB reach: read block 3's live prescription and
   confirm `eligible` / decision / basis against it.
3. **Both deploy probes, post-merge** (`#116` timing, `#121` coverage). Backend:
   `railway deployment list` SUCCESS and `GET /checkin-v2/cbti/evaluation` answers. Frontend:
   `railway service health-app-frontend` SUCCESS and grep the live `assets/index-*.js` for
   `Cycle complete · evaluation ready`.
4. **The hub shell's own frontend deploy probe is still un-run** from the prior session — grep the
   live bundle for `HRV, sleep and overnight vitals`. It merged without it.
5. **No frontend test runner.** The evaluation copy is inspection-and-node-backed, not test-backed.
6. **No block-close path exists.** If the engine recommends `close`, the operator reaches a state the
   app surfaces but cannot action. That is deliberate (`#118`), but it is a dead end until a close
   path is built.

### Single next action

Review `feat/cbti-eval-trigger` (`f30dd49`, pushed). Before merging, decide whether the live prod
verification in item 2 must run first — it is the one gate the brief set that this session could
not meet.

### Governance stores changed this session

`DECISIONS_LOG.md` · `OPEN_QUESTIONS.md` · `ROADMAP.md` · `BRANCHES.md` · `CLAUDE.md`
(`FEEDBACK.md` and `Ideas.md` unchanged.)
