# Code session close-out — Visuals increment 3 (exercise progression + phase markers), 2026-09-10

## 1. Real commits this session

Three authored commits, all landed on master via **PR #189** (merge commit `4425ad9`), branch
`claude/exercise-progression-phase-markers-aze636` **merged + remote-deleted**:

```
da8e48f Merge remote-tracking branch 'origin/master' into claude/exercise-progression-phase-markers-aze636
d1b0e52 gov(visuals): increment 3 #278 (D1–D5); ROADMAP test-1 See + surfacing item 2; increment-2 OWEDs closed; BRANCHES row; Recent-landings
b1a560c feat(visuals): exercise progression + phase markers (increment 3)
```

Master advanced **mid-session**: **PR #188** (increment-2 close-out, `25209cf` → merge
`415038d`) landed while this branch was in flight — `closeout.md` only, no code. It was merged
into the branch cleanly via `da8e48f` (no conflict). Number-at-merge: decisions max re-read at
merge = **#277**, so the new entry claimed **#278** and did not collide.

The close-out governance commit (this file + its BRANCHES row) is separate, on
`chore/closeout-inc3-278` (restarted from master), below.

## 2. Pending-queue reconciliation

**No `;cc` pending-commit queue was carried in.** This session ran directly from a written
brief (Visuals increment 3). Nothing is provisional — every change landed on master under
PR #189:

- Backend `GET /series/exercises` + `GET /series/exercise/{template_id}` (read-only over
  `hevy_workouts.raw`) + `backend/tests/test_series_exercise.py` → `b1a560c`.
- Frontend `ExerciseChart`, `PhaseMarkers`, `TimeSeriesChart` `markers` prop, the three sibling
  charts + `Metrics.jsx` threaded, fixtures + tests → `b1a560c`.
- DECISIONS_LOG **#278** (D1–D5), ROADMAP (See pointer + surfacing item 2 increment-3 DONE +
  both increment-2 operator OWEDs closed), BRANCHES row, CLAUDE.md Recent-landings → `d1b0e52`.

**Increment-2 operator OWEDs — CLOSED this session (operator-confirmed mid-turn):** the #121
served-bundle grep passed on `index-BSgJsRq2.js` (Fitness/Readiness render strings + the
unit-guard message served), and the user-1 populated-window read is **mechanical, metabolic,
neuromuscular**. Recorded in DECISIONS_LOG #278 and ROADMAP surfacing item 2.

## 3. Cold-resume handoff

**Landed — Visuals increment 3, extending v1 test 1 "See".** `/metrics` now carries a fourth
chart, `ExerciseChart` (per-exercise strength progression), plus a training-phase overlay on
**all four** charts. This is the first chart Hevy cannot draw: the phase boundary across the
e1RM line ("e1RM fell here — that's when Decompression started") is the platform's read.

- **Backend (read-only, no migration).** `GET /series/exercises` — selector source: templates
  with ≥ 3 qualifying session-days in range, most-frequent first (D5). `GET /series/exercise/
  {template_id}` — per-session points: e1RM by Epley from the top set (reps > 10 excluded from
  e1RM but not volume — D1), volume kg·reps (D2), working-sets count, one point per `_local_day`;
  warmup + `excluded_at` + `dedup_flag` filtered exactly as `engine/resolver` does (D3). No
  `/series/phases` — the phase ledger is **reused** via the existing `GET /engine/phase/history`.
- **Frontend.** `ExerciseChart` = two small multiples on `TimeSeriesChart` (e1RM line with null
  gaps + volume bars, distinct units on own axes), an exercise selector, sharing the page range.
  `PhaseMarkers` (`usePhaseMarkers` one fetch/page + `referenceLinesFor`) snaps `entered_on`/
  `closed_on` boundaries to in-range chart categories and threads them into LoadChart, FormChart,
  ReadinessChart and ExerciseChart via `TimeSeriesChart`'s new `markers` prop (D4).
- **Gates.** pytest (14), vitest (21 new / 158 total), 0 new eslint, bundle **+8.79 kB raw /
  +2.09 kB gzip**. All three CI checks green on the merged head.

**The one judgment call (an implementation detail, not a new decision).** The phase-marker snap
drops a boundary that falls **before** a chart's first data category (a phase begun before the
window — off-screen, D4's "in range" only) and one that falls after the last category. On a
sparse chart a real phase change near an edge therefore shows no line. This is the honest
choice; an edge-clamped alternative ("phase changed around here") is a one-line change if the
operator prefers it — flagged, not actioned.

**Single clearest next action.** Operator, prod-side (no Code step, no prod egress this session):
the **#121 served-bundle grep** against the live `health-app-frontend` bundle for the `e1RM`
string + the `phase-marker` label to confirm increment 3 is LIVE (LANDED ≠ LIVE, FEEDBACK §8),
and an eyeball of the live `/metrics` exercise chart against Hevy for an exercise Luke knows
(e1RM sanity-check, the whole reason D1 uses the same metric Hevy shows). Both literals are
confirmed present in the local build.

**NOT touched this session — the standing feature lanes (v1-triage).** This was the last queued
Visuals (See) increment; the other three v1 tests stood still and none was advanced. **Three
consecutive sessions (#277 inc1, #187 inc2, #278 inc3) have all gone to the Visuals instrument.**
The visual "See" surface is now rich; the health-intelligence core that the appointment brief
synthesises has not moved. Next pick should leave the Visuals lane unless a specific gap is named.

- **Weekly resolver consumer — test 2 (Know)** (surfacing seq 1, **Oct 5 anchor**): the
  resolver itself is BUILT (`#276`, `engine/resolver.py`, `/engine/resolver` + `/engine/next`
  default-to-due) and the panel POSITION landed (`#276` STEP 7). What is still owed for "Know"
  is enforcement-against-the-plan surfacing beyond position — UNSTARTED here. This is the
  strongest next pick by the #275 sequence.
- **Appointment brief v1 — test 3 (Walk in)** (surfacing seq 3): UNSTARTED here — the
  synthesising consumer the whole co-equal-modules sequencing points at.
- **Surface-debt sweep — test 4 (Loop)** (surfacing seq 4): UNSTARTED here.
- **Visuals lane (See)**: v1 core MET; increment 3 was its last queued item. Remaining Visuals
  work (the wrap-vs-plan view that "comes after the resolver", RPE progression once dense) is
  **NEXT, not NOW** — a demotion candidate, surfaced rather than left to ride lane momentum.

**Open OWED carried from prior sessions (not this session's work, unchanged):**
- **#273 test-lane binding** — `frontend tests (vitest)` + `backend tests (pytest)` are NOT
  required on ruleset `20414758` (proven by PR #178, FEEDBACK §38); only `placeholder guard
  (POSIX)` gates the merge. Operator must add both context strings verbatim GitHub-side. Until
  then, "green" for self-merge is guard-only. (This session's PR #189 nonetheless had all three
  green before merge.)
- **`claude/ci-binding-probe`** leftover remote branch — a prior session hit 403 on delete;
  rowed in BRANCHES.md, operator-delete.
- **Q140** (naive `date.today()` AEST skew, two live sites), **Q139** (interpretation
  increment 3 frontend tap surface) — OPEN, untouched.

**Session maxima:** decisions **#278** · questions **Q141**.
