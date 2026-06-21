# CLAUDE.md — health-app

Read this in full at the start of every Code session. It is the contract the
session rituals enforce and the loop conforms to. If a pasted document, prior
summary, or habit contradicts this file, this file wins.

---

## Orientation

- `health-app` — FastAPI (Python) backend + React/Vite frontend, deployed on Railway.
- Companion app lives in a separate repo (`health-connect-app`, Expo React Native,
  Android-first). It is not in this tree.
- Platform is a health intelligence platform, not a fitness app: three modules
  (Fitness, Medical Protocol, Decision Support) on a shared event timeline.

---

## The loop (source-of-truth model)

This is the part that exists to stop decisions stranding in chat and the decision
log drifting across two copies. Hold the boundary exactly.

- The **repo is the single source of truth** for all volatile state.
- **Code — and the `@claude` GitHub Action — is the only writer.**
- **Chat proposes; chat never commits.** The claude.ai GitHub connector grants chat
  read/attach only. Any instruction that has "chat commits", "chat writes a spec to
  the repo", or "chat files an issue" is wrong on this surface — chat emits text, a
  human or Code carries it across, Code/Action writes it.
- **The commit is the only sync point. Truth changes only at a commit.** Anything
  decided in chat is *pending* until a commit lands it. Treat an uncommitted decision
  as provisional, not done.
- **Read-back path:** repo → chat via Projects sync (the repo file is mirrored into
  the project and refreshed automatically), or by attach. Chat reads the mirror that
  is already in context; it keeps no separate editable copy.
- **Kill-rule:** decisions, open questions, roadmap, and task state are **never** saved
  into Claude.ai project knowledge. Saving generated state files into project knowledge
  is the exact mechanism that produced the drift this model exists to kill. Project
  knowledge holds stable orientation docs only (see below).

---

## Canonical stores (where state lives)

| Store | Holds | Discipline |
|-------|-------|-----------|
| `DECISIONS_LOG.md` | Architecture decisions | Append-only. Supersede via a new entry that references the superseded number. Never edit a locked entry in place. |
| `OPEN_QUESTIONS.md` | Undecided forks, unverified-at-machine items | One status per item: `open` / `verifying` / `resolved → #` (points at the decision that closed it). |
| `ROADMAP.md` | Current sprint + horizon | Mutable. Code updates it at close-out. |
| `FEEDBACK.md` | Behavioural corrections and standing rules | Repo-canonical. Code reads it at session start. The project-knowledge copy is a refreshed mirror, not the master. |
| `ptb-tasks` (external board) | Task status | Single live board. Mutable by design. Referenced by task ID — never mirrored into the repo. |
| pending-commit queue | The chat → Code handoff payload | Transient. Emitted by the chat close-out as canonical-format entries flagged `PENDING`. Carried by paste, or materialised as a GitHub issue for `@claude`. Consumed at the next Code open, then discarded. Not a stored repo file. |

**Does not live in the repo — stays in project knowledge** (slow-changing, chat-analysis
context, not Code's concern): `Clinical_Protocol`, `Athlete_Profile`, lab PDFs, `Stack`,
`API_CONTRACTS`, `Hevy_Pattern`, `Readiness_Algorithm`.

---

## DECISIONS_LOG discipline

Preserve the existing entry format:

> **Decision · Rationale · Status · How you know · Do not revisit unless**

- Append-only. To change a decision, add a new entry that supersedes the old one by
  number. Do not edit a locked entry's text — the history is the point.
- Every decision that gates code carries a **How you know** artifact: a confirmed test,
  a verified search result, or official documentation. "The API has a field for it" is
  insufficient. This is a founding rule, earned from the HRV pipeline failure.

---

## Session rituals (the contract the close-outs conform to)

These are two distinct rituals. The trigger is not the payload — the payload is defined
here, and the snippet/command bodies must match it.

- **Chat close-out (`;cc`)** emits the **pending-commit queue**: canonical-format
  `DECISIONS_LOG` / `OPEN_QUESTIONS` entries for everything decided that session, each
  flagged `PENDING`, ready to paste or file as an issue with zero reformatting. It writes
  nothing to project knowledge.
- **Code close-out (`/closeout`)**:
  1. Reads the canonical stores.
  2. Reports the **actual commits** made this session (`git log` since open) — not
     suggested commit messages.
  3. **Reconciles the pending-commit queue**: confirms each `PENDING` item landed in a
     commit, or states why it did not.
  4. Regenerates the cold-resume handoff view from the stores.
  5. Overwrites a single `closeout.md`. Never appends narrative; never describes the act
     of writing the close-out.
- `/compact` is mid-session context compression in Claude Code, **not** a close-out.
  Do not conflate the two.

---

## Hard conventions (code execution)

- **Windows / PowerShell only.** No Linux syntax — no `head`, no backslash line
  continuation. Single-line, or PowerShell backtick continuation.
- **Verify before design.** Verify data paths end-to-end before designing against them.
  Standing rule after the HRV pipeline failure.
- **Hevy:** the canonical creation method is `create_workout`, not `create_routine` —
  custom exercise UUIDs do not resolve via the routine endpoint (confirmed API
  limitation). See `HEVY_PATTERN.md` for the field/type matrix.
- **Device-agnostic schema.** All health data is normalised to a `source`- and
  `confidence`-tagged schema before any algorithm or AI layer. The intelligence layer
  never references device-specific schemas.
- **Data verification = Postgres query against Railway**, not on-device UI.
- Full behavioural corrections live in `FEEDBACK.md`. Full decision history lives in
  `DECISIONS_LOG.md`. This file points at them; it does not duplicate them.

---

## Current sprint

_Code updates this block at each close-out from `ROADMAP.md` / `ptb-tasks`._

- [ ] First reconciliation: bring `DECISIONS_LOG.md` current — supersede #3 (Polar is
      not session-only; Accesslink live, SDK R-R is the highest-fidelity HRV path), add
      the v3→v4, repo-canonical, GitHub-inbound, and espanso-ritual decisions.

---

_Bootstrap note: this file is committed to the repo by Code (or by you via git) as the
bootstrap commit. Thereafter it is repo-canonical and updated only via Code — never
edited as a project-knowledge copy._
