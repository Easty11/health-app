# docs/design — architecture-scale design docs

RFD-style design docs for items too large for a GitHub issue. Small and medium questions are
issues (see `CLAUDE.md` → *Filing a question*); a design doc is for anything architectural. The
issue, if there is one, is a one-line pointer labelled `design`.

Start from `0000-template.md`. The existing `docs/*design*.md` files are not moved into this
store.

## Numbering

Zero-padded four digits, next free at creation: `NNNN-short-title.md`. These are files, not
`DECISIONS_LOG` entries, so there is no number-at-merge; a collision between two branches is
resolved by renaming the later one.

## States

`**State:**` is one of:

| State | Meaning |
|-------|---------|
| `ideation` | A shape worth writing down; the proposal may be thin and the Unresolved-questions table may be empty or incomplete. |
| `discussion` | The proposal is stable enough to argue with; the Unresolved-questions table is being worked down. |
| `committed` | The design is settled. Every Unresolved-questions row is `resolved` or `struck (out of scope)`. |
| `abandoned` | Closed without being built. A normal ending; the Abandonment note says why. |

## The one rule

A doc cannot move to `committed` while any Unresolved-questions row is not `resolved` or
`struck (out of scope)`. Each resolution lands as a `DECISIONS_LOG` entry and is pointed at from
the doc's *Decisions landed* section (`- #N — <one line>`). The row's *Door* column is one-way or
two-way, as defined by *Merge disposition* in `CLAUDE.md`.

## Who moves state

- **Code** moves a doc's state in the PR that changes it and updates **Last moved**. The move to
  `committed` is gated by the one rule above; the resolutions that gate it are `DECISIONS_LOG`
  entries and follow door class (*Merge disposition*), so a one-way-door resolution holds for
  explicit operator instruction.
- **chat** proposes docs and may draft their text; chat never commits (the loop rule).
- **Owner** names who is carrying the doc (`chat`, `Code`, or `Luke`); it changes by editing the
  line.

## Session close-out

`/closeout` lists the docs not in a terminal state (`ideation` or `discussion`):

    grep -l "State:\*\* \(ideation\|discussion\)" docs/design/*.md
