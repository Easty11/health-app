# Session close-out

## 1. Real commits this session

Session-open ref: `629e2c7` (master head after fast-forwarding local master to origin at
session start). Branch: `feat/cbti-eval-trigger-v2`, cut fresh from `629e2c7`.

```
ee9b2eb feat(cbti): surface the PM evaluation offer in NightlyCloseOut (frontend)
853bed1 feat(cbti): PM evaluation trigger on the 4-night engine (backend)
```

Plus this `chore: session close-out` commit — governance only: `DECISIONS_LOG.md`
(mint `#NEXT`), `ROADMAP.md` (three strikes), `BRANCHES.md` (v2 row + obsolete-row update),
`CLAUDE.md` (Recent-landings), `closeout.md`.

The branch is **not merged** — code + tests are full human review (no guard-only land,
#176(c)). It is pushed/PR'd for review; the merge is the human's gated step.

## 2. Pending-queue reconciliation

No `;cc` pending-commit queue was carried into this session — it started from a written
work brief, not a chat close-out. Nothing to reconcile.

The decision minted this session (`### #NEXT` in `DECISIONS_LOG.md`) is **provisional until
the branch lands** — an uncommitted-to-master decision is not yet a sync point. `#NEXT`
resolves to a real integer at the merge instant (re-read master's max; **#212** at this
session), which the placeholder guard enforces before merge.

## 3. Cold-resume handoff

### What moved this session
The **CBT-I PM evaluation trigger (#118's PM half)** was rebuilt onto the 4-night hunting
engine and is `#NEXT` in `DECISIONS_LOG.md`. Read-only offer `GET /checkin-v2/cbti/evaluation`
+ witnessed accept `POST .../accept`, surfaced in `NightlyCloseOut.jsx`, both through
`cbti.replay.evaluate_live_cycle` (#128 ledger-read reuse). This is the last piece to *close*
a titration cycle in-app.

Key facts a cold reader needs:
- **Fresh port, not a branch merge.** The obsolete `feat/cbti-eval-trigger @ fec0324` was
  cut against the 7-night converge-and-close engine and is reference-only. It was NOT merged;
  it is deleted when v2 lands (`BRANCHES.md`, both rows).
- **The block-close path is gone, not refused.** The hunting engine emits a `converged HOLD`,
  never `close` (#107 / #165). The branch's whole close arm — the `acceptable` flag, the accept
  409, the dead-control UI — was DELETED as unreachable, not ported.
- **Master features the obsolete branch would have dropped are preserved:** `centre_minutes`
  / `centre_cycles_n` / `dither_minutes` on `CBTIContextOut` and its `windows` read; and
  `DeepSleepLevers` + the centre estimate in `NightlyCloseOut.jsx`. Only `EvaluationOffer`
  was added. `evaluationCopy.js`'s "no frontend test runner" claim was stale (vitest ships),
  so the copy test is written, not OWED.
- **Numbers, measured not derived:** backend suite **838 = 828 + 10** (pre/post on fresh
  master via `.venv`); frontend vitest **+12** (32 total). A default night tst=420 vs a 390
  window targets 450, +60 capped to +15 → a **405** proposed window; selected cycle is the
  last complete 4-night span.
- **Gates G1–G5 all verified:** G1 `evaluate_live_cycle` reads master's `replay()` series dict
  with no KeyError (the `converged` key was preserved); G2 offer/GATE-1-nap-guard parity pinned
  in `test_excluded_nights_are_surfaced_not_just_counted`; G3 close-reasoning grep clean in the
  trigger + endpoint + UI paths (the `close` vocabulary member stays only in `engine.py` + DB
  CHECK); G4 eligibility gates on `days >= CYCLE_NIGHTS`, not logged nights; G5 `#NEXT`/baseline
  discipline followed.

### ROADMAP strikes (both stale-DONE, code already on master)
- inc-2 **rephrase pass** UNSTARTED → **DONE #202** (`presentation.py` / `rephrase_validator.py`,
  migration `c3f1a8b2d9e4`; training-wheels review #1 verified in-DB).
- **Hevy create-time freshness** NEXT chip → **DONE #212**.
- The dated-NOW **eval-trigger row** closed (reworked, held for review → `#NEXT`).

### The single clearest NEXT ACTION
**Human review of `feat/cbti-eval-trigger-v2`, then land it.** At the merge instant:
(1) resolve `### #NEXT` in `DECISIONS_LOG.md` → the real integer, re-reading master's max
(#212 now — treat a mismatch as investigate-worthy); (2) `git push -u origin
feat/cbti-eval-trigger-v2` (if not already pushed) → `gh pr create --fill --base master` →
after review `gh pr merge --merge --delete-branch`. The placeholder-guard red check is the
strict-mode pause, not a failure. Then set the `BRANCHES.md` v2 row → DONE with the SHA and
delete `feat/cbti-eval-trigger`.

### What was NOT touched (named, not inferred)
This was a **product-code session** (backend + frontend feature), the first after two
governance/instrument sessions. Lanes that stood still, and the questions gating them:
- **Interpretation increment 3** (lever-tap → scoped education thread) — UNSTARTED; increment 2
  (rephrase) is now struck DONE, so inc-3 is the sequenced continuation.
- **Interpretation small lanes** — `lab_accession` persistence, `Bilirubin conjugated` / `CK`
  canonical map, marker display-name polish, glossary — all UNSTARTED.
- **CBT-I user surface (interim)** — gated on **Q60 / #47** (show state-only vs the MOVE/REVERSE
  verdict). The engine and now the evaluation trigger are built, but CBT-I remains invisible in
  the app (no route/page/nav) until #47 resolves. Unchanged this session.
- **Q45 nap day-attribution** — still OPEN and now DATED (contaminating capture live for block 3);
  the eval trigger surfaces nap exclusions (Q45/Q78 visibility) but does not resolve the
  attribution. Needs the VA CBT-I protocol docs or the administering clinician.
- **Banister readiness build** — OWED, data precondition met, model unbuilt.
- **#116 / #121 frontend deploy probe** — still never run.
- **Cross-repo propagations** (shared-block, number-at-merge enforcement) — OWED, HCA-rooted only.

### Governance maxima (re-read at the merge instant, never reuse)
Decisions **#212**, questions **Q100** at this session. `#NEXT` → **#213** if master has not
advanced; re-resolve if it has. No new question minted.
