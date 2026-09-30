# Close-out — Session fidelity into chat and the session views (#354–#357); landed via PR #289

## Real commits this session

The session is `session-fidelity` (Brief A + C.1), on branch `claude/nifty-hopper-s8m3kc`, a name the harness
assigned and pinned (CLAUDE.md bans `claude/<hash>` names for in-flight work; the harness pin won here, as it did
for #287/#288, and the branch is rowed in `BRANCHES.md`). It was cut from master `6d8f098`.
- Master's maxima at open were decisions **#353** and questions **Q193**, re-read at governance time (master had
  not advanced). That gives **#354–#357** and **Q194**.
- Local setup at open: `core.hooksPath` and `alias.land` were both unset (fresh clone) and were set. The clone was
  shallow; `git fetch --unshallow` was needed for `test_context_builder_output_unchanged_pre_post_refactor`.

`git log --format="%h %ad %s" --date=short 6d8f098..HEAD` (before the governance commit):

```
53ce6ff 2026-09-30 test(read-door): register the A6 dry-run script as a raw-set toucher (Brief A)
9021367 2026-09-30 feat(training): session review by reference; the session list shows one correct row per bout (Brief A A3/A5)
3633bbc 2026-09-30 feat(arbitration): richness-first - a row without HR never suppresses a same-bout row with HR (Brief A A6)
5957bf4 2026-09-30 test(read-door): register session_focus as a by-id lookup toucher (Brief A A1)
961107f 2026-09-30 feat(load): hevy_sync soft-fails like polar_sync — ingest steps soft-fail, compute steps hard-fail (Brief A C.1)
0f75211 2026-09-30 feat(chat): focus_session pins the session under review, rendered by the backend (Brief A A1/A2/A4)
```

The first governance commit, the two feature commits for the operator's rulings of 30 Sep, and the landing
commits (all after the close-out was first pushed):

```
(landing record) gov(session-fidelity): A6 dry run recorded (0 flips); landing; close-out refreshed
f2a4da8 2026-09-30 chore(gitignore): ignore *_token.json - OAuth token files are live credentials
44c9d37 2026-09-30 gov(session-fidelity): operator rulings on #354 - window [anchor-7, anchor+3] same day included; Q194 ruled (b), closed
85898ed 2026-09-30 feat(chat): the session focus persists for the conversation (Q194 ruled option b)
8d9c602 2026-09-30 feat(chat): context window is [anchor - 7, anchor + 3] local days, same day included (operator ruling on #354)
c75fe77 2026-09-30 gov(session-fidelity): #354-#357 session focus, canonical list, richness-first arbitration, ingest soft-fail; Q194; Q19 re-measure; FEEDBACK 55; close-out
```

Three `gov(session-fidelity)` commits in all (`c75fe77`, `44c9d37`, and the landing record). That is more than the
one-`gov`-per-session rule allows: the rulings and then the operator's dry-run result arrived after earlier gov
commits were pushed, so further commits were the alternative to rewriting pushed history. Named here as a
deviation, not folded in. The `.gitignore` entry is its own commit, not gov, as the operator asked.

- **Tests:** backend **2443 passed** (baseline 2403); frontend **329 passed** (baseline 302). CI was green on
  `c75fe77` and on `44c9d37` (all three required checks each time); the landing head's CI is reported in the PR.
- **Mutation checks (each proven to fail the suite, then restored):** focus window 7→5 days; the focus anchor on the
  UTC date; dropping the canonical filter from the window; deleting the tier from `_win_key` (6 tests);
  removing `hevy_sync` from `SOFT_STEPS` (4); frontend UTC-slice date (3), no canonical filter (5), context sent as
  session (2), UTC date on the aerobic card (1), HubLayout dropping the focus (3), ChatPanel dropping it (4).
  For the rulings: same-day-and-later aerobic dropped (2), Hevy window ending at the anchor (2), the anchor day's
  schedule skipped (2); typed turns not carrying the focus (4), focus not persisted (1), New chat keeping it (2),
  a new review not replacing it (5). One weak assertion was found by its mutation (a recurring "Tuesday" item also
  matched 22 Sep) and rewritten as a dated one-off.
- **Caught by the full suite, not the targeted runs:** the read-door drift guard failed twice (`session_focus.py`,
  then `scripts/arbitration_flip_report.py`); both are allow-listed with reasons (`5957bf4`, `53ce6ff`).
- **Deploy verification** (both Railway services and the served-bundle grep, #116/#121) happens after the merge and
  cannot ride the merged branch; its result is posted on PR #289 and reported to the operator.

## Pending-queue reconciliation

No `;cc` queue was carried in. The brief (one paste block, addressed to this session by name) and where each item
landed:

- **V1** (feedback wiring, `formatHevyMessage`, `fmtDate` as described): confirmed.
- **V2** (`ChatRequest` = `{message, conversation_history}`): confirmed.
- **V3** (`arbitrated_sessions` rows carry `canonical` and `session_date`; `_win_key` as described): confirmed.
- **V4** (`polar_sync` soft, `hevy_sync` hard): confirmed.
- **V5** (identify the "exercise card"): **ambiguous, halted and asked.** No component is named that. The operator
  ruled: the **WorkoutPanel list cards** (the Strength latest-Hevy card and the Aerobic latest-session card).
- **A1** → `0f75211` (`backend/session_focus.py`, `routers/chat.py`). **A2** → `0f75211` (`aerobic_format.py`,
  `context_builder.render_workout`; MCP output and `_section_hevy` proven byte-identical).
- **Operator rulings, 30 Sep (addressed to this session):** (1) window anchored on the session's local date: RATIFIED;
  (2) window amended to [anchor − 7, anchor + 3] local days, same day included, both lanes and scheduled items, only
  the focused session excluded → `8d9c602`; (3) Q194 → option (b), the focus persists for the conversation, close
  Q194 as RULED (b) → `85898ed`, Q194 moved below `## CLOSED` as `DONE → #354`. Tests added and mutation-checked:
  a same-day later session appears (both lanes); a follow-up turn carries the focus. #354's text updated.
- **A3** → `9021367`. **A4** → `0f75211` (test) + `9021367`: `session_analysis` does **not** reach chat context,
  so the `analyse-session` call was **left as-is** (the ruling's "if not").
- **A5 (a)–(d)** → `9021367`. **A6** → `3633bbc` (+ the dry-run script). **C.1** → `961107f`.
- **G1–G5** → met by tests (see #354–#357). **G7** → measured and recorded on Q19 (361 px × 819 px at 1280×779).
- **G6 (prod, operator)** → **OWED**, after deploy. It has a ROADMAP NOW row.
- **A6 dry-run flip list** → **DONE (operator, prod, 30 Sep):** 91 sessions arbitrated, **0 flips**. Recorded in #356
  as operator-reported (Code did not run it). 0 is expected: no `health_connect` row carries HR/zones yet, so the tier
  is a forward guard for Q159 stage 2 and zoneless v4 rows. Landing therefore changes no canonical row today.
- **`*_token.json` gitignore** (operator, 30 Sep) → `f2a4da8`, its own commit. Verified no `*_token.json` is tracked
  on master or the branch (`git ls-tree` / `git ls-files`: empty).
- **LOG:** FEEDBACK §55; DECISIONS #354–#357 (headings written as integers, not `#NEXT`, because the pre-push hook
  refuses `#NEXT`; re-resolve if master advances); Q194 opened; Q19 note (G7); BRANCHES row; ROADMAP NOW row;
  CLAUDE.md Recent landings.
- **GUARD:** held. No schema change or migration. Arbitration changed only by the A6 tier (overlap threshold,
  writer-class table, source ranks, transform untouched). No sport-exclusion change. `/health/analyse-session` and
  its entries untouched. Chat context outside the pinned blocks is unchanged (proven: `with_focus == without + block`).

**Divergences and calls (named at the gate, §44):**
- **Merge was held, then released.** The brief's own pre-merge dry-run requirement held it (the three build-time
  defaults that also held it were resolved by the operator on 30 Sep); the operator posted the dry run and cleared
  all holds. The PR was opened **ready-for-review, not draft** (CLAUDE.md wins over the harness default).
- **One reading of the ruling to confirm.** "For both completed sessions and scheduled items" was implemented
  literally: the scheduled list covers the whole window, including the 7 days before the anchor and the anchor day.
  A schedule item cannot be matched to the session that satisfied it, so the anchor day's list normally includes
  the focused session's own slot. It is one line per matching item per day. If only the forward half was meant,
  it is a one-line change (`_scheduled_window`'s start day).
- **A "New chat" control and a "Reviewing: …" chip were added** to `ChatPanel` as part of ruling (3): "until cleared/new"
  needs a way to clear, and the panel had none. Cost of the persisted focus: one DB read per turn while pinned.
- **The aerobic pin is one line** (the MCP renderer, plus a local start time). It carries no `cardio_load`,
  `muscle_load` or `recovery_hours`, because the shared renderer does not, on either surface. "Exactly as the
  backend renders it" was read literally.
- **A Hevy focus needs the workout in `hevy_workouts`.** One not yet synced reads as not-found. Not verified against prod.
- **The latest aerobic card now requests `limit=10`** and takes the first canonical row, not `limit=1`: the newest
  row can be a non-canonical twin.
- **`week_plan`'s day-coverage helpers became module-level** (`item_days`, `event_span`, `item_covers`) so the
  scheduled window and the planner share one definition. Behaviour of `plan_week` is unchanged (its suite passes untouched).
- **`test_hevy_hard_failure_skips_polar_like_every_later_step` was replaced**, not deleted: it pinned the behaviour
  C.1 supersedes (#357).

## Cold-resume handoff

**Current sprint.** Surfacing phase toward the four v1 tests (See MET; Know, Walk in, Loop open). This session added
the session-review path (chat sees the whole session, from any surface) and fixed the aerobic list.

**Single clearest next action (owner: Luke).** G6, after the deploy (below); nothing else is owed from this brief.
The A6 dry-run tool, for reference (it is what produced the 0-flip result):
`\copy (SELECT id, user_id, source, source_package, session_date, start_time, stop_time, sport_name, duration_minutes,
hr_avg, hr_max, z1_seconds, z2_seconds, z3_seconds, z4_seconds, z5_seconds FROM aerobic_sessions ORDER BY id) TO
'aerobic_sessions.csv' CSV HEADER` via `railway connect` to `health-app-DB`, then, in the backend venv,
`python -m scripts.arbitration_flip_report --csv aerobic_sessions.csv`. Re-run it when Q159 stage-2 rows land, since
that is when the tier can first change an outcome. G6: session feedback on the 29 Sep lower cites the hip thrust RPE
7.5/8/9 and the suitcase carries; the context review on it references the same-day pilates and what is scheduled
around it; a follow-up in the same chat still sees the session; the list shows one 28 Sep elliptical and the 26 Sep
Pilates dated 26 Sep.

**Open questions, by status** (from `OPEN_QUESTIONS.md`):
- **Closed this session:** Q194 → `DONE → #354` (ruled option b, 30 Sep).
- **OPEN, touched:** Q19 (desktop scroller; re-measured, not reproduced on `/training`, fork moot unless the panel
  returns to a half-height column).
- **OPEN, unchanged and relevant:** Q193 (Polar webhook; recommendation: don't build), Q10, Q22.
- **OWED (operator):** #353's G4 (record a Polar session, no Sync press); G6 for this brief; the #269 injury-sweep
  clearance; the appointment brief's owed items.

**What was NOT touched (named on purpose).**
- **Brief B.** The metabolic sport-exclusion ruling (supersedes #322) and the fate of `/health/analyse-session`
  were explicitly out of this brief and did not move. The analyse-session endpoint is now known to feed nothing the
  chat model reads (A4), which is input to that decision.
- **The appointment brief (v1 test 3, Walk in).** Its OWED operator items did not move, including the date-anchored
  one: the Thu **1 Oct** follow-up row and the served-bundle grep of `Leave with` / `Changes since`. Today is 30 Sep.
- **The lab upload pipeline and the interpretation layer** (`Lab upload pipeline`, `Interpretation layer build` NOW rows).
  No work; both are gated by their own design/consumer questions and by the 28 Sep ruling that labs are out of v1.
- **Injury clearance (#340 sweep, OWED operator)** and the **Polar new-session check (#353 G4, OWED operator)**:
  unchanged; both are prod actions only the operator can take.
- **Cross-repo shared-block propagation** to `health-connect-app` (two OWED rows): unchanged.
- **The companion app** (`health-connect-app`): untouched.
- **Instrument vs the thing instrumented.** This session was product work (fidelity, list correctness, ingest
  resilience), not governance tooling. The recent run before it (#345–#353) was mixed; no instrument-only drift to
  flag, but the arbitration dry-run tool is itself instrumentation for a change that is not yet live.

**v1-triage of NOW lanes** (which test each serves; a lane serving none is a demotion candidate):
- **Session fidelity (this brief)** — **Loop** (a review that sees the whole session) and **Know** (context scope
  judges against phase and load). Stays.
- **Aerobic ingest automated (#353 check)** — **See** and **Loop**. Stays (an operator check, cheap).
- **Injury clearance (#340 sweep)** — **Know** and **Walk in**. Stays.
- **Appointment brief** — **Walk in**. Stays; date-sensitive.
- **Lab upload pipeline** and **Interpretation layer build** — serve **no v1 test** under the 28 Sep reframe (labs
  out of v1). They are in NOW by lane momentum. **Demotion candidates: surfaced for the operator, not moved.**
- **Cross-repo propagation rows (OWED)** — serve no v1 test; they are shared-loop housekeeping pinned by #112.
  Stay, but they are not v1 work.
