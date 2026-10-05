# Close-out — HRmax restatement path and the `adjusted` provenance are built and held for operator release (#385); user 1's value is ruled 175, superseding #384's 177; nothing is applied in prod

## Real commits this session

Session `hrmax-restatement`. Range: `98b8f8b` (master at open) to this close-out. Fresh-clone settings were unset at open and were set and verified (`core.hooksPath` = `.githooks`, local `alias.land`). Maxima at open: decisions 384, questions 216. Maxima now: decisions 385 (#385), questions 216 (unchanged).

- `b718c59` `feat(hrmax-restatement): restatement path and `adjusted` provenance for user_hrmax (#383, #384)` - migration `d6f8b1a3c5e7`, the rank rule in `hr_zones.hrmax_in_force`, `set_hrmax --restate`, both readers, tests, SCHEMA.md section 043, the provenance doc line.
- `874b1b5` `gov(hrmax-restatement): #385 user 1's HRmax is 175 (supersedes #384's 177); restatement path built and held for release` - DECISIONS #385, a Q199 note, the ROADMAP HC zones row, BRANCHES (this branch's row, and the previous row's SHA resolved to `98b8f8b`), the CLAUDE.md Recent-landings pointer.
- The `chore: session close-out` commit carrying this file: its hash is on the branch (a file cannot name its own commit).
- **One `gov(...)` commit**, as CLAUDE.md allows. The branch name `claude/amazing-mendel-spknid` is the harness's, kept per the harness instruction (recorded in BRANCHES).
- **Code and schema: yes. One migration, so the PR is HELD** (CLAUDE.md § Merge disposition). Opened ready-for-review, not merged; the operator's release decision is the only thing it waits on.
- **No prod write by Code, and no prod read.** A scratch Postgres 16 in the scratchpad (stopped at close) and a Python 3.12 virtualenv carried the verification.

## Pending-queue reconciliation

Nothing came from the chat `;cc` queue as a PENDING item. The brief's four items, one by one:

1. **Provenance `adjusted`: DONE on the branch (`b718c59`), held.** Requires `base_bpm` (different from the value, plausible) and `rationale`; the CHECK is `tested | observed | adjusted` (amends #364 R2); `estimated` stays banned. Verified on Postgres 16.
2. **Restatement path: DONE on the branch (`b718c59`), held.** (a) A restatement shares its target's `effective_from`: the plain unique key became a partial unique index over dated rows. (b) Explicit rank rule in `hrmax_in_force`: an entry any other entry restates is superseded; the greatest date wins among the rest; input order is irrelevant; an unranked same-date tie now raises. (c) The prior row is never touched; the new row links to it (`restates_id`) with a required `rationale`. (d) `set_hrmax --restate`, dry-run supported, append-only kept. **Tests asked for:** same-date restatement wins (both input orders, and through `enrich_user` with the DB returning the seed first); a dated change still applies forward only (resolver and through `enrich_user`); chained restatements resolve to the latest (resolver, script, `enrich_user`).
   - **A divergence from my own first design, reported.** I built a composite foreign key `(restates_id, user_id, effective_from)` so that same user and same date were database rules. The full suite failed 22 tests in `test_retire_user.py`: `scripts/retire_user.py` refuses composite keys (`GraphError`), so the user-deletion tool would have refused to run in prod. I replaced it with a plain self-FK. **Same user and same date are therefore NOT database rules**; the script holds them by construction and the resolver raises on a chain that breaks either (the chain step then fails loudly, zones unchanged). A test pins the trade-off so no one assumes the database covers it. Recorded in #385 (d).
3. **Hold the PR for release; give the commands: DONE (PR held; commands below, rehearsed).** The exact strings in the ROADMAP row were run through a real shell against a scratch SQLite database seeded with the real seed row shape: the dry run says `restates row #1: 173 bpm (observed) effective 2026-03-01` and lists each HC row 173 -> 175 and writes nothing; the apply writes the linked row and leaves the seed untouched; a second paste is refused (`already 175`). `refresh_load` was not rehearsed (it syncs over the network); its zone fill is covered by the `enrich_user` tests.
4. **Post-apply: re-run `arbitration_flip_report --hc-zones` and report the per-band divergence at 175: NOT DONE, cannot be.** It needs the prod database after release and the apply. It is OWED to the operator (command in the handoff). Baselines to compare against, from the record: at 173, HC minus Polar on 28 Sep, minutes z1..z5, +0.28/+0.11/-0.50/-0.38/+0.88; at 177, z5 -1.04, and the other bands at 177 were relayed to no store (Code never saw them). **Guessing:** if z5 moves linearly between the two, it lands near -0.08 at 175; the bands are not linear in HRmax, so this is a sanity bound, not a prediction.

**Un-ratified calls surfaced for release** (CLAUDE.md § Merge disposition; the PR is held anyway, so release is the ratification): #385 (a)-(f): `adjusted` and "restatement" are separate axes; a restatement carries its target's date strictly; a rationale is required for a restatement; the resolver raises on an unranked tie (a same-date `--hrmax` projection is now refused, it used to be ignored); the database does not enforce same user and same date; downgrade refuses over restatement or `adjusted` rows.

Provisional until merged: everything on this branch.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** The HC zones row now reads: landed, seeded, verified; HRmax 175 ruled (#385); restatement path built and held for release. No other row changed.

**State.** One PR, held: schema migration `d6f8b1a3c5e7` (revises `c5e7a9b1d3f2`). Railway runs `alembic upgrade head` at boot, so merging deploys it; the migration is additive for data (the seed row satisfies every new constraint; checked on Postgres 16 with that row present). Numbers resolved at master max #384 / Q216 (`98b8f8b`): **re-read master's max and re-resolve #385 if master advances before landing.** CI note: the Postgres tests in `test_user_hrmax_restatement_schema.py` skip in CI (no Postgres service); the migration-versus-model parity is as fresh as the last run with `HEALTH_APP_TEST_PG_URL` set (it was, this session).

**Single clearest next action.** The operator reads the PR and releases it or rules on the calls in #385. On release, a Code session lands it end to end (FEEDBACK section 1): re-read master's max, push, guard green, merge with a merge commit, delete the branch, confirm the Railway deploy reaches SUCCESS and the migration applied in the boot logs.

**Operator actions owed, after the landing** (container shell; PowerShell only for the first line; run one command at a time, read it, then act). First `railway ssh --service health-app-backend`, then:

    cd /app
    /opt/venv/bin/python -m scripts.set_hrmax --user 1 --effective-from 2026-03-01 --bpm 175 --provenance adjusted --restate --base-bpm 173 --rationale 'Bike-modality lower bound: every observation was on an Echo bike; Polar zones imply about 175 (operator ruling 2026-10-05)' --note 'Base: observed 173, Echo bike, Polar H10, Fitness sessions 2026-06-17 and 2026-07-17 (polar_v4 rows 35, 47)' --dry-run

It must print `restates row #1: 173 bpm (observed) effective 2026-03-01` and list every health_connect row of user 1 as `173 -> 175` (29 on 5 Oct, more if synced since). Anything else, stop. Then the same command without `--dry-run`, then:

    /opt/venv/bin/python -m scripts.refresh_load --user 1
    /opt/venv/bin/python -m scripts.arbitration_flip_report --hc-zones --user 1

and report the 28 Sep HC-versus-Polar minutes per band at 175 against the 173 and 177 baselines above. Also still owed from earlier: read Polar Flow's profile HRmax by hand and report it as context (#384); the Q159 in-activity HR read on or after 9 Oct; the items in the previous handoff that this session did not touch.

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212, carried from the last count; no question changed state). This session: Q199 gained a dated note and stays OPEN; no question opened.

**What was NOT touched (named so absence does not read as finished).**
- **The Polar boundary stays unmanaged by design (#385 item 3):** Polar rows keep Polar's own zones (Q198). The restatement moves HC rows only; the seam is measured after the apply, not corrected. **Polar Flow's profile HRmax is still unread.**
- **HR-reserve zoning (Q216), the bands, Polar's own zoning:** out of scope and unmoved. A reserve model would change what a restatement restates (#383).
- **A projected restatement in the flip report:** `--hrmax` still models only a dated change; to project one at a stored date, date it after (`--hrmax 1=177@2026-03-02`). Not built; not needed for the apply.
- **`retire_user` and composite foreign keys:** left as it is; the one place the same-user, same-date rules could become the database's if that tool ever learns them.
- **Single-row HC bout deposits (rows 79-83, 70, 86, 87, 94, 101):** not read; low priority (#384). **The seven pre-reach unzoned rows (72-78) and user 4's `no_hrmax`:** unmoved.
- **Q199's maximal-effort test, the "Resting HR" label (Q200), the Polar re-zoning (Q198):** unmoved. A `tested` value would now be a `--restate --provenance tested` row.
- **The shared phase-entry and ledger build (#378, #379), Q213, Q214, Q212; the sRPE floor, Source hierarchy (Q201, Q203), the marker exposure (#367, Q206), the sibling sync races (Q208), the Garmin self-evaluation read, #371's proof:** unmoved.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still. **Medical protocol:** CBT-I and the injury ledger did not move.
- **Known gaps carried:** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` and have not been checked for flipping on the 15th. `verify_series_integrity.py:56` still says `railway run`. The sandbox clone is shallow, so `test_context_builder_output_unchanged_pre_post_refactor` fails here (and not in CI, which checks out full depth).
- **Pattern to say out loud:** this was another session spent on the zone record (a build, but of the record's correction mechanism, not of Walk in). Three consecutive sessions have gone to HC zones; the unbuilt phase-form work (#378, #379) and Walk in are where the queue stands still.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- HC zones (#364, #385, OWED for the release and the apply): **See**, **Know** and **Loop**. After the apply this lane has no remaining work except the per-band report.
- Phase-change form (#375, #376, #378, #379; the build in NEXT): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED): **Know** and **Loop**.
- HC sync reliability (#369-#371, #377, #380, Q159, Q202, Q208, Q214, OWED): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted).
- The shared phase-entry and ledger build (NEXT), HR input layer per second (Q213), the instrument datasheets brief and the `review_by` fixtures watch row (LATER): no v1 test; **Loop** for the phase build.
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
