# Close-out — 2026-07-19 · #88 interruption-survival governance

Branch: `master` @ `0b24da7` (pushed, origin in sync). Session anchor: `eed3c76` (#87).

---

## 1. Real commits this session

`git log --oneline eed3c76..HEAD` (health-app), pre-close-out:

```
0b24da7 gov: mint #NEXT -> #88 at merge — master max was #87 (eed3c76), no branch merged since
3cf3d16 gov: #NEXT interruption-survival — unseeable-surface rule, state vocabulary, ledger, close-out git-log
5243dd6 gov: HANDOFF ledger — CHAT->CODE receipt for interruption-survival brief (#NEXT)
```

Repo self-record — `git log --format="%ad %s" --date=short -10` (per the #88 close-out rule;
immutable commit dates, not a self-reported stamp):

```
2026-07-19 gov: mint #NEXT -> #88 at merge — master max was #87 (eed3c76), no branch merged since
2026-07-19 gov: #NEXT interruption-survival — unseeable-surface rule, state vocabulary, ledger, close-out git-log
2026-07-19 gov: HANDOFF ledger — CHAT->CODE receipt for interruption-survival brief (#NEXT)
2026-07-19 gov: #87 oracle fixture display_name re-sync — #86's contract-divergence caveat exercised
2026-07-19 test(interpretation): re-sync fixture group display_name + assert it (close silent oracle gap)
2026-07-18 gov: #86 interpretation producer foundation (4a) — gates, is_moved, flat ungrouped
2026-07-18 gov: reconcile declared-state number-at-merge debt — mint #NEXT -> #85, BRANCHES row LANDED
2026-07-18 feat(interpretation): foundation producer (4a) — newest+prior gates, is_moved, flat ungrouped
2026-07-18 gov: BRANCHES row for feat/protocol-declaration — in flight, local-only
2026-07-18 gov: #NEXT structured declared-state ledger — continuity-aware types + phase derivation
```

Cross-repo (health-connect-app, separate repo, pushed `4f36432..63bdc73`):

```
63bdc73 gov: propagate shared loop-rules block — unseeable-surface rule, state vocabulary, close-out git-log
```

A `chore: session close-out` commit follows this file on `master`.

---

## 2. Pending-queue reconciliation

No chat `;cc` pending-commit queue was carried in — this session ran from a pasted **brief**
(interruption-survival governance, 4 changes / 5 gates). Reconciling the brief's payload against
landed commits:

| Brief item | Landed | State |
|---|---|---|
| 1 · Unseeable-surface rule → CLAUDE.md shared block (both repos) | `3cf3d16` (health-app) + `63bdc73` (HCA) | **DONE** |
| 2 · State vocabulary (DONE/BLOCKED/OWED/UNSTARTED) → shared block (both repos) | `3cf3d16` + `63bdc73` | **DONE** |
| 3 · `HANDOFF.md` — append-only ledger, health-app root, receipt-first | `5243dd6` (receipt, pre-work) + `3cf3d16` (landing entry) | **DONE** |
| 4 · `/closeout` emits `git log --date=short -10` → bound in CLAUDE.md (not session-local `closeout.md`) | `3cf3d16` | **DONE** (exercised in §1) |
| 5 · FEEDBACK §12 — the #87 declarative-precondition incident | `3cf3d16` | **DONE** |
| DECISIONS #88 minted at merge | `0b24da7` | **DONE** |

Gate results (verified on landed `master`):

- **G1** — CLAUDE.md shared blocks byte-identical across both repos: **PASS** (committed diff clean; 147 lines / 9585 bytes each). No pre-existing divergence — the blocks were already identical before edit.
- **G2** — full suite green, count unchanged from 206: **PASS** (`206 passed`, re-run on landed master).
- **G3** — `git diff --stat` scoped to `CLAUDE.md` ×2, `HANDOFF.md`, `FEEDBACK.md`, `BRANCHES.md`, `DECISIONS_LOG.md`; no `backend/`/`frontend/`/`alembic/`: **PASS**.
- **G4** — `HANDOFF.md` non-vacuous (≥ #87 land + this brief's receipt): **PASS** (3 entries).
- **G5** — vocabulary applied to two live BRANCHES rows: **PASS** — `fix/probe-harness-fidelity` → OWED (names the outstanding container run), `feat/recovery-metrics-rhr` → BLOCKED (names the HCA node-dump blocker + owner Luke). Neither resisted the four states.

Nothing decided-but-uncommitted. All provisional items landed.

---

## 3. Cold-resume handoff

### Branch terminal state
- **Touched this session:** `gov/interruption-survival` — merged (ff to master `0b24da7`) + local branch deleted. Never pushed to origin (ff'd into master, which is pushed). **Resolved.**
- **Pre-existing branch-gate DEBT (not touched this session, surfaced by the close-out sweep):** three local branches carry real unmerged work but have **no dedicated `BRANCHES.md` row** — only prose mentions inside rows 5/6:
  - `feat/feedback-ledger` (+4 vs origin/master)
  - `feat/interpretation-view-skeleton` (+3)
  - `feat/checkin-injury-probe` (+2)
  Each needs a proper row (purpose / why-parked / unblocks-on), or push/discard. Not fabricated here — their verified state is not in hand this session. `feat/recovery-metrics-rhr` (+1) does have a row (now **BLOCKED**).

### Current sprint (ROADMAP NOW)
Health Connect permissions fix (record types 38/35/11/37); Samsung Health package-name correction (`com.sec.android.app.shealth`, verify via Railway Postgres); morning check-in screen (Hooper Index, primary daily touchpoint); persistent conversation history (clears on refresh); session-cards-not-clickable + dual-panel scroll UI bugs; `mcp_server.get_hevy_workouts` unimported `Session` one-line fix.

### Open questions (by status)
- **open:** Q13 (HRV scraper-only single point of failure), Q15 (`3497…` prod-drift reconciliation), Q17 (HRV step-change (A) instrumentation vs (B) physiology — blocked on Task-1 HCA node dump), Q18 (`samsung_hrv_readings` out-of-range historical sweep, verify-at-Railway), Q19 (desktop workout-detail scroller starved), Q20 (clinical findings vs restrictions conflated in `user_knowledge_entries.value`), Q22 (promote exercise-region tags to source-agnostic layer, deferred), Q23 (`_RADICULAR_/_RA_FLARE_` block-set revision), Q24 (`laterality` consumers / `capability_state.side`), Q25 (cross-repo: HCA remote branch `claude/hevy-api-workout-query-teulc2` disposition — HCA-rooted session), Q27 (Capability_Taxonomy v1 strength-ratio axis), Q28 (`Pullover` not a constraint-neutral probe subject — next harness-open).
- **resolved:** Q21 (lab expectation contract vs injury trajectories — rhyme, no shared code), Q26 (→ #76, three-state coverage).

### Lead worth chasing (cross-repo, not consumed here)
`health-connect-app` has an untracked **`nodedump.txt`** (plus modified `src/healthConnect.js` and untracked `checkin_build_brief.md`, `hevy_routine.json`) — uncommitted WIP left untouched. Given Q17 / `feat/recovery-metrics-rhr` are BLOCKED precisely on "the Task-1 HCA node dump," that filename is a candidate unblocker. Unverified (unpushed local disk — an instruction to verify, not a fact). Investigate from an HCA-rooted single-repo session.

### Single clearest next action
Resolve the pre-existing branch-gate debt: give `feat/feedback-ledger`, `feat/interpretation-view-skeleton`, and `feat/checkin-injury-probe` dedicated `BRANCHES.md` rows (or push/discard) so no local branch with real work sits in undefined limbo. (Then, separately: chase the HCA `nodedump.txt` lead above.)
