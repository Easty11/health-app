# Session close-out

_Session of 2026-08-17. Opened at `4657d50`, maxima **#216 / Q102**. Master closed at the
merge of this branch. Both fresh-clone settings verified present at open
(`core.hooksPath` = `.githooks`, local `alias.land`)._

## 1. Real commits this session

```
2b2f91d feat: map Cystatin C to cystatin_c in the canonical dictionary
c71e497 Merge pull request #72 from Easty11/feat/canonical-map-cystatin-c
```

Plus this close-out commit on `chore/session-closeout-0817` — the session's single `gov`
landing, per the governance-batching rule.

**Branch terminal-state gate: PASS.** `feat/canonical-map-cystatin-c` is merged and deleted
local + remote. Three pre-existing `claude/*` branches were enumerated by the gate and carry
**zero** unique commits vs `origin/master` (`git cherry` returns neither `+` nor `-`), so none
triggers the push-or-row requirement; two live in worktrees and were left untouched — they are
not this session's to dispose of.

## 2. Pending-queue reconciliation

This session opened on a two-part chat brief, not a `;cc` PENDING queue.

- **Brief A — canonical-map expansion (Cystatin C).** **LANDED.** `2b2f91d`, merged `c71e497`
  via PR #72; prod backfill applied the same session. Recorded as `DECISIONS_LOG #217`
  (integer resolved at this branch's merge).
- **Brief B — renal derived metrics.** **NOT BUILT, deliberately.** Spec-only by its own
  header. Its precondition — a mapped `cystatin_c` — was unmet at session open and is met now.
  Its one open design fork was closed this session by a read-only trace (below) and folded into
  B's spec as an amendment by chat. B builds next session.
- **`backend/probe_cystatin.py`** — deleted, not committed, as instructed. It was never tracked,
  so it leaves no trace in history.

Nothing decided this session is uncommitted. No provisional state carries forward.

## 3. Cold-resume handoff

### What landed this session

**One entry in `backend/reference/marker_canonical.json`**: raw `Cystatin C` -> `cystatin_c`,
`unit_established` `mg/L`, `loinc` null (69 -> 70 entries, all keys unique). Data only; no code
path changed. The `#55`-sibling backfill rider then bound the single row that had been sitting
with `marker_canonical` NULL since the 2026-08-04 SNP draw — the state that raised the app's
"not a known marker" banner and caused the brief to exist.

The load-bearing detail is that `unit_established` was taken from the **stored**
`unit_canonical`, not the printed form. The §6 over-collapse guard is a byte equality, so a case
or form variant in the map would have refused the *next* upload of this marker with a 422 —
loud, but a self-inflicted outage on a marker that had only just been mapped. The precision
check against prod (row id 220: raw name 10 bytes, unit `mg/L`, both byte-exact) ran **before**
the entry was written.

Nine new tests in `backend/tests/test_canonical_cystatin_c.py`, built on the
`test_canonical_urine_acr` precedent and written to discriminate rather than merely pass: the §6
refusal is asserted at three wrong units including the case variant `MG/L`, and a null-unit row
is asserted to **pass**, fixing the guard's meaning as unit-CONFLICT rather than unit-REQUIRED.
Suite 869, up from an 860 baseline. `test_canonical_urine_acr.py`'s whole-file count assertion
moved 69 -> 70 — it exists to force that notice on every expansion, and it did.

**Prod evidence chain**: deploy `188c8050` SUCCESS at `c71e497` (prior image `REMOVED`) ->
dry-run reported the named line `'Cystatin C' -> 'cystatin_c': 1 row(s) would update`, total 1
across **70** known mappings (the "70" doubling as the `#116` image-discriminating probe: the
prior image would report 69 and print no Cystatin C line) -> `--apply` returned `Committed. 1
row(s) backfilled.` -> the same dry-run re-run post-apply returned 0 rows. **One gap, recorded
rather than glossed:** row 220 was not separately read back as a `SELECT` projection post-apply.
The written literal is `cystatin_c` by construction (the UPDATE binds `:canonical` from the same
map lookup the dry-run printed) and the 0-row re-read proves the NULL is gone, but a direct
projection is the one confirmation this session does not carry. A single dashboard statement
closes it if ever wanted.

**Read-only trace: what writes `is_derived = true`.** Nothing does. Only two non-test
constructions of `LabResult` exist (`routers/labs.py` confirm, and a fixture generator); the
confirm construction omits the field entirely, so every row takes the column default `false`,
and the field is absent from the extraction schema so there is no inbound path even in
principle. The only `true` settings anywhere are three tests. This closed Brief B's placement
fork: both existing `is_derived` channels — the column, and the `marker_groups.json` reference
flag on lab-derived markers like `testosterone_free_calculated` — presuppose a *stored row*,
and B's metrics are computed at read time and stored nowhere. B therefore mints its own producer
output slot rather than reusing either.

### What was NOT touched — the standing lanes

Named explicitly, because a close-out that lists only what moved hands the next session more of
the same kind of work.

- **CBT-I Q45 nap day-attribution.** ROADMAP NOW, **dated and contaminating capture now** — the
  engine reads a night's naps from `date − 1` on an unverified attribution, live for block 3
  (`cbti_blocks.id` 2), and it now gates a second user at the 4-night cadence. Untouched this
  session. This is the oldest live-contamination item on the board and it did not move.
- **Interpretation layer build.** 4b is DONE/DELIVERED; the remaining increments — the rephrase
  pass (2), lever-tap threads (3), go-live (5) — were not started. Untouched.
- **Lab upload pipeline.** Untouched beyond this session's reference-data addition.
- **Appointment brief.** Untouched.
- **`SCHEMA.md` stale for the entire lab family.** Still OWED; it documents a *superseded*
  design. This session touched the lab family without a schema change, so it did not fall
  further behind — but it is no less wrong than it was at open.
- **Frontend deploy probe (`#116`/`#121`).** Still never run. Not required here — this change is
  backend-only — but the debt is unchanged.

**Session-shape note.** This was a data addition plus a read-only trace: product-adjacent, not a
feature build. It follows `#216` (product code) and, before that, two governance/instrument
sessions. The instrument-over-thing run is not acute, but it is real, and **Brief B is now the
first genuinely unblocked feature lane on the board**. The next session should build it rather
than produce more governance.

### Open questions minted this session

- **`Q103` — `lab_results.is_derived` is write-dead.** No production path sets it true, which
  makes `context_builder.py`'s stale-derived suffix branch unreachable in prod. Corrupts
  nothing, gates nothing; raised so nobody later debugs it as a mystery. The fork is whether the
  column is dead-by-design (and should be removed rather than left as a trap) or was always
  meant to be wired. **State: OPEN**, no blocker, owner Luke.

No question was closed this session. Tally at close: 53 OPEN / 41 DONE.

### Single clearest next action

**Build Brief B — renal derived metrics — in the 4b interpretation producer.** Every
precondition is now discharged: the input marker maps, the placement fork is closed to a
producer output slot, and both equations plus the seed fixture (Scys 1.24 / male / 45 ->
eGFR-cys 62.05; ratio 0.795 -> modest band) were independently reproduced this session against
the published CKD-EPI forms.

Two things B's session must verify at open rather than assume, both flagged in its spec:
the `lab_reports` collection-date column name (run `\d lab_reports` before writing the
same-draw join — SNP splits one draw across multiple report documents, so cross-report pairing
is the normal case, not the edge), and that a capped `>90` eGFR really lands in `value_operator`.
The capped-row refusal is a named gate: the reader must refuse, never consume `value_num` alone
and silently substitute 90.

### Explicitly out of scope this session

- Brief B's code — spec-only by its header, and its precondition was unmet at open.
- LOINC population (dormant per §7, deferred to the B2B phase).
- Zinc — `Zinc-plasma` already maps; its row needed nothing.
- The three pre-existing `claude/*` branches — enumerated by the gate, zero unique commits, not
  this session's to dispose of.
