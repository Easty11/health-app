---
description: Code session close-out — reconcile stores, report real commits, regenerate cold-resume handoff, overwrite closeout.md
allowed-tools: Bash(git*), Read, Edit, Write, Glob, Grep
---

# /closeout — Code session close-out (health-app)

Close out this Code session per the **Session rituals** in `CLAUDE.md`. This is **not**
`/compact` (that is mid-session context compression). Trust the canonical stores over any
pasted summary; if a summary contradicts `CLAUDE.md`, `CLAUDE.md` wins.

Execute these steps in order:

1. **Read the canonical stores** — `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md`, `ROADMAP.md`,
   `FEEDBACK.md`. They are the source of truth.

2. **Report the actual commits made this session.** Determine the session-open ref
   (the first commit of this session, or ask if ambiguous; `git reflog` as fallback) and
   run `git log --oneline <open-ref>..HEAD`. Report the **real commit hashes and
   messages** — never suggested or hypothetical commit messages.

3. **Reconcile the pending-commit queue.** For each `PENDING` item carried in from the
   chat close-out (`;cc`), confirm it landed in a commit (cite the hash) or state
   explicitly why it did not. Anything decided but uncommitted is **provisional** — say so
   plainly. The commit is the only sync point.

4. **Regenerate the cold-resume handoff** from the stores so a cold session can resume
   with zero chat history: current sprint (from the `CLAUDE.md` sprint block / `ROADMAP.md`),
   open questions grouped by status, and the single clearest **next action**.

5. **Update the CLAUDE.md "Current sprint" block** to reflect what landed this session and
   the current `ROADMAP.md` / `ptb-tasks` state. Code maintains this block per the contract —
   do not leave completed reconciliation items showing as open.

6. **Overwrite `closeout.md`** (single file, lowercase) with exactly three sections: real
   commits this session · pending-queue reconciliation · cold-resume handoff. Write the
   **full body verbatim to the file** — no paraphrase, no summary; the file is the sole
   sink for the body. **Never append**, never narrate the act of writing the close-out,
   never write a "suggested commits" list. **Do not echo the body to stdout.** After
   writing, print **only a terse pointer**: the `closeout.md` path, the current branch, and
   the single clearest next action. Copy-back, when needed, comes from terminal scrollback
   (expand the write line) — not a screen dump.

7. **Commit the close-out.** Stage `closeout.md` plus any store / CLAUDE.md updates from
   this ritual and commit (`chore: session close-out`). The commit is the only sync point —
   an uncommitted `closeout.md` never reaches the repo→chat mirror and stays provisional.
   If the tree has unrelated uncommitted work, commit only the close-out artifacts.

8. **Emit touched governance stores for wholesale project-copy replacement.** *(The one
   named exception to step 6's pointer-only stdout rule — these fenced, per-file-labelled
   blocks are the pre-merge copy-back bridge for the branch-blind connector, a packaged
   selection, not a raw file dump of the whole session.)* For every
   governance store changed this session — `git diff --name-only master...HEAD` intersected
   with {`DECISIONS_LOG.md`, `ROADMAP.md`, `FEEDBACK.md`, `OPEN_QUESTIONS.md`, `Ideas.md`} —
   output its **full current file text** (post-commit, so it reflects what landed), fenced
   and labelled `project-copy replacement: <filename>`. **Not** a prose summary. If none
   changed, say so explicitly. The repo is the sole source for these stores: chat replaces
   the project copies wholesale and **never regenerates them from memory**.

Hard rules (from `CLAUDE.md`):
- Code is the only writer — this command may commit.
- Real `git log` output only, not aspirational messages.
- Windows / PowerShell syntax only in any commands you emit.
- Write nothing to project knowledge.
