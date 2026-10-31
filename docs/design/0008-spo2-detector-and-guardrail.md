# 0008 — SpO2 detector and guardrail
**State:** discussion
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#544. Folded questions: Q150. The triage placed this as architecture-scale, discussion (pinned; safety-relevant).

Capture is DONE (DECISIONS_LOG #425): overnight SpO2 is stored as a series (`spo2_nights`, `spo2_samples`, `breathing_disruption_intervals`), ingested raw with no filter, no confidence threshold and no derived metric. This doc covers only what is not built: the detector and the false-reassurance guardrail. The entry is safety-relevant.

## Proposal

none yet

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q150 | Detector design: what reads the raw series, and when (deferred until a baseline accrues) | none yet | A baseline accrues (per the entry's Findings) | unclassified | open |
| Q150 | False-reassurance guardrail: it binds any surface that shows SpO2 | none yet | none recorded; see the entry's hard scope boundary paragraph in the appendix | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q150 — Oxygenation awareness capture — overnight SpO2 as a series, not a scalar [SAFETY-RELEVANT]</summary>

````
## Q150. Oxygenation awareness capture — overnight SpO2 as a series, not a scalar [SAFETY-RELEVANT]

Retrospective, morning-review awareness of overnight oxygenation for a CPAP-dependent user
(ResMed AirMini — sealed, no SpO2 input, no clinician-grade export; verified dead end).
**Source (rewritten 18 Oct 2026, chat ruling):** the Garmin sleep payload, `wellnessEpochSPO2DataDTOList`
(60 s epochs, each with a `readingConfidence`), read through the Lane A no-refresh client (#361) by the
nightly Garmin sweep. The Samsung path is secondary: the ring is away on warranty, and its scraper posts
only a scalar average. Hardware path forward is owned separately, deliberately not specced here.

**What this is:** nightly SpO2 MINIMUM, count/duration of dips below a threshold (88% clinical
convention, user-configurable), and dip timestamps — so mask-off / mask-shift desaturations
are visible after the fact and trends are trackable over weeks. **What is built is the raw capture
that a detector will read; the detector itself is not designed** (see Findings: detector design is
deferred until a baseline accrues).

**Hard scope boundary — must be enforced in UI + framing:** NOT real-time alerting (cannot and
must not wake the user), NOT a safety device, NOT a mask-failure backstop. The CPAP and its own
alarms are the safety layer; this is pattern-awareness only, never positioned or relied on
otherwise.

**Storage shape (built and released, `#425`):** a series, not a scalar —
`spo2_nights` (user, night, source, the sleep window, `reading_count`, `gap_count`) with children
`spo2_samples` (time, `spo2_pct`, `reading_confidence`, `epoch_duration_s`) and
`breathing_disruption_intervals`, mirroring `hrv_readings`/`hrv_samples` (`SCHEMA.md` 048). Ingested raw:
no filter, no confidence threshold, no derived metric.

`SamsungHRVReading.spo2_average_pct` (`models.py:476`) is ACTIVELY WRONG for this purpose: a
nightly mean masks the dips by construction. It is currently surfaced as the SpO2 figure in
`context_builder.py:805`, `routers/recovery.py:65`, `routers/health.py:52`, and
`mcp_server.py` (×2) — every one of those reads the masking average. The device-agnostic target
already reserves the metric: `'spo2'` is in `CANONICAL_METRIC_TYPES` (SCHEMA.md). SpO2 is
therefore pulled OUT of the trim decision entirely — neither keep nor trim: it is REBUILD.

**GATE: ANSWERED 16–17 Oct 2026, by a direct probe of Garmin's own payload, not by the scraper trace
test** (which stays unrun and is no longer the gate). The question was whether the SAMPLE SERIES is
reachable; for Garmin on user 1 it is. Evidence, with the exact pathway (FEEDBACK section 17; each
negative below is only as broad as its scope):
  - *Pathway.* `GET /userprofile-service/socialProfile` (the display name), then `GET
    /wellness-service/wellness/dailySleepData/{displayName}?date=D&nonSleepBufferMinutes=60` (the
    library's `get_sleep_data`), through the no-refresh client; one profile GET plus one GET a night.
    Element layout: `epochTimestamp` (an ISO GMT string), `spo2Reading`, `readingConfidence`,
    `epochDuration` 60, plus a profile id and device id that are not recorded anywhere.
  - *Event night* (wake-date 16 Oct; sleep 15 Oct 22:39:28 to 16 Oct 04:31:28 AEST): **350 readings, 1
    gap** (02:27 and 02:28 missing), median cadence 60 s. *Control night* (wake-date 15 Oct): **439
    readings, 0 gaps.** The payload's own summary scalars match the app on both nights (lowest 85 / 90,
    average 97 / 98).
  - *The daily SpO2 endpoint is hourly-only and insufficient.* `/wellness-service/wellness/daily/spo2/{date}`
    returned 24 hourly averages a day; `spO2SingleValues` and `continuousReadingDTOList` were null on all
    three dates probed (14, 15, 16 Oct). Its hourly minimum was 94 or 95 against day-lows of 85 and 87: the
    averaging hides exactly the dips Q150 is about. That is a negative for that endpoint, these dates, this
    account.
  - *Health Connect is not the route, and is unverified as a source.* The companion never fetches or posts
    `OxygenSaturation`, so `health_connect_record_sources` holds no `oxygen_saturation` row for user 1 (an
    operator query, 16 Oct: zero rows) and that says nothing about what Garmin writes. "Garmin's Health Connect
    SpO2 is spot-only at best" is chat's ruling and is NOT verified from this tree.

**Findings (chat rulings on the probe result; one event night and one control night, a wrist sensor, 60 s
epochs, the event's timing as the operator reported it: awake about 03:00 to 03:10, detach time unknown):**
  - **The app-summary minimum came from sleep onset, not the 03:00 hose event.** The night's lowest reading
    was 85 at 15 Oct 23:10, about four hours before the awakening.
  - **The event produced no dip.** 02:45 to 03:15 is 31 consecutive readings, minimum 94 (03:09), typically 97;
    the watch kept sampling while the operator was awake. Nothing was below 90 after 02:18.
  - **An 88% threshold would fire on onset noise.** 15 readings were under 90 on the event night (10 between 22:42
    and 23:19, 5 between 01:57 and 02:18), 8 at or below 88 (22:48, 23:06, 23:07, 23:08, 23:10, 23:18, 02:06,
    02:18), and none in the event window; the control night had none under 90. Consecutive epochs swing 3 to 5
    points at onset, and there is a run of 100 at 02:08 to 02:11.
  - **`breathingDisruptionData`** had 10 intervals on the event night and 2 on the control (`value` 0 on both
    control intervals). Its scale is undocumented, so it is stored raw and not interpreted. `readingConfidence`
    is stored and not yet examined; its scale is undocumented too.
  - **Detector design is deferred until a baseline accrues.** No threshold, no dip count, no summary and no
    minimum is surfaced anywhere (no UI, no MCP tool).

**Scope fit with #258 (chat ruling).** SpO2 is treated as withheld from Health Connect (chat's ruling: the companion
never posts it, and Garmin's Health Connect SpO2 is spot-only at best; the second half is unverified, see the Health
Connect point above), so it sits inside #258's "withheld metrics only" scope. Pulling the sleep payload for SpO2 does
NOT decide Q129: sleep stages stay on Health Connect.

**GUARDRAIL — false reassurance is the critical failure mode for this user:** never render a
night "fine"/green on sparse or thin coverage. Absence of a recorded dip is NOT absence of a dip.
Every oxygenation surface must show coverage/confidence and degrade to "minimum recorded: X%,
coverage thin" rather than an unearned all-clear.

**Coverage for the guardrail (chat review of PR #392, 18 Oct 2026).** `gap_count` is accepted as built: it counts the places
where the series has a hole, not how long the holes are. The eventual guardrail needs MISSING MINUTES (how much of the
night has no reading), which is derivable from `spo2_samples` (the epochs expected across the night, less the ones stored).
Not built now: no surface exists yet to need it.

**Missing-night detection for future coverage / guardrail work (chat ruling, 18 Oct 2026).** A "missing night" is a night with **no `spo2_nights` row once it is older than the sweep's re-pull window**, not a count taken from a single run. The window is the sweep default of 7 days back from the Brisbane wake-date: the current wake-date plus the 7 before it, 8 wake-dates, so a night is re-pulled by 8 sweeps (those dated the night itself through 7 days later) and is out of reach of the nightly sweep after that; only a backfill could then fill it. The sweep's per-run `nights_empty` is **not** the measure: it includes the not-yet-slept wake-date every night, and also every genuinely empty night still inside the window (user 1's 12 Oct is counted empty on each run until it leaves the window), so a healthy run reads `nights_empty >= 1` per user. Nothing is built for this; no surface exists yet to need it.

**Value even at coarse resolution:** the AirMini gives zero SpO2 visibility. A consistent nightly
minimum alone surfaces mask-effectiveness drift over weeks, clustering of bad nights, and the
effect of a mask/cushion change — the near-term win is retrospective trend.
*(Written before the probe. The one night observed where the summary minimum was not the event is in the
Findings above; whether any derived trend tracks mask effectiveness is the deferred detector question.)*

**Related:** skin-temp + respiration overnight traces are the same "capture withheld Samsung
traces" family, same two-gate logic (withheld-from-HC + scraper-reachable), lower priority —
separate ticket. The trim decision (SpO2 excised per above) is not yet registered in this repo.

**RESOLVES WHEN:** raw capture built and released (`#425`); the backfill run and its result recorded here (done 18 Oct 2026); the first nightly sweep's `spo2` counts and the
not-yet-slept wake-date response recorded here (done, 16:00Z 18 Oct); the detector designed once a baseline has accrued;
the guardrail enforced on any surface that is ever added; SpO2 removed from the trim scope once that ticket
lands. Full event-detection may remain gated on next hardware.

**Observed (boot sweep, 18 Oct 2026, 02:40Z = 12:40 Brisbane).** The first deploy of `#425` (merge `9b30f04`, deploy `50056ecc`) ran the migration (`Running upgrade e2a4c6d8f1b3 -> e0d53feadc9d`, one occurrence, no traceback) and then, because the load sweep found itself stale, one startup sweep. Its summary, both Garmin users summed (the per-user split is not in the logged summary): `spo2` `nights_fetched 16`, `nights_inserted 15`, `nights_replaced 0`, `nights_unchanged 0`, `nights_empty 1`, `readings 5980`, `skipped_epochs 0`, `duplicate_epochs 0`, `skipped_needs_refresh 0`, `errors 0`; `users_failed 0`. The window was the sweep default of 7 days back from the Brisbane date, so 11-18 Oct, 8 nights for each of 2 users (inferred from `_DEFAULT_SWEEP_DAYS = 7` and 16 = 2 x 8, not logged). The end date, 18 Oct, was already slept at that hour, so **this run did not exercise the not-yet-slept wake-date**; the 02:00 Brisbane sweep on 19 Oct is the first that will. Which night was the empty one is not in the log; the per-user breakdown below answers it (user 1, 12 Oct).
**Backfill run (18 Oct 2026, operator, user 1, dry run first, then real; reported by the operator, not re-read from the container).** Nights with SpO2 found: 2026-09-11 to 2026-10-18, 37 of the 38 calendar days in that span, 13,856 epochs, 91 gaps. Stored: inserted 30, replaced 0, unchanged 7 (30 + 7 = 37; the 7 are user 1's boot-sweep nights, which the real run found already stored with an identical payload). **Stopped at empty streak:** 21 nights in a row with no SpO2, last date reached 2026-08-21 (21 nights, 21 Aug to 10 Sep inclusive). On its own that stop was a stop rule firing, not evidence that the history starts on 11 Sep: a stretch with Pulse Ox switched off looks the same. The second probe, next, goes further back.
**Second probe (18 Oct 2026, operator, user 1, dry run; reported by the operator, not re-read from the container).** `--newest 2026-08-20 --stop-after-empty 60`: 60 nights walked from 20 Aug back to 22 Jun, **0 nights with SpO2**, nothing written. With the first run's 21 empty nights (21 Aug to 10 Sep) that is **81 consecutive nights with no SpO2 on the sleep endpoint before 2026-09-11** (22 Jun to 10 Sep inclusive). "Empty" is the capture's own test: the payload carries no `wellnessEpochSPO2DataDTOList`. Scope: user 1 only. User 4 has had no backfill: its captured history is the 8 nights the sweep took (11-18 Oct).
**Ruling (chat, relayed by the operator, 18 Oct 2026).** Treat 11 Sep 2026 as the effective start of user 1's Garmin SpO2 history. This is a ruling about what to rely on, not a measurement of when Pulse Ox was switched on: the 81 empty nights are evidenced, their cause is not. The operator's Pulse Ox start date is therefore no longer owed (the operator may confirm it; nothing rests on it), and no further backfill is to be run.
**Per-user breakdown (18 Oct 2026, operator; read-only query on `spo2_nights` for users 1 and 4, wake-dates 11-18 Oct; reported by the operator, not re-read from the container).** The boot sweep's one empty night is **user 1, 2026-10-12**: no `spo2_nights` row. The operator reports that user 1 also has no Garmin HRV row for that night and reads it as one night the watch did not record; the HRV coincidence and that reading are the operator's, not checked here. **User 4: 8 of 8 nights stored.** Integrity: `sample_rows` equals `reading_count` on all 15 stored nights (user 1's 7, user 4's 8), and user 1's 15 Oct (439 readings, 0 gaps) and 16 Oct (350 readings, 1 gap) match the 16-17 Oct probe recorded above exactly. This replaces the earlier inference (15 inserted = 7 + 8), which the query confirms.
**State:** OPEN — the gate is answered, the raw capture is built and released (`#425`; PR #392, hold (a) released by the operator on
18 Oct 2026, conditional on backend and frontend CI green on the head), and the backfill is done (two runs, above; no further backfill). The first nightly sweep has been read (below). Nothing is owed from the operator or from Code on the capture itself; what keeps Q150 OPEN is in RESOLVES WHEN: the detector design once a baseline
has accrued, the guardrail on any surface that is ever added, and SpO2 leaving the trim scope.
**Post-release ruling (chat, 18 Oct 2026).** After the first nightly sweep (02:00 Brisbane, 19 Oct), Code checks the `spo2` counts and records the observed response for a not-yet-slept wake-date either way. If that date returns a non-200 and lands in `errors`, a follow-up classifies the case as "pending" (neither empty nor error) so `errors` stays zero on a healthy night.
**First nightly sweep (02:00 Brisbane 19 Oct 2026 = 16:00Z 18 Oct; read from the backend logs by Code at 16:30Z; deploy `9add9268`, commit `3f88092`).** The sweep ran 16:00:02Z to 16:00:44Z. `spo2`, both Garmin users summed (the per-user split is not in the logged summary): `nights_fetched 16`, `nights_inserted 0`, `nights_replaced 0`, `nights_unchanged 13`, `nights_empty 3`, `readings 0`, `skipped_epochs 0`, `duplicate_epochs 0`, `skipped_needs_refresh 0`, `errors 0`; Garmin `users_attempted 2`, `users_succeeded 2`, `users_failed 0`; `selfeval` `errors 0`. The window was the sweep default of 7 days back from the Brisbane date, 12-19 Oct, 8 nights for each of 2 users (16 = 2 x 8; derived from `_DEFAULT_SWEEP_DAYS = 7` and the date, not logged). **The not-yet-slept wake-date (19 Oct) was asked for, for both users, and did not land in `errors`.** The counts reconcile one way only: 13 unchanged = the nights already stored in the window (user 1: 13-18 Oct, 6; user 4: 12-18 Oct, 7), so the other 3 fetches were user 1's 12 Oct (the known empty night above) and 19 Oct for each user, all counted in `nights_empty`. The same sweep's HRV lines (user 4: 7 days with data, user 1: 6) fit it: no HRV for 19 Oct, and none for user 1's 12 Oct. **Not recorded in the logs:** the HTTP status or body of the 19 Oct response (only counts are logged). What the counts do establish: no request in the walk raised (`errors 0`; the walk goes oldest first and stops at the first failure, and 19 Oct is its last step), and the client raises on every status of 400 or above, so the response was not an error status; it carried no usable SpO2 epoch list (absent, empty or not a list) and was counted empty. The 04:10Z boot sweep on the `#397` redeploy (window 11-18 Oct) reads `nights_fetched 16`, `nights_inserted 0`, `nights_replaced 0`, `nights_unchanged 15`, `nights_empty 1`, `readings 0`, `errors 0` (fields not shown in the filtered log lines are not claimed). Re-pulls of 13 and 15 stored nights replaced nothing, so a stored night's payload is stable across pulls.
**Outcome of the post-release ruling (Code, 18 Oct 2026).** The condition, a non-200 for the not-yet-slept wake-date landing in `errors`, was not met: `errors` stayed zero on a healthy night, so **no "pending" follow-up is opened.** For later: the current wake-date is counted in `nights_empty` every night until the sweep after it, so a healthy night reads `nights_empty >= 1` per user; that is a normal reading, not a defect. By construction the sweep window includes the previous wake-date, so the 19 Oct nights should be stored by the 02:00 sweep on 20 Oct (not yet observed). This closes the watch-point in `#425`'s Not-verified list about what the endpoint answers for a wake-date not yet slept.
**Steady-state check (02:00 Brisbane sweep 20 Oct 2026 = 16:00Z 19 Oct; read from the backend logs by Code at 16:30Z, deploy `2491eec4`).** `spo2`, both users summed: `nights_fetched 16`, `nights_inserted 0`, `nights_replaced 0`, `nights_unchanged 14`, `nights_empty 2`, `readings 0`, `skipped_epochs 0`, `duplicate_epochs 0`, `skipped_needs_refresh 0`, `errors 0`. **The expected `nights_inserted 2` was not met at this sweep: the 19 Oct nights were already stored.** They were inserted by the startup sweep of the `#399` redeploy at 21:59:16Z on 18 Oct (07:59 Brisbane, 19 Oct): `nights_fetched 16`, `nights_inserted 2`, `nights_replaced 0`, `nights_unchanged 13`, `nights_empty 1`, `readings 1030`, `errors 0`; the redeploys at 22:38Z, 22:50Z and 23:40Z then each read `inserted 0`, `unchanged 15`, `empty 1`. The 14 unchanged (13-19 Oct, 7 per user; derived) and 2 empty (20 Oct, not yet slept; derived) reconcile. So a night is stored by the first sweep that runs after it, but **the 02:00 sweep itself has not yet been seen storing a night**, because a deploy-triggered startup sweep got there first; a clean observation needs a night with no redeploy between the user waking and 02:00.
**Clean 02:00 observation: not pursued (operator ruling, 20 Oct 2026); closed by reasoning, not by observation.** The startup sweep and the scheduled 02:00 sweep both run the same `_sweep` (`load_sweep.py`, `asyncio.to_thread(_sweep)` on both triggers) into `sweep_garmin_hrv` and its `_spo2_step`, so they share the capture path; the 02:00 trigger has been seen firing (`load sweep (02:00 Brisbane) done` at 16:00:44Z on 18 Oct and 16:00:39Z on 19 Oct); and a startup sweep has been seen storing the 19 Oct nights (`inserted 2`, above). **Still unobserved:** the 02:00 sweep itself inserting a night.
Detector design is deferred until a baseline accrues.
````

</details>
