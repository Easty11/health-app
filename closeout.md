# closeout — health-app

Branch: **master**, in sync with `origin/master` (0 ahead / 0 behind).
Session: five sequential chat implementation briefs — exercise-tag coverage → Hevy resolver activation
→ resolver candidate suggestions → probe-harness fidelity.
Status: **complete + landed + prod-verified.**

---

## 1. Real commits this session

Session-open ref: `87ddd0c`. `git log --oneline 87ddd0c..HEAD` — 20 commits, all on master, all pushed:

```
3feaa44 gov: #83 ratio tier EXERCISED live — floor admits noise, ranking carries it
7330030 gov(branches): fix/probe-harness-fidelity LANDED at adb67e8
adb67e8 gov(branches): fix/probe-harness-fidelity row
5c5b43f fix(probe): fail loudly when a probe never reaches its subject
40c8b0d gov: #83 verified at 494 rows (quality yes, threshold unexercised) + FEEDBACK 11
bc5f4f7 gov: DECISIONS_LOG 83/84 + BRANCHES
62bf248 feat(probe): land the resolver probe harness as a repo instrument
b21ce7f feat(chat): name candidates in the unresolved-title warning
35f4d1c feat(hevy): suggest_candidates — ranked candidates for an unresolved title
d19b0b4 gov(branches): feat/hevy-resolver-activation LANDED at 9193453
9193453 gov: DECISIONS_LOG 80/81/82 + BRANCHES + strike ROADMAP resolver row
320eedf test(chat): pin id+title provisioning path — B3 needed no code change
8ca6108 feat(chat): permit canonical TITLE emission; narrow the #43 parity guard
bc81911 feat(chat): render workout history with CATALOGUE titles, not logged snapshots
e626e54 gov: record G5 confirmed in prod + FEEDBACK 10 (false-green instruments)
fee7f3e gov(branches): fix/exercise-tag-coverage loop CLOSED — prod fallback hit-rate 0
d01603c gov(branches): fix/exercise-tag-coverage LANDED at 8a29b1f
8a29b1f gov: DECISIONS_LOG #79 (reference titles key to the catalogue) + BRANCHES
727adb3 feat(exercise-tags): ID-keyed coverage audit + extract the three-state rule
68e3c9e fix(exercise-tags): key BSS reference title to the catalogue, not the workout log
```

Decisions minted: **#79 – #84** (each claimed only after re-checking master's max at commit time; all
uncontested). FEEDBACK gained **§10** (false-green instruments) and **§11** (a probe that presumes its
own answer). ROADMAP's "Hevy resolver activation" NEXT row struck at `9193453` — it shipped.

Test suite: **137 passed** at close (94 at open). No migration, no schema change, all session.

---

## 2. Pending-queue reconciliation

**No `;cc` pending-commit queue was carried in** — the session ran from five direct chat briefs, each
reconciled at its own gate. Every brief item landed:

| Brief item | Landed |
|---|---|
| BSS reference title → catalogue-keyed | `68e3c9e` |
| ID-keyed coverage audit + `classify_coverage` extraction | `727adb3` |
| G5 prod-clobber recorded + FEEDBACK §10 | `e626e54` |
| History renders catalogue titles (#81) | `bc81911` |
| Title emission + parity-guard narrowing (#80/#82) | `8ca6108` |
| `suggest_candidates` + candidates in the warning (#83) | `35f4d1c`, `b21ce7f` |
| Probe harness as a repo instrument (#84) | `62bf248` |
| Probe fails loudly when it never reaches its subject | `5c5b43f` |

**Brief premises that did not survive contact with the tree** (reported, not improvised across):

- **Bulgarian test reconciliation** — no such reference existed. `tests/test_exercise_region_tags.py`
  never pinned the bare title; the seeder test derives fixtures from the proposal, so a rename is
  invisible to it by construction. No commit.
- **`unresolved` discarded in `_process_routine_actions`** — false. It already surfaced the titles and
  skipped `create_routine` (fail-closed, whole-routine), pinned since #60 by
  `test_unresolvable_title_skips_routine`. **No code shipped**; `320eedf` pins the id+title path that
  #82 newly opened instead.
- **Threading `db` into `context_builder`** — rejected. It would have broken the formatter-only
  invariant the #43 guard protects, then hidden the breach behind an optional-default parameter. The
  join runs upstream in `routers/chat.py` (`bc81911`); the guard is untouched structurally.
- **The "byte-parity guard" not found by grep** — it exists:
  `test_context_builder_output_unchanged_pre_post_refactor` (`tests/test_current_state.py:138`), a
  full-string assertion against pinned SHA `3360ed5`, **unre-baselineable** (the SHA cannot move without
  going old-vs-old, per the test's own comment). Forced #80's narrowing: measured before accepting —
  5055/6398 chars (79%) stay under the assertion, and 1338 of the 1343 dropped chars ARE the excised
  section.
- **Guard re-baseline had no decision entry** — ROADMAP:36 named it decision-grade and the brief dropped
  it. Minted as **#80**; the brief's #80/#81 shifted to #81/#82.

**Provisional / uncommitted:** nothing. Every decision landed in a commit.

---

## 3. Cold-resume handoff

### What shipped

The #60/#61 title→id resolver is **live in prod and verified end-to-end**, having been dormant since it
landed. The chain: tag reference keyed to the catalogue (#79) · history rendered to the model with
catalogue titles via an upstream `canonical_title` join (#81) · provisioning accepts a canonical title,
matching still EXACT (#82) · unresolved titles return ranked candidates instead of a dead end (#83) ·
the #43 parity guard narrowed rather than retired (#80) · model-facing contracts verified by an
operator-run probe (#84).

**Prod verification (2026-07-15, live 494-row catalogue, real model):** fallback hit-rate **0** over 38
distinct movements (25 tagged / 13 adjudicated no-pattern / 0 untagged). A bare `Calf Raise` misses and
returns 5 genuine candidates; fail-closed holds until the user disambiguates, then the routine
provisions. `B5D3A742` resolves as `Bulgarian Split Squat (Dumbbell)` while still logged as bare
`Bulgarian Split Squat` — #79's drift, confirmed in prod.

### Open items owed on this work

1. **`Pullover` is not constraint-neutral → OPEN_QUESTIONS Q28.** `probe_resolver.py` labels it so, but
   the live model flagged it against the active **shoulder injury** (horizontal adduction / overhead).
   It proceeded after confirmation so the measurement survived — the probe passes for a reason it does
   not state. Q28 records that the obvious replacements each fail one of the two required constraints
   (Reverse Fly is in the 28-day window → no title forced; Cable Crossover is horizontal adduction), and
   that dropping `Pullover` outright probably suffices.
2. **`_SUGGEST_MIN_RATIO = 0.5` — closed, do not re-open naively.** The ratio tier fired live
   (`Preacher Curl` → `Rope Cable Curl` 0.643 / `Drag Curl` 0.636; `Pullover` → `Pull Up` 0.533). The
   floor admits noise; containment-first **ranking** carries the feature. #83 records explicitly: **do
   not raise the floor** — 0.512 (a real candidate) sits below 0.533 (noise), so ratio does not separate
   signal from noise in either direction at this scale.
3. **G5 live-resync clobber** — confirmed in prod 2026-07-14 (operator run), but the fingerprints are
   **pre-BSS (36 tags / 55 adjudicated)** and prod is now 37/56: a dated, superseded baseline, not a
   reproducible check. The result stands (the mechanism is row-count-indifferent).
4. **Q27** — the 13 adjudicated no-pattern movements (rotator-cuff / isolation families) park behind the
   v1 strength-ratio axis. Separate design pass, not a gap.

### Open questions by status

**Opened this session: Q28** (`Pullover` is not a constraint-neutral probe subject — the resolver probe
passes by luck). None resolved. No other OPEN_QUESTIONS entry edited.
- **open:** **Q28 (new)** · Q5 (Polar `hrv[]` payload) · Q7 / Q20 (findings-vs-restrictions schema gap) · Q13 ·
  Q17 (HRV instrumentation-vs-physiology, blocked on the `health-connect-app` node dump) ·
  Q18 (Railway historical sweep, independent of Q17) · Q19 (desktop scroller) · Q27 (v1 strength-ratio
  axis) · the `health-connect-app`-rooted items (carry across; single-repo scope rule).
- **verifying:** the #64 G4 item.

### Current sprint (ROADMAP NOW)

Health Connect permissions (record types 38/35/11/37) · Samsung Health package-name correction
(`com.sec.android.app.shealth`; verify via Railway query) · morning check-in screen (Hooper Index) ·
persistent conversation history · session cards not clickable · dual-panel scroll ·
`mcp_server.get_hevy_workouts` unimported `Session` (pre-existing one-line import fix).

### Branches

- Landed + deleted this session (none ever pushed to origin): `fix/exercise-tag-coverage` ·
  `chore/g5-record` · `feat/hevy-resolver-activation` · `feat/resolver-candidate-suggestions` ·
  `chore/resolver-loop-close` · `fix/probe-harness-fidelity` · `chore/ratio-tier-exercised`.
- `feat/recovery-metrics-rhr` — **PARKED** (prior session, not touched here; `git cherry` → `+ a4e1887`,
  real unmerged work). Held on the HRV Task-1 node dump in `health-connect-app`.
- Gate: **PASS** — no branch in undefined limbo.

### Single clearest next action

**Resolve OPEN_QUESTIONS Q28** — drop `Pullover` from `_RESOLVER_PROBE` in `backend/probe_resolver.py`
(keeping `Calf Raise` + `Preacher Curl`, both prod-confirmed to force a title), then re-run
`/opt/venv/bin/python probe_resolver.py 1` in the Railway container. It is the only item this session
leaves that can silently rot: the probe currently passes for a reason it does not state, which is the
exact shape FEEDBACK §11 was written about. **The backing is Q28, not this file** — `closeout.md` is
session-local and the next close-out overwrites it. After that, pick up the ROADMAP NOW items.

### Untracked, left alone (not mine)

`.claude/launch.json`, `backend/gate_test.py`.
