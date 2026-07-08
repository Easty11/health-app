# Close-out — promote orientation docs to repo-canonical (SCHEMA.md)

## Real commits this session

Session-open ref: `d5163ac` (master tip at open). Branch
`chore/orientation-docs-into-repo` built then ff-landed to master. `git log --oneline d5163ac..HEAD`:

```
<closeout> chore: session close-out
79169dd docs: claim DECISIONS_LOG #62 (was #NEXT) + recent-landings
2bf5653 docs: DECISIONS_LOG #NEXT — SCHEMA.md promoted to repo-canonical
a34747a docs: add SCHEMA.md-repo-canonical convention (repo-specific)
e7fdb3b docs: add SCHEMA.md as repo-canonical database reference
```

Landed `--ff-only`: `origin/master` d5163ac..79169dd; feature branch merged + deleted
(local; never on remote). `origin/master` == `79169dd`.

## Pending-queue reconciliation

Direct BRIEF (promote orientation docs), not a `;cc` queue. Concern-split as specified:

- **Step 1** SCHEMA.md at root — `e7fdb3b`. GATE 1 met (content = the pasted chat-authored
  file; markdown code fences/headings flattened by chat→paste transport were restored, no
  content altered; table 015 matches landed migration `3497ab483935`).
- **Step 2** PLATFORM.md — **SKIPPED** by Luke's decision (public-exposure gate not cleared).
  Stays project-knowledge; non-mirrored-refresh rule applies to it alone. GATE 2 resolved.
- **Step 3** CLAUDE.md convention — `a34747a`. GATE 3 met: bullet under Repo-specific →
  Conventions, below `END SHARED LOOP RULES`; shared-block diff vs origin/master empty
  (verified by slice-diff), so no cross-repo propagation.
- **Step 4** DECISIONS_LOG — `2bf5653` (`### #NEXT`) then claimed **#62** at merge in
  `79169dd` (origin/master max was #61, no competing branch). GATE 4 met.
- **Step 5** Land — done (`--ff-only`, pushed, branch deleted). GATE 3 (SHA equality) met.

No decisions provisional. One SCHEMA-vs-source note: SCHEMA.md uses a logical 001–015
migration-sequence abstraction (documentation ordering by FK dependency), not the repo's
alembic hash filenames — as authored in chat; not a discrepancy to fix.

## Cold-resume handoff

**State:** `SCHEMA.md` is live at master root (`origin/master` = `79169dd`) and is now the
repo-canonical database reference, auto-mirrored into project knowledge via Projects sync.
CLAUDE.md records the SCHEMA ⇄ `backend/migrations/` lockstep (update SCHEMA in the same or
an immediately-paired commit as any schema migration). DECISIONS_LOG #62 records the
promotion. PLATFORM.md was deliberately not promoted.

**SINGLE NEXT ACTION (Luke — project knowledge, outside Code's reach):** after confirming the
connector surfaces the repo `SCHEMA.md`, **delete the manual project-knowledge upload of
SCHEMA.md**. Until deleted, dual-master persists (repo copy + stale manual copy) — the task
is not done. (PLATFORM.md stays as-is in project knowledge — it was not moved.)

**Standing rule now in force:** any migration that changes the schema must update `SCHEMA.md`
in the same commit or an immediately-paired governance commit — it must never lag master.

**Follow-ups (not blocking):**
- If PLATFORM.md's public-exposure gate later clears, promote it under its own DECISIONS_LOG
  entry (same pattern).
- Hevy resolver activation (context_builder prompt + byte-parity re-baseline) remains the
  deferred #60 loose-name decision. Prior Railway migration for #61 (`3497ab483935`) — confirm
  its post-apply stamp if not already done.

**Sprint context (unchanged):** ROADMAP NOW unchanged — Health Connect permissions, Samsung
package-name correction, morning check-in, persistent conversation history, known UI bugs.

**Open questions:** none opened or resolved; OPEN_QUESTIONS untouched.
