# Close-out — 2026-08-12b (dispatch brief: C4 governance-view regen · §19 ledger row · interpretation training-wheels verify)

## Real commits this session

Session-open ref: `4256e72` (prior master tip, PR #60). `git log --oneline 4256e72..HEAD`
before this close-out commit: **empty** — no feature or governance commit landed mid-session.
This session executed a chat-authored dispatch brief (three items), and the only repo write
is the one FEEDBACK §19 ledger row, which rides *this* close-out commit.

The close-out commit itself (this branch, `chore/session-closeout-0812b`) carries: the
`FEEDBACK_ARCHIVE.md` §19.6 row id-20 addition, `closeout.md`, the `CLAUDE.md`
Recent-landings prepend + 3-cap trim, and the `BRANCHES.md` self-row. Governance/docs-only;
no code, no migration. Guard-gated per #176(c): the §19 row and the BRANCHES self-row are
pure additions; the `closeout.md` overwrite and the Recent-landings capped-trim are both
declared replacement regions — no removed line falls outside one. Lands via PR,
`--merge --delete-branch`.

## Pending-queue reconciliation

**No `;cc` PENDING queue carried in.** The three items came from a chat-authored *dispatch
brief* (never committed), not the pending-commit queue. Each reconciled:

1. **C4 — governance-view regen: DONE, uncommitted by design.** Ran
   `python scripts/gen_governance_view.py` against **live master** (`4256e72`; the script
   resolves master via `git ls-remote` and reads `raw.githubusercontent.com`, not the local
   tree). Output: `build/CONSOLIDATED_GOVERNANCE_VIEW.md` (gitignored — a derived artifact is
   never committed). **Count parity confirmed against the store maxima:** health-app
   DECISIONS_LOG **210 entries = max #210**, OPEN_QUESTIONS **99 = max Q99**; the script's
   own count/parity/non-empty-extraction gates all passed (health-connect-app read clean at
   master `1c32c42`). The output path is handed to Luke for the claude.ai project-knowledge
   placement — his to place via the UI, not committed here.

2. **Interpretation draft promotion — recorded, NOT owed, NOT a store write.** The promotion
   is a production DB state change, not a ref: `interpretation_rephrases.status` went
   `ai_draft → human_verified` via the app's promote action (#202's training-wheels
   mechanism — the table is the record by design, so there is no SHA and nothing in the tree
   changes). Verified read-only via `railway connect health-app-DB`:
   `SELECT id, register, status, created_at FROM interpretation_rephrases;` returns exactly
   **one row** — `id=1, register=plain, status=human_verified, created_at=2026-08-11
   19:45:51+00`. **Training-wheels review #1 is complete, verified in-DB.** No governance
   store records it (correct per #202); this prose line is the anchor.

3. **FEEDBACK §19 ledger row — LANDED, rides this commit.** Row **id 20** added to the
   §19.6 integrity ledger in `FEEDBACK_ARCHIVE.md` (append-only; ids 11/12/14 are pre-existing
   expected gaps, last row was 19). Failure-derived, `source=MODEL`, dated **2026-07-22** —
   the secret-render-during-env-checks incident chain documented at #110/#111 (a
   presence-check that rendered the value while establishing no credential had been exposed;
   halt + rotation followed). The row captures the Bash `${VAR:-…}` vector: the expansion
   prints the value on the missing branch, so presence must be checked by exit code
   (`test -n "$VAR"`), never by expansion (`:-` vs `:+` is one character between a check and a
   disclosure); rotate on any render. Implementation guidance under the existing secrets
   prohibition — **no new rule minted** (the secrets rule already existed). `status=STANDS`.
   *Date basis is inferred from the #110/#111 incident chain (repo-anchored: #110 landed
   2026-07-22, "secrets residuals closed" 2026-07-23); if the `${VAR:-}` render was a distinct
   later episode, correct the row's `date` — §19's mutable-status mechanism is the backstop.*

**Scope guard honoured:** C4 (uncommitted) + one FEEDBACK row + /closeout. No other store
edits; no decision minted.

## Cold-resume handoff

**Session class: INSTRUMENT/governance.** This session ran a dispatch brief — regenerated the
consolidated governance view (uncommitted, Luke-placed), verified one production DB promotion
read-only, and landed one §19 ledger row. **No product or feature code moved.** As with the
prior two close-outs, the risk is that a governance handoff begets more governance; the
product queue below is the real state.

### What landed
- **FEEDBACK §19 ledger row id-20** (`FEEDBACK_ARCHIVE.md` §19.6): expansion-based secret
  presence checks (`${VAR:-}`) render the value; presence checks must be exit-code-based.
  Implementation guidance under #110/#111; no rule minted.
- **Governance view regenerated** against master (#210/Q99 parity) — `build/`-only,
  uncommitted, handed to Luke for the claude.ai UI swap.
- **Interpretation training-wheels review #1** recorded as complete (verified in-DB, one
  `human_verified` row) — a production state fact, not a repo change.

### Maxima at close
- Decisions max: **#210**. Questions max: **Q99**. (Confirmed by both the direct store grep
  and the governance-view parity gate: 210 decision entries, 99 question entries.)

### Current sprint — ROADMAP NOW (dated, by external date)
1. **CBT-I: resolve Q45 nap day-attribution** — DATED, contaminating capture now (`naps_min`
   date−1 read live for block 3, unverified; also gates a second user at the 4-night cadence,
   Q78). Close from the VA CBT-I protocol docs / clinician, not the workbook. Owner: Luke.
   **Dated head of the queue.**
2. **CBT-I: manual witnessed evaluation trigger** — BUILT but SUPERSEDED, needs REWORK
   (`feat/cbti-eval-trigger`, OWED — rowed in BRANCHES.md). Do not force-merge.
3. Lab upload pipeline (uploading unpaused; junk-row operator decision owed).
4. Interpretation layer build (1b delivered; go-live #194 done; **increment 2 rephrase** is
   the strongest product pick — increments 3 remain).
5. Appointment brief (depends on lab pipeline + interpretation).
6–8. Cross-repo shared-block propagations to `health-connect-app` (all OWED, HCA-rooted).

### Open questions (grouped)
- **OPEN, pre-existing, untouched this session:** Q45 (nap attribution — dated head), Q75
  (Hevy catalogue freshness), Q77 (custom-create round-trip), Q27 (capability-taxonomy v1).
  None changed.
- This session opened/closed no questions and minted no decisions.

### Single clearest next action
**Resolve Q45** (VA nap day-attribution) — dated head of ROADMAP NOW, gates the CBT-I
eval-trigger rework, and gates a second user. Owner: Luke; closes from the VA CBT-I protocol
docs or the administering clinician (workbook searched to exhaustion). If the next session is
free to pick product, the bias points at **interpretation increment 2 (rephrase)**, which
go-live (#194) surfaced as needed and whose training-wheels review #1 is now complete in-DB.

### What was NOT touched this session (named explicitly)
Third-order risk named plainly: this is the third recent INSTRUMENT/governance close-out in a
row, and the product lanes stood still again. The real queue:

- **Interpretation increment 2 (rephrase)** — UNSTARTED, operator-confirmed *needed* by
  go-live (#194): the base text is too complex for a layperson. Training-wheels review #1 is
  now verified complete in-DB, which is the on-ramp for this lane. Untouched.
- **Interpretation increment 3 (lever-tap → scoped education thread)** — UNSTARTED.
- **Interpretation small lanes from the go-live census** — `Bilirubin conjugated` + `CK`
  canonical-map, marker display-name polish, selectable-term glossary, `lab_accession`
  persist. All UNSTARTED. Untouched.
- **`feat/cbti-eval-trigger`** — OWED/REWORK (obsolete against master's 4-night engine after
  #165). Full rework checklist on its BRANCHES.md row. Pushed, unmerged. Untouched.
- **CBT-I user surface** — invisible in-app; gated on #47 (state-only vs action). Q60.
- **Banister readiness build** — OWED; data path unblocked, model unbuilt. Untouched.
- **#116/#121 frontend deploy probe for the hub shell (#162)** — still never run. Untouched.
- **Cross-repo propagations (health-connect-app)** — three OWED shared-block copies, all
  HCA-rooted, all untouched (correctly — not landable from a health-app-rooted session).

If free to pick, the product bias points at **interpretation increment 2 (rephrase)**.
