# CBT-I cycle verdict store: design for DECISIONS_LOG #437

**Status: AMENDED 2026-10-23; STILL DESIGN ONLY.** The design landed as #418 (approved 2026-10-22). On
2026-10-23 the operator ruled the five open points of section 8 and added two items: a converged
verdict is offered, not applied (item 6), and a night's prescription is attributed by wake date
(item 7). The rulings are recorded in `DECISIONS_LOG` #440 and the text below carries them. Nothing is
built: no migration is written, no code changes, and the implementation PRs hold under Merge
disposition (a) (a schema migration). Drafted 2026-10-21 against master `cb3a5ba`; the Alembic head
was `c4e9a1f27b36` then and is `e5b2c8a91d47` on master as of 2026-10-22, which is why the build
re-reads it.

What #437 rules, in one paragraph: a HOLD verdict, including an insufficiency HOLD, applies without
acceptance and the next cycle chains from the previous cycle's close; a move (extend or compress)
needs acceptance, the next cycle starts at the new prescription's `effective_from`, and the nights
between the offer and the acceptance are unscored by design; a move offer that is superseded
without acceptance is recorded as lapsed; the plateau history (`prior_basis_tst`) draws only from
verdicts that applied (accepted or auto-applied), so a lapsed or superseded cycle contributes
nothing. **Amended by #440:** a converged HOLD is the one HOLD that does not apply on its own. It is
offered and needs the witnessed accept, like a move, because convergence ends restriction.

## 1. What exists today, and what is missing

| Fact | Where | Consequence |
|---|---|---|
| A cycle is never stored unless it is accepted. The offer is recomputed on every read. | `replay.evaluate_live_cycle` (`replay.py`), `GET /checkin-v2/cbti/evaluation` | A HOLD has no record; a superseded or unaccepted cycle leaves nothing behind. |
| Accepting mints a `cbti_prescriptions` row with `effective_from` = the accept day and sets the prior row's `effective_to` to the day before. | `checkin_v2.py:1103-1131` | Every acceptance restarts the cycle clock, and the nights from the offered cycle's end to the accept day belong to no cycle. |
| The offer is `complete[-1]`: the latest complete cycle of the live prescription. | `replay.py:357-364` | An earlier unaccepted cycle is replaced silently. |
| The plateau history is every replayed cycle's basis, accepted or not. | `replay.py:264` (`prior_tst.append`) | A lapsed cycle still shapes a later plateau check (cycle 10-15..18 feeds basis 406 on master). |
| `cbti_prescriptions` is append-only by model and application invariant, with two permitted UPDATEs (`effective_to`, `superseded_by`). No DB trigger. | `models.py` `CBTIPrescription`, migration `e5f2a9c7b104` | The new table follows the same discipline. |
| The ledger carries a per-night snapshot and a ruleset version since migration `d4a1c9f6b230` (2026-08-30). | `basis_ledger`, `ruleset_version` | Cycle windows can be pinned for prescriptions minted after that date, and not for earlier ones. |

## 2. The store: one table, `cbti_cycle_verdicts`

One row per adjudicated cycle, frozen when written. A prescription is still minted only by a
witnessed acceptance (#118); a verdict row is a record of a finding, not a prescription, so
writing one is not minting.

```sql
CREATE TABLE cbti_cycle_verdicts (
    id                        INTEGER PRIMARY KEY,
    block_id                  INT NOT NULL REFERENCES cbti_blocks(id) ON DELETE CASCADE,
    prescription_id           INT NOT NULL REFERENCES cbti_prescriptions(id) ON DELETE CASCADE,
                                                          -- the prescription in force over the cycle's nights
    cycle_start               DATE NOT NULL,
    cycle_end                 DATE NOT NULL,
    chains_from_id            INT REFERENCES cbti_cycle_verdicts(id) ON DELETE SET NULL,
                                                          -- the previous verdict in the block's chain; NULL for the first
    status                    VARCHAR(10) NOT NULL,       -- applied | offered | accepted | lapsed
    decision                  VARCHAR(10) NOT NULL,       -- hold | extend | compress
    outcome                   VARCHAR(12) NOT NULL,       -- no_decision | hold | converged | extend | compress (outcome_of)
    sufficient                BOOLEAN NOT NULL,
    converged                 BOOLEAN NOT NULL,
    reason                    TEXT NOT NULL,
    -- the window as it stood and what the engine recommended
    window_minutes            INTEGER NOT NULL,
    rec_window_minutes        INTEGER NOT NULL,
    rec_lights_out            VARCHAR(5) NOT NULL,
    -- the basis, frozen at authorship (never restated, #323 T2)
    basis_tst_min             INTEGER,
    basis_se_pct              FLOAT,
    basis_nights_n            INTEGER NOT NULL,
    basis_nights_logged       INTEGER NOT NULL,
    basis_n_flagged           INTEGER NOT NULL DEFAULT 0,
    excluded_nights           JSON NOT NULL,
    basis_ledger              JSON NOT NULL,
    ruleset_version           VARCHAR(40) NOT NULL,
    -- lifecycle
    created_at                TIMESTAMPTZ NOT NULL,       -- when the verdict was frozen
    applied_on                DATE,                       -- the day a HOLD applied, or a move was accepted
    minted_prescription_id    INT REFERENCES cbti_prescriptions(id),
                                                          -- accepted move: the row it minted (backfill: also a historical HOLD that minted one)
    lapsed_by_id              INT REFERENCES cbti_cycle_verdicts(id) ON DELETE SET NULL,
    lapsed_on                 DATE,
    unscored_from             DATE,                       -- accepted move only: the nights between the offer and the acceptance
    unscored_to               DATE,
    surfaced_on               DATE,                       -- set once, by the AM check-in submit after the verdict was shown (section 3B)
    origin                    VARCHAR(10) NOT NULL DEFAULT 'engine',   -- engine | backfill

    CONSTRAINT uq_cbti_verdict_cycle   UNIQUE (block_id, cycle_start),
    CONSTRAINT ck_cbti_verdict_status  CHECK (status   IN ('applied','offered','accepted','lapsed')),
    CONSTRAINT ck_cbti_verdict_decision CHECK (decision IN ('hold','extend','compress')),
    CONSTRAINT ck_cbti_verdict_outcome CHECK (outcome  IN ('no_decision','hold','converged','extend','compress')),
    CONSTRAINT ck_cbti_verdict_origin  CHECK (origin   IN ('engine','backfill')),
    CONSTRAINT ck_cbti_verdict_span    CHECK (cycle_end >= cycle_start),
    -- a HOLD that is not converged applies on its own; a move or a converged verdict is
    -- offered, then accepted or lapsed. Nothing else (#440 item 6).
    CONSTRAINT ck_cbti_verdict_kind    CHECK ((status = 'applied') = (decision = 'hold' AND NOT converged)),
    -- convergence is a HOLD and carries the converged outcome, and only that outcome
    CONSTRAINT ck_cbti_verdict_conv    CHECK (converged = (outcome = 'converged') AND (NOT converged OR decision = 'hold')),
    -- only a HOLD can be a non-decision
    CONSTRAINT ck_cbti_verdict_suff    CHECK (sufficient OR (decision = 'hold' AND outcome = 'no_decision')),
    CONSTRAINT ck_cbti_verdict_accept  CHECK (status <> 'accepted' OR minted_prescription_id IS NOT NULL),
    CONSTRAINT ck_cbti_verdict_lapse   CHECK ((status = 'lapsed') = (lapsed_by_id IS NOT NULL)),
    CONSTRAINT ck_cbti_verdict_mint    CHECK (origin = 'backfill' OR status <> 'applied' OR minted_prescription_id IS NULL)
);

CREATE INDEX ix_cbti_verdicts_block ON cbti_cycle_verdicts (block_id, cycle_start);
-- one pending offer per block
CREATE UNIQUE INDEX uq_cbti_verdicts_one_offer ON cbti_cycle_verdicts (block_id) WHERE status = 'offered';
-- the plateau read: applied or accepted verdicts that recorded a basis
CREATE INDEX ix_cbti_verdicts_plateau ON cbti_cycle_verdicts (block_id, cycle_start)
    WHERE status IN ('applied','accepted') AND basis_tst_min IS NOT NULL;
```

All CHECKs, partial indexes and the `JSON` columns are hand-written, as SCHEMA.md's Alembic
caveats require (autogenerate does not produce them). `JSON` matches the existing
`basis_ledger` and `excluded_nights`.

**Append-only discipline, same as `cbti_prescriptions`: a model and application invariant, no DB
trigger.** Everything is frozen at authorship except two transitions of a `status = 'offered'` row and
one marker:

| Transition | Columns it may set | Trigger |
|---|---|---|
| `offered` -> `accepted` | `status`, `minted_prescription_id`, `applied_on`, `unscored_from`, `unscored_to` | the witnessed accept |
| `offered` -> `lapsed` | `status`, `lapsed_by_id`, `lapsed_on` | the next cycle's verdict is written while this one is still `offered` |
| an `applied` or `lapsed` row | `surfaced_on`, once | the AM check-in submit that follows the verdict being shown (section 3B) |

### State machine

| Verdict | Written as | Then |
|---|---|---|
| HOLD that is not converged (adherence, merits HOLD) | `applied`, `applied_on` = the day it was frozen | terminal. Chains to the next cycle. Shown at the next check-in (section 3B). |
| Insufficiency HOLD | `applied`, `outcome = 'no_decision'`, `sufficient = false` | terminal. Chains to the next cycle. Reads as a finding, never a decision (`outcome_of`, #214, #218). Shown at the next check-in. |
| Converged HOLD (`converged`, `outcome = 'converged'`) | `offered` (#440 item 6) | accepted by the witnessed act, or lapsed when the next cycle's verdict is written. |
| Move (extend or compress) | `offered` | accepted by the witnessed act, or lapsed when the next cycle's verdict is written. |

## 3. How each #437 requirement is met

**(a) HOLDs apply without acceptance, and the next cycle chains from the previous close.** A HOLD
other than a converged one (item 6, (d) below) is written `applied`. The next cycle's `cycle_start` is the previous `cycle_end + 1`, and
`chains_from_id` names the previous verdict. The accept path no longer sees applied HOLDs, so #218's
409 for an insufficiency HOLD goes away: there is nothing to refuse.

**(b) A move needs acceptance, and the next cycle starts at the new `effective_from`.** The move is
`offered`. `POST .../accept` takes the verdict id, checks it is the block's one `offered` row, mints
the successor prescription (`effective_from` = the accept day), and sets the verdict `accepted` with
`minted_prescription_id`. The nights between the offer and the first night the new window governs
are the accepted-as-designed unscored nights; `unscored_from` and `unscored_to` record them so a
surface can say so, and they belong to no cycle of the new prescription. **Where the new
prescription's first cycle starts is OPEN (section 3A, Q236):** as built today it is the accept day,
and the proposal there is the day after.

**(c) A superseded move offer is recorded as lapsed.** When the materializer writes a new verdict
for a block that still has an `offered` row, it sets the old row `lapsed` with `lapsed_by_id` = the
new verdict and `lapsed_on` = the day. The unique partial index guarantees there is never more than
one pending offer. A new move becomes the new `offered` row; a new HOLD is `applied` and the old
offer still lapses, because the cycle that would have replaced it has closed.

**(d) A converged verdict is offered, not applied (item 6).** The plateau HOLD does not apply on its
own: it is written `offered` and needs the witnessed accept, like a move, because convergence ends
restriction (#118's reason for the witnessed act). If the next cycle closes without an accept it
lapses, and a lapsed converged verdict contributes nothing to the plateau history. Checked on master
`88c4c5b` before ruling:

- The engine turns a plateau into a HOLD with the window unchanged and `converged = True`
  (`engine.py`, the converged branch); `outcome_of` labels it `converged`.
- **Nothing in the application closes a CBT-I block.** No code path sets `cbti_blocks.closed_on`
  (block rows come from the import and open scripts only), and the engine never emits `close`
  (#165 made the titration perpetual). A converged outcome therefore ends no restriction today.
- The accept path treats a converged HOLD as an acceptable decision (`sufficient` is true) and mints
  a `hold` prescription with the window unchanged and its basis; that restarts the cycle clock.
- The replay script only prints "engine FIRST converged". The frontend never reads the `outcome`
  field, so a converged HOLD shows as "Hold the window" with the engine's reason text.

So today a converged outcome is acted on by exactly one thing: an optional accept that mints an
unchanged-window prescription. **What accepting a converged verdict should write is not ruled
(Q237).** Recommended: keep today's behaviour (a `hold` prescription minted with its basis), and no
block close, which is a separate decision.

**Plateau history draws only from applied verdicts.** `prior_basis_tst` becomes, in `cycle_start`
order:

```sql
SELECT basis_tst_min FROM cbti_cycle_verdicts
WHERE block_id = :bid AND status IN ('applied','accepted') AND basis_tst_min IS NOT NULL
ORDER BY cycle_start;
```

A lapsed cycle, an offered one that has not been decided (a converged verdict included until it is
accepted), and an adherence HOLD that recorded no basis (#436: a basis only with at least 3 valid
nights) contribute nothing. Rx 21's basis 406 stays in the history as persisted (#323 T2); it is a
merits HOLD, not a converged one, so item 6 does not touch it. `replay()` stops
accumulating `prior_tst` from every replayed cycle on the live path; the offline replay script
keeps its in-memory chain, labelled as a diagnostic.

## 3A. Which prescription a night belongs to (item 7, OPEN: Q236)

**Finding: a night is attributed by its WAKE date, and the night whose wake date is the accept day
belongs to the newly minted prescription.** Evidence:

- Accepting sets the successor's `effective_from` to the accept day and the prior row's
  `effective_to` to the day before (`checkin_v2.py:1105-1131`).
- Every reader attributes a night to the latest prescription whose `effective_from <= wake date`:
  `_cbti_context` (`checkin_v2.py:421-426`) and the MCP diary's `_rx_in_force`
  (`mcp_server.py:444-456`). The replay starts a prescription's first cycle at its `effective_from`
  (`replay.py`, `cycle_start = rx.effective_from`).
- `daily_records` stores no prescription id, so the join is made at read time and flips the moment
  the successor is minted.
- Live data: the diary read-out on 2026-10-22 shows night 2026-10-21 with rx 21, and rx 21 was
  accepted on 2026-10-21. That night was lived under rx 20: its lights-out was the evening of 10-20,
  before the acceptance.

**Why it matters only for a move.** Rx 21 was a HOLD, so the window did not change and the
attribution was harmless. A move changes the window, and a new window can only govern the evening
after the accept, which is the night with wake date accept day + 1. Counting the accept day's night in
the new prescription's first cycle scores a night run under the old window against the new one.

**Proposal (not ruled).** For a MOVE, and for an accepted converged verdict that mints a
prescription, the new prescription's first cycle starts at the accept day + 1, and the unscored range
runs from the offered cycle's `cycle_end + 1` to the accept day **inclusive**. That is at least one
unscored night even when the accept is made on the first eligible day.

`effective_from` is not redefined; it stays the date of the act. Three ways to carry the new start:

- **A (recommended): an additive column `cbti_prescriptions.first_night DATE NULL`**, the wake date of
  the first night the window governs. NULL means `effective_from`, which is every existing row, so
  no history is restated. At accept, `first_night` = accept day + 1 and the prior row's
  `effective_to` = the accept day, so the old window governs the accept day's night. Readers
  attribute by `COALESCE(first_night, effective_from)`: `_cbti_context` (two queries), the MCP
  `_rx_in_force`, and the replay's prescription load. It is one nullable column in its own
  migration, separate from the verdict table.
- **B: a code rule** (a move's first night is `effective_from + 1`). It cannot tell a post-cutover
  move from rx 15 to 17, which were accepted moves attributed the old way, so it either restates
  them or needs a cutover date. Rejected.
- **C: redefine `effective_from`** as the first governed night. Rejected: it loses the date of the
  act and changes the meaning of every existing row.

An edge to rule on: the rule is by calendar wake date. An accept made after the evening's lights-out
still names the night that began that evening as the first governed night, which is then already
partly run.

## 3B. Surface requirement (item 5)

An auto-applied HOLD is shown at the next check-in and is never silent. Wording is deferred to the
cutover PR; the requirement is built into the store now. Mechanism: `surfaced_on`, set once for each
`applied` or `lapsed` verdict by the AM check-in submit that follows its being shown. The AM prefill
(a GET, which does not write) lists every `applied` verdict with `surfaced_on IS NULL`, and the AM
submit response returns the verdicts it has just materialized, so a HOLD written at a submit is shown
in that response and again on the next prefill until the following submit marks it. A skipped
check-in leaves it unmarked, so it is shown again. `surfaced_on` is the third permitted update.

## 4. The write path

**Materialization.** A function `materialize_verdicts(db, block, today)` walks the block forward
from the last stored verdict, adjudicates each closed cycle with the engine, and writes one row per
cycle. It is idempotent: `UNIQUE (block_id, cycle_start)` plus `INSERT ... ON CONFLICT DO NOTHING`
means two concurrent callers write each cycle once, and the loser re-reads.

```
cursor   = (last stored verdict).cycle_end + 1       # applied or lapsed: chain
           or the live prescription's first governed night   # first cycle, or just after an acceptance (3A)
for cycle [cursor .. cursor + CYCLE_NIGHTS - 1] while today > cycle_end:
    nights = logged nights in the cycle
    if no nights: cursor = cycle_end + 1; continue    # nothing to adjudicate; dates still tile
    v = engine.evaluate_cycle(...)                    # the live prescription's window and anchor
    write the verdict; lapse any 'offered' row it supersedes
    cursor = cycle_end + 1
```

**Freeze point (ruled).** A cycle is written once `today > cycle_end`, the day after its last night,
so a diary entry made by the end of that last day still counts. A later correction (the 2026-10-09
row, corrected on 2026-10-21, is the example) never reopens a frozen verdict, and there is no
re-adjudication path (ruled); that is the ledger rule (#323 T2), now applied to HOLDs.

**When it runs (ruled): the AM check-in submit and the accept call only.** Not a schedule and not a
background sweep (#118: nothing mints on a schedule or from a data signal), and **a GET never
writes.** `GET /cbti/evaluation` and the AM prefill compute the not-yet-written head in memory. The
cost is that a day with no check-in leaves the head unwritten until the next submit.

## 5. Read path and API

- `GET /checkin-v2/cbti/evaluation` returns the pending `offered` verdict (a move or a converged one,
  or none), the latest applied verdict, and the recent lapsed ones, computing the unwritten head in
  memory (a GET does not write). `eligible` stops meaning "a cycle is acceptable" and starts meaning
  "an offer is waiting".
- `POST /checkin-v2/cbti/evaluation/accept` takes `{verdict_id}`. It no longer recomputes: the
  verdict is frozen, and the client cannot post a decision the engine did not write because the id
  names a stored row. The idempotency 409 survives; the insufficiency 409 does not.
- The MCP `get_cbti_diary` tool can list the verdict chain in a follow-up; it reads
  `cbti_prescriptions` today and is untouched by the first PRs.

## 6. Migration shape

One additive Alembic revision, hand-written, `down_revision = 'e5b2c8a91d47'` (the head on 2026-10-22; re-read the head at
build time and re-chain if it has moved).

- `upgrade()`: `op.create_table('cbti_cycle_verdicts', ...)` with every named CHECK, the unique
  constraint, and the three indexes above (the two partial ones through `op.create_index(...,
  postgresql_where=...)`). No data in the revision.
- `downgrade()`: drop the three indexes, then the table.
- Verified the way the repo already does it: the Alembic chain does not replay on SQLite, so stamp
  the prior head on a scratch Postgres, upgrade one step, downgrade one step, upgrade again. The
  prod check needs the DB service's `DATABASE_PUBLIC_URL`.
- `SCHEMA.md` entry `050 — cbti_cycle_verdicts` in the same commit, and the `models.py` class with
  the append-only docstring.

**Backfill is a separate operator script**, `scripts/backfill_cbti_verdicts.py`, dry-run by default
and `--apply` to write, idempotent through the unique constraint (the repo's pattern for operator
writes). It runs in the prod container (`railway ssh --service health-app-backend`, then
`/opt/venv/bin/python -m scripts.backfill_cbti_verdicts`) after the migration deploys.

### How the existing ledger maps onto it

Read from prod on 2026-10-21 (block `cbti_blocks.id` 2, programme block 3). A cycle window can be
pinned only where the accepted prescription carries a `basis_ledger`; the cycle is
`[min(ledger date), min + 3]`, checked to end before the successor's `effective_from`.

| Prescription | Accepted on | Cycle | Ran under | Verdict | Basis TST | Backfilled |
|---|---|---|---|---|---|---|
| rx 10 | 2026-07-24 | n/a | n/a | opening `adopt` | 349 (device) | no: not a cycle |
| rx 11 | 2026-07-27 | n/a | n/a | operator correction | none | no: not a cycle |
| rx 12 | 2026-08-13 | not stored | rx 11 | hold, 2 nights | none | no: window unpinned, pre-ledger |
| rx 13 | 2026-08-20 | not stored | rx 12 | extend | 440 | no: window unpinned, pre-ledger |
| rx 14 | 2026-08-27 | not stored | rx 13 | extend | 405 | no: window unpinned, pre-ledger |
| rx 15 | 2026-09-04 | 08-31..09-03 | rx 14 | compress | 369 | yes, `accepted` |
| rx 16 | 2026-09-12 | 09-08..09-11 | rx 15 | extend | 387 | yes, `accepted` |
| rx 17 | 2026-09-20 | 09-16..09-19 | rx 16 | extend | 406 | yes, `accepted` |
| rx 18 | 2026-09-27 | n/a | n/a | operator correction | none | no: not a cycle |
| rx 19 | 2026-10-11 | 10-05..10-08 | rx 18 | hold (adherence) | 424 | yes, `applied` (it minted rx 19) |
| rx 20 | 2026-10-15 | 10-11..10-14 | rx 19 | hold | 351 | yes, `applied` (it minted rx 20) |
| rx 21 | 2026-10-21 | 10-15..10-18 | rx 20 | hold (`excused_guard`) | 406 | yes, `applied` (it minted rx 21) |

Six rows are backfilled, `origin = 'backfill'`, `ruleset_version` copied from the prescription
(rx 21's ledger keeps its `training_constrained` row and ruleset `cbti-basis/2026-09-23.1`, which is
the point of never restating), `applied_on` = the successor's `effective_from`, and
`minted_prescription_id` set (that is why `ck_cbti_verdict_mint` exempts backfill: a historical HOLD
did mint a row).

Field sources for a backfilled row: `window_minutes` is the window of the prescription the cycle
ran under; `rec_window_minutes` and `rec_lights_out` are the minted prescription's; `outcome` is
`hold`, `extend` or `compress` from its `decision` (never `no_decision`: every one of the six was
a decision on the merits); `excluded_nights` is rebuilt from the ledger's `excluded` rows, because
the prescription's own `excluded_nights` column is NULL; `reason` is the fixed text "backfilled
from prescription N", since the original engine reason string was not stored.

Not backfilled, deliberately:
- **Cycles that were never accepted** (for example 09-12..15, four adherence failures, replaced
  unaccepted by 09-16..19). They were never persisted, and a verdict derived today would be written
  under today's rules, not the ones the operator saw. The store starts without a lapsed history.
- **Rx 12 to 14.** They pre-date the ledger, so no window is stored. Only the last two entries of
  the plateau history are ever read (`prior_basis_tst[-1]` and `[-2]`), so leaving them out cannot
  change a plateau check.

**Plateau at cutover.** From the backfilled rows the history is 369, 387, 406, 424, 351, 406 in
`cycle_start` order. The check reads the last two (351, 406): a difference of 55 against a
tolerance of 10, so no spurious convergence, the same as today. Rx 21's 406 becomes the latest
entry; it is the basis of an accepted verdict and the persisted record.

## 7. Alternatives considered

- **Add states to `cbti_prescriptions`.** Rejected: a HOLD that applies without acceptance would
  have to mint a prescription row, which resets `effective_from` and the cycle clock (the defect
  being fixed) and breaks #118. The ledger stays a record of windows.
- **A JSON list on `cbti_blocks`.** Rejected: no foreign keys, no unique key on `(block, cycle)`,
  no partial index for "one pending offer", and a block row that is otherwise append-only.
- **Keep recomputing (status quo).** Rejected: nothing is frozen, so a HOLD can change when a late
  device session lands, and a lapsed cycle leaves no record.
- **A second table for lapsed offers.** Rejected: one lifecycle table with a status column is
  simpler to constrain and to read.

## 8. Rulings and what is still open

Ruled by the operator on 2026-10-23 and recorded in `DECISIONS_LOG` #440:

| # | Point | Ruling |
|---|---|---|
| 1 | Does `GET /cbti/evaluation` write? | No. Materialize on the AM check-in submit and the accept call only. |
| 2 | Freeze point | The day after `cycle_end`. |
| 3 | Post-freeze corrections | Never reopen a verdict; no re-adjudication path. |
| 4 | Rx 21's basis 406 | Stays in the plateau history as persisted (#323 T2), contingent on item 6. It is a merits HOLD, so item 6 does not touch it. |
| 5 | Surface | Wording deferred to the cutover PR. Requirement now: an auto-applied HOLD is shown on the next check-in, never silent (section 3B). |
| 6 | Converged verdicts | Not auto-applied: written `offered`, needs the witnessed accept, like a move (section 3(d)). |

Still open:

1. **Which prescription a night belongs to, for a move (item 7, Q236).** Section 3A proposes that a
   move's first cycle starts the day after the accept and that the unscored range includes the accept
   day, carried by a new nullable `first_night` column (option A).
2. **What accepting a converged verdict writes (Q237).** Recommended: a `hold` prescription minted
   with its basis, as today, and no block close.
3. **Surface wording**, in the cutover PR.

## 9. Build plan

Each step is its own PR; the first two hold for review.

1. **Migration, model, SCHEMA.md `050`** (this table, empty, with `surfaced_on` and the amended
   `ck_cbti_verdict_kind` and `ck_cbti_verdict_conv`). No behaviour change. Holds (schema). The
   `first_night` column of section 3A, if ruled, is a separate migration after this one.
2. **Backfill script**, run by the operator after step 1 deploys: dry-run first, read the plan,
   then `--apply`. Holds until the dry-run is read.
3. **Materializer in shadow**: writes verdicts from the AM check-in and the accept call, while the
   offer, accept and plateau still use today's logic. A test pins that the stored verdicts equal
   what `replay()` computes for the same nights, so the cutover is a read swap, not a new rule.
4. **Cutover**: the offer, accept and plateau read the store; #218's insufficiency 409 is removed;
   the frontend renders the chain. Tests: a HOLD chains with no gap; a converged verdict is written
   `offered` and lapses without an accept; an accepted move starts its successor's cycle where 3A
   rules and records the unscored nights; a superseded move lapses and the plateau ignores it; an
   applied HOLD is shown until a submit marks `surfaced_on`; a GET writes nothing; a late diary
   correction does not move a frozen verdict; two concurrent materializations write each cycle once.

**Rollback.** Steps 1 and 2 are inert and `downgrade()` drops the table. Step 3 can be switched off
without data loss (the table is only written). Step 4 is the only behavioural change and reverts by
restoring the read path; the stored verdicts remain valid.
