# Code session close-out — 2026-09-09

## 1. Real commits this session

Branch `claude/training-phase-ledger-q112-p8uywe` (now merged + deleted). Session-open ref
`3540785` (master at branch time).

```
2cf4e9f Merge pull request #167 from Easty11/claude/training-phase-ledger-q112-p8uywe
34b03ed gov(q112): resolve Q112 -> #270; amend Q106 scope; SCHEMA §031; ROADMAP offseason note
9eab120 feat(engine): training_phases ledger — phase-scoped exposure modulation (Q112)
```

Merged to master via PR #167 (`--merge`, per the repo rule that `BRANCHES.md` records landing
SHAs — squash/rebase would dangle them). Required check `placeholder guard (POSIX)` green;
`mergeable_state: clean`; branch remote-deleted on merge, local branch deleted at close.

## 2. Pending-queue reconciliation

No `;cc` pending-commit queue was carried into this session — the work was driven directly from
the Q112 brief, not from a chat close-out handoff. Nothing provisional remains: every item the
brief specified landed in the two commits above, and the governance half (DECISIONS_LOG #270,
Q112 → DONE→#270, Q106 amended, SCHEMA §031, ROADMAP note, BRANCHES row) is committed, not
pasted. GATE 7 held — feature commit `9eab120` carries no governance; governance commit `34b03ed`
carries no code.

Two small validation calls the brief did not specify were made and are now live (flagged to the
operator, not blocking): `sessions_per_cycle` bounds `0–28` on the microcycle slot, and
`close_reason` required-non-empty on `POST /engine/phase/close`. Adjust in a follow-up if either
is wrong; neither is load-bearing on the resolved design.

## 3. Cold-resume handoff

**What landed (this session).** Q112 resolved as **DECISIONS_LOG #270** — the `training_phases`
store (migration `f2b7c1a4d9e0`): a per-user, append-only, exactly-one-open ledger separating
DOING NOW (the open phase) from the profile's standing BUILDING TOWARD. `models.TrainingPhase`;
`engine/training_phase.py` (validate / open / close / current / `phase_at` half-open);
router `/engine/phase` (open, close→404-if-none, GET current, history); `select_next` hooks
E1–E6 (suppressed→probe-budget-0/fortify; capacities REMOVE-only filter, Q105 resolve-before-
compare, never re-admits a #221 stop; fortify target never filtered, disagreement surfaced;
block only when a phase is open; `None`→byte-identical); `context_builder` + `current_state`
surfaces. S7 `_local_day()` is now the single AEST-today source, extended to the
`resolve_injury` / `resolve_schedule_item` `resolved_on` default (was Railway-UTC `date.today()`).
`Capacity` stays movement-quality only — aerobic posture lives in `intent` prose, gated by
nothing. 43 tests; full suite 1353 passed (2 pre-existing env failures unrelated to this change).

**Current sprint (from `ROADMAP.md` NOW).** Dated CBT-I titration-cycle work; the standing
cross-repo shared-block propagation debt (pinned to ROADMAP NOW by #112 — still OWED, structural
orphaning of `#NEXT` tokens outside the stores). No date-anchored item was touched this session.

**Open questions (grouped).**
- *Resolved this session:* Q112 → #270.
- *Amended this session:* Q106 (the weekly-resolver `minutes` question) — its input is now
  phase-current over profile-baseline: read `phase.microcycle`, fall back to `weekly_template`.
  Still OPEN, still blocks only the (unbuilt) weekly-resolver lane.
- *Open, untouched:* Q105 (resolve-before-compare trade), Q106 (resolver lane), Q109 (no unread
  structure), Q120 (no onset field on injuries), Q129–Q133 (Garmin garth cluster), Q137
  (naive-`date.today()` audit — this session fixed the two resolve endpoints but did NOT sweep
  the rest), Q138 (session-close BRANCHES/merge-reality sweep), **Q139 (interpretation
  increment 3 frontend tap-to-thread surface — the standing next-action before this session)**.

**Single clearest next action.** **Q139 — build the interpretation increment-3 frontend
tap-to-thread surface** (build-sequence step 5; the backend spine landed at #268). It was the
next-action at the last close-out and this session did not touch it. Alternatively the dated
CBT-I NOW rows, or the first Decompression phase can now be authored live against the new ledger
(`POST /engine/phase`, the brief's worked example).

**What was NOT touched — named explicitly.** This session built engine *instrumentation* (a new
store + engine modulation), not product-facing surfaces. Standing still:
- **Q139 interpretation frontend** — the actual user-facing tap-to-thread lane; backend has been
  ready since #268 and is now one session further from its frontend.
- **The weekly-resolver lane (Q106)** — this session gave it phase-scoped *input* and did not
  build it; fortnightly/microcycle dosing is declared, not enforced, until it lands.
- **Adaptive programming lane (Plan schema steps 2–4 + taxonomy v1 / Q27)** — the offseason
  Block-A target; untouched.
- **Q137 naive-`date.today()` audit** — only the two resolve endpoints were converted to
  `_local_day()`; the broader sweep of other AEST-mismatched call sites is still open.
- **The `training_phases` ledger has zero rows in prod** — landed ≠ live. The first phase
  (Decompression, per the brief's worked example) has not been authored; the migration is applied
  on merge but no phase exists until the operator POSTs one. Nothing verifies the live write path
  yet (SQLite tests only).

Consecutive sessions (this one, the 2026-09-08 governance-hygiene checkpoint) have gone to
instrument and governance rather than to the interpretation frontend that has been the named
next-action throughout. Worth a deliberate pick, not a drift, next session.
