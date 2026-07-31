# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-01 (second session that day; the prior close-out is `b94a59f`).
Branch at close: `master` (clean). Session-open ref: `b94a59f`.

## 1. Real commits this session

Six commits, all on master and pushed. `git log --oneline b94a59f..HEAD`:

```
d65e98e governance: #158 — declined uploads leave the results list; SCHEMA.md drift recorded
fb1fe00 feat(labs): declined reports leave "Your Results" for the upload history
7ad5f40 fix(labs): pre-check copy read "All 1 marker were recorded"
975635d feat(labs): upload history — every ingested report, including those that added nothing
3570af1 feat(labs): record WHY a report contributed no rows — decline is not fault
8d399eb feat(labs): collision pre-check at the confirm screen, before anything is written
```

`git log --format="%ad %s" --date=short -10`:

```
2026-08-01 governance: #158 — declined uploads leave the results list; SCHEMA.md drift recorded
2026-08-01 feat(labs): declined reports leave "Your Results" for the upload history
2026-08-01 fix(labs): pre-check copy read "All 1 marker were recorded"
2026-08-01 feat(labs): upload history — every ingested report, including those that added nothing
2026-08-01 feat(labs): record WHY a report contributed no rows — decline is not fault
2026-08-01 feat(labs): collision pre-check at the confirm screen, before anything is written
2026-08-01 chore: session close-out
2026-08-01 governance: resolve #NEXT -> #157, Q-NEXT -> Q68 (on-branch, pre-ff)
2026-08-01 governance: #NEXT — ingest asserts persistence; the zero-row reports were #156 working
2026-08-01 feat(labs): a stored report with zero results reads as a fault, not as emptiness
```

Suite **527 passed**, from a **521** baseline — reconciled against the brief's stated 521. The +6
are `backend/tests/test_labs_zero_row_reason.py`.

**Branch gate.** `feat/labs-upload-history` — merged + deleted, local and remote;
`git cherry origin/master` returned empty. `git branch` shows `master` only;
`refs/remotes/origin` shows `origin/master` only. Row added to `BRANCHES.md` (**DONE**,
`d65e98e`). No branch in limbo.

## 2. Pending-queue reconciliation

The brief carried **one** `PENDING` item: a DECISIONS entry.

| Item | Disposition |
|------|-------------|
| DECISIONS `### #NEXT` — results list carries values; pre-check; declined vs unparseable | **Landed** as **#158** in `d65e98e`, renumbered in the same commit (master max was #157). The `[VERIFY]` placeholder in the drafted "Distinguishing declined from unparseable" clause is resolved with what was actually found. |

The drafted entry left one clause open: *"[VERIFY — state whether the store already
distinguished them, or what was added so it could.]"* Resolved, and the answer was worse than the
brief's two options allowed for — see §3.

Nothing decided this session is uncommitted. No provisional state carried forward.

## 3. Cold-resume handoff

### What this session established

**The pre-check needed no endpoint.** `GET /labs/results` already returns every stored report with
`collected_date`, `marker_canonical` and `marker_name_raw`; `GET /labs/canonical-map` resolves an
extracted raw label exactly as `_duplicate_key` does. Both are fetched on mount to render the
results table, so the collision check is client-side computation over state already in hand.

**`#156`'s write-time guard is untouched, and that is proven rather than asserted.** Both regions
hash byte-identical to the pre-change baseline: detection block `fb9e9cbf84a535c5`, write-loop skip
`c478d7313ea5c50f`. Two mechanisms, different jobs — the pre-check informs a decision, the guard
protects the data.

**The store could not distinguish a decline from a fault, and the gap was deeper than a missing
field.** Both findings verified directly against the pre-change handler:

1. Nothing persisted the outcome — the confirm response carried `duplicates`, but no column
   recorded it, so after the fact both cases were simply a report with zero rows.
2. **An unparseable document could not reach the store at all.** `results=[]` tripped
   `assert row_confidences`, which raised *before* `db.commit()` — HTTP 500, no row written. The
   fault case had no representation to be confused with; it had none.

`lab_reports.zero_row_reason` was added (migration `d7c4b1a90e35`): `NULL` when the report
contributed rows, `all_markers_declined`, or `no_values_extracted`. The assert became a recorded
event — a chart or scan with no results table is a real document the operator uploaded and is owed
a record of. Finding (2) is also what makes the backfill a **proof** rather than an inference: the
fault value was unreachable before this change, so no legacy row can carry it.

**Divergence from the brief, stated not absorbed.** The brief said not to reword the zero-row red
panel. But the panel must survive for faults (G4), and its copy attributed the emptiness to a
repeat — *"this usually means every marker was already recorded ... the upload was a repeat."* Left
in place it would tell the operator that an unreadable chart PDF was a duplicate. The decline copy
was not polished; it leaves that surface with the declines, and the fault has copy true of it.

### Gate evidence

| Gate | Evidence |
|---|---|
| **G1** | Real page driven with a stubbed axios adapter. Confirm screen states *"Every marker in this report is already stored ... on report 1"* with a stored-vs-incoming table, before any write. Buttons become **Cancel — nothing to add** (default) / **Save anyway (keep both)**. **Cancel issued ZERO requests** — no `/labs/confirm`, none at all. |
| **G2** | SHA-256 of both guard regions identical to baseline (above). |
| **G3** | History lists every report with a contribution note; live DB shows all 10 legacy zero-row rows carrying `all_markers_declined`. |
| **G4** | Non-vacuity. Both a declined and an unparseable report have zero rows; the filter keys on `zero_row_reason`, never on row count. Declined → absent from results, present in history. Unparseable → present in **both**, with fault copy. Backend test asserts the two reasons are *unequal* so a future collapse fails there. |
| **G5** | Live: 10 zero-row reports, all `all_markers_declined`, total still **43** — none deleted. |
| **G6** | 527, from 521. |

### Deploy state — verified per `#121` on BOTH services

| Service | Discriminating probe | Result |
|---|---|---|
| `health-app-backend` | AST introspection of the live imported handler + live DB | `alembic=d7c4b1a90e35`; `zero_row_reason` column present; handler sets it; only the alignment assert remains; `min(..., default=0.0)` live |
| `health-app-frontend` | served-bundle grep of `assets/index-HenL5rqa.js` | 6 new string literals present; removed decline copy **absent** (negative control) |

Both deployments `SUCCESS` at `2026-08-01 07:50 +10:00` before probing (#116 — timing).

**A `#113` false positive was hit and caught.** A substring grep for `assert row_confidences`
against the live handler returned **True** — from the *comment explaining the assert's removal*.
The executable statement is gone; an AST walk shows the only remaining assert is
`len(row_confidences) == len(resolved)`. Exactly the corrected-document shape `#113` warns about:
read the match, not the count.

### What `#157`'s owed operator decision became

**DISSOLVED, not deferred.** The ten zero-result reports are reclassified as upload events rather
than junk. `#155` retention holds unchanged and no deletion decision is required. Nothing was
deleted — the live report count is still 43.

### Open questions

- **Q68** — should a full-collision re-upload create an empty `LabReport` envelope at all?
  Unchanged and still open, but materially softened: the envelope is now a legible history entry
  rather than an unexplained empty card, so the cost of keeping it has dropped. Still settled
  properly only by report-level identity (`Document ID` / `Lab ID`, uncaptured). Trigger, not
  blocker.

### OWED — new, surfaced this session

**`SCHEMA.md` is stale for the entire lab family** (`ROADMAP.md` NEXT). `CLAUDE.md` makes it
repo-canonical and says it must never lag master. It documents a **superseded** design —
`lab_results` hanging off `lab_panel` *events*, plus `marker_aliases` and `unknown_markers`, none
of which exist. The implemented `lab_reports`/`lab_results` pair (#52) has never been in it, and no
lab migration has ever updated it (`c655bd6`, `005c1a6`, `7753758`, `d7c4b1a90e35`). Discovered
while landing `zero_row_reason`: the rule could not be honoured because there is no table entry to
update without first authoring the whole family. A doc rewrite with its own scope — deliberately
not absorbed here. Owner: Luke.

### Single clearest next action

**Resume the lab backfill.** The confirm screen now warns before the write, cancelling costs
nothing, and the upload history answers which documents went in. A repeat is a two-click cancel; a
corrected result is visible as a differing value and resolved with **keep both**.

Then, unrelated and unchanged: **4b-ii's sole remaining hold is `axis_verdict`** — the
source-factor rule for the `factors` list → scalar `protocol_phase`, plus the evaluability-keyed
authoring table. See `ROADMAP.md` → Interpretation layer build sequence.
