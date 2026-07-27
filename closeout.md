# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

## 1. Real commits this session

Session-open ref: `82df331` (prior `chore: session close-out`). `git log --oneline 82df331..HEAD`:

```
c541561 governance(4b-i): record the assembly/authority split across all four stores
3a9b18e feat(interpretation): emit relations_rendered with operand degradation (4b-i)
f6b3d1c feat(interpretation): three-pass restructure + draw-dated protocol snapshot (4b-i)
e84383d governance: correct stale safety-asset facts, resolve Q41 -> #139
```

Date-stamped (`git log --format="%ad %s" --date=short`, immutable):

```
2026-07-28 governance(4b-i): record the assembly/authority split across all four stores
2026-07-28 feat(interpretation): emit relations_rendered with operand degradation (4b-i)
2026-07-28 feat(interpretation): three-pass restructure + draw-dated protocol snapshot (4b-i)
2026-07-28 governance: correct stale safety-asset facts, resolve Q41 -> #139
```

All four are on `feat/interpretation-relations`, pushed to `origin/feat/interpretation-relations`
(0 unpushed), all `+` under `git cherry origin/master` (real work, unmerged). A fifth
`chore: session close-out` commit carries this file + the CLAUDE.md Recent-landings update.

The branch delivers the **structural half of 4b (4b-i)** from the `SPEC_4b_producer.md` brief:
three-pass producer restructure, member `relations_rendered[]`, and draw-dated
`meta.protocol_context_snapshot`. Demotion, `shared_levers`, `axis_verdict`,
`member_lever_effects`, `mechanism`, `stable_rationale`, `expected_by_phase`, the endpoint, and
fixture regeneration are **deliberately held for 4b-ii** (each named in `BRANCHES.md`).

Backend suite **453 passed** (baseline 448 per #139, **+5**). Gates G1–G9 all reported green in
session (behaviour-neutral restructure proven by empty pre/post `build_foundation` diff + 4a test
file byte-unchanged at the checkpoint; snapshot draw-dated with a live negative control; relations
degrade-not-fabricate; feedback `unresolvable` + `on_trt` in no non-test source; `news_gate`
two-key with no `demot` basis; held fields absent; split recorded in all four stores).

## 2. Pending-commit queue reconciliation

**No `;cc` pending-commit queue was carried into this session.** The session was driven by the
`SPEC_4b_producer.md` brief (a chat-authored proposal, not a pending-queue paste), so there are no
`PENDING` items to reconcile against. The brief WAS the payload; every step (A–E + governance) landed
in the four commits above. Nothing decided this session remains uncommitted **on the branch** — but
the whole branch is provisional against master until it ff-merges: the DECISIONS `#NEXT`×3 and
OPEN_QUESTIONS `Q-NEXT`×2 are unminted, and 4b-i is not truth-on-master until the merge.

## 3. Cold-resume handoff

**Where things stand.** 4b-i (interpretation producer structural half) is complete, tested, pushed,
and **held for review** on `feat/interpretation-relations` — not merged. The producer is now
three-pass (`_assemble_members` → `_relations_rendered` → `_should_surface` inside `_build_group`),
emits member `relations_rendered[]` (operand `complete`/`degraded`+`operands_missing`, `feedback`→
`precondition_status: "unresolvable"` echoing the raw `precondition_phase`), and emits
`meta.protocol_context_snapshot` dated to the panel's `collected_date`. No demotion; gate 1 still raw.

**Single clearest next action:** review `feat/interpretation-relations`; on acceptance, ff-merge to
master (`git checkout master; git merge --ff-only feat/interpretation-relations; git push origin master;
git branch -d feat/interpretation-relations; git push origin --delete feat/interpretation-relations`).
At that merge, resolve the three `### #NEXT` DECISIONS headings to the next three integers
(140/141/142) and the two `## Q-NEXT` OPEN_QUESTIONS headings to Q56/Q57, and set the ROADMAP 4b-i row
status from OWED to DONE(SHA). BRANCHES.md carries the branch row (OWED) with the full merge checklist.

**Open questions by status (this session's additions):**
- **UNSTARTED (Q-NEXT, mint Q56/Q57 at merge):**
  - `precondition_phase` (`on_trt`) vs `derive_phase` (`steady|episodic|washout|stopped|re_entering|
    None`) — no mapping in asset or code. Blocks 4b-ii demotion of the `feedback` arm. Asset content.
    Owner: Luke.
  - Lever→declared-factor join absent (no mapping field on lever nodes). Blocks I3 `shared_levers[]`.
    Smallest fix: authored `declared_factor_keys: []` per lever node. Asset content. Owner: Luke.
- **DONE this session:** Q41 → `DONE → #139` (safety-asset stale-fact correction, commit `e84383d`).

**4b-ii blockers (none block 4b-i):** the two Q-NEXT above (asset content) + ingestion (empty
`lab_reports`/`lab_results`, unverified-from-session) which blocks 4b-ii's view-wiring half only. The
safety-band citation blocker is discharged (#139).

**Two cosmetic 4b-ii carry-overs (flagged in review, non-blocking):**
- Duplicate `# ---------- G5` section label in `test_interpretation_producer_foundation.py` (two
  gate-numbering schemes collide: 4a-brief G5 = gate-2 source vs this brief's G5 = vocab gap).
  Harmless to pytest; sweep when that file is next open (4b-ii).
- The G5 grep proves no bare `on_trt` literal, not no *mapping*. Right guard for the live threat
  (hardcoded `if phase == "on_trt"`); 4b-ii's phase-resolution work needs a positive test that the
  mapping does the right thing, not a substitute discharged here.

**Sprint (ROADMAP):** interpretation build sequence now splits 4b into **4b-i** (OWED, this branch) and
**4b-ii** (BLOCKED — interpretive half: demotion, levers, verdict, endpoint, view fixture→live). Forks
still open for 4b-ii: cache-on-confirm vs compute-on-read, and `axis_verdict` depth.

**Loop discipline:** single-repo (health-app only) throughout; no `frontend/`, no `health-connect-app`,
no shared-CLAUDE.md-block edits. `INTERPRETATION_OUTPUT_CONTRACT.md` (UI-maintained) not written.
