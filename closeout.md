# Close-out — Injury clearance sweep (surfacing-only) + legacy free-text bleed (#340, #341)

## Real commits this session

Session-open ref: master `360b385` (the PR #268 merge). One PR, branch `claude/zealous-wozniak-b3f2g8`
(harness-assigned; the brief's `feat/injury-clearance-sweep` yielded to it and the name is recorded in
BRANCHES), merged with `--merge` and remote-deleted:

```
11be50e Merge pull request #269 from Easty11/claude/zealous-wozniak-b3f2g8
244528b gov(injury-sweep): #340 clearance sweep, #341 free-text bleed; Q9 annotated; Q180
ab2617c feat(prompt): injury facts leave the free-text knowledge_update categories
718d261 feat(injuries): clearance sweep card after resolve; Sweep again on resolved rows
b879e22 feat(sweep): hamstring aliases + primary/secondary term tiers (G1 ruling)
aeaad29 test(sweep): G1 raw prod fixture -- the 15 regex lines at their real indexes
9ac86fa feat(sweep): other-injury labels collapse superseded keys, skip same body part
e200716 feat(sweep): label hit lines as history and by other injuries named
51fbfcf test(sweep): id 29 restrictions confirmed from prod (matches seed)
30a5017 test(sweep): prod resolution bases and re-home row 94 in the audit fixture
560f1a1 feat(knowledge): sweep audits restrictions for orphans; real-data fixture
f6ec3a2 feat(knowledge): injury clearance sweep (surfacing-only)
0711535 fix(seed): injury seed keys on key regardless of active
```

This close-out lands as a second, governance-only PR from the same branch, re-cut from master `11be50e`.
No migration. No production data was written by Code at any step; every prod read was operator-run.
Self-merged on green (placeholder guard, pytest, vitest); master was re-read at the merge instant
(#339 / Q179, unmoved) so #340, #341 and Q180 were claimed on the branch. Backend 1983 → 2031,
frontend 231 → 240; eslint clean on touched files (6 pre-existing errors elsewhere, unchanged).

## Pending-queue reconciliation

No `;cc` queue was carried in. Chat handed off one gated brief plus rulings in-session; each item:

- **S0 verification (G0).** Reported. (a)/(b) held; (c) prod read OPERATOR-RUN, later relayed; (d) store
  inventory reported; **(e) was FALSE on master**: `_seed_injuries` skipped only on an ACTIVE key, so a re-seed
  would resurrect a resolved injury. Ruled into S1.
- **G0 ruling 1 (seed fix).** LANDED `0711535`. Test fails on the old filter.
- **G0 rulings 2–3 (line-level hits, action edit; side as a flag).** LANDED `f6ec3a2`.
- **G0 ruling 4 (S3, prompt only).** LANDED `ab2617c` → #341. Byte difference declared (1032 → 1510, +478);
  parity guard narrowed at the section with a no-op control, verified to refuse the old section.
- **G0 ruling 5 (Q9 annotate, new Q, browser chat history on the checklist).** LANDED: checklist item
  `f6ec3a2`; Q9 annotation + **Q180** `244528b`.
- **G0 addendum (restriction orphan audit, radicular warning, raw-data fixture).** LANDED `560f1a1`,
  `30a5017`, `51fbfcf` (prod bases, row 94, id 29 restrictions confirmed = seed), `aeaad29` (the 15 raw lines at
  their real indexes; rows 3/5 personal and medication detail omitted from the repo).
- **G1 ruling 1 (id 29 striding/sprinting orphans).** RECORDED as a known limit in tests, PR and #340; matcher
  not tuned.
- **G1 ruling 2 (raw set is the fixture; (A)-(F) is the after-set).** LANDED `e200716`/`aeaad29`: labels
  `marked_resolved` + `other_injuries` built; before/after pair asserted.
- **G1 ruling A/B (aliases + term tiers).** LANDED `b879e22`. Raw result, both sweeps: 15 hits = operator's 15
  − 2/56 (calf, no hamstring term) + 2/54 (semitendinosus alias → row 75); 2/8 and 2/55 hit via alias; swim
  lines 3/10, 3/12 dropped. Reverses the G0 calf-line expectation, by ruling.
- **G2 (frontend).** LANDED `718d261`; operator GO given.
- **G2 forward-compat note** (`reaches_context` must be derived from the renderer's inclusion rule, not a
  per-store constant). RECORDED in the Q9 annotation `244528b`; no rework, by instruction. **Still a constant
  in code** — it flips only when Q9 lands.
- **S4 governance.** LANDED `244528b`: #340, #341, Q9 annotation, Q180, BRANCHES, CLAUDE.md Recent landings.
- **A second brief (typed `constraint` / `finding` entries) was received mid-session and WITHDRAWN by the
  operator** ("finish this work; new session for the subsequent brief"). Nothing was built for it: a local
  `feat/constraint-finding-types` branch was cut from `360b385` for the anchor check only, never committed to,
  never pushed, and deleted. It is **not provisional work** — it is unstarted, and its brief lives in chat.
- **Operator-owed (not Code's):** the post-deploy clearance itself — now a ROADMAP NOW row.

## Cold-resume handoff

**What landed.** The injury ledger is the only authority on injury state (#340). `GET
/knowledge/injuries/{id}/sweep` finds every copy of an injury outside the ledger — free-text `user_knowledge`
per line, non-injury structured entries, Hevy routine notes via the cache — labelled (restriction terms =
stale order, history, other side, other injuries named, reach), with a restriction audit
(covered / rehomed / orphan, radicular warning) and a fixed manual checklist. The Injuries page runs it after a
resolve and on "Sweep again". The coach no longer writes injury facts to free text (#341). A re-seed can no
longer resurrect a resolved injury.

**Sprint position.** v1 is See (MET) / Know / Walk in / Loop. This session served **Know** and **Walk in**
indirectly: stale injury copies were re-imposing a resolved hamstring on the coach every turn and would have
fed the appointment brief's injury section. It was debt, not product surface.

**Open questions touched:**
- **OPEN, annotated:** Q9 (retire or render-gate the free-text store). Now carries a live cost and the
  derived-label requirement. This is the structural fix the sweep only mitigates.
- **OPEN, new:** Q180 (browser chat history: one non-expiring conversation re-sent every turn; unsearchable copy
  store, unbounded tokens).

**Single clearest next action.** Operator: after the #269 deploy settles, do the ROADMAP NOW "Injury
clearance" row — bundle grep `Clearance sweep —`, then sweep ids 18 and 29 and edit each flagged line in
Settings (stale orders first; lines naming active row 94 are edited, never cleared). For Code, the next
brief is the one the operator withdrew into a new session: typed `constraint` / `finding` entries, which is
where Q9 is ruled.

**What was NOT touched this session (named, not implied finished):**
- **Walk in — appointment brief, lab upload pipeline, interpretation-layer build.** All three NOW rows
  unchanged. The brief remains the synthesising consumer that sets build order.
- **Know — the plan of record and Q27's slot-keying design.** The prior close-out's single next action;
  untouched. The decompression phase's real design still waits on it.
- **Know — the metabolic INGEST bridge.** Untouched for a second session running.
- **Loop — the surface-debt sweep and persistent conversation history.** Untouched; Q180 now names the
  history problem but builds nothing.
- **CBT-I** (Q177 items 1/3, Q178 migration). Untouched.
- **Honest pattern note.** Two consecutive sessions went to instrument over product: last session to
  classification tooling, this one to a clearance instrument for data the app itself had duplicated. Both
  were warranted — each fixed a live false signal — but neither advanced a v1 test's own surface. The next
  Code session should be the typed-entries brief only if it is on the path to Walk in (the brief reads
  findings and constraints); otherwise Q27 or the appointment brief.

**v1 triage of NOW:**
- **Injury clearance (operator), new:** serves Know and Walk in (true injury state for coach and brief).
- **Training seed row:** DONE → #339; drops out at the next ROADMAP sweep.
- **Two CBT-I rows:** both DONE; drop out at the next sweep.
- **Lab upload pipeline, interpretation-layer build, appointment brief:** serve Walk in (test 3).
- **Cross-repo shared-block edit (owed):** serves no v1 test; in NOW only by #112's pin for cross-repo debt —
  a demotion candidate if that pin is revisited.
