# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md` · open forks: `OPEN_QUESTIONS.md` · roadmap: `ROADMAP.md`._

Session date: 2026-07-30.

## 1. Real commits this session

Session-open ref: `faf4ba9` (prior `chore: session close-out`). Six commits, all on
master and pushed (`origin/master` 0 ahead / 0 behind). `git log --oneline faf4ba9..HEAD`:

```
55b05e0 governance: mint #150 navigation model (hub-as-home, persistent chat) + Q63 (interp tile)
f8212f2 governance(open-questions): Q62 — how is #47 enforced structurally for a generated field?
5d1cab7 feat(interpretation): 4b-ii/1a — emit shared_levers + member_lever_effects (I7 pair)
5e6f2c2 feat(interpretation): 4b-ii/1a — emit member stable_rationale (asset projection)
e395eac governance(open-questions): Q61 — labs read-back #47-omission reasoning does not hold; re-examine
95355fa governance(roadmap): lift stale readiness suppression; readiness row -> Banister build (owed)
```

Immutable dated log (`git log --format="%ad %s" --date=short`):

```
2026-07-30 governance: mint #150 navigation model (hub-as-home, persistent chat) + Q63 (interp tile)
2026-07-30 governance(open-questions): Q62 — how is #47 enforced structurally for a generated field?
2026-07-30 feat(interpretation): 4b-ii/1a — emit shared_levers + member_lever_effects (I7 pair)
2026-07-30 feat(interpretation): 4b-ii/1a — emit member stable_rationale (asset projection)
2026-07-29 governance(open-questions): Q61 — labs read-back #47-omission reasoning does not hold; re-examine
2026-07-29 governance(roadmap): lift stale readiness suppression; readiness row -> Banister build (owed)
```

Files touched this session (`faf4ba9..HEAD`): `DECISIONS_LOG.md`, `OPEN_QUESTIONS.md`,
`ROADMAP.md`, `backend/interpretation/producer.py`,
`backend/tests/test_interpretation_producer_foundation.py` (+ this close-out and CLAUDE.md
Recent-landings).

### What each commit did

- **95355fa** — lifted the stale `Basic readiness score` ROADMAP suppression. The ≥7-day
  HRV precondition was **Code-verified against Railway Postgres**: `samsung_hrv_readings` =
  47 distinct `passive_overnight` days (2026-06-08 → 2026-07-29, all `hrv_ms` non-null), 32
  propagated to `daily_records.passive_hrv_ms`. Row now tracks the still-owed Banister build;
  the `context_builder.py:368-369` low-confidence caveat preserved.
- **e395eac** — Q61: `GET /labs/results` omits `computed_flag`/`confidence` under a `#47`
  bound that `#47`'s text does not support (computed_flag = value-vs-printed-range =
  education). Recorded for re-examination on its own merits (#49 seam / confidence-at-a-glance).
  No code change.
- **5e6f2c2** — 4b-ii/1a: producer emits member `stable_rationale` (asset projection of
  `lever_dictionary.marker_interpretation[m].stable_rationale`). G1 diff added-keys-only;
  suite 464→465.
- **5d1cab7** — 4b-ii/1a: producer emits group `shared_levers` (I1-cited via `_citable_lever`,
  `member_effects` present-filtered, already-in-play status via #145 `declared_factor_keys` +
  `is_assumable_present`) and member `member_lever_effects` (the I7 pair). G1 added-keys-only;
  gates.py/reference byte-identical to master; suite 465→467.
- **f8212f2** — Q62: how is `#47` enforced structurally for a generated field? Generated prose
  (`axis_verdict.text`) has only the prompt (behavioural half); every emitted field today is
  structurally bounded. Same shape as #59's lab-value structural absence and Q60. Candidates
  (a)–(d) recorded. Blocks `axis_verdict.text`. No code change.
- **55b05e0** — `#150` navigation model (hub-as-home, chat docked-not-routed, header links
  retire into hub, dashboard panels → Recovery/Training tiles; Constraints A/B/C) + `Q63`
  (what the interpretation tile shows). Decided (design), build-deferred behind 4b-ii.
  Verify-before-mint checklist run against master.

## 2. Pending-commit-queue reconciliation

No chat `;cc` pending-commit queue was carried into this session — work arrived as four
briefs (Part-A verify sweep + three riders; the 4b-ii/1a build brief; a CORRECTION
superseding it; the navigation-model PROPOSAL). All resulting decisions landed in commits;
nothing is provisional.

- 4b-ii/1a producer fields (3 of 5, deterministic) → **5e6f2c2, 5d1cab7** (landed).
- `axis_verdict` + `mechanism` (2 of 5, not deterministic) → **deliberately NOT built**;
  recorded as Q62 (**f8212f2**) + the ROADMAP 4b-ii row. `mechanism` reclassified a
  content-task (chat-side); `axis_verdict.verdict` derivability = an unrun read, deferred by
  the CORRECTION.
- Navigation model → `#150` + `Q63` (**55b05e0**, landed).
- Rider 2 (readiness suppression) → **95355fa**. Rider 3 (labs projection) → **e395eac / Q61**.
  The PROPOSAL's two "raise separately" items duplicated these; **not** re-minted (checklist
  said to drop the ROADMAP note if already rewritten — it was).

## 3. Cold-resume handoff

### State
- Branch: `master`, clean, synced with `origin/master` (0/0). No other local or remote
  branches — every feature/governance branch this session was ff-merged + remote-deleted.
  `BRANCHES.md` unchanged (nothing to row).
- Suite: **467 passed** (backend). Baseline this session was 464; +3 tests from 1a.
- DECISIONS max **#150**; OPEN_QUESTIONS max **Q63**.

### Sprint (ROADMAP NOW)
Two dated CBT-I items: Q45 nap day-attribution (contaminating capture now); the ~31 Jul
manual evaluation trigger (#118's PM-offer half). Interpretation-layer build is the large
lane; lab pipeline + appointment brief downstream. Cross-repo debt (shared-block propagation
to `health-connect-app`) OWED — needs an HCA-rooted session.

### Interpretation layer — where 4b-ii stands
1a landed (producer emits the three deterministic asset fields). Remaining is **not uniform**:
- **`mechanism`** — content task: author a `marker_interpretation.mechanism` slot, then a
  trivial deterministic projection. No LLM. No repo home yet (the slot doesn't exist).
- **`axis_verdict`** — `.text` is generated prose, blocked on **Q62** (structural-#47).
  `.verdict`-enum derivability from member gates / relation kinds is an **unrun read** (deferred).
- **demotion** — relation authority over gate 1's delta arm; needs a **seeded haematocrit
  band-crossing pair** to exercise I8 end-to-end (the #139 asset is populated but haematocrit
  is not in `seed_engine.py`).
- **1b (delivery)** — regenerate the fixture from the producer (fixes missing `ungrouped[]`
  and the `protocol_context_snapshot` shape by construction), then correct the view (consume
  `should_surface`, not the gate-1∨2 recompute; add the Ungrouped section; fix the
  `protocol_context_snapshot` reader), then the endpoint (draw-triggered #147), then wire
  fixture→live. The view currently hard-reads the held fields, so wiring cannot precede the
  field work.

### Open questions (by status)
- **OPEN, blocked by 4b-ii:** Q63 (interpretation-tile content — design, under #150
  Constraint A), Q60 (CBT-I user surface — gating fork is #47 verdict-as-directive).
- **OPEN, design/policy:** Q62 (structural #47 for generated fields — blocks `axis_verdict.text`),
  Q61 (labs projection `computed_flag`/`confidence` omission — re-examine on merits, not #47).
- **OPEN, infra:** Q59 (nothing verifies the deployable artifact — no CI, no boot check).
- Q45 (nap day-attribution) is the live sprint blocker on the CBT-I lane.

### Single clearest next action
**4b-ii still holds the build lane.** The next producer step is the smallest safe one: write
the **1b delivery brief** starting with fixture regeneration from the now-richer producer
(it fixes `ungrouped[]` absence and the `protocol_context_snapshot` shape by construction) —
or, to pick off the cheap content task first, author the `marker_interpretation.mechanism`
slot. `axis_verdict` stays parked until **Q62** resolves. The nav hub (#150) build stays
deferred behind 4b-ii.
