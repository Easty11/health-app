# Code session close-out — 2026-09-10

## 1. Real commits this session

Session-open ref: `60708aa` (master tip at start, PR #175 close-out merge). Feature + governance
landed via **PR #176** (merge commit `edbce94`), branch `claude/exposure-ui-write-increment-2-280tv4`
(merged + remote-deleted). Two disjoint commits on that branch:

```
3c10818 gov: Exposure UI increment 2 (write) — DECISIONS #274, ROADMAP, BRANCHES
00c3d29 feat(exposure-ui): increment 2 — the operator writes from the panel
```

- `00c3d29` — **feature (frontend only, no backend/schema/migration).** Three components under
  `frontend/src/components/exposure/`: `PhaseForm` (`POST /engine/phase`), `ClosePhaseDialog`
  (`POST /engine/phase/close`), `PhaseHistory` (`GET /engine/phase/history`, read-only) + helper
  `phaseTime.js` + fixture `phaseHistory.json`. `ExposurePanel.jsx` wired additively (Phase controls
  row; review-due badge is now a button opening the form, #228; `onWritten` refetches `/engine/next`;
  no chat push on write, #59). Tests: `PhaseForm`/`ClosePhaseDialog`/`PhaseHistory` units +
  `ExposurePanel.write.test.jsx` integration (kept separate so the #272 tests stay untouched). Full
  frontend suite 110 pass (91 #272-era untouched + 19 new); no new eslint (`todayLocal` split into
  `phaseTime.js` for react-refresh).
- `3c10818` — **governance (disjoint commit).** DECISIONS #274; ROADMAP (inc-2 → DONE +
  microcycle-editor sub-item; inc-3 unchanged, blocked on Q106); BRANCHES terminal row. Number-at-merge:
  master max re-read #273 → resolved #274 (no advance at merge).

Close-out commit (this file + CLAUDE.md Recent-landings + FEEDBACK §37) is separate, on branch
`claude/closeout-exposure-ui-write`, below.

### Post-merge verification folded in this session
- **#121 served-bundle check (operator-run, 2026-09-10) — both increments confirmed LIVE on
  `health-app-frontend`.** Bundle `assets/index-CHeBgVK8.js`; PRESENT strings: `No exposure profile
  yet` + `Probe suppressed by training phase` (#272), `Close to baseline` + `Phase history` (#274) —
  the #121 discriminating probe, not a version string. **#116 instance-identity:** the served bundle
  hash `index-CHeBgVK8.js` matches the local `npm run build` output, so the instance answering prod is
  exactly #274's code, not a stale image. LANDED → LIVE closed for the exposure write surface.

## 2. Pending-queue reconciliation

**No pending-commit queue was carried in.** The session implemented the attached Exposure-UI
increment-2 brief directly (chat-designed 2026-09-10, frontend-only non-migration, no new judgment →
self-merge on green under § Merge disposition). Every brief call landed as specified (DECISIONS #274,
not provisional — committed + merged). One process error occurred and was contained:

- **A repo-wide `sed 's/#NEXT/#274/g'` over the three governance stores clobbered historical `#NEXT`
  mentions in unrelated rows** (the number-at-merge convention is quoted verbatim across the
  append-only history — the §113 substring trap in write form). Caught before any commit; all three
  files reverted and the additions re-applied with the literal `#274` typed into the new text only.
  The final governance diff was +64/−1 (the one deletion the ROADMAP inc-2 row replaced in place).
  **Recorded this session as `FEEDBACK` §37** (#176's report had flagged it without recording it).

## 3. Cold-resume handoff

**Where things stand.** The **Exposure UI lane** now has increments 1 (read, #272) and 2 (write, #274)
both shipped, merged, and confirmed LIVE (#121). From `/training` the operator can open the next
phase, close to baseline, and read the phase ledger; the review-due badge opens the form (#228); writes
refetch `/engine/next` so the recommendation visibly changes; no chat push on write (#59). The server
remains the sole validator (422 `detail` shown verbatim; no client-side re-validation).

**Open questions gating the lane (unchanged this session, named so they don't read as finished):**
- **Q106 — the three non-equivalent readings of microcycle `minutes`** (scales set volume / caps region
  count per session / advisory only). Blocks **Exposure UI increment 3 (dose)** — no dose arithmetic
  client-side until it settles and a due-slot resolver exists.
- **Q105 — slot capacities stored verbatim** → a consumer must route through `taxonomy.resolve_capacity`,
  not string-compare. Settle in the same stroke as the weekly resolver (its first real consumer).
- **The Weekly-resolver lane** (`weekly_template` → which slot is due) is still unbuilt; "pick-by-readiness",
  not blocked.

**NEXT ACTION (single clearest) — PROVE THE #273 TEST-LANE BINDING, and it is the one item from this
arc still OWED.** #176's report called it "the first PR gated by the #273 test CI lane", but nothing has
verified the two contexts are actually *required* — #176 merged green, which proves the jobs RUN and
REPORT, never that a red one would BLOCK. A required-but-unbound context lets a red PR merge. **At next
session-open, open a throwaway PR that deliberately fails one test** (e.g. a one-line failing assertion
in a frontend test) and confirm it lands **red and blocked — merge refused — not grey/pending or
mergeable**, then **close it unmerged** (never merge, never leave it open). Red-and-blocked = bound;
mergeable-or-pending = the operator ruleset edit binding `frontend tests (vitest)` + `backend tests
(pytest)` on ruleset `20414758` (id, alongside `placeholder guard (POSIX)`) has NOT happened — read the
ruleset directly (`gh api repos/Easty11/health-app/rules/branches/master`), a green run is never proof
of binding (#273). This discharges the OWED binding item or proves it still open. Binding itself is an
operator-side ruleset edit Code cannot version.

**Session-open maxima to re-read:** DECISIONS `#274`, questions `Q139` (both confirmed on master at this
close).

**v1-triage handoff prompt (standing, from the v1 steer — the `DECISIONS_LOG` v1-definition entry).** For
each lane in NOW: which v1 test does it serve (See / Know / Walk in / Loop)? If none, state why it is in
NOW.

### NOT touched this session — named explicitly
This session, like the two before it (#273 test lane, #272 read surface), was **frontend/instrumentation
work, not the health-intelligence core**. Three consecutive sessions have gone to the UI and its CI
scaffolding rather than to the thing being instrumented. Standing still:
- **The engine/algorithm lane** — Banister Form per-window load (`load_metrics`, #248) is computed but the
  dosing seam still does not read it (#271/#274 notes); no work here this session.
- **Increment 3 (dose)** and the **Weekly resolver** — both untouched, blocked/unready per Q106/Q105 above.
- **Microcycle editor** — newly queued as a ROADMAP sub-item this session; not started (the advanced-JSON
  escape hatch is the whole write affordance increment 2 shipped).
- **Injury-ledger lanes** (backfill audit #222/#223, edit-and-supersede path) — untouched.
- The **5 October live test** is the real proof of the write path against real data (review badge fires →
  open Aerobic Base from the panel, posture held, capacities per that block, fortnightly A/B microcycle in
  the advanced field, watch the recommendation change) — an operator event, not Code work.
