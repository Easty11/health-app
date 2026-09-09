# Code session close-out — 2026-09-10

## 1. Real commits this session

Session-open ref: `b1ba6ad` (master tip at start, PR #173 merge). All work landed via
PR #174 (merge commit `82b1804`), branch `claude/test-ci-lane` (merged + remote-deleted).

```
82b1804 Merge pull request #174 from Easty11/claude/test-ci-lane
2155c76 gov: test CI lane — DECISIONS #273, FEEDBACK §36, ROADMAP, BRANCHES
ca16e74 ci: run frontend suite on Node 22, not 20
d666676 ci: add test lane — frontend (vitest) + backend (pytest) on every PR
```

- `d666676` — **workflow.** `.github/workflows/tests.yml`: two jobs on push/PR to master —
  `frontend tests (vitest)` (`npm ci` + `npm test`) and `backend tests (pytest)` (Python
  3.12, `pip install -r backend/requirements.txt`, `pytest -q` on the SQLite default,
  `fetch-depth: 0`, ephemeral stdlib `FERNET_KEY`, throwaway `SECRET_KEY`/`ALGORITHM`). No
  change to `governance-guard.yml`.
- `ca16e74` — **Node fix.** Bumped the frontend job Node 20 → 22 after the first PR run
  crashed every jsdom worker (`webidl.util.markAsUncloneable` — `undici@8.10` via `jsdom@30`
  needs `worker_threads.markAsUncloneable`, Node 22.0.0+).
- `2155c76` — **governance (disjoint commit).** DECISIONS #273; FEEDBACK §36; ROADMAP
  lint-fix-then-bind row; BRANCHES row.

Close-out commit (this file + CLAUDE.md Recent-landings) is separate, below.

## 2. Pending-queue reconciliation

**No pending-commit queue was carried in.** The session implemented the attached
`claude_TEST_CI_LANE_BRIEF.md` directly (chat-designed, non-migration → self-merge on green
under § Merge disposition). Two brief premises proved false and were handled in-tree, both
recorded in DECISIONS #273 (not provisional — committed):
- The brief's env list omitted `FERNET_KEY`; `encryption.py` needs it at import. Fixed
  (ephemeral in-workflow key).
- The brief specified Node 20; the jsdom/undici test stack needs Node 22. Fixed (`ca16e74`).
- The brief listed `npm run lint` as a frontend-job step; it is red on 6 pre-existing eslint
  errors. **Operator-ratified this session:** lint dropped from the vitest job, the six
  recorded as debt (FEEDBACK §36), a ROADMAP row queues the fix-then-bind PR. Nothing here
  is uncommitted.

## 3. Cold-resume handoff

**Maxima:** DECISIONS `#273` · OPEN_QUESTIONS `Q139`.

**Branch:** none in flight — `claude/test-ci-lane` merged (PR #174, `82b1804`), remote
deleted, rowed in `BRANCHES.md` DONE → #273. On `master`.

### What landed
Test CI lane, `#273` — `frontend tests (vitest)` + `backend tests (pytest)` run on every PR
to master. Closes the hole where a green governance guard alone let a test regression
self-merge (#271, #272 both did, on local runs).

### OWED — the operator action that makes the lane bite
The two contexts **`frontend tests (vitest)`** and **`backend tests (pytest)`** are NOT yet
required. Bind them on ruleset `master-pr-gated` (id `20414758`), alongside
`placeholder guard (POSIX)` — a GitHub-side ruleset edit Code cannot version. Until bound,
the jobs run but do not gate. (VERIFY note: the ruleset was confirmed *functionally* live
this session — every PR required the guard and direct pushes were refused — but not read via
`gh api`, which is unavailable in this environment; read it when you make the edit.)

### What was NOT touched — the standing feature lanes, unchanged
This was an **instrument** session (CI plumbing + governance), as #271 (engine tidy) and, in
part, #272 (UI read) leaned toward. The product lanes stood still:

- **Exposure UI increment 2 (write)** — open next phase / close to baseline / phase history
  from the panel; the review badge becomes actionable. First `POST` from that surface.
  Unblocked once the phase open/retire write endpoints are confirmed in
  `backend/routers/training_phase.py`. Untouched.
- **Exposure UI increment 3 (dose)** — **blocked on `Q106`** (how a slot's `minutes` reaches
  the prescription, still OPEN) and the Weekly-resolver lane (ROADMAP NOW). Untouched.
- **Interpretation increment 3 frontend (`Q139`, OPEN)** — the tap-to-thread surface;
  backend spine landed at #268, frontend unbuilt, needs served-bundle verification (#121).
  Untouched.
- **Frontend lint debt (new, #273)** — 6 eslint errors (`ChatPanel` ×2, `WorkoutPanel` ×2,
  `PlainPanel`, `Settings`); a dedicated PR fixes them then binds `frontend lint (eslint)`
  as a third required job. Not started.
- **Dated NOW items** (Lab upload pipeline, Appointment brief, Banister build) — unchanged.

Note for the next session: three of the last four sessions have gone to instrument or
governance (#271 engine tidy, #273 CI lane, plus the governance-hygiene checkpoint), with
#272 the one product surface. The exposure lane has a read surface and no write surface; the
interpretation lane has a backend and no frontend. The next pick should be a **product**
lane (Exposure increment 2 is the most unblocked), not more instrumentation.

### Single clearest next action
The operator binds the two CI contexts on ruleset `20414758` (above) — the lane does not
gate until then. In parallel, the next build pick is **Exposure UI increment 2 (write)**,
unblocked once the phase write endpoints are confirmed present.
