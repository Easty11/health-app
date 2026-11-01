# 0002 — Plan-log reconciliation
**State:** discussion
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#538. Folded questions: Q24, Q197. The triage placed this as architecture-scale, discussion (the `hevy_workouts.raw ? 'routine_id'` check runs first).

#363 rules that a quota slot is satisfied by doing the PLANNED session. That leaves the judgment of a session that
does not match its plan: moved, substituted, added to, cut short. This question is that judgment. **Everything below
is a chat proposal, not ruled.** The thresholds are placeholders.

**Dependency.** Plan↔log reconciliation, the unbuilt consumer named in Q24 (`laterality` and any `capability_state.side`
join wait on it too). This is the same component. Q27's region tags feed the substitution test.

## Proposal

Copied from the Q197 entry; it is a chat proposal, not ruled, and its thresholds are placeholders.

**Proposal (2026-10-01).**
- **Match by identity, within the week, not by date.** A logged workout is matched to a planned session by routine
  and exercise overlap. A session done on another day is recorded as MOVED, not as a deviation.
- **Per planned exercise, one of four outcomes:**
  - *done*: logged as planned.
  - *substituted*: a different exercise with the same PRIMARY region (region tags carry this; see Q27).
  - *added*: in-brief if its region is in the session's planned region set. Out-of-brief neither counts nor
    penalises.
  - *dropped*.
- **Drops: auto-credit first.** If a same-window activity covers the dropped regions, the drop is credited. This
  needs a coarse activity-type → region map for non-Hevy activities (Pilates → trunk/core, for example). Worked case:
  the Monday session moves to Tuesday; core is dropped because a fixed Pilates appointment followed. Covered, counted.
- **Bands.** Region-matched share of planned working sets ≥ ~80% with no restriction hit → auto-tick. < ~50% → not
  done. Between → the operator gets a one-tap confirm with a REASON CODE: covered elsewhere / time / pain / fatigue /
  equipment.
- **Pain reason = the per-session pain capture point** (moved from Q27). A "pain" reason routes to the restriction
  record `{target, qualifier, side, reason, source, review_date}`, including the pain-gated progression qualifier.
  The restrictions in force at the move are recorded in Q27 (lumbar, L knee squat depth, L thumb) as evidence.
- **Repeat drops flag the plan.** A drop reason repeating across weeks on sessions done ON their planned day flags
  the plan for revision. Drops in MOVED sessions do not.
- **No LLM in the verdict.** It is deterministic. An LLM may write the one-line explanation shown on the confirm.

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q197 | Does the Hevy workout payload carry the source routine id? (the check that runs first) | none yet | The verification query in the Q197 entry (appendix): `has_key` against `non_empty` on `hevy_workouts.raw` | unclassified | open (owed before the design relies on it) |
| Q197 | Plan-conformance adjudication: how deviations from a planned session are judged | See Proposal above (not ruled) | none recorded | unclassified | open |
| Q24 | Should a `capability_state.side` join exist? (`capability_state.side`) | none yet | none recorded | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q24 — Should a `capability_state.side` join exist?</summary>

````
## Q24. Should a `capability_state.side` join exist?

**Re-scoped 2026-10-26 (operator-ruled, `DECISIONS_LOG` #459).** Discharged: (a) is answered yes — #239 D-E session-pairing consumes `laterality`, and #302 narrows that to provenance-only. **Now asks only:** (b) should a `capability_state.side` join exist, given that #427/#428 built per-side strength on `exercise_region_tags.side` deliberately without capability rows.
Original title: "Does anything besides reconciliation consume `laterality`? Is there a `capability_state.side` join that should exist?"

_The entry below is kept as minted, for provenance; where it differs from the paragraph above, the paragraph above governs._

`capability_state` already carries a `side` column (left / right / bilateral). `hevy_exercise_templates.laterality`
now records whether a movement is unilateral. A unilateral logged exercise plausibly should feed a per-side
`capability_state` row, but no such join exists today. `laterality` is currently written and consumed only
by (future) plan↔log reconciliation.

**State:** OPEN — blocker: the plan↔log reconciliation is not built, and it is `laterality`'s ONLY
consumer, so whether a `capability_state.side` join *should* exist cannot be settled until that consumer
exists. Owner: Luke. Unblocks on: reconciliation being designed/built.
````

</details>

<details><summary>Q197 — Plan-conformance adjudication: how deviations from a planned session are judged</summary>

````
## Q197. Plan-conformance adjudication: how deviations from a planned session are judged

#363 rules that a quota slot is satisfied by doing the PLANNED session. That leaves the judgment of a session that
does not match its plan: moved, substituted, added to, cut short. This question is that judgment. **Everything below
is a chat proposal, not ruled.** The thresholds are placeholders.

**Proposal (2026-10-01).**
- **Match by identity, within the week, not by date.** A logged workout is matched to a planned session by routine
  and exercise overlap. A session done on another day is recorded as MOVED, not as a deviation.
- **Per planned exercise, one of four outcomes:**
  - *done*: logged as planned.
  - *substituted*: a different exercise with the same PRIMARY region (region tags carry this; see Q27).
  - *added*: in-brief if its region is in the session's planned region set. Out-of-brief neither counts nor
    penalises.
  - *dropped*.
- **Drops: auto-credit first.** If a same-window activity covers the dropped regions, the drop is credited. This
  needs a coarse activity-type → region map for non-Hevy activities (Pilates → trunk/core, for example). Worked case:
  the Monday session moves to Tuesday; core is dropped because a fixed Pilates appointment followed. Covered, counted.
- **Bands.** Region-matched share of planned working sets ≥ ~80% with no restriction hit → auto-tick. < ~50% → not
  done. Between → the operator gets a one-tap confirm with a REASON CODE: covered elsewhere / time / pain / fatigue /
  equipment.
- **Pain reason = the per-session pain capture point** (moved from Q27). A "pain" reason routes to the restriction
  record `{target, qualifier, side, reason, source, review_date}`, including the pain-gated progression qualifier.
  The restrictions in force at the move are recorded in Q27 (lumbar, L knee squat depth, L thumb) as evidence.
- **Repeat drops flag the plan.** A drop reason repeating across weeks on sessions done ON their planned day flags
  the plan for revision. Drops in MOVED sessions do not.
- **No LLM in the verdict.** It is deterministic. An LLM may write the one-line explanation shown on the confirm.

**Hypothesis to verify before the design relies on it.** Does the Hevy workout payload carry the source routine id?
If not, matching falls back to date window + exercise overlap. Findings (2026-10-01, this session):
- *Certain:* nothing in this repo reads a workout-side routine id. `routine_id` appears only on the routine
  read/update paths (`connectors/hevy.py`, `routers/chat.py`, `mcp_server.py`, `context_builder.py`), which take a
  routine id as INPUT.
- *Certain:* the untouched workout payload is already stored. `hevy_workouts.raw` is JSONB and `hevy_workouts.py`
  writes `row.raw = w`. If Hevy sends the field, it is in prod storage now and needs no re-fetch.
- *Not verified:* whether Hevy sends it. The public API docs (`api.hevyapp.com`) are blocked by this container's
  egress policy. From memory the public Workout object includes `routine_id` (*Guessing*, not evidence). This is an
  instruction to verify, not a fact.
- **Verification query (operator, via `railway connect` to `health-app-DB`):**

      SELECT count(*) AS n,
             count(*) FILTER (WHERE raw ? 'routine_id') AS has_key,
             count(*) FILTER (WHERE coalesce(raw->>'routine_id','') <> '') AS non_empty
      FROM hevy_workouts WHERE user_id = 1;

  Read `has_key` against `non_empty`: a key that is present but always null means Hevy sends the field and only
  workouts started FROM a routine fill it. That is still usable for matching, but it cannot cover workouts started empty.

**Dependency.** Plan↔log reconciliation, the unbuilt consumer named in Q24 (`laterality` and any `capability_state.side`
join wait on it too). This is the same component. Q27's region tags feed the substitution test.

**Note (21 Oct 2026): a narrower matching rule was proposed for the week strip, and not taken.** The week planner
report offered a rule short of this question's adjudication: a scheduled box shows done when a done session with the
same `kind:key` lands on a day the box covers, each session consumed once, a moved session staying a plain chip.
The operator declined it. R6 (#390) stands and matching stays here. The failure modes, for whoever designs the
real match:
- *`kind:key` is coarser than the item.* For `load_window:metabolic` the key names the whole conditioning window, not
  one item. On a day with a single metabolic item placed (Monday and Saturday carry `running` alone) any ride would
  tick `running`: a tidy display that names an item the session was not.
- *The tie-break fails on a multi-item day.* Wednesday 21 Oct carries `running` (3 a week) and `echo` (1 a week), both
  metabolic. "No tick when ambiguous" ticks neither, so that day's Echo session would show nothing at all. A
  time-proximity tie-break (echo 16:30-17:00, running 18:00-18:30) was also offered; it was not run against the
  session's start time, and `days[].actual` carries no start time today.
- *The trade.* Keeping R6 costs a second chip beside the box. The narrow rule would cost a tick that is sometimes
  wrong. If the clutter matters, the lever is this question's priority.

**State:** OPEN — chat proposal, not ruled; the Hevy routine-id check is owed before design relies on it. Owner: Luke.
````

</details>
