# closeout.md — health-app session handoff (2026-08-09)

## Real commits this session

Session-open ref: `4bd99cc` (master tip at open).

**health-app** (`git log --oneline 4bd99cc..68cb97c`):

- `0c719df` gov: prune governance contract to invariants; archive provenance (#NEXT → #186)
- `68cb97c` Merge pull request #41 from Easty11/chore/governance-prune

**health-connect-app** (propagation, landed via PR #25):

- `af78a6f` gov: replace shared loop-rules block with health-app's pruned version (#NEXT → #34)
- merge of PR #25 into HCA master

This close-out branch (`chore/session-closeout-0809`) adds its own commit on top —
`closeout.md` + its BRANCHES self-row.

## Pending-queue reconciliation

No `;cc` chat pending-commit queue was carried in. The work originated from the
governance-prune brief and was extended in-session by chat's reviewed §§1–6 disposition (a
second, adjudicated pass — same operation class as the §§7–28 split). Everything decided
landed:

- **health-app `#186`** (Governance contract pruned) — landed at `68cb97c`. Number-at-merge
  resolved `#NEXT → 186` (master max re-read at land = 185), guard clean (exit 0), CI
  `placeholder guard (POSIX)` green on PR #41.
- **HCA `#34`** (shared-block return trip) — landed via PR #25. `#NEXT → 34` (HCA master max
  re-read = 33), guard clean, CI green.

Gate results (all recorded in `#186`): G1 shared block 97 / whole file 249; G2 `FEEDBACK.md`
73 lines (≤200), archive carries all 22 §7–§28 headings and its §§1–3 (21,689 B) + §§7–28
(75,166 B) bodies byte-identical to the 4bd99cc original; G3 all 18 invariants; G4 hook fires
on `#NEXT` / clears resolved in both repos; G5 shared block byte-identical across both masters;
G6 both decision entries landed, moratorium verbatim. Nothing deleted — full provenance
(§§1–3, §5 tombstone, §§7–28, full pre-prune `CLAUDE.md`) preserved in `FEEDBACK_ARCHIVE.md`.

**Owed to chat (project-knowledge folds, post-land):** §6 CPAP context → `Clinical_Protocol`
(surfaced verbatim in-session; near-duplicate of §1.1's CPAP specifics, which are in the
archive). §5 injury snapshot → `Athlete_Profile`; injury truth is the Postgres declared-state
ledger (`type='injury'`), the archived copy is a superseded tombstone, not live state.

## Cold-resume handoff

**What landed.** The governance contract was pruned from auditing to shipping. Session-start
read load fell from 21,325 to 3,316 words (84%): `CLAUDE.md` 453→249 lines (shared block 97),
`FEEDBACK.md` 1328→73 lines. All stripped provenance is in the new `FEEDBACK_ARCHIVE.md`, which
is **not read at session start**. Two new shared standing rules are now in force:

- **Severity gate on review** — gate only defects that change an outcome, corrupt data, leak a
  secret, or block the next step; cosmetic/wording defects batch into a trailing "nits" note.
- **Governance batching** — ≤1 `gov(...)` commit per session, at close-out; never interleaved
  with feature work. (This close-out session is exempt — governance WAS the work.)

**Moratorium (active).** No new governance rules, hooks, or mechanisms until **three product
items land** from: lab-confirm Brief A, lab-confirm Brief B, interpretation producer 4b, Polar
wired into the chat handler. Interim defects get one condensed `FEEDBACK` line — no essay, no
mechanism.

**Open questions.** `OPEN_QUESTIONS.md` max = Q87 (artefact-parity register — OPEN). No question
was opened or resolved this session.

**What was NOT touched — and must be named.** This is the **fourth consecutive
instrument-over-product session** (the prior close-out named the third). The contract got
lighter; the product did not move. Standing still, unchanged this session:

- **Interpretation producer lane** — increments **2 (rephrase) → 3 (lever-tap) → 5 (go-live)**
  (ROADMAP NOW build-sequence). Producer 4b is one of the moratorium's own gating items.
- **CBT-I manual evaluation trigger** — `feat/cbti-eval-trigger` (#118's unbuilt half), a dated
  NOW row (~31 Jul); pre-existing local branch, untouched.
- **#116/#121 frontend deploy probe** — never run (owed since the hub-shell #162 land).
- **Polar → chat handler wiring** — a moratorium gating item; not started.
- **Lab-confirm Briefs A and B** — two moratorium gating items; not started.

The moratorium was written precisely so these become the next session's legible queue instead of
more governance. A governance session hands off governance unless it says otherwise — it is
saying otherwise here.

**Cross-repo note.** The shared-block propagation this session carried the number-at-merge
ENFORCEMENT bullet to HCA byte-identically, partially addressing ROADMAP NOW rows 18/20
(cross-repo shared-block debt). The deeper sub-parts — HCA-rooted adjudication of the
Python-vs-Node guard decision (row 18) and extending `#NEXT` to code-comment tokens (row 20) —
remain OWED and were not touched. Reconcile those rows from an HCA-rooted session; do not mark
them DONE from here.

**Next action (single, clearest).** Pick a product lane, not more governance — the moratorium
forces it. Strongest single pick: **interpretation increment 2 (rephrase)** or the **CBT-I
manual evaluation trigger** (dated NOW). Both move a moratorium gating item toward landing.
