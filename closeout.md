# Close-out — freshness-load-card: snapshot sleep is Garmin-primary and named by writer (#405); a freshness read model and a home load card put an age under every load number (#406); the companion's status line shows a relative age (health-connect-app #51); Q224 and Q225 opened

## Real commits this session

`git log --format="%h %ad %s" --date=short 0939eaf..HEAD` (session opened at health-app master `0939eaf` and health-connect-app master `eed6492`; maxima at open: health-app `DECISIONS_LOG` #404 and `OPEN_QUESTIONS` Q223, companion #50 and Q25):

health-app:
- `73a0a89` 2026-10-09 feat(readiness): snapshot sleep is Garmin-primary and named by writer; HRV continuity counts Garmin
- `2156b71` 2026-10-10 Merge pull request #358 (PR 1)
- `6d2ea4d` 2026-10-09 feat(freshness): freshness read model, snapshot block and the home load card
- `f855919` 2026-10-10 fix(freshness): "data as of" is the last Health Connect delivery, not the newest arrival
- `ed1764e` 2026-10-10 Merge pull request #359 (PR 2)
- `efa7765` 2026-10-10 gov(freshness): record snapshot sleep as Garmin-primary (#405), open Q224 and Q225
- `db797ac` 2026-10-10 gov(freshness): record the freshness model and load card (#406), F1/F2 and the five rulings
- the close-out commit below this file (`chore: session close-out`), on the same governance PR

health-connect-app:
- `201daee` 2026-10-10 feat(sync): the "Last background sync" line shows a relative age, amber past 13 h
- `845f8c4` 2026-10-10 Merge pull request #70 (PR 3)
- the companion `gov(...)` and close-out commits, in that repo's own handoff

PR 1 and PR 2 were merged by Code on green. PR 2 was **held** for the operator's ruling (it carried data-meaning defaults the brief had not ratified, per the Merge disposition) and merged only after the five rulings of 10 Oct 2026; one of them (the "data as of" anchor) changed the code, pushed as `f855919` before the merge.

## Pending-queue reconciliation

No `PENDING` items were carried in; the chat brief was the only input. Its LOG block is written:
- *Snapshot sleep is Garmin-primary, recorded as the operator ruling of 9 Oct:* `DECISIONS_LOG` #405 (`efa7765`).
- *Freshness model and load card, F1 and F2 rulings, and the five #359 rulings:* `DECISIONS_LOG` #406 (`db797ac`).
- *Leave companion Q25 open and add that freshness is now visible:* in the companion's own close-out (health-connect-app), not here.
- Two questions the build surfaced, opened (raising needs no hold): Q224 (per-writer nightly sleep aggregates) and Q225 (the on-device deep-sleep confidence verdict reaching the backend).
Nothing is decided and uncommitted.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** One row added: *Data freshness, Garmin-primary snapshot sleep and the home load card* (#405, #406). The other NOW rows were not edited.

**State.** All three PRs are merged and the backend is deployed on `ed1764e` (both services SUCCESS). Verified live: the real `get_readiness_snapshot` prints sleep labelled `Garmin`, continuity `7/7 nights (garmin 7)` where it read 0/7, and the new `Data freshness` block (Health Connect delivery not amber; four stale writers named: Samsung Health heart rate, Samsung Health sleep, the Samsung scraper, unattributed steps). Suites: backend 3109 passed, 3 skipped (baseline 3070 / 3); frontend 47 files / 409 tests (baseline 45 / 390). The companion sim `npm run test:sync-age` passes at stamps 1 h, 14 h and 3 days.

**Single clearest next action.** The operator's two small checks, then the next open v1 leg: (1) the served-bundle grep of the live frontend (#121), which Code could not run because the egress policy refused that domain: the bundle should carry `Load summary`, `Data age unavailable` and `fatigue rising`; (2) a look at the amber "Last background sync" line on the next phone build. Neither blocks anything.

**Operator actions owed.**
- The two checks above.
- A decision on whether to open the egress policy to the app's own frontend domain, so that Code can run the #121 grep itself (the recipe is in the Environment network settings).
- Optional, not blocking: a ruling on a label for form (cut-points were deliberately not invented; F1).

**Things the next reader should know.**
- The freshness read is **read-side only**: no table, no migration, no ingest change. It adds one grouped query over the user's `health_connect_record_sources` rows per Dashboard open (indexed by user only). It is a watch-point, not a measured problem (#406).
- The usual gap is measured at **day grain**, over the 28 days ending at each writer's own last record. A window anchored at now drops dead writers (FEEDBACK 63); do not re-anchor it.
- "Data as of" is the **last Health Connect delivery**, the same clock as the 13 h amber gate; Polar is information only and never drives amber (operator ruling, 10 Oct).
- The Metrics tile is gone from the hub: the load card's `Metrics` link is the one doorway to `/metrics`.
- The MCP data session drops on every backend redeploy ("session expired" until it reconnects); a retry after a minute works.
- `reads/freshness_reads.py` is on the read-door drift guard's allow-list with a reason; a new direct toucher of `aerobic_sessions` fails that test.
- Real health values are kept out of the repo: the live checks above are described by label and count only (public repo, guard 2).

**What was NOT touched (named so absence does not read as finished).**
- **Every open v1 leg:** the reconcile leg of Walk in (NEXT, #386) and every Loop item. This session was visibility infrastructure for data age, plus one sleep-source repoint; it serves **See** directly (a load number never shows without its age) but did not move Walk in or Loop.
- **The cause of the 8-9 Oct background silence** (companion Q25): still unknown. Only its visibility is fixed; the discriminators (`am get-standby-bucket`, `dumpsys jobscheduler`, the battery setting) have not been taken. The next silence will now show on the phone and on the home card.
- **The Samsung scraper** (companion Q24): not fixed, by instruction (no live device). Its silence is now an amber `STALE` line; the re-verification when the ring returns is still owed.
- **Everything in the medical-protocol and ingest lanes:** the ingest and dedupe lane (Q217-Q219), the marker exposure (#367, Q206), the source hierarchy (Q201, Q203), the Polar re-zoning (Q198), the HC sync reliability lane (Q159, Q208, Q214), the MCP OAuth gates G4 and G5 (#404, Q222, Q223), the clinical-documents upload UI (Q221).
- **Out of scope by the brief:** the schedule MCP tool and the merged recent-sessions tool (a separate brief to follow), a label for form, and any `load_metrics` maths.
- **Pattern to say out loud:** the last three sessions have gone to infrastructure around the product (the document store, connector persistence, and now data-age visibility), not to an open v1 leg. The next session should go to the reconcile leg or a Loop item.

**Open questions by status.** 125 OPEN and 7 OWED above `## CLOSED` (two new this session: Q224, per-writer nightly sleep aggregates, trigger a second sleep writer going live again; Q225, whether the on-device deep-sleep confidence verdict reaches the backend, trigger the companion's threshold review completing).

**v1-triage of the NOW lanes** (the new row only; the rest are unchanged):
- Data freshness, Garmin-primary snapshot sleep and the load card (#405, #406): **See** (an age under every load number; a late pipe visible before the number is trusted) and **Loop** (the next silence is caught, not found by accident).
- Candidates for removal from NOW, as the previous close-outs named them: the phase-change form (#389, DONE), HC zones (#364, #385, #388), Know (d) (#390-#394).
- Carrying no v1 test: the CBT-I items, the injury sweep, the typed-constraints seed; the operator should rule on whether any belongs in NOW.
