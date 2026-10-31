# 0005 — HR input layer
**State:** ideation
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#541. Folded questions: Q198, Q213, Q216. The triage placed this as architecture-scale, ideation (waits on Q10 / Q244).

Q244's verify issue (GH#536) is an input: its result feeds this doc when it lands. The triage records this doc as waiting on Q10 / Q244.

## Proposal

none yet

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q198 | Source-neutral re-zoning from raw HR (Polar and any other pathway the inventory shows) (re-zoning from raw HR) | none yet | none recorded | unclassified | open |
| Q213 | The HR input layer, per second: Edwards retained, source precedence, bounded gap interpolation, and the sRPE floor (per-second layer, precedence, interpolation) | none yet | none recorded | unclassified | open |
| Q216 | Should HC zoning move to heart-rate reserve (Karvonen: resting HR to HRmax), so zones adapt forward with fitness through resting HR? (Karvonen/HRR) | none yet | none recorded | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q198 — Source-neutral re-zoning from raw HR (Polar and any other pathway the inventory shows)</summary>

````
## Q198. Source-neutral re-zoning from raw HR (Polar and any other pathway the inventory shows)

Raised 2026-10-01 with #364. #364 zones `health_connect` rows only; Polar rows keep the zones Polar computed, under Polar's own
HRmax and limits. This follow-on is to re-zone Polar (and any other pathway with raw per-sample HR) onto the same model from
`hr_samples`, with a full-history recompute. The follow-on brief is scoped from the inventory below, not from chat's
assumptions. The table is the S0(e) inventory carried verbatim, updated with the prod reads of 1 Oct 2026 (operator-run
queries Q1/Q3/Q4/Q7 on `health_connect_record_sources`, `aerobic_sessions` and `health_connect_sync_events`). A negative
covers only the exact pathway tested; anything not tested says "untested".

| pathway | raw per-sample HR available? | resolution (in activity / outside) | typical lag to arrival | history depth reachable | currently persisted? (where, or "discarded at <file:line>") | evidence | exact endpoint / path tested |
|---|---|---|---|---|---|---|---|
| Health Connect · `com.garmin.android.apps.connectmobile` | Y | in activity: median gap 7-16 s, max 25-44 s; passive (outside activity, and Pilates rows 69/85/92): exactly 120 s | newest sample 0.0-7.6 h old at each of 47 POSTs; every POST re-sends ~7 days, so late in-bout HR reflows for 7 days | 17,828 records since 2026-08-23; deepest re-post seen 30.9 days (a `periodDays=30` POST) | before #364: discarded at `routers/health_connect.py` `_capture_record_sources` (keeps type, timestamp, writer only; bpm fed only the daily median in `_aggregate_day`). From #364's deploy: `hr_samples` | prod queries Q1, Q3, Q4 (operator, 1 Oct 2026) | `POST /health-connect/sync`, `heartRate[]` of `{time, bpm, sourcePackage}` |
| Health Connect · `com.sec.android.app.shealth` (Samsung Health / Galaxy Ring) | Y until 2026-09-14 | median 10 s, max 10 s; the HR stream starts ~3.5 min after the walk's start (rows 79-83) | as above | 28,511 records, 2026-06-27 to 2026-09-14, 76 days; none after 14 Sep (Samsung exercise rows 68/84 have no same-writer HR) | as above | Q1, Q4 | same |
| Health Connect · `fi.polar.polarflow` (H10 via the Polar Flow app) | Y | median 1 s, max gap 1-5 s (row 88: 2,026 samples in 33.8 min) | as above | 24,332 records on 9 days since 2026-06-30; 14 Polar bouts have an HC copy (operator-reported, Q7); sessions before 30 Jun (rows 29-42 and their twins) have no HC copy | as above | Q1, Q4, Q7 | same |
| Health Connect · `unknown` writer | Y, no identity | untested | n/a | 13,939 records, 2026-06-24 to 2026-07-04 (before the identity cutover); never attributable | as above | Q4 | same |
| Health Connect · `nl.appyhapps.healthsync`, `com.withings.wiscale2` | Y | untested | n/a | 468 records (27-28 Jun) and 14 records (29 Jul to 26 Aug) | as above | Q4 | same |
| Polar AccessLink v4 `samples` | untested. Third-party summaries (one web search; `polar.com` is egress-blocked here) say a `samples` feature exists returning per-second HR inline: a hypothesis, not evidence | untested | untested | untested. The `zones` feature caps `to - from` at one day (#261, live-probed); the cap for `samples` is untested | never requested: `connectors/polar.py` `list_zoned_sessions` sends `features='zones'` only; if fetched, `import_polar._parse_session` reads only `exercises[0].zones[].inZone` and would drop it | tree; one web search | `GET /v4/data/training-sessions/list?features=samples`; read OWED: `s0_polar_read.py --mode samples` (may refresh the Polar token via the app's own `store_tokens`) |
| Polar Flow export (ZIP) | untested | untested | manual upload (user-triggered) | the whole account at export time (Likely) | discarded: `import_polar.import_flow_export` opens only `training-session_*.json` members and `_parse_session` reads only `exercises[0].zones[].inZone` | tree | read OWED (local, no token): list the ZIP's members and one session's `exercises[0]` keys |
| Garmin direct connector (`scripts/garmin_sync`, `connectors/garmin.py`) | untested | n/a | n/a | n/a | not fetched: the connector calls only `get_hrv_data` (5-min RMSSD, not HR) and the social-profile call; no HR or activity endpoint is called anywhere | tree | none. Stays untested; no client built (operator, 1 Oct). A live read must follow #361 (never refresh a Garmin token) and build on `scripts/garmin_identity.py`'s no-refresh seam |

Separate from raw HR but needed to compare with Polar: the per-zone LIMITS Polar applied. They are not persisted (`_parse_session`
reads `inZone` only, for both v4 and the Flow export), and whether either payload carries them is untested; read OWED:
`s0_polar_read.py --mode zones` (prints the zone dicts raw, derives the implied HRmax and % bands).

**Update (5 Oct 2026, #384).** The `s0_polar_read.py` reads named above (`--mode zones` and `--mode samples`) are retired as owed: the file is in no repo, ref or container. The operator reads Polar Flow's profile HRmax by hand and reports it as context. The per-limit read of Polar's own zones, and the `samples` feature's availability, stay untested.

**What the data already shows.** The 28 Sep elliptical is three rows (HC `fi.polar.polarflow` #88, HC Garmin #89, `polar_v4` #91, the
only one zoned before #364). Row 88 is the same H10 stream Polar zoned, at 1 s: it isolates the zone MODEL (HRmax and bands) from the
sensor. #364's G2 report compares HC-zoned minutes per band against Polar's stored zones for every HC row that shares a bout with a
Polar row, as the interim invariance check.

**To decide.** (a) Whether Polar rows with an HC copy are re-zoned from `hr_samples` (a series-wide change: it moves the metabolic
series, so it needs a ruling and a recompute, never an edit). (b) The pathway for sessions with no HC copy (the Flow ZIP's samples if
the read shows they exist, or keep Polar's zones). (c) Whether Polar raw HR through the API is worth fetching at all, given HC already
carries 1 s Polar H10 HR from 30 Jun.

**State:** OPEN. Not blocking; #364 stands without it.
````

</details>

<details><summary>Q213 — The HR input layer, per second: Edwards retained, source precedence, bounded gap interpolation, and the sRPE floor</summary>

````
## Q213. The HR input layer, per second: Edwards retained, source precedence, bounded gap interpolation, and the sRPE floor

Raised 5 Oct 2026 (operator; carried from the 1-4 Oct close-out). **Not drafted; nothing built; this records the design direction the operator named, not a ruling.** The direction: Edwards TRIMP stays the load measure; a per-second source precedence (which source's samples win where several cover one bout); bounded gap interpolation; and the sRPE floor (Q202) as the fallback when no usable device HR exists.

**It waits on Polar per-second ingest.** Polar rows are zone-seconds only today, so the layer has no per-second Polar input (Q10: AccessLink per-second ingest, pathway specified in #46, not built; Q198: the v4 `samples` feature is untested). Health Connect rows already keep every posted sample (`hr_samples`).

**Where the pieces already sit.** Source ranking (#365, Q201, Q203); the sRPE floor and its capture (Q202, Q209 closed, Q189); the whole-session overlap with Hevy (Q206). Zoning credits at most `hr_zones.MAX_SAMPLE_GAP_S` (60 s) per gap, the gap bound Q206 records; whether another exists was not searched for.

**To decide (Luke).** When to draft, and whether it is one brief or follows Q10's trigger. A related brief, instrument datasheets, is not drafted either (ROADMAP LATER).

**State:** OPEN. Owner: Luke. Not blocking; waits on Q10. Related: Q10, Q198, Q201, Q202, Q203, Q189, Q206.
````

</details>

<details><summary>Q216 — Should HC zoning move to heart-rate reserve (Karvonen: resting HR to HRmax), so zones adapt forward with fitness through resting HR?</summary>

````
## Q216. Should HC zoning move to heart-rate reserve (Karvonen: resting HR to HRmax), so zones adapt forward with fitness through resting HR?

Raised 5 Oct 2026 (operator, with #383). The platform's zones are %HRmax: `hr_zones.BAND_PCT` 50/60/70/80/90 of the HRmax in force (#364; SCHEMA.md HR Zone Computation). Garmin already zones by %HRR on the watch (max 180, resting 66, LTHR 157, the LTHR estimated; the context note in #365), and none of that is an input to the app. The proposal: derive HC zones from reserve, so a falling resting HR through fitness moves the zones forward without anyone writing a new HRmax, while HRmax stays a quasi-fixed constant that is restated, not dated (#383).

**What a reserve model needs, checked on master `2236cd4`.**
- **A resting-HR input the app does not have.** `health_connect_syncs.resting_heart_rate` is the day's median of every HR sample, not a resting value (Q200), so it cannot be the input. Q200's own "derive a true resting value" from `hr_samples` is the candidate, and it is untested. SCHEMA.md forbids age-predicted values, so a resting HR would have to be measured.
- **A dated resting-HR store** the way HRmax has `user_hrmax`, or a rolling derivation; which, and what a row before the first value does, is open (an unseeded user reads `no_hrmax` today; the equivalent state would be a new reason in the closed set).
- **The band edges.** Karvonen's target is resting HR plus a percentage of (HRmax minus resting HR). Whether the platform keeps 50/60/70/80/90 of reserve or adopts the edges Garmin uses is open; Garmin's edges are not read anywhere in this repo.
- **Series effect.** Every HC row's zones would move, and with them the metabolic TRIMP series and the ACWR. The step at the switch is what #383 warns about; a full-history recompute is the only way to avoid one, and it is a series-wide change that needs a ruling.
- **Comparability.** Polar rows keep Polar's own zones (Q198), so a reserve model for HC rows changes the HC-against-Polar read recorded in the ROADMAP HC zones row, and Q198's re-zoning question moves with it.
- **Supersession.** SCHEMA.md's HR Zone Computation (`ZONE_BOUNDARIES_PCT_HRMAX`) and #364 R3 would be superseded by a new decision, not edited.

**To decide (Luke).** Whether to move at all; if so the resting-HR source and its provenance, whether it is dated like HRmax, the band edges, and the recompute. Not this session's build.

**State:** OPEN. Not blocking; nothing built. Related: #364, #383, Q198, Q199, Q200.
````

</details>
