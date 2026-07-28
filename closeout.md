# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

## 1. Real commits this session

Session-open ref: `c4e5da2` (the silently-failed governance commit this session repairs).
`git log --oneline c4e5da2..HEAD`:

```
f8f020a gov: resolve #149 / Q59 missed at c4e5da2; record the staging failure (FEEDBACK §21)
```

Date-stamped (`git log --format="%ad %s" --date=short`, immutable — recent history for context):

```
2026-07-29 gov: resolve #149 / Q59 missed at c4e5da2; record the staging failure (FEEDBACK §21)
2026-07-29 gov: number-at-merge - #149, Q59; branch row DONE       <- c4e5da2, the failed no-op
2026-07-29 governance: record MCP-pin decision + the deployability gap; park branch
2026-07-29 fix(deps): pin mcp[cli]==1.28.1 to restore deploys
2026-07-29 governance: resolve #NEXT -> #146/#147, Q-NEXT -> Q58, +#148 scope rule (on-branch, pre-ff)
2026-07-28 governance(ingestion): record derived-confidence + draw-as-trigger; findings; unblock 4b-ii
```

One commit this session, direct on master (no branch — see §2). It repairs `c4e5da2`, whose
message claimed "#149, Q59; branch row DONE" but which committed ONLY an untracked
`.claude/launch.json`: the governance edits were never staged (`git add -A` found only the stray
file, so `git commit` succeeded and masked the would-be "nothing to commit"). `f8f020a` resolves
`### #NEXT` → `### 149.` (MCP pin), `## Q-NEXT` → `## Q59.` (deployability gap), flips the
`fix/pin-mcp-sdk` BRANCHES row OWED → DONE with the deploy verification, and adds FEEDBACK §21
(stage governance by name, never `git add -A`; a passing `git commit` proves the instrument works,
not that it committed what you meant — §17's discriminate-on-identity in a new mechanism).

Staged by name; suite **460**, unchanged; no code touched. `.claude/launch.json` left tracked
(inspected: no secrets, nothing machine-specific — removing/ignoring it would be a second unrelated
change on a repair commit).

## 2. Pending-commit queue reconciliation

**No `;cc` pending-commit queue was carried into this session.** The session was a targeted repair
of a prior merge's silent no-op, driven by a chat-authored brief (not a pending-queue paste). No
`PENDING` items to reconcile. Everything the brief specified landed in `f8f020a`; nothing decided
this session remains uncommitted.

**Branch terminal-state gate: PASS.** This session cut no branch — the repair ran directly on
master (renumber-then-land does not apply: `fix/pin-mcp-sdk` was already merged as `c4e5da2` and
deleted before this session, so there was nothing to renumber on, and cutting a branch would only
widen the window master carried live placeholders). `git branch` shows only `master`, even with
`origin/master` (0/0). The `fix/pin-mcp-sdk` row in `BRANCHES.md` is DONE (`c4e5da2`), with the
missed-renumber cause, the deploy verification, and the one still-outstanding operator check.

## 3. Cold-resume handoff

**Where things stand.** Master is at `f8f020a`, even with origin, tree clean. DECISIONS through
**#149**, questions through **Q59**, zero live `#NEXT`/`Q-NEXT` placeholders anywhere. Production
is **healthy**: the MCP-pin deploy (`1778471d`) is Online, `GET /health` → `{"status":"ok"}`,
database at `c1e8b4d70f92` with both ingestion migrations confirmed by operator query (no
`overall_confidence` zeros; `marker_canonical IS NULL` count = 0).

**Single clearest next action:** begin **4b-ii** (the interpretation producer's interpretive half)
— it is UNSTARTED and fully unblocked (ingestion exercised, Q56/Q57 discharged, trigger resolution
settled as a draw per #147). Its own brief covers: relation-based demotion of gate 1's delta arm,
`shared_levers` with already-in-play filtering, `axis_verdict`, `mechanism`/`stable_rationale`, the
draw-triggered `GET /labs/interpretation` endpoint, and the view wired fixture→live.

**Open questions (this session's additions + the live near-term ones):**
- **Q59 (new, UNSTARTED)** — nothing verifies the deployable artifact: no CI, and no check observes
  that the app boots (the 2.0 outage passed 460 tests against a session venv that already had the
  SDK). One gap, two faces. Owner: Luke — design call on where a boot check lives given no pipeline.
- **Q58 (UNSTARTED)** — the editable-confirm increment (read-only screen has no remedy for a wrong
  value; `missingCollected` dead-end; post-edit provenance undesigned). Needs a provenance design
  before build.
- **Q56/Q57 — DONE** (#143 / #145). **Q41 — DONE** (#139).

**Operator items still owed (unreadable from a Code session; recorded on the `fix/pin-mcp-sdk`
BRANCHES row):**
- The last-good pre-failure Railway build log's `Successfully installed` line names the exact prior
  mcp version — if it differs from 1.28.1, prefer it. (The pin is verified sound in a clean venv;
  this is a belt-and-braces cross-check.)

**Sprint (ROADMAP):** interpretation build sequence — 1 / 4a / declared-state / 4b-i all DONE; **4b-ii
UNSTARTED, unblocked**; increments 2 (rephrase), 3 (lever-tap thread), 5 (go-live) UNSTARTED.

**Process note this session (FEEDBACK §21):** stage governance files by name, never `git add -A`,
and read `git diff --stat` before staging — a `git commit` that succeeds does not prove it committed
the intended files, and an incidental untracked file can supply the signal that masks a no-op.

**Loop discipline:** single-repo (health-app) throughout; no `frontend/`, no `health-connect-app`,
no shared-CLAUDE.md-block edits; `backend/` untouched (the pin is live and correct).
