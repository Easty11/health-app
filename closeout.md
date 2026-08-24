# closeout — /injuries operator view (#100) + banked follow-ups

## Real commits this session

Two branches, both off the same master tip (`bca7e89`).

**`claude/injuries-operator-view-lbxyvf`** — PR #100 (draft, open, NOT merged), code, full human review:

    5e31321 fix(injuries): stop asserting contraindication; label restrictions as surfaced-not-enforced
    ba6d6cf fix(injuries): state the record-age date positively, never via onset/age
    57345b0 feat(injuries): /injuries operator view over the #222/#223 endpoints

Frontend suite **57 passed** (10 in `Injuries.test.jsx`); `npm run lint` at the pre-existing
6-error baseline (all in untouched files); `npm run build` clean. Reviewed by Luke: "Verified at
`5e31321`. All three edits landed as specified."

**`gov/injuries-followups-closeout`** — governance batch (#176), docs-only, guard-gated. Carries the
`OPEN_QUESTIONS`/`ROADMAP`/`BRANCHES` edits below plus this `closeout.md`. Commit hash is the
`chore: session close-out …` commit that adds this file (self-referential; not quotable from within
itself). Removed-line audit (`git diff | grep '^-'`) run clean pre-commit — every removed line is an
in-place replacement of a declared region (ROADMAP row rewrite, this file's overwrite); appends
elsewhere.

## Pending-queue reconciliation

No `;cc` pending-commit queue was carried in — this session ran from a build brief, not a chat
close-out. The reconciled items are the four governance follow-ups the review surfaced:

1. **LANDED (gov branch)** — `OPEN_QUESTIONS` **Q120**: the injury value shape has no onset field;
   `/injuries`'s "on record since" is a compensation for that absence, recorded so it does not later
   read as a design preference.
2. **LANDED (gov branch)** — `ROADMAP` backfill-audit lane **reframed**: the five live rows are all
   current and cross-referenced; observed drift lives in `restrictions[]`/`detail`, not the `active`
   flag; every maintenance event in evidence is a restatement, not a retirement. Justification changed
   from "stale rows suppress regions" (which the data and `is_contraindicated`'s logic both refute) to
   "the active set has never been operator-reviewed against current truth."
3. **LANDED (gov branch)** — `ROADMAP` new NEXT lane: an **edit-and-supersede path** is the next
   injury-ledger build, ahead of the #232 review badge (which renders nothing today — no active row
   carries `review_when`).
4. **HELD, deliberately** — the `DECISIONS_LOG` **#100 stub**. It is a decision entry *for PR #100*,
   and #100 is a draft. Numbers are minted at merge, never in advance (number-at-merge); landing the
   stub now would either invent a number or land a numberless entry, and would assert as decided a
   thing not yet merged. It lands when #100 merges — re-read master's max, mint `#N`, write the DONE
   row + Recent-landings pointer in the same stroke. Its content is settled: motivation is that the
   ledger is **write-only** (chat/api/system all write injury rows, no route retires them); it carries
   **no** stale-row-suppression claim (the five row bodies refute it).

Provisional until their branches merge: everything above is on unmerged branches. Both PRs are draft;
neither has reached master.

## Cold-resume handoff

**What this session did.** Built the `/injuries` operator view (frontend-only, PR #100) — the
reachable half of the #222/#223 resolution loop — then corrected its effect readout to stop asserting
contraindication (a server-side computation absent from the payload) and to label `restrictions[]` as
surfaced-not-enforced. Banked three governance follow-ups (Q120 + two ROADMAP edits) on a separate
gov branch; held the #100 decision stub for merge.

**Single clearest next action.** Review and merge **draft PR #100** (`claude/injuries-operator-view-lbxyvf`,
head `5e31321`). On merge: mint the `DECISIONS_LOG` number, write the `#N` DONE row in `BRANCHES.md`,
add the Recent-landings pointer, and land the held #100 stub (governance item 4). Then merge the
`gov/injuries-followups-closeout` PR (independent; guard-gated). Neither is to be self-merged without
Luke — both are draft by instruction.

**Open questions touched / added.**
- **Q120 (new, OPEN)** — injury value shape has no onset field; `/injuries` compensates read-side,
  asserts nothing false; no consumer needs true onset yet.
- **Q102 (OPEN, unchanged)** — `restrictions[]` is dead data in `is_contraindicated`; this session's
  readout fix is consistent with it (the view now states `restrictions[]` gates nothing).
- Maxima at open: decisions **#236**, questions **Q119** (Q120 added this session).

**What was NOT touched — named so the queue does not read as empty.** This was a small frontend
lane plus its governance; the substantive product lanes stood still and are where the next real work
is, not more injury-ledger polish:
- **Interpretation layer** increments 2 (rephrase) → 3 (lever-tap) → 5 (go-live) — the sequenced NOW
  continuation, untouched this session.
- **CBT-I user surface** — engine built, still invisible in-app; gated on **#47** (state-only vs
  action) and **Q60**, neither moved.
- **Lab upload pipeline** — the medical-spine hero feature; `SCHEMA.md` lab-family staleness (OWED)
  and `lab_accession` persistence still open.
- **`weekly_template` resolver** (#221 lane, Q105/Q106) and the **cross-repo `#NEXT` sweep** (ROADMAP
  NOW, OWED) — both untouched.
- Injury-ledger specifically: the reframe above means the next injury build is the **edit-and-supersede
  path**, not the backfill audit (now a human-recall exercise) and not the #232 badge (renders nothing
  today). But none of these should crowd out the interpretation/CBT-I/lab lanes above, which are the
  product, not the instrument.

**Branch states (see `BRANCHES.md`).** `claude/injuries-operator-view-lbxyvf` → **OWED** (PR #100
draft, merge + mint-number owed). `gov/injuries-followups-closeout` → **OWED** (gov PR draft, merge
owed). No branch merged or deleted this session.
