# 0006 — Sleep writers and admission
**State:** ideation
**Owner:** Luke   **Opened:** 2026-10-31   **Last moved:** 2026-10-31

## Context

Folded from `OPEN_QUESTIONS.md` in Phase B (DECISIONS_LOG #468); pointer issue GH#542. Folded questions: Q175, Q224, Q225. The triage placed this as architecture-scale, ideation (trigger: a second live sleep writer).

## Proposal

none yet

## Alternatives considered

none recorded

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| Q175 | Device identity for HC sleep sessions — persist the recording device so per-source rules key on it (device identity on the wire) | none yet | none recorded | unclassified | open |
| Q224 | Should nightly sleep be stored per writer, so a two-writer night can be split and the Garmin-primary rule applied literally? (per-writer storage, allow-list admission) | none yet | none recorded | unclassified | open |
| Q225 | Should the on-device deep-sleep confidence verdict reach the backend? (deep-sleep confidence verdict) | none yet | none recorded | unclassified | open |

## Decisions landed

- none yet

## Appendix: original entries (byte-faithful, no longer maintained)

<details><summary>Q175 — Device identity for HC sleep sessions — persist the recording device so per-source rules key on it</summary>

````
## Q175. Device identity for HC sleep sessions — persist the recording device so per-source rules key on it

Raised 2026-09-25 with #329. Per-source sleep rulings must key on the **recording device**: Samsung Health relays other devices' sessions (09-16), so `sourcePackage` is the writer app, not the device. The device is not on the wire for sleep. HCA's `fetchSleepData` mapper (`healthConnect.js` L227–234) sends only `startTime`, `endTime`, `stages`, `durationMinutes` and `sourcePackage`, and drops the library's `metadata.device`, `recordingMethod` and `id`. The exercise mapper does forward them; per #35, Samsung Health leaves them at their UNKNOWN sentinels there. The backend's `extra="allow"` would retain them if sent.

**To decide:** add `metadata.device` (manufacturer/model/type), `recordingMethod` and `id` to HCA's sleep mapper, and persist a per-endpoint device alongside `sleep_*_source_package`. Settle first whether relaying writers populate the device at all (the #35 sentinels suggest Samsung Health may not).

**State:** OPEN. Needs an HCA change and a schema migration (hold (a)).
````

</details>

<details><summary>Q224 — Should nightly sleep be stored per writer, so a two-writer night can be split and the Garmin-primary rule applied literally?</summary>

````
## Q224. Should nightly sleep be stored per writer, so a two-writer night can be split and the Garmin-primary rule applied literally?

Raised 10 Oct 2026 (the freshness brief, #405). `health_connect_syncs` keeps one aggregate row per night, a union over every writer's sessions (#254, #256), and `health_connect_record_sources` keeps a writer and a timestamp per record but no stage minutes. So a night written by both Garmin and the Samsung Health relay cannot be separated: the snapshot labels it `Health Connect (multiple)` and withholds the stage split rather than show mixed stages under one name. The operator ruling (snapshot sleep is Garmin-primary, never blended) can only be applied literally to single-writer nights.

**Trigger.** A second sleep writer is live again (the ring returns, or Withings is re-enabled), so that two-writer nights recur; or the withheld split is wanted on a historical two-writer night.

**Open design points, for when it fires.** A per-(night, writer) aggregate table or columns written at ingest (a schema change, hold (a)); whether history is backfilled from the retained records; whether the card's `Health Connect (multiple)` label then changes to the priority writer. Reading is not the problem: the read-side rule is already built (#405).

**Admission is also undecided (folded in from Q83, `DECISIONS_LOG` #460).** Which writers a night admits at ingest: a default-untrust allow-list of registered measuring sources, so that an unknown future writer (the next Health-Mate mirror) is excluded by default, versus the read-side preference ordering #457 built (`SLEEP_WRITER_PRIORITY`: Garmin, Samsung Health, Withings), which Q83 argued fails on the next mirroring app. The allow-list is gated on device identity (Q175), and `'unknown'` must be a decided value (admit-with-flag, fall back to max-pick, or log-and-count), not a default that means exclude, or the filter silently drops legitimate untagged records. Both halves fire on the same trigger, a second live sleep writer. Q83's closed row holds the full argument, including the source-side move (revoking Withings' Health Connect sleep write).

**State:** OPEN. Not blocking: the live night is single-writer today. Nothing built. Related: #405, Q24 (companion), #254, #256, Q83 (folded in at #460), Q175 (device identity, the admission gate).
````

</details>

<details><summary>Q225 — Should the on-device deep-sleep confidence verdict reach the backend?</summary>

````
## Q225. Should the on-device deep-sleep confidence verdict reach the backend?

Raised 10 Oct 2026 (the freshness brief, #405). The brief asked for the existing stage-trust logic to be reused in the snapshot. The only such logic is `deepSleepConfidence.js` in `health-connect-app`: it runs on the phone, scores whether a night's deep-sleep reading is trustworthy (companion #3), and is deliberately held back from readiness and Banister modelling until its thresholds get a manual review (companion #4). Its verdict is not in the sync payload or any backend table, so the snapshot's stage split carries no trust signal.

**Trigger.** The companion's threshold review is complete (companion #4 unblocks), or a stage-dependent reading in the snapshot or the coach is judged to need a trust tag.

**Open design points, for when it fires.** Whether the verdict rides the sync payload (a wire change in the companion contract) and where it is stored; whether a backend counterpart is written instead (a second implementation of the same rule, which drifts); how an untrusted night reads in the snapshot.

**State:** OPEN. Not blocking; nothing built. Related: #405, Q224, companion #3 and #4.
````

</details>
