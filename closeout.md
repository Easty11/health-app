# Close-out — Resolved-injury parent for constraints (#352); Q192 closed; row 104 parented

## Real commits this session

The session is `q192-resolved-parent`, on branch `claude/quirky-lovelace-h85how` (assigned by the harness). It was
cut from master `33d989d` (the #284 merge). Master's maxima at open were decisions **#351** and questions **Q192**.
They were re-read against master `091ad5b` before the governance commit, and were still #351 and Q192.

`git log --format="%h %ad %s" --date=short 33d989d..HEAD` (before this commit):

```
091ad5b 2026-09-29 Merge pull request #285 from Easty11/claude/quirky-lovelace-h85how
0a2c138 2026-09-29 feat(knowledge): a constraint may name a resolved injury as parent (Q192)
```

This close-out lands as one governance commit (`gov(knowledge): #352 resolved-injury parent; Q192 closed;
BRANCHES row; Recent landings; close-out`) in its own PR. The branch was restarted from master `091ad5b` after PR
#285 merged.

- **Tests:**
  - Backend: 2370 → 2383 passed, with one test deselected (it needs commit `3360ed5`, which this shallow clone
    lacks).
  - The 5 allow and own-message tests fail on master's validator.
  - Each of the 6 discriminators was removed in turn, and every removal fails at least one test.
  - CI was green on PR #285.
- **Deploy:** the Railway backend build from `091ad5b` reached SUCCESS (checked through Railway MCP) before the
  ledger write. The new image answered: the prod pre-write check found `_is_resolved_injury` (#116). Nothing
  changed in the frontend, so no #121 grep is owed.
- **Ledger:** the operator ran the write in the container (`railway ssh` → `/opt/venv/bin/python`) through
  `upsert_knowledge_entry` with `source='api'`. Row **110** supersedes row **104**. This was a separate act from
  the validator commit, and it came after the deploy.

## Pending-queue reconciliation

No `;cc` queue was carried in. The operator paste blocks (all addressed to this session) and where each landed:

- **VERIFY 1** (the parent-must-be-active check is at `knowledge.py:1039-1052`): confirmed on `33d989d`.
- **VERIFY 2** (row 104's exit): the operator read it as `on_condition` only, with `review_by` 2026-10-26 and
  `asserted_by` user. The HALT case did not apply.
- **VERIFY 3** (nothing ends or hides a constraint under a resolved parent): #351's result stands. The cited files
  had not moved since #351's commit.
- **STEP 1, narrow the validator:** → `0a2c138`, PR #285.
- **STEP 2, tests plus mutation check:** → `0a2c138`.
- **STEP 3, supersede row 104:** DONE in prod. Row 110 carries the same value except `parent_key` =
  `injury_shoulder_right`. `with_parent` stays absent and there was no `/confirm` call.
  - Before the write, Code found that a value stamped by `/confirm` (`confirmed_on`) cannot be rewritten
    verbatim. The operator's read found no `confirmed_on` key on row 104, and the operator ruled to supersede
    verbatim.
- **STEP 4, the brief check:** `in current_constraints: 1`. The ask that resolves the constraint (id `shoulder`)
  has `unresolved: false` and `folded: ["review_due", "undated_exit"]`.
  - `review_due` is additional to the operator's forecast. It is correct: 2026-10-26 falls within the appointment
    date plus 30 days.
- **GATE, backend green plus the mutation check:** met.
- **GATE, prod brief:** met at the data level. The printed-copy read (ask `shoulder` prints "(see Restrictions I'm
  working under above)") is **OWED (operator)**.
- **GATE, row 104 superseded rather than deleted:** met (`active` false, `superseded_by` 110).
- **GUARD, separate validator and ledger commits:** held (the ledger write is not a commit). **Brief scope and
  finding parenting unchanged:** held. **Q192 closed at close-out:** it moved below `## CLOSED`, `DONE → #352`.

**Divergences and calls (named in #352):**
- The `with_parent` refusal keeps the code `invalid_parent`; only its message is new.
- An ACTIVE proposed constraint or finding still passes as a parent, as it did before. The ruling's "a proposed
  current row" is applied to the resolved-parent path only.

## Cold-resume handoff

**Where things stand.**
- Master is `091ad5b`, plus this PR (the close-out). Decisions max **#352**; questions max **Q192**, which is now
  CLOSED.
- The 1 Oct brief now shows the right-shoulder ER load cap under Restrictions, parented to the resolved
  `injury_shoulder_right`.
- The appointment (`appt_20261001_aubrey`) is **Thu 1 Oct 2026**, two days from this close-out.

**NOW lanes and the v1 test each serves:**
- **Appointment brief** (Walk in). Built through #352. What's left:
  - one printed copy (OWED, operator);
  - the #121 greps for #348–#351 (OWED, operator);
  - PR2, post-visit transcript reconciliation (LATER, after 1 Oct).
- **Injury clearance** (Know / Walk in). Step (3) is OWED (operator).
- **Lab upload pipeline** and **Interpretation layer build** (Walk in). Untouched.
- **Cross-repo rows.** They serve no v1 test and are pinned by #112. The paste-addressing propagation to HCA is still
  owed.
- **Demotion candidates:** DONE rows still sitting in NOW (tags seed #339, CBT-I Q45 #219, eval trigger #213, G6
  #342).

**Open questions:** 105 OPEN and 4 OWED (Q78, Q176, Q178, Q181). Q192 closed this session.

**OWED (operator), carried:**
- The Q192 orphan query, run through `railway connect` to `health-app-DB`:
  `SELECT id, key, value->>'status' AS status, value->'exit' AS exit FROM user_knowledge_entries WHERE type = 'constraint' AND active AND COALESCE(value->>'parent_key', '') = '' ORDER BY id;`
  - Any other live constraint with a null parent sits in no brief's scope.
  - Each one can now be parented to a resolved injury through the same path, provided its exit is not
    `with_parent`.

**What was NOT touched this session (and what gates it).**
- **Other orphaned constraints:** unknown until the orphan query runs. Nothing was re-parented except row 104.
- **Q191** (standing review sweep for rows past `review_by` or under a resolved parent): untouched. Six live
  constraints share `review_by` 2026-10-26, and row 110 is one of them. Their alignment waits on the 1 Oct visit.
- **Appointment brief PR2**, **Q181 / brief 2** (retire free-text `user_knowledge`), **Q182–Q184**: untouched.
- **Interpretation layer increments 2, 3 and 5; lab pipeline residuals (Q104):** untouched.
- Seven consecutive sessions (#345–#352) have gone to the appointment brief and what it needs. That is deliberate,
  because v1's synthesising consumer has a dated visit. Once the 1 Oct visit has happened, the next session should
  turn to a Walk-in lane that has stood still, not to more brief polish.

**Single clearest next action.** The operator prints the 1 Oct brief and checks two things: the ER load cap
appears once under Restrictions, and ask `shoulder` reads "(see Restrictions I'm working under above)". Then run
the orphan query above.
