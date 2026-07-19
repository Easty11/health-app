# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

Session: 2026-07-19/20 — session closure sweep, Phase 1. Branch `master` @ `a9d8264` (all work landed).

---

## 1 · Real commits this session

Open-ref `56eb6b7` (the prior session's close-out, pre-existing at my start) → `HEAD`:

```
a9d8264 gov(branches): gov/session-closure-sweep DONE at 05f0282 + Phase 1 handoff
05f0282 gov: DECISIONS_LOG #90 + FEEDBACK 13 — vocabulary adoption is a sweep
f836bb8 gov: OPEN_QUESTIONS + ROADMAP swept to valid states
14a7574 gov(branches): step-5 — every row relabelled to the four states
613dab6 gov(branches): step-4 loop adjudications — 2 closed on evidence, 2 stay OWED
ed04c07 gov(branches): document gov/session-closure-sweep as an in-flight OWED row
e0391e9 gov(branches): dedicated rows for 3 pushed branches + resolver/markitdown adjudications
e99c09e gov(handoff): session closure sweep receipt — received, not started
```

Repo's own dated record — `git log --format="%ad %s" --date=short -10`:

```
2026-07-20 gov(branches): gov/session-closure-sweep DONE at 05f0282 + Phase 1 handoff
2026-07-20 gov: DECISIONS_LOG #90 + FEEDBACK 13 — vocabulary adoption is a sweep
2026-07-20 gov: OPEN_QUESTIONS + ROADMAP swept to valid states
2026-07-20 gov(branches): step-5 — every row relabelled to the four states
2026-07-19 gov(branches): step-4 loop adjudications — 2 closed on evidence, 2 stay OWED
2026-07-19 gov(branches): document gov/session-closure-sweep as an in-flight OWED row
2026-07-19 gov(branches): dedicated rows for 3 pushed branches + resolver/markitdown adjudications
2026-07-19 gov(handoff): session closure sweep receipt — received, not started
2026-07-19 chore: session close-out
2026-07-19 gov: mint #NEXT -> #89 at merge — master max was #88; step-5 HCA pointer deferred
```

All 8 landed on `master` via ff-only merge, pushed to `origin/master`.

**Gate evidence at merge.** Governance-only: `BRANCHES.md`, `DECISIONS_LOG.md`, `FEEDBACK.md`,
`HANDOFF.md`, `OPEN_QUESTIONS.md`, `ROADMAP.md` — zero `backend/`, `frontend/`, `alembic/`.
Backend suite **206 passed**, unchanged from #88's 206.

---

## 2 · Pending-queue reconciliation

| PENDING item (from brief) | Outcome |
|---|---|
| `DECISIONS_LOG.md` **#89** — vocabulary adoption is a sweep | **LANDED as #90** in `05f0282`. Renumbered: master max was already **#89** (Q17 / HRV instrumentation), not the #88 the brief assumed. Next free number taken, per the brief's own PRECONDITION. |
| `FEEDBACK.md` **§13** — a rule proven on two rows is not a rule applied to the store | **LANDED** in `05f0282`, including the corollary that a brief's predicted verdict is a hypothesis with a hint, not a licence. |

**Two departures from the brief's #90 draft, both committed:**

- **Scope narrowed to health-app.** The draft asserted the sweep covered "both repos."
  `health-connect-app` is an unseeable surface from this repo and was never swept, so writing
  that would have committed the exact defect #90 names. HCA is recorded as OWED inside #90.
- **Three findings stated once as a shared root**, not three times: a claim inheriting authority
  from where it sits rather than from what attests it — position
  (`feat/resolver-candidate-suggestions`), completeness (`feat/interpretation-view-skeleton`),
  recency (this brief's own scrollback claim).

**Provisional — decided but NOT committed:**

- **Phase 2 (`health-connect-app`) — UNSTARTED.** Its anchor requires the session rooted in
  `health-connect-app`; this session is rooted in `health-app`, so the single-repo rule forbids
  it. Recorded OWED in #90, not asserted done.
- **CLAUDE.md internal contradiction — OPEN, unresolved.** The canonical-stores row
  (CLAUDE.md:60) assigns `open` / `verifying` / `resolved → #` to `OPEN_QUESTIONS.md`, while
  #88's state-vocabulary section (CLAUDE.md:72) says the four states apply to it. Left undecided
  on purpose: that text sits inside the verbatim-propagated shared block, so editing it obligates
  `health-connect-app`. **This gates Phase 2 step 10**, which assumes four-state on questions.

---

## 3 · Cold-resume handoff

### State at close

- `master` @ `a9d8264`, pushed. Tree clean but for untracked `.claude/launch.json`.
- **BRANCHES.md: 22 rows, all four-state** — 12 DONE / 9 OWED / 1 UNSTARTED. Zero superseded
  labels in any status column.
- **OPEN_QUESTIONS.md: 29 questions, all valid** — 18 `open` / 1 `verifying` / 10 `resolved`.
  (The brief claimed a filtered read showed no unresolved entries; a direct read disproved it.)

### Branch terminal-state gate — PASSES

| Branch | `git cherry` | Remote | Terminal state |
|---|---|---|---|
| `gov/session-closure-sweep` | merged | never pushed | ff-merged @ `05f0282`, local branch deleted |
| `feat/feedback-ledger` | `+` (4) | on origin | OWED, dedicated BRANCHES row |
| `feat/interpretation-view-skeleton` | `+` (3) | on origin | OWED, dedicated BRANCHES row |
| `feat/checkin-injury-probe` | `+` (2) | on origin | OWED, dedicated BRANCHES row |
| `feat/recovery-metrics-rhr` | `+` (1) | LOCAL-ONLY | UNSTARTED, parked in BRANCHES row |

### Loops owed on Luke (named commands, from BRANCHES.md)

1. `fix/probe-harness-fidelity` — `/opt/venv/bin/python probe_resolver.py 1` in the container.
2. `fix/hrv-sleep-integrity` Task 3 — Railway historical HRV bounds-guard sweep.
3. `feat/hevy-resolver-activation` — limb 2: a live chat request naming a nonsense movement;
   confirm the routine is refused **and** the unresolved title is named back.
4. `feat/connector-error-policy` — live "See all" E2E through the deployed backend against a
   valid connector key (>1 page of workouts).
5. `feat/protocol-declaration` — confirm `current_state.declared_state` reads back 23 factors in
   prod (the seed WRITE is attested; the read-back is not).
6. `feat/constraint-consumption` — browser-verify `CheckInAM.jsx` renders injury-derived AM
   soreness items.

### Merge-time debt on the three pushed branches

- `feat/feedback-ledger` — its DECISIONS **#85–#88** collide with master's; renumber at merge,
  §12 heading ref follows.
- `feat/checkin-injury-probe` — **#89/#90** collide; the `#89`/`#90` in `injury_probes.py` and
  `tests/test_injury_probes.py` docstrings must move with them.
- `feat/interpretation-view-skeleton` — no renumber debt (uses `#NEXT`), but carries a verified
  **contract drift**: its fixture is `['groups','meta']` against master's
  `{meta, groups, ungrouped}` (#86). Wiring it as-is silently drops every ungrouped marker.

### Sprint (ROADMAP NOW)

Health Connect permissions fix · Samsung Health package-name correction · Morning check-in screen ·
Persistent conversation history · Session cards not clickable · Dual-panel scroll layout ·
`mcp_server.get_hevy_workouts` unimported `Session` type.

### Open questions by status

- **`verifying` (1):** Q4 (HC date offset — resolved in code at #64, awaiting confirmation).
- **`open` (18):** Q3, Q5, Q6, Q7, Q9, Q10, Q13, Q15, Q18, Q19, Q20, Q22, Q23, Q24, Q25, Q27,
  Q28, Q29. Cross-repo: Q25 belongs to an HCA-rooted session.
- **`resolved` (10):** Q1, Q2, Q8, Q11, Q12, Q14, Q16, Q17, Q21, Q26.

### Single clearest next action

**Decide the CLAUDE.md vocabulary contradiction (line 60 vs line 72)** — does `OPEN_QUESTIONS.md`
keep `open` / `verifying` / `resolved → #`, or adopt the four states? Phase 1 kept the former and
fixed only the entries invalid under either. The answer determines whether Phase 2 step 10 relabels
HCA's Q1/Q2/Q4/Q5 to `BLOCKED` or to `open`. Decide it, then open a **`health-connect-app`-rooted**
session and cut `gov/branches-vocabulary` from its master.
