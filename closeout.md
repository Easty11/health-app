# Code session close-out — Region→exercise consumer (#290), 2026-09-13

## 1. Real commits this session

Session-open ref: `0b383cd` (`HEAD == origin/master` at open — branch `claude/lucid-gauss-5jatl6`
cut from master, no prior commits). Two authored feature/gov commits, merged via **PR #203**
(merge commit `434bc06`, `--merge`, branch remote-deleted on merge):

```
38be999 feat(engine): region→exercise consumer — loose mode-router
bd63bac gov(engine): DECISIONS #290 region→exercise consumer; Q148 deferred lifecycle/§G
<closeout> chore: session close-out — region→exercise consumer (#290)
```

Concern-split held: feature (`backend/engine/region_exercise.py` · `backend/routers/engine.py`
wiring · `backend/tests/test_region_exercise_consumer.py`) and governance (`DECISIONS_LOG` #290 ·
`OPEN_QUESTIONS` Q148 · `BRANCHES` row · `CLAUDE.md` Recent-landings) never shared a commit.
No migration — the consumer reads existing tables (`exercise_region_tags`,
`hevy_exercise_templates`, `hevy_sets`); SCHEMA.md unmoved. Self-merged on green under
§ Merge disposition (chat-ratified brief, no un-ratified judgment embedded).

`#NEXT` → **#290** resolved against master max **#289** (Q max **Q147** → **Q148**); master did
not advance between resolve and merge (base stayed `0b383cd`), so no re-resolve. Placeholder guard
(POSIX), backend pytest, and frontend vitest all green on head `bd63bac`.

## 2. Pending-queue reconciliation

**No `;cc` pending-commit queue carried in.** The session ran entirely from an in-session Code
brief (the tagged-exercise-pool arc: survey → screen-vs-train read → REV-2 build brief). Nothing
is provisional: the brief's design calls were ratified by the operator in-session — the routing
axis (tags-and-measure, after Code disproved the brief's "§E is queue_eligible=False" premise
against the tree), tiered tag usability, §G honest stub, and loose-not-lifecycle — all recorded in
`DECISIONS_LOG` #290 and landed under PR #203.

## 3. Cold-resume handoff

### What landed this session
- **#290 — region→exercise consumer (loose mode-router).** The prescribe-direction the engine
  never had: `select_next` names a region×capacity×side, this consumer resolves it to a concrete
  exercise (TRAIN) or a screen (SCREEN), pure-downstream. Routing axis = **tags-and-measure**
  (has `exercise_region_tags` → train, laterality-filtered, rotation/recency; measure but no tags
  → screen via the Measure layer [§E hop/decel/COD]; neither → honest "no instrument yet" stub
  [§G]; non-region fortify target → honest). Tiered tags: `human_confirmed` trusted, `llm_proposed`
  usable-but-provisional **with the flag surfaced in the reason**, none → fallback. Wired into
  `GET /engine/next` (adds an `exercise` key; `select_next`/`compute_probe_queue` untouched).

### Open questions from this session
- **Q148 (OPEN — DEFERRED, logged not built):** (a) tight screen→train lifecycle + progression-tier
  selection; (b) declaring §G measures on the taxonomy so §G screens via the Measure layer instead
  of the honest stub (additive, no migration, gated on domain grounding); (c) proactive §G surfacing
  via a `compute_probe_queue` change (today §G reaches the consumer only as a fortify target).

### Owed (non-blocking)
- **VERIFY-live — prod `exercise_region_tags` counts by `source`** (`human_confirmed`/adjudicated vs
  `llm_proposed`). Unreachable from this session (no railway CLI, no SQL MCP). It tells us whether
  train-mode launches mostly-trusted or entirely-provisional; the consumer handles both by design,
  so it is reporting, not a gate. Operator's `railway connect` route. Draft query:
  `SELECT source, COUNT(*) FROM exercise_region_tags GROUP BY source;`
  and `SELECT COUNT(*) FROM hevy_exercise_templates WHERE adjudicated_at IS NOT NULL;`
  If both are still all-`llm_proposed`/zero-adjudicated, every train result ships provisional-flagged
  (correct behaviour) until a `--confirm` seed runs (`backend/seed_exercise_region_tags.py --confirm`).

### Current sprint — v1 NOW (from ROADMAP `## Surfacing phase`)
1. **Weekly resolver** — v1 test 2 **(Know)**, Oct 5 anchor. *The named next surfacing-phase item.*
2. **Visuals** — v1 test 1 **(See): MET** (#277/#278, load+readiness+e1RM+phase on `/metrics`).
3. **Appointment brief v1** — v1 test 3 **(Walk in)**, sequence position 3. NOT STARTED, substrate
   complete; design brief owed.
4. **Surface-debt sweep** — v1 test 4 **(Loop)**.

### v1-triage — which v1 test did this session serve?
**None directly.** #290 is Decision-Support **engine** infrastructure (the tagged-exercise-pool arc):
it makes `select_next`'s prescription resolve to a concrete exercise instead of the model improvising
one. It touches the **Loop** test tangentially (recommendation quality) but is **not on the named
surfacing-phase sequence** (weekly resolver → visuals → appointment brief → surface-debt). It rode the
tagged-pool arc's own momentum, not the v1 path. Surfaced per the standing v1-triage prompt: this is a
capability-depth lane, legitimate but off the demonstrable-v1 critical path.

### NOT touched this session (named, per the handoff discipline)
- **The three live v1 surfacing lanes stood still:** the **weekly resolver** (Know, Oct 5 — the #1
  sequenced item and the nearest dated deliverable), the **appointment brief v1** (Walk in, seq 3,
  design brief still owed), and the **surface-debt sweep** (Loop). None moved this session.
- **Direction note (per the "instrument vs the thing" caution):** this session went to the engine's
  internal capability, not to a v1 surfacing lane. The tagged-exercise-pool arc (survey → read → build)
  has now consumed one full build session; its next steps (confirm tags / declare §G measures / tight
  lifecycle) are all off the v1 path. The nearest dated v1 obligation is the **weekly resolver (Oct 5)**,
  which has not been started.

### Single clearest next action
**Start the weekly resolver** (v1 test 2, Know; Oct 5 anchor) — the #1 sequenced surfacing-phase item
and the nearest dated v1 deliverable. It consumes `weekly_template` (#221) via the phase-scoped resolver
input (#270); the #290 consumer just built is a natural downstream (resolve each due slot → a concrete
exercise), so the two compose, but the resolver is the v1-critical piece and is not yet begun.

_(Off-v1-path but ready when wanted: run VERIFY-live + a `--confirm` seed so #290's train mode leaves the
provisional tier.)_
