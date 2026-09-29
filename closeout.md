# Close-out — Appointment brief print wording (#351); row-104 parenting halted (Q192)

## Real commits this session

Session `brief-print-polish`, on branch `claude/elegant-hamilton-kuc1og` (harness-assigned), cut from master
`f0bcc80`. Master's maxima at open and again before the governance commit: decisions **#350**, questions
**Q191**.

`git log --format="%h %ad %s" --date=short f0bcc80..HEAD` (before this commit):

```
8d6970d 2026-09-29 feat(appointment): print wording for injury changes; capitalised Area
```

This close-out lands as one governance commit (`gov(appointment): #351 print wording; Q192; BRANCHES row;
Recent landings; close-out`) in the same PR.

- **Tests:** backend 2370 passed (1 deselected: it needs commit `3360ed5`, absent from this shallow clone);
  frontend 298 → 302; eslint clean on touched files. Real-browser print: the fixture is 1 A4 page.
- **Deploy:** not checked from here. The frontend check is a #121 served-bundle grep for `Recorded as resolved`.

## Pending-queue reconciliation

No `;cc` queue was carried in. The operator paste blocks (both addressed to this session) and where each landed:

- **STEP 1, print wording in the Since table** ("Recorded as resolved"; "Updated: <after>" with a grey
  "Previously: <before>"; "Injury first recorded"; "Injury record updated"). → `8d6970d`.
- **STEP 2, capital Area in print only.** → `8d6970d`.
- **VERIFY (original):** `BriefPrint.jsx` rendered `changes_vs_history.injuries` as "<before> → <after>" and
  `since.injuries` as the change word. Confirmed on `f0bcc80`. The prod row-104 read (null parent, 29 Sep) is
  the operator's own; this container cannot see prod.
- **Addendum STEP 3a, parent row 104 via the typed supersede path.** **NOT written: HALTED.** The standard
  path refuses a `parent_key` that names an inactive row (`routers/knowledge.py:1039-1052`), and a resolved
  injury is `active=False`. The brief forbids raw SQL. The fork is raised as **Q192** (needs a ruling), and
  the ledger is unchanged.
- **Addendum VERIFY 1 (row 104's exit and review_by) and 3 (injury in the appointment's scope):** **OWED
  (operator).** There is no prod route here (no Railway CLI, no database URL, no API token). The queries are
  in Q192.
- **Addendum VERIFY 2 (does any path end or hide a constraint under a resolved parent):** done from code.
  None does, unless the exit is `with_parent` alone. File:line citations are in #351.
- **Addendum STEP 3b and the prod-brief gates:** not exercised; they depend on 3a.
- **Addendum STEP 3c (orphan report, read-only):** **OWED (operator).** The query is in Q192.
- **GUARD:** no ledger write, and print and ledger work kept in separate commits: held (there is no ledger
  commit). The decision entry is #351, landed with this close-out.

**Divergences (named in #351):** a backend `change` field (additive); since-resolved wording extended to match;
capital Area applied to the Background tables too.

## Cold-resume handoff

**Where things stand.**
- Master is `f0bcc80`, plus this PR (`8d6970d` and this close-out). Decisions max **#351**; questions max
  **Q192**.
- The print document prints injury changes in words. The 1 Oct brief still cannot show the right-shoulder ER
  load cap (row 104), because its parent is null and the fix is blocked on Q192.
- The appointment (`appt_20261001_aubrey`) is **Thu 1 Oct 2026**, two days from this close-out. If Q192 is not
  ruled and built by then, the cap will not print under Restrictions. The operator can carry it by hand, or by
  a note on the ask.

**NOW lanes and the v1 test each serves:**
- **Appointment brief** — Walk in. Built through #351. Blocked residue: Q192 (row 104 in scope).
- **Injury clearance (operator)** — Know / Walk in. OWED: step (3).
- **Lab upload pipeline** and **Interpretation layer build** — Walk in. Untouched.
- **Cross-repo rows** — no v1 test; pinned by #112. The paste-addressing propagation to HCA is still owed.
- **Demotion candidates:** DONE rows still in NOW (tags seed #339, CBT-I Q45 #219, eval trigger #213, G6 #342).

**Open questions:** 106 OPEN (Q192 new), 4 OWED (Q78, Q176, Q178, Q181).

**What was NOT touched this session (and what gates it).**
- **The ledger:** no write of any kind. Row 104's parent waits on the Q192 ruling. Other orphaned constraints
  are unknown until the operator runs the Q192 orphan query.
- **Appointment brief PR2** (post-visit transcript reconciliation, LATER): untouched. It needs the 1 Oct visit
  to have happened.
- **Interpretation layer increments 2, 3 and 5; lab pipeline residuals (Q104):** untouched.
- **Q181 / brief 2** (retire free-text `user_knowledge`), **Q191** (standing review sweep), **Q182–Q184**:
  untouched.
- Six consecutive sessions (#345–#351) have gone to the appointment brief. That is deliberate, since it is
  v1's synthesising consumer with a dated visit, but every other Walk-in lane has stood still meanwhile.

**Single clearest next action.** Chat rules **Q192** (recommended: option (a), allow a resolved, unsuperseded
parent when `with_parent` is not true). The operator runs the Q192 row-104 exit read first. If the exit is
`with_parent` alone, set a new exit before any parenting.
