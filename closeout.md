# Close-out — 6 Nov 2026: Garmin activity metrics (display only) and the activity HR stream (#507, #508; PR GH#642 released)

## Real commits this session

Session opened at health-app master `10b59e5` (the merge of PR GH#641, the previous close-out), the anchor the brief
named. Maxima at open: `DECISIONS_LOG` #506, no open `fork` issue. At close: #508 on this branch (#507 and #508
resolved at master max #506 and re-read unchanged immediately before the merge), still no open `fork` issue; no issue
filed or touched.

One harness-assigned branch, `claude/quirky-faraday-wmnjvk` (accepted per #387), one PR, GH#642. It opened
ready-for-review and was held, because it carries a schema migration (§ Merge disposition, one-way door). The operator
released it in-session ("merge when green"). It merges on green with `--merge` and the branch is deleted at merge. The
merge SHA and the `deploy-check` run are reported in the session's final message, because this file is written before the
merge. Seven commits:

| Commit | What |
|---|---|
| `0ad9c5b` migration(garmin-metrics) | `a9d3f5b7c2e4` adds `garmin_activity_metrics`: one row per (user, activity), every metric nullable and stored as received, the raw `summaryDTO`, no session link (R1), plus `hr_stream_fetched_at` / `hr_stream_samples` (an addition to the brief's column list, so each stream is fetched once). The model, SCHEMA §052 and the `hr_samples` writers note are in the same commit, along with the schema parity test. The anchors schema test no longer pins `e7b2a4c9d1f3` as head. |
| `4343f46` feat(garmin) | `garmin_activity_metrics.py`, the selfeval upsert from the same detail, the stream pass in the selfeval lane, `sample_writers_for`, the overlap placement read, the sessions API field, the MCP suffix, the guard test, the probe hint. |
| `554abce` feat(garmin) backfill | `scripts/garmin_activity_backfill.py` and its tests. |
| `12cb835` feat(ui) | The "Garmin" tiles on the session detail. |
| `a1fd11d` docs | Design 0010 row 7, plus the details endpoint row in the Personal API plan. |
| the `gov(garmin-metrics)` commit, plus a release follow-up (this file rides them) | `DECISIONS_LOG` #507 and #508, the ROADMAP zone-model row (Part B), the `BRANCHES.md` row, the `CLAUDE.md` Recent-landings pointer (the #505 pointer dropped under the cap of 3), and this file. |

**Step 1 VERIFY, before code. No mismatch, so no halt.**

1. **The selfeval read.** `garmin_selfeval.sync_user` makes one list GET, then one detail GET per new activity and per unrated activity due a re-check. It keeps `directWorkoutRpe` and `directWorkoutFeel` only. CONFIRMED.
   - The read window is 14 days back (`LIST_WINDOW_DAYS`), or from one day before the last captured start if that is later. It reads one page of 50, oldest first.
   - Unrated activities are re-checked for 7 days, at most once per 20 h.
   - Pacing is the `PersonalClient`'s 2 s minimum gap on the real host (`PACE_S`). The lane runs once a night in the 02:00 sweep.
2. **#506's densest-writer selection.** It is `hc_zone_enrich._row_samples`, fed by `sample_writers_for(row)`. It takes `max(streams, key=len)` over any tuple of writers, and a tie keeps tuple order. It already generalises to a writer list per row, and #508 reuses it unchanged.
3. **maxChartSize.** This was NOT measurable here, because the probe printed key names only and no fixture carries real counts.
   - `garminconnect` 0.3.11's `get_activity_details` sends `maxChartSize=2000` / `maxPolylineSize=4000` by default, so the endpoint does thin. The probe's details call sent no parameter.
   - The code therefore asks `maxChartSize=100000` and `maxPolylineSize=0`, and retries once without them on HTTP 400. It reports thinning on every fetch, with the effective interval.
   - The backfill's `thinned` and `median_interval_s` counts settle the question on the operator's run.
   - **The brief's comparison pair is likely the wrong pair (Likely, not Certain).** In Garmin's details payload, `measurementCount` is the number of metric descriptors. The rows returned are `metricsCount`, and the full-resolution total is `totalMetricsCount`. The code compares `totalMetricsCount` with the rows returned.

**Step 4 VERIFY.**

- No other row type gains cross-writer reads. Tests cover Samsung HC, Polar Flow HC, a NULL-package HC row, `polar_v4` and `polar_flow_export`.
- `garmin` / `personal_api` is never in any row's writers.
- INV-7 is unchanged: a Garmin HC row with only wellness samples is withheld with NULL zones.
- A mutation that points the writer at the wellness lane fails 3 tests.
- One known gap is documented in the code: `over_ceiling_prompts` reads the HC writer only, so an over-ceiling sample held only in the activity stream is counted by the chain report but not prompted.

**Step 7 VERIFY.** The probe's token is the DI token. `wake_day_capture` runs `_di_spo2_lane(keepalive=True)` when the Recovery page opens (Refresh forces it) or the morning check-in opens, and that refreshes and saves the DI token. The hint now says so. Other scripts still carry the old "Garmin card" hint and were left alone because they are out of scope: `garmin_spo2_backfill.py` and `garmin_identity.py`.

**Tests.**

| Suite | Result |
|---|---|
| Backend | 4607 passed, 4 skipped, 1 xfailed. 1 failed: the known `test_current_state.py` shallow-clone `git show`, local only. |
| Frontend | 583 passed, 65 files |
| `scripts/check_governance_placeholders.py` | exit 0 |

No prod write by Code, no backfill run, no token refresh.

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief `Garmin Activity
Metrics - Echo Bike Zones Review`. Each step against where it landed:

- **ANCHOR**: DONE. The repo, HEAD containing `10b59e5`, and the branch `claude/quirky-faraday-wmnjvk` were confirmed before the first edit. The fresh-clone `core.hooksPath` and `land` alias were set.
- **Step 1**: DONE, as above.
- **Step 2 migration**: DONE `0ad9c5b`, HELD.
- **Steps 3 and 4**: DONE `4343f46`.
- **Step 5 backfill**: DONE `554abce`.
- **Step 6 display and guard**: DONE `4343f46` and `12cb835`.
- **Step 7 probe message**: DONE `4343f46`.
- **Step 8 tests**: DONE across those commits.
- **Step 9**: DONE. The commits are concern-split. The PR was held, then released by the operator and merged on green.
- **LOG**: #507 and #508 in the gov commit, worded from the brief. #508 also records the resolution handling.
- **Provisional**: nothing. Master's max was re-read as #506 immediately before the merge.

## Cold-resume handoff

**Current sprint (ROADMAP NOW).**

- **Zone model.** DONE and seeded. #503 to #506 have landed and the export path is fixed. Part B (this PR) is BUILT and HELD.
- **OWED (operator), from the previous session.** Re-upload the Flow export and read its HR-samples line. Open the Training page. Ask chat for `get_zone_coverage`. (The LTHR restatement is DONE: 157 bpm, `device_estimated`, restating the 2026-03-01 seed, in force.) Report back a Z2 Echo-bike ride read on its card.
- **OWED, this PR.** The deploy check (Code, in-session). Then the backfill dry run and live run, with the counts pasted (operator).
- **Unchanged.** Ledger UX follow-ups (GH#622 to GH#629), coach ledger writes (GH#612 to GH#617), injury lifecycle (design 0009) and the wake-day three-morning gate.

**Open `fork` issues.** None.

**Design docs not in a terminal state.** 0001, 0002, 0004, 0005, 0006, 0007, 0008 and 0009. 0010 is `committed` and gained row 7, resolved. 0000 is the template.

**Branch gate.**

- `claude/quirky-faraday-wmnjvk` is rowed DONE in `BRANCHES.md`, merged and deleted at merge.
- `chat/render-status-transport` and `claude/cbti-verdict-table` were not touched. They belong to other sessions, as reported before.

**Not touched this session (named so it is not read as finished).**

- The backfill itself, and therefore the resolution finding. These are operator acts.
- GH#635 (Garmin time-in-zone cross-check), GH#634 (AccessLink samples), Q231, #365 and the Polar relabel limbs.
- No companion-app work and no `FEEDBACK.md` change.
- Six consecutive sessions have now gone to the zone model and its inputs. The Z2 ride read on its card is still not reported back.

**The single clearest next action (operator).** Once `deploy-check` is green on both services, run these in `railway ssh --service health-app-backend` from `/app`:

1. `/opt/venv/bin/python -m scripts.garmin_activity_backfill --user-id 1 --limit 5`, a quick dry run.
2. The same command without `--limit`.
3. The same command with `--confirm`.

Paste the count lines. Then open the Training page, and ask chat to read `get_recent_sessions` and `get_zone_coverage`.

## Addendum — the empty-stream follow-up (#509)

After GH#642 merged (`02a7fcc`, `deploy-check` SUCCESS on both services), the operator ran the backfill dry run.

| Run | Activities | With HR | Samples | Median interval | Thinned | Fallback |
|---|---|---|---|---|---|---|
| `--limit 5` | 5 | 0 | 0 | none | 1 | 0 |
| full | 104 | 24 | 25,778 | 1.0 s | 11 | 0 |

The parser and the resolution request are confirmed: Garmin accepted `maxChartSize`, and the streams that carry HR come back at 1 s. The 80 empty streams could not be explained from the counts, and the deployed capture would have closed each one on first read. #509 (this branch restarted from `02a7fcc`, a self-merged two-way PR) closes a stream only when the result explains itself. It counts the reason for every empty stream and adds `--diagnose`.

**Next action (operator).** Once this PR's deploy check is green, re-run the dry run and paste its `empty_reasons`. If it shows `no_rows` or `hr_column_no_samples`, run `--diagnose --activity-id <one of them>`. Then run `--confirm`, since only explained streams are closed.

## Addendum — backfill outcome, coordinates, recovery time (#510)

The operator ran the backfill live after #509 deployed.

| Count | Value |
|---|---|
| Activities listed | 104 (10 already captured by a lane run) |
| Metrics rows written | 94 |
| HR samples written | 25,778 from 24 activities |
| Median interval | 1.0 s |
| Empty streams | 70: 52 details unavailable, 18 no HR column |
| Left open | 0 |

The seven "thinned" warnings were all activities whose details are unavailable (0 rows returned, Garmin reports 1), so no HR stream was thinned. The resolution question is closed. Chat's `get_recent_sessions` shows the 5 Nov ride as `garmin=[kcal 581 TE 5.0 aerobic / 3.1 anaerobic load 276]`, with TE and load as the brief expected.

The operator asked whether recovery hours are included. They are not on the activity: the key read of every stored `summary_raw` gave 74 keys and no recovery-time key, only `recoveryHeartRate`. The same read showed start and end coordinates. #510 drops them at write, and `scripts/garmin_activity_scrub.py` clears them from the stored rows. `scripts/garmin_readiness_probe.py` asks whether the Personal API serves the daily readiness / status endpoints, where recovery time lives.

**Next action (operator).** In `railway ssh`, run `/opt/venv/bin/python -m scripts.garmin_activity_scrub` (dry run), then with `--confirm`. Run `/opt/venv/bin/python -m scripts.garmin_readiness_probe --user-id 1` and paste its output. Open the Training page, then ask chat for `get_zone_coverage`; Health Connect's withheld count was 34 of 75 before the chain re-ran.

## Addendum — the operator's close-out questions (6 Nov 2026)

1. **The 5 Nov ride's stream (activity 24970929418).** The live backfill's median sample interval was 1.0 s, and no HR stream was thinned. Code has no prod read, so the per-activity count is the operator's query below; about 2,090 rows are expected for 34:49. If it comes back far below, `--diagnose --activity-id 24970929418` prints `metricsCount`, `totalMetricsCount`, `measurementCount` and the rows returned, both asked and bare. `measurementCount` is likely the number of metric descriptors, not rows (Likely), so the rows against `totalMetricsCount` is the comparison that settles thinning.
2. **The 34 withheld Health Connect rows.** The premise that coverage is live from samples holds for Polar rows only. `reads.zone_reads.row_zoning` reports a Health Connect row withheld when its STORED `z1_seconds` is NULL, which only the load chain (`hc_zone_enrich`, run on Training-page open and nightly) writes. So a Training-page visit does change the Health Connect count. The query below lists each withheld row's `source_package` and its `garmin` / `activity_details` sample count. Which of the 52 no-details activities are hevy2garmin uploads is not in stored data: the empty reason and the uploader are not persisted, and the 74 summary keys carry no uploader. The backfill's new `--reasons` mode answers it by counting every activity by reason, type and the list item's `manufacturer`.
3. **Nothing beyond the HR samples is kept from the details payload.** `read_stream` keeps only (time, bpm) pairs, and the metrics row gains only `hr_stream_fetched_at` and `hr_stream_samples`. The request asks `maxPolylineSize=0`, and `test_the_details_payload_is_never_kept_beyond_its_hr_samples` feeds a `geoPolylineDTO` and asserts only `hr_samples` gains rows. The readiness probe has no write path. Its session is rolled back, and its token write-back is a no-op because the guard refuses any exchange.
4. **LTHR.** In force: 157 bpm, `device_estimated`, restating the 2026-03-01 seed, read from MCP `get_hr_zone_config` on 6 Nov. The ROADMAP OWED clause and the previous section's line now say so. #502's text (158, the seed) is locked and historical, and design 0010's worked examples quote the brief's anchors.

Operator queries, in psql via `railway connect`:

```sql
SELECT m.hr_stream_samples, m.duration_s, count(h.id) AS stored FROM garmin_activity_metrics m LEFT JOIN hr_samples h ON h.user_id = m.user_id AND h.source = 'garmin' AND h.source_package = 'activity_details' AND h.sample_time BETWEEN m.start_time_gmt AND m.start_time_gmt + m.duration_s * interval '1 second' WHERE m.garmin_activity_id = 24970929418 GROUP BY m.hr_stream_samples, m.duration_s;
```

```sql
SELECT a.id, a.session_date, a.sport_name, a.source_package, count(h.id) AS garmin_stream FROM aerobic_sessions a LEFT JOIN hr_samples h ON h.user_id = a.user_id AND h.source = 'garmin' AND h.source_package = 'activity_details' AND h.sample_time BETWEEN a.start_time AND a.stop_time WHERE a.user_id = 1 AND a.source = 'health_connect' AND a.z1_seconds IS NULL GROUP BY a.id ORDER BY a.session_date;
```

## Addendum — the operator's close-out answers, measured (6 Nov 2026)

1. **The 5 Nov ride (24970929418).** `hr_stream_samples` is 1,115, with 1,114 rows inside the 2,088.7 s window. `--diagnose` gives:

   | Request | Rows returned | `totalMetricsCount` | `measurementCount` |
   |---|---|---|---|
   | Asked (`maxChartSize=100000`) | 1,117 | 1,117 | 9 |
   | Bare (no parameters) | 229 | 1,117 | 9 |

   The lane gets every row Garmin holds (Certain). Without the parameter, the API returns about a fifth. `measurementCount` is the number of metric descriptors (9), not rows, so comparing rows with it would misread every activity as thinned. The 1.87 s average cadence is the watch's smart recording (Likely); "Every Second" recording would give 1 s. The backfill's 1.0 s figure is a median of per-activity medians.
2. **The withheld Health Connect rows.** The query returned 35 rows with NULL zones: 18 Strava, 10 Samsung Health, 6 Garmin Connect, 2 Polar Flow. Nine hold `garmin` / `activity_details` samples in their window: rows 103, 115, 118, 119, 120, 121, 122, 125 and 129.
   - **Row 129** (13 Oct Pilates, Garmin-written, 663 samples) is the only one #508 lets read the stream. It still reads withheld after a chain run, so it is likely sparse.
   - **The other eight** are uncounted copies, per `get_training_sessions`. Five are Strava or Samsung twins of a counted Polar-export or Health Connect row. Two are Strava weightlifting rows likely relayed from Hevy. One is a Samsung twin of the 8 Oct walk. Zoning them would change no load, so #508 is not extended to Strava rows.
   - **The other five Garmin-written rows** (69, 85, 92, 135, 139) have no stream: Garmin holds no details for those activities.
3. **Uploads (`--reasons`, 104 activities).**

   | Group | Count |
   |---|---|
   | `DEVELOPMENT` strength training: no details | 52 |
   | `DEVELOPMENT` strength training: no HR column | 20 |
   | Garmin-recorded Pilates and rugby: no details | 8 (5 and 3) |
   | With HR | 24 |

   All 72 strength activities are third-party FIT uploads (likely hevy2garmin) and carry no HR.
4. **Coordinates.** The scrub wrote 5 rows and removed 20 keys.
5. **Recovery time.** The Personal API returns 404 for `trainingreadiness` and `trainingstatus/aggregated` on 2026-11-05 and 2026-11-06. Recovery hours are out of scope; the negative covers these two paths on this host only.

**Open, for the operator.** A Z2 Echo-bike ride read on its card, as before. Optionally, switch the watch to "Every Second" recording.
