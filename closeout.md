# Close-out — Chat write-shape repair + bounded in-turn retry (#344)

## Real commits this session

Continuation of the typed-entries session: the previous close-out landed as `56c2197` (PR #272). Branch
`claude/blissful-brahmagupta-mk7hcf` (harness-assigned; restarted from master before each PR). Each PR was
merged `--merge` on green and its remote branch auto-deleted. Master's maxima were re-read immediately before
every merge.

`git log --format="%h %ad %s" --date=short 56c2197..HEAD`:

```
9652c58 2026-09-28 fix(chat): write-shape examples are placeholder templates, never user-specific values
ddca1dc 2026-09-28 Merge pull request #274 from Easty11/claude/blissful-brahmagupta-mk7hcf
ff4e3c5 2026-09-28 gov(q185): #344 records the bounded in-turn retry and prompt-cost rulings; Q185 -> DONE; BRANCHES
43211f2 2026-09-28 feat(chat): bounded in-turn retry for shape-refused knowledge writes (Q185); drop the region list from the prompt
7e68f58 2026-09-28 Merge pull request #273 from Easty11/claude/blissful-brahmagupta-mk7hcf
3b8b636 2026-09-28 gov(write-shape): Q185 (bounded in-turn retry, ruling owed); BRANCHES row
c88cc48 2026-09-28 fix(chat): generate the constraint/finding write shape from the validators; pass-2 stops promising retries
```

Plus this close-out commit (`chore: session close-out`), landing with `9652c58` in one PR.

- **Deploys:** `7e68f58` and `ddca1dc` both show SUCCESS on backend and frontend. Every change here is
  backend-only, so there is no served-bundle literal to check.
- **Tests:** backend 2216 → 2250; frontend 241, unchanged.

## Pending-queue reconciliation

No `;cc` queue was carried in. The operator paste blocks and where each landed:

- **BUG, prod 28 Sep: constraint writes refused for shape.** The guidance is now generated from the validators
  (#313 pattern), and pass-2 no longer promises retries. → `c88cc48` (PR #273).
- **BUG, prod 28 Sep: stuck loading bubble after a retry.** NOT reproduced; the server logs contradict it.
  Every `/chat` POST from 03:29 to 04:21 UTC returned 200 (6–56 s). The retries were refused again server-side,
  because blocks the user types are never parsed. Locally, a refusal then a retry completes in milliseconds.
  Recorded in BRANCHES; the operator reports a UTC time if the bubble recurs.
- **Q185 ruling:** yes, scoped. → `43211f2`, #344 (`ff4e3c5`, PR #274). Q185 → DONE → #344.
- **Prompt-cost ruling:** drop the region list. → `43211f2`. The unknown-region refusal now names the valid
  set, a prerequisite the ruling assumed and the code lacked.
- **Correction:** the right-shoulder ER constraint is an advisory cap, not an engine block. → examples fixed
  in `43211f2`, then made placeholder templates in `9652c58`. The operator reported the confirmed 9.5 kg cap
  (row 104), so the "11.25 kg" example values were user-specific and contradicted live data.
- **Instruction:** do not run the 11.25 kg test; Q185 is proven by its tests; the next real chat write is the
  prod check. → no test write was made.

**Nits (no gate):** the `ff4e3c5` commit message reads "decisions max on master is #341... #343" (a stray
fragment; #343 was the max). This is cosmetic in history only.

## Cold-resume handoff

**Where things stand.**
- Master is `ddca1dc`, plus this PR (`9652c58` and this close-out).
- Decisions max **#344**; questions max **Q185** (DONE).
- Typed constraints and findings are live, with 4 seeded advisory constraints (ids 95–98) and the
  operator-confirmed right-shoulder 9.5 kg cap (row 104).
- The coach's constraint/finding write shape is generated from the validators, with placeholder examples and
  no region list. A shape refusal gets one in-turn retry.
- **Open prod check:** the next real chat constraint or finding write. The operator reports it.

**NOW lanes and the v1 test each serves** (unchanged this session apart from #344):
- **Injury clearance (operator)** — Know / Walk in. OWED: the narrowed step (3).
- **Typed constraints G6** — Know. DONE → #342.
- **Lab upload pipeline** — Walk in.
- **Interpretation layer build** — Walk in. Increments 2, 3 and 5 remain.
- **Appointment brief** — Walk in. **Not started; substrate complete.**
- **Cross-repo rows** — no v1 test; pinned by #112. They include the paste-addressing propagation to HCA.
- **Demotion candidates:** the DONE rows still sitting in NOW (tags seed #339, CBT-I Q45 #219, eval trigger
  #213).

**Open questions:** 100 OPEN, 4 OWED — Q78, Q176, Q178, and Q181 (retire `user_knowledge`: brief 2, GO ruled,
not cut). Closed this segment: Q185 → #344.

**What was NOT touched this session (and what gates it).**
- **Appointment brief v1 (Walk in, sequence position 3):** still no design brief. Five consecutive sessions
  (#334–#344) have gone to substrate and repair — taxonomy tagging, the clearance sweep, typed entries, and now
  chat-write repair. None moved the synthesising consumer. Say it plainly: the default next session is the
  brief.
- **Interpretation layer increments 2, 3 and 5, and the lab pipeline residuals (Q104):** untouched.
- **Loop surface debt**, including Q180 (server-side chat history). The stuck-bubble report may belong here if
  it recurs.
- **Q181 / brief 2** (retire free-text `user_knowledge`): GO, not cut. Until it lands, the coach still reads
  the free-text rows beside the typed ones.
- **Q182** (default engine constraints from the in-code maps), **Q183** (engine cap/caution, watch) and
  **Q184** (budgeted context builder, LATER): untouched.
- **Cross-repo:** the paste-addressing rule is still not propagated to `health-connect-app`.

**Single clearest next action.** Chat cuts the **Appointment brief v1 design brief** (Walk in). Operator side:
report the next real chat constraint or finding write (the Q185 prod check), then injury-clearance step (3).
