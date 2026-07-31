# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-01. Branch at close: `master` (clean). Session-open ref: `2cc8cb6`.

## 1. Real commits this session

Six commits, all on master and pushed. `git log --oneline 2cc8cb6..HEAD`:

```
7ff5d26 governance: resolve #NEXT -> #157, Q-NEXT -> Q68 (on-branch, pre-ff)
6a4cf44 governance: #NEXT — ingest asserts persistence; the zero-row reports were #156 working
03dc017 feat(labs): a stored report with zero results reads as a fault, not as emptiness
2e38a51 fix(labs): do not promise "nothing was lost" when a value was in fact discarded
4a8b620 fix(labs): report what the save actually wrote instead of an unconditional toast
36af7f1 fix(labs): a marker repeated in one document no longer drops every copy
```

`git log --format="%ad %s" --date=short -10`:

```
2026-08-01 governance: resolve #NEXT -> #157, Q-NEXT -> Q68 (on-branch, pre-ff)
2026-08-01 governance: #NEXT — ingest asserts persistence; the zero-row reports were #156 working
2026-08-01 feat(labs): a stored report with zero results reads as a fault, not as emptiness
2026-08-01 fix(labs): do not promise "nothing was lost" when a value was in fact discarded
2026-08-01 fix(labs): report what the save actually wrote instead of an unconditional toast
2026-08-01 fix(labs): a marker repeated in one document no longer drops every copy
2026-07-31 governance(open-questions): Q67 — phase-conditional co_movement has no expressing shape (pointer)
2026-07-31 governance(open-questions): Q66 — no supersede affordance on LabResult
2026-07-31 governance: #156 — series integrity guarded at ingest, not assumed
2026-07-31 chore(labs): post-backfill series-integrity verification query
```

Suite **521 passed**, from a **513** baseline measured at session open — reconciled against the
brief's stated 513. The +8 are `backend/tests/test_labs_confirm_persistence.py`.

**Branch gate.** `fix/labs-confirm-persistence` — merged + deleted, local and remote;
`git cherry origin/master` clean. `git branch` shows `master` only; `refs/remotes/origin` shows
`origin/master` only. Row added to `BRANCHES.md` (**DONE**, `7ff5d26`). No branch in limbo.

## 2. Pending-queue reconciliation

The brief carried **one** conditional `PENDING` item: a DECISIONS entry, *"conditional on Step 2
confirming the blind spot."*

**Step 2 did not confirm it — it falsified it.** The drafted entry asserted that `#156`'s guard
"cannot fire on a write that produces no rows" and that a lab result displayed on the confirm
screen was failing to reach the database. Neither is true. The guard fired, correctly, and
*caused* the zero-row writes by design. The entry was therefore **rewritten, not landed as
drafted**: the persistence-standard clause survives, the blind-spot clause is replaced by what was
actually found.

| Item | Disposition |
|------|-------------|
| DECISIONS `### #NEXT` — persistence standard + `#156` blind spot | **Landed rewritten** as **#157** in `6a4cf44`; renumbered in `7ff5d26`. Blind-spot framing falsified in the entry text; persistence standard stands. |
| Q68 — not in the brief's queue, surfaced by the investigation | **Landed** as **Q68** in `6a4cf44`. |

**Numbering collision, flagged deliberately.** The brief lists *"Q68's cross-date operand
question"* under "Not in this brief", as though Q68 exists. **It does not and never did** — repo
max was Q67. Number-at-merge claims the next sequential integer at the instant of merge, so this
session's entry **is** Q68. The cross-date operand question is still pending in chat and takes the
next free number when it lands. `OPEN_QUESTIONS.md` Q68 carries this note inline.

Nothing decided this session is uncommitted. No provisional state carried forward.

## 3. Cold-resume handoff

### What this session established — read before re-opening the lab lane

**There was no data loss.** All ten `lab_reports` rows carrying zero `lab_results` are re-uploads
in which **every** submitted marker already existed for that user at that `collected_date`. Each
row was skipped by `#156`, `result_count` returned `0`, and the envelope was still created per
`#155` retain-raw. The values are held on the earlier report.

Live database at investigation (queried inside the container; `DATABASE_URL` never rendered, #111):

```
reports=43  results=168  empty_reports=10  distinct_markers=66
series integrity: CLEAN — no marker duplicated at any collection date
```

66 distinct canonical markers against a 66-entry `marker_canonical.json` — every mapped marker is
present.

**What actually failed was silence.** `#156` closes by recording that `result_count` reports rows
written *"so a skipped collision is visible to the caller."* It was visible. The caller —
`Metrics.jsx` — awaited the POST, discarded the response, and rendered an unconditional
`"Report saved"`. The read-back then drew the resulting empty report as column headings above
nothing, which reads as a report that had no results rather than as a fault. **A field that is
returned but not read is not a report.**

**A genuine loss was found separately.** The skip set was keyed by *marker* and the write loop
tested membership by that key, so a marker appearing twice inside one submission suppressed every
row carrying it — including the first, which had nothing to collide with. Now decided per **row
index**. Latent today (no canonical id has more than one raw synonym); armed by any synonym added
to the map.

**Non-vacuity is on the record.** Against the pre-fix handler the new persistence file ran
**2 failed, 6 passed** (the two intra-batch cases); **8 passed** after. The six that passed pre-fix
state the standard against a happy path that was never broken, and are reported as such rather
than dressed up as regressions.

### Deploy state — verified per `#121` on BOTH services

| Service | Discriminating probe | Result |
|---|---|---|
| `health-app-backend` | introspect the **live imported handler** in-container | `skip_indices` present, `skip_keys` absent; `tests/test_labs_confirm_persistence.py` on disk |
| `health-app-frontend` | served-bundle grep of `assets/index-CgweDcPR.js` | three new string literals present; removed `"Report saved"` **absent** (negative control) |

Both deployments `SUCCESS` at `2026-08-01 07:07:38 +10:00` before probing (#116 — timing).

### OWED — operator decision, not a Code step

**Ten zero-result `LabReport` rows and eight duplicate `(collected_date, panel)` groups are
reported and NOT deleted.** `#155` ratified retention and a delete is the operator's call. A
zero-result report carries no data, so removal costs nothing — but it is still a delete.

| id | collected | panel | file | data lives on |
|---|---|---|---|---|
| 32 | 2025-05-16 | Haematinics | `20250516__Haematinics.pdf` | 8, 9, 10, 33, 34, 35 |
| 22 | 2025-12-27 | Routine Chemistry | `20251227__Routine_Chemistry.pdf` | 11–17, 24 |
| 23 | 2025-12-27 | 25-OH Vitamin D | `20251227__25-OH_Vitamin_D.pdf` | 11–17, 24 |
| 21 | 2026-01-07 | Androgens | `20260107__Androgens.pdf` | 18, 19, 20 |
| 37 | 2026-04-20 | Androgens | `20260420__Androgens.pdf` | 36, 42 |
| 38 | 2026-05-30 | Prostate Specific Antigen (PSA) | `20260530__PSA.pdf` | 1–7 |
| 39 | 2026-05-30 | Homocysteine | *(none)* | 1–7 |
| 40 | 2026-05-30 | Homocysteine | `20260530__Homocysteine.pdf` | 1–7 |
| 41 | 2026-05-30 | HbA1c | `20260530__HbA1c.pdf` | 1–7 |
| 43 | 2026-05-30 | Prostate Specific Antigen (PSA) | `20260530__PSA.pdf` | 1–7 |

Duplicate `(collected_date, panel)` groups: `2025-05-16` Haematinics (10, 32) · `2025-05-16`
Haematology (9, 33) · `2025-12-27` 25-OH Vitamin D (14, 23) · `2026-01-07` Androgens (19, 21) ·
`2026-04-20` Androgens (36, 37) · `2026-05-30` HbA1c (3, 41) · `2026-05-30` Homocysteine
(2, 39, 40) · `2026-05-30` PSA (1, 38, 43).

**Uploading is unpaused.** It was paused on the belief that reports were silently dropping their
results. They were not.

### Open questions touched

- **Q68 (new, open)** — should a full-collision re-upload create an empty `LabReport` envelope at
  all? `#155` retain-raw says the document exists; the envelope carries no data. Settled properly
  only by report-level identity (`Document ID` / `Lab ID`, uncaptured). **Trigger, not blocker** —
  the schema change is possible now, it is simply not yet worth doing.
- **Q66** (no supersede affordance on `LabResult`) — unchanged, and now has a concrete consumer:
  the confirm outcome panel tells the operator when a re-upload carries a *changed* value, which
  `skip` discards. `keep_both` remains the only resolution.

### Single clearest next action

**Resume the lab backfill.** The ingest path is fixed, verified on both deployed services, and now
reports what it wrote. If a re-upload collides, the outcome panel names the marker and shows
stored-vs-incoming, so a corrected result is distinguishable from a repeat.

Then, unrelated and unchanged: **4b-ii's sole remaining hold is `axis_verdict`** — the
source-factor rule for the `factors` list → scalar `protocol_phase`, plus the evaluability-keyed
authoring table. See `ROADMAP.md` → Interpretation layer build sequence.
