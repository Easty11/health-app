# Code session close-out — Lab batch ingestion adjudicated (#280), 2026-09-10

## 1. Real commits this session

Session-open ref: `39ddbcb` (`HEAD == origin/master` at open — the branch was cut from master
with no prior commits). Branch `claude/lab-ingestion-handoff-rqxrp1`. Two authored commits:

```
7207192 gov(labs): DECISIONS_LOG #280 lab-batch ingestion adjudication (D1-D6); OPEN_QUESTIONS Q142 imaging/DEXA target; CLAUDE Recent-landings
<closeout> chore: session close-out — lab batch adjudication (#280)
```

**Governance-only — no code, no migration, no prod write, no lab data committed.** The batch's
extraction JSON was NOT written to the repo (kill-rule: lab data lives in the prod DB and project
knowledge, never in git).

## 2. Pending-queue reconciliation

**No `;cc` pending-commit queue carried in.** The session ran from a written handoff
(`INGESTION_HANDOFF.md` + two extraction JSONs, attached as session inputs). Nothing is
provisional: the two operator calls (three binds, imaging defer) were ratified in-session and are
recorded in `DECISIONS_LOG` #280; both are then landed under one PR.

## 3. Cold-resume handoff

**What landed — an adjudication, not an ingestion (#280).** The 24-report / 97-result SNP batch
(2026-08-04 GP TRT panel + 2026-09-02 endocrinology pituitary/renal work-up) was reconciled against
master and the operator's two decisions recorded. It was **not stored**, by design.

- **Table binding (reconciled).** Write target is `lab_reports` (1/report) + `lab_results` (N).
  `collected_date` is a **DATE**, so the handoff's "anchor on the collected datetime" cannot hold at
  time granularity (both 09-02 events store `2026-09-02`). `POST /labs/confirm` resolves
  raw→canonical **from the live `marker_canonical_entries` map by `marker_name_raw`, ignoring the
  extractor's proposed `marker_canonical`** — the proposed keys are advisory only.
- **Two 09-02 events stay separate by construction** — `544974970` (Rangaswamaiah, endocrine, 9
  envelopes) and `544975535` (Wolanski, PSA + Urine MCS, 2 envelopes) are distinct `lab_report`
  rows with disjoint marker sets; the `(user, marker, collected_date)` guard never false-trips
  across them. No special handling needed.
- **The handoff's "first-seen" list was wrong and was NOT used as-is** — `cystatin_c` is already
  seeded; it OMITS `CK`, `Bilirubin conjugated`, `Free PSA`; and every proposed key that collides
  with a seeded analyte is wrong (`hdl`/`ldl`/`total_testosterone`/`psa_total`/… vs seed
  `hdl_cholesterol`/`ldl_cholesterol`/`testosterone_total`/`psa`/…). The **live `/labs/canonical-map`
  is authoritative** (seed is only the migration floor, #220); the confirmation screen's `unmapped[]`
  is the real bind trigger.
- **Three canonical binds RATIFIED (operator), to execute prod-side via `POST /labs/canonical/bind`:**

  | raw name | canonical | unit | note |
  |---|---|---|---|
  | `IGF-1 (Liaison)` | `igf1` | `nmol/L` | "(Liaison)" is an assay tag; a future non-Liaison IGF-1 raw name binds to the same `igf1` as its own row |
  | `Free PSA` | `psa_free` | `ug/L` | pairs with seeded `psa` (total) |
  | `% Free PSA` | `psa_free_percent` | `%` | derived ratio |

  Remaining unmapped-vs-seed markers **NOT decided** (bind later; they store unmapped, retain-raw
  #58/#155): `ACTH`, `Cortisol am`, `Free T4`, `CK`, `Bilirubin conjugated`, and the 8 urine M/C/S
  markers (`pH`, `Protein`, `Glucose`, `Specific Gravity`, `Leucocytes`, `Erythrocytes`,
  `Squam Epi Cells`, `Culture`).
- **Imaging/DEXA deferred → Q142.** No landed home (`health_events` narrative parent deferred
  #43/#52); forcing DEXA numerics into `lab_results` refused.

**#280 operator prod-side ingestion — DISCHARGED & VERIFIED (#282).** The batch is ingested: all
24 reports (2026-08-04 + 2026-09-02) confirmed in prod, the three binds (`igf1`, `psa_free`,
`psa_free_percent`) live, marker series continuous (late-bind backfill confirmed). Verified this
session via `get_lab_results` (2026-09-12), reconciling the operator's 2026-09-11/12 check. No
remaining prod-side OWED on #280. Imaging/DEXA still deferred (Q142).

**NOT touched this session — the feature lanes stood still.** This was an ingestion/governance turn;
no v1-test surface moved. Per the v1 steer (#275), the standing NOW lanes are unchanged:

- **Weekly resolver consumer — test 2 (Know)** (surfacing seq 1, Oct 5 anchor): resolver BUILT
  (#276); enforcement-against-the-plan surfacing beyond panel position is still UNSTARTED. Strongest
  next feature pick.
- **Appointment brief v1 — test 3 (Walk in)** (surfacing seq 3): UNSTARTED. It reads the `/series/lab*`
  surface (#279) and the interpretation layer — this lab batch, now ingested (#282), is the
  first real multi-panel corpus that brief would synthesise. Substrate complete (#220/#194/#268).
- **Surface-debt sweep — test 4 (Loop)** (seq 4): UNSTARTED.
- **Visuals lane (See)**: v1 core MET at increment 3 (#278); remaining work is NEXT, not NOW.

**Open OWED carried from prior sessions (unchanged this session):**
- **#273 test-lane binding** — `frontend tests (vitest)` + `backend tests (pytest)` are NOT required
  on ruleset `20414758` (FEEDBACK §38); only `placeholder guard (POSIX)` gates the merge. Operator
  adds both context strings verbatim GitHub-side. Until then "green" for self-merge is guard-only.
- **`claude/ci-binding-probe`** leftover remote branch — prior 403 on delete; operator-delete.
- **Q140** (naive `date.today()` AEST skew, two live sites), **Q139** (interpretation increment 3
  frontend tap surface), **Q141** (`model_forecast` semantics) — OPEN, untouched.
- **Q142** (imaging/DEXA target) — NEW, OPEN, operator/chat-owned.

**Session maxima:** decisions **#280** · questions **Q142**.
