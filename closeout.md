# Close-out — 6 Nov 2026: Polar Flow export per-second HR (`DECISIONS_LOG` #506); Part B gated at the B1 probe

## Real commits this session

Session opened at health-app master `dacf22e` (the merge of PR GH#639, the previous close-out), the anchor the brief
named. Maxima at open: `DECISIONS_LOG` #505, no open `fork` issue. At close: #506 on the branch (resolved at master max
#505, `dacf22e`; re-resolve if master advances before the merge), still no open `fork` issue; no issue filed or
touched (the issues-updated-since read returned nothing; GH#634 stays `build`, rescoped in the design doc and the
ruling, not edited on GitHub).

One harness-assigned branch, `claude/tender-pasteur-v3dgx9` (accepted per #387; the harness forbids pushing to any other
name), one PR (ready-for-review, self-merged on green), four commits:

| Commit | What |
|---|---|
| `f70f2ae` feat(polar): store the Flow export's per-second HR in hr_samples and zone Polar rows on the model from it | `import_polar._hr_samples` (the path `exercises[0].samples.heartRate[].{dateTime, value}`, local time per `timezoneOffsetMinutes`), `_store_export_samples` (insert-or-ignore on `uq_hr_sample`, same transaction as the row, written for already-present sessions too), the four summary keys and their echo in the upload response, `--keys` on the CLI; `hc_zone_enrich.POLAR_SAMPLE_WRITERS` as `(source, source_package)` pairs, `sample_writers_for` returning pairs, `_row_samples` zoning from the densest writer alone; the coverage formatter line; `tests/test_polar_export_samples.py` (24) and the two touched test files. |
| `ba6b988` feat(garmin): --keys mode on the self-evaluation probe prints the activity detail and details-stream key names | `scripts/garmin_selfeval_probe.probe_keys` / `format_keys_report` / `--keys`: the `summaryDTO` keys, the detail's top-level keys, the details endpoint's top-level keys, its `metricDescriptors[].key` metric names and each top-level list's first-item keys; no value printed; a failed details fetch reports its error class; five tests. The B1 gate the operator runs. |
| `86dd428` docs(zones): SCHEMA §041 names the three hr_samples writer lanes and design 0010 rescopes row 6 to the export samples | SCHEMA §041 (the `source` column comment, a writer-lanes bullet, the per-class paragraph's Polar sentence); design 0010 row 6, the R2 proposal paragraph, the Decisions-landed line. |
| the `gov(export-hr)` commit (this file rides it; it cannot name its own hash) | `DECISIONS_LOG` #506 (ruling); the ROADMAP zone-model row and `Last updated`; the CLAUDE.md Recent-landings pointer (the #502 pointer dropped under the cap of 3); the BRANCHES row; this file. |

**Verified, reported before any code (A1).** (1) `import_polar._parse_session` reads `exercises[0].zones[]` only and
writes no sample anywhere: CONFIRMED. (2) The export's per-sample HR path: NOT CONFIRMABLE from the tree. No fixture
under `tests/` carries samples (the `_training_session` fixture builds zone totals only), the parser never read one,
and design 0005's appendix records the Flow-export read ("list the ZIP's members and one session's `exercises[0]` keys")
as still owed; two web searches found no page naming this export's keys. The brief's expected path
`exercises[0].samples.heartRate[].{dateTime, value}` is therefore what the code reads, tagged **Guessing** for the path,
and the build is shaped so a wrong guess costs nothing and shows at once (#166, FEEDBACK §23): the write is additive
insert-or-ignore, `hr_samples_found` 0 with `found` > 0 in the upload response is the alarm, and `import_polar.py --keys`
reads the real file's key names locally (no value, no database). (3) `hr_samples` is unique on (user_id, sample_time,
source, source_package): CONFIRMED (`models.HrSample`, migration `b4d6f8a1c3e5`). `_row_samples` filtered on BOTH
`source == 'health_connect'` and `source_package IN sample_writers_for(row)`: CONFIRMED, so A3's "extend minimally" is the
pair form. (A3 VERIFY) the HC same-writer rule is unchanged: an HC row's writers are `((health_connect, its package),)`;
`tests/test_polar_export_samples.py::test_a_health_connect_row_never_reads_export_samples` and the whole of
`test_hc_zone_enrich.py` green; `hr_nadir` reads `health_connect` only; `over_ceiling_prompts` joins HC rows to HC samples
only. One finding beyond the brief: the SQLite suite stores an aware datetime naive WITHOUT converting (FEEDBACK §49),
and `_parse_session` stores the row's `start_time` in the session's local offset, so the samples are returned aware in
that same offset (one instant on Postgres; the same naive clock as the row on SQLite). A second finding: `hr_samples`
already has a third lane, `garmin` / `personal_api` (the wellness daily HR, `garmin_wellness.store_hr_samples`), which
bears on B4's naming.

**Verified, reported before any code (B1).** (1) `garmin_selfeval.sync_user` fetches `ACTIVITY_LIST_PATH` once and
`ACTIVITY_PATH/{id}` per activity and keeps `summaryDTO.directWorkoutRpe` / `directWorkoutFeel` only: CONFIRMED. (2) How a
Garmin activity is matched to an `aerobic_sessions` row today: it is NOT stored. The adapter keeps no link
(`garmin_selfeval` docstring: "no link to a Health Connect row, no relink pass"); `reads.srpe_reads._place` places an
observation at READ time on the counted session it overlaps most (`_overlap_s`, the `overlaps_workout` predicate), from
the observation's own `start_time` / `stop_time`. So "reuse it, no new matcher" means: store the activity's UTC window on
the metrics row and place by overlap on read, as the sRPE store does; the brief's `aerobic_session_id nullable` column
would be a second, stored matcher. Flagged for the B2 design, which is gated anyway. (3) Field names: not assumed; the
probe's `--keys` mode is the gate (`ba6b988`). Also for B4: the Garmin wellness lane already writes `hr_samples` as
(`garmin`, `personal_api`), so the brief's (`garmin_api`, `com.garmin.android.apps.connectmobile`) would be a third
Garmin identity; the pair form of `sample_writers_for` takes either, but the name wants ruling with the probe output.
Part B stops here by the brief's own GATE.

**Tests.** `tests/test_polar_export_samples.py` 24 passed; `tests/test_garmin_selfeval_probe.py` and
`test_garmin_selfeval.py` 77 passed; the full backend suite 4541 passed, 4 skipped, 1 xfailed with
`tests/test_current_state.py` excluded (the known shallow-clone `git show`); `scripts/check_governance_placeholders.py`
exit 0. No prod write by Code, no recompute, no anchor row or load data touched, no migration.

**Merge disposition.** Two-way door, no migration: PR 1 self-merges on green under § Merge disposition. The merge SHA and
the `deploy-check` run (#491: backend SUCCESS owed, frontend SKIPPED expected, only `backend/` changed) are reported in
the session's final message, not here (this file is written before the merge). PR 2 (Part B, the migration) does not
exist: nothing of B2 to B7 is built, by the brief's gate.

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief
`Export HR & Garmin Metrics - Echo Bike Zones Review`; each step against where it landed:

- **ANCHOR** — master HEAD `dacf22e` as stated; the branch is the harness-assigned `claude/tender-pasteur-v3dgx9`,
  confirmed before the first edit.
- **A1 VERIFY** — DONE, reported above before code; item (2) is unverifiable from the tree and is carried as a
  Guessing-tagged path with a loud failure mode, not a halt (no mismatch was found; nothing to mismatch against).
- **A2** — DONE (`f70f2ae`): `import_flow_export` writes each bout's samples, insert-or-ignore, bpm as received, same
  transaction. One addition the brief did not name: samples are written for SKIPPED (already-present) sessions too,
  because the operator's post-deploy re-upload is of an export whose rows already exist; without it the step would
  store nothing.
- **A3** — DONE (`f70f2ae`): `POLAR_SAMPLE_WRITERS` gains the export writer; `_row_samples` extended to `(source,
  source_package)` pairs; the same-writer rule verified unchanged. One rule beyond the brief, taken now because Part A
  creates the case: with two permitted writers covering one bout, the densest is zoned from alone (the brief's B4 rule,
  brought forward; mixing two 1 s streams would double the sample count at zero time cost but is not a reading of either).
- **A4** — DONE (`f70f2ae`): samples stored, Polar row zoned on the model, re-import idempotent, no-sample export keeps
  the vendor fallback, HC same-writer unchanged; plus the dry run, the transaction, the reverse-by, the densest rule and
  the tie, the `--keys` probe.
- **A5** — the commits, the PR ready-for-review, the merge, the merge commit and the `deploy-check` id and status follow
  in-turn in the final message. The operator's re-upload and Training-page chain run are OWED (operator), recorded in
  the ROADMAP and BRANCHES rows.
- **B1 VERIFY** — DONE, reported above; the probe mode built (`ba6b988`) and shipped in PR 1 so it is deployable for
  the operator to run (a held PR 2 could not have carried it). GATE: stopped here.
- **B2 to B7** — UNSTARTED by the brief's gate (the probe output before B2). Two design notes for B2/B4 recorded above
  (the read-time overlap placement; the existing `garmin` / `personal_api` lane).
- **LOG entries** — #N landed as #506 (ruling tier: `**Tier:** ruling`, Decision, Reverse-by, `CLAUDE.md` wins over the
  brief's draft wording; the brief's substance kept). #N+1 and #N+2 are NOT minted: they belong to Part B, which did not
  land; they are drafted in the brief and will be minted by the PR that lands them.
- **Provisional:** nothing. Everything decided is committed; the merge and the deploy check follow in-turn.

## Cold-resume handoff

**Current sprint (ROADMAP NOW).** Zone model: DONE and seeded; R8 ruled (#503); the restatement guard fixed (#504);
coverage readable from chat (#505); the export's samples stored and zoned (#506, this session). OWED (operator): the
Flow export re-upload and its `hr_samples_found` / `hr_samples_stored` read, the Training-page chain run, the
`get_zone_coverage` read (the `vendor` count should fall), the B1 Garmin probe (`--keys`) output; the standing LTHR
restatement to `device_estimated` and an Echo bike Z2 ride read on its card. Ledger UX follow-ups (GH#622 to GH#629):
PR-A and the ruling landed 5 Nov; the rest UNSTARTED. Coach ledger writes (GH#612 to GH#617): UNSTARTED. Injury
lifecycle in-app (design 0009): branches landed; its remaining rows unchanged. Wake-day capture: DONE, three-morning gate
OWED. The other NOW rows are OWED to the operator or Code as their cells say and did not move.

**v1 triage of NOW.** Zone model — See (a Z2 ride reads and deposits as Z2) and Know (the conditioning quota counts load
the device agrees with); this session moves the Polar rows without an HC copy onto the model, which is the See test's
data, and gates Part B (display-only vendor metrics) on a probe. Ledger UX, coach ledger writes, injury lifecycle — Know
and Walk in. Wake-day capture and lane visibility — Loop. Missed-PM catch-up, data freshness, plan/schedule tools — Loop
/ See, DONE and riding for their owed checks. RPE fallback (Q231) — See, OWED (Code once the gate opens). Source
hierarchy (#365) and the Polar relabel limbs — OWED (Luke), serving See / Know; neither moved this session and neither is
a demotion candidate: each waits on a named operator act.

**Open `fork` issues.** None.

**Design docs not in a terminal state.** 0001, 0002, 0004, 0005 (Q213 still open; its Flow-export key read is now
served by `import_polar.py --keys`), 0006, 0007, 0008, 0009. 0010 is `committed`. 0000 is the template.

**Branch gate.** This session's one branch, `claude/tender-pasteur-v3dgx9`, is rowed DONE in `BRANCHES.md` against this
PR, self-merged in-turn, deleted at merge. `origin` also holds `chat/render-status-transport` and
`claude/cbti-verdict-table`, each one commit ahead of master by `git cherry`, neither touched this session and neither
rowed in `BRANCHES.md`: they appeared after the previous close-out (which read `origin` as master plus one branch) and
belong to another session; reported, not acted on. No `BRANCHES.md` row carries OWED or BLOCKED status, so the Q138
sweep for landed-but-unflipped rows is empty.

**Not touched this session (named so it is not read as finished).** Part B of the brief in its entirety: no
`garmin_activity_metrics` table, no metrics upsert, no dense Garmin HR stream, no session-card tiles, no guard test; it
waits on the operator's probe output and then on the operator's release of its migration. The export sample path is a
guess until the re-upload confirms it. The ledger UX defects GH#623 to GH#629 and the coach ledger writes GH#612 to GH#617
stood still; the RPE fallback (Q231), the source hierarchy ruling (#365), the Polar relabel limbs, the appointment
reconcile leg, the three-morning wake-day gate, the single-row HC bout deposit read (#384 item 4) and GH#635 (Garmin
time-in-zone cross-check) are unchanged, all gated on the operator acts or capacity their rows name. Four consecutive
sessions have now gone to the zone model, its governance, its instrumentation and now its Polar input; the thing being
instrumented — a Z2 ride on the Echo bike reading as Z2 on its card — is still an operator read that has not been
reported back. No companion-app (`health-connect-app`) work; no `FEEDBACK.md` change.

**The single clearest next action (operator).** Once this PR's deploy check is green on the backend: re-upload the Polar
Flow export through the existing import route and read `hr_samples_found` / `hr_samples_stored` in the response. If
found is 0 with members found, run `python import_polar.py --zip <export.zip> --keys` locally and paste the key names.
Then open the Training page (the chain re-zones), ask chat to call `get_zone_coverage`, and in the same sitting run the
Garmin probe (`railway ssh --service health-app-backend`, `cd /app`, `/opt/venv/bin/python -m
scripts.garmin_selfeval_probe --user-id 1 --keys`) and paste its output: that opens Part B.
