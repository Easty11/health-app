# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-08-01 (fourth session that day; the prior close-out is `d1193c2`).
Branch at close: `master` (clean). Session-open ref: `9ee9cc3`.

## 1. Real commits this session

Five commits, all on master and pushed. `git log --oneline 9ee9cc3..HEAD`:

```
bf4b5f8 governance(open-questions): Q70 — censored deltas assert a comparison never performed
cf501a8 feat(interpretation): GET /interpretation endpoint
2894e03 fix(interpretation): correct the view against the regenerated fixture
b19f5fb feat(interpretation): generate the frontend fixture instead of hand-maintaining it
093c8a1 feat(interpretation): axis_verdict emits the invariant per-group frame
```

`git log --format="%ad %s" --date=short -10`:

```
2026-08-01 governance(open-questions): Q70 — censored deltas assert a comparison never performed
2026-08-01 feat(interpretation): GET /interpretation endpoint
2026-08-01 fix(interpretation): correct the view against the regenerated fixture
2026-08-01 feat(interpretation): generate the frontend fixture instead of hand-maintaining it
2026-08-01 feat(interpretation): axis_verdict emits the invariant per-group frame
2026-08-01 governance(branches): row for governance/q-temporal-bound (DONE, Q69)
2026-08-01 governance: resolve Q-NEXT -> Q69 (on-branch, pre-ff)
2026-08-01 governance(open-questions): Q-NEXT — marker_series has no temporal bound
2026-08-01 chore: session close-out
2026-08-01 governance: #158 — declined uploads leave the results list; SCHEMA.md drift recorded
```

Suite **539 passed**, from a **527** baseline — reconciled against the brief. +6 axis-frame,
+6 endpoint.

**Branch gate.** `feat/1b-delivery` — merged + deleted, local and remote; `git cherry
origin/master` returned empty. `git branch` shows `master` only. Row in `BRANCHES.md` (**PARTIAL —
stopped at Step 4**, `bf4b5f8`). No branch in limbo.

## 2. Pending-queue reconciliation

The brief carried **one conditional** `PENDING` item: a DECISIONS entry for `axis_verdict.text`,
gated on *"VERIFY 1.2 finds the interim content unestablished."*

| Item | Disposition |
|------|-------------|
| DECISIONS `### #NEXT` — `axis_verdict.text` renders an invariant per-group frame | **NOT MINTED — the condition failed.** `#154` already establishes it: *"`axis_verdict` emits the invariant per-group floor sentence in the interim, which satisfies `#151`'s producer-complete requirement against the reduced contract and unblocks 1b delivery immediately."* Authoring three strings is implementation of a decided position. A duplicate entry was correctly avoided. |
| Q70 — not in the brief's queue | **Landed** as **Q70** in `bf4b5f8`. |

No DECISIONS integer claimed this session; max stays **#158**. `Q-NEXT` resolved to **Q70**
(master max was Q69). Nothing decided is uncommitted.

## 3. Cold-resume handoff

### Step 0 — the producer over real series, first run ever

Precondition met: `#156`'s script returned **exit 0** ("no marker appears more than once at any
collection date"). Inventory: 6 collection dates, 66 markers, **39 of 66** current values from a
draw other than the newest, 56 of 66 carry a prior.

| group | should_surface | members' current draw |
|---|---|---|
| `hpg_axis` | **False** | all 2026-05-30 |
| `hepatocellular` | True | **all 2026-03-06** — 85 days before the trigger |
| `erythroid` | True | all 2026-05-30 |

Ungrouped: **51 rows**. `is_news` true for 15 of 66.

**The single most important finding: all three out-of-range markers are stale.** `ast` 47 H,
`alt` 53 H, `bilirubin_total` 28 H — every one from `2026-03-06`, against a header naming
`2026-05-30`. The most alarming content of the interpretation does not come from the panel it
claims to read. This is Q69 made concrete and is why Step 3's date display was worth doing.

**Gate 3 fires on nothing.** No marker sits in any authored band; `haematocrit` returns
`status: not_in_band, contested: true`. Live but inert, as `#139` predicted.

**Two brief/Q69 illustrations were falsified.** The `oestradiol` example does not work: its delta
is **censored** (prior `<50`), so no percentage is computed at all — the "same bare percentage
across 40 vs 154 days" claim does not hold for that pair. The true cross-interval statement is
40 d (`hpg_axis`) vs 69 d (`hepatocellular`) vs 85 d (`erythroid`), all judged by bare percentages.

**`is_derived` is false on all 168 rows** — including `anion_gap`, `non_hdl`, `egfr`,
`testosterone_free_calculated`. The field exists, is emitted, and has never been set at ingest.
Not actioned.

**Judgement: nothing halted the build.** Every gate behaves as written and as decided; the
findings are known questions (Q69), designed consequences (censoring), or presentation gaps
Steps 1/3 address. The one genuine output defect found is recorded as **Q70** rather than fixed in
passing.

### Q65 pointer — neither of the brief's two options

The brief expected "pointer stale" or "`#154` closed something it did not cover". It is a third
thing: **Q65 carries two contradictory status lines** — header `**State:** open`, footer
`**Status:** DONE → #154` — and `#154` itself ends "Resolves Q65." That violates one-status-per-item.
Reported, not actioned, per the brief.

### Step 3 — both lists

The brief's four are all real. The derivation found three more:

| # | correction | on the brief's list? |
|---|---|---|
| 1 | `sections.js` recomputed moved-ness, dropping gate 3 → consumes `should_surface` | yes |
| 2 | no Ungrouped section (would drop 51/66 live) | yes |
| 3 | `protocol_context_snapshot.map()` — it is an object, this threw | yes |
| 4 | `axis_verdict.verdict` / `.confidence` removed (#152) | yes |
| 5 | `range_gate.note` — no such field; dead block | **no** |
| 6 | `rel.partner` — superseded by `operands_missing`; dropped the naming of what a degraded relation could not see | **no** |
| 7 | `safety_gate` rendered nowhere — left alone, gate 3 fires on nothing; recorded not skipped | **no** |

### Step 2 re-scoped, per the brief's own VERIFY

The fixture was **hand-transcribed**, not generated (`DECISIONS_LOG:2249`), so regenerating it by
hand would rebuild the fragility. It is now a build artefact —
`backend/scripts/gen_interpretation_fixture.py`. `backend/tests/fixtures/interpretation_s2.json`
is deliberately untouched: it is the conformance **oracle**, and generating it from the producer it
tests would make the test self-referential. Seed is synthetic, not the live series — the fixture is
committed to git and the live data is one person's lab results.

98 → 134 key paths. All 14 removals accounted for in the commit message.

### Deploy state — verified per `#121` on BOTH services

| Service | Probe | Result |
|---|---|---|
| `health-app-backend` | in-container: live route table + `get_interpretation` over the real DB | `/interpretation` registered; all three `axis_verdict.text` frames populated; 5 grouped members flagged as not from the trigger draw |
| `health-app-frontend` | served-bundle grep of `assets/index-Bo8gNYRx.js` | 3 new literals present; `axis_verdict.verdict`, `.confidence`, `range_gate.note`, `rel.partner` all **absent** |

**A `#116` timing trap fired and was caught.** The first frontend probe fetched a **cached
`index.html`** and returned the previous session's asset hash — all new literals absent, removed
literals present. The negative control is what exposed it; a cache-busted re-fetch gave the current
bundle and passed. Reported because the naive read was "the deploy did not take".

### Step 5 — STOPPED on Q69, and the wording that stopped it

> **State:** open. **Blocks:** wiring the interpretation view to live data (1b).
>
> **Resolve before:** the interpretation view is wired to live data. A temporally incoherent
> reading with a UI on top is harder to see than one in a JSON dump, and 1b's Step 0 exists to
> prevent exactly that.

**Q69 does not admit the brief's reading.** The brief argued Step 3's date display discharges the
*reason* for the gate. But the operative words are "Blocks" and "Resolve before", and candidate
(c) — surface the age — is by Q69's own text *"the mitigation that holds whichever of (a), (b) or
(d) is chosen"*. Implementing one candidate that explicitly composes with the others does not
decide which input rule governs. Q69's State is still `open`.

`#150` was checked and does **not** forbid interim links — rule 2 plans for hub absorption, and its
rationale anticipates the interpretation view adding one. Q69 is the sole blocker.

The link was also not added alone: the view still renders the fixture, so linking it would present
synthetic example data to the operator as their interpretation.

### Single clearest next action

**Resolve Q69 by choosing between (a) recency-bounded operands, (b) draw-scoped interpretation and
(d) hybrid.** (c) is already built. That unblocks the last 1b commit, which is small: point
`InterpretationView` at `GET /interpretation` and add the dashboard link.

Then: **Q70** (censored deltas assert a comparison never performed) before any basis token is shown
to a reader or used to generate prose.
