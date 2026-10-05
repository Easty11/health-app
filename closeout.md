# Close-out — three phase-machinery questions are filed (Q211 direct open and quota, Q212 posture carried on a Move, Q213 the per-second HR input layer); the 4-5 Oct sync and Garmin read evidence is recorded; the HC scheduled-sync fix is NOT confirmed; one test-only date-bomb fix (PR #319)

## Real commits this session

Session `phase-open-path-and-carried-items` (the `phase-form-save-order` session had closed out and merged at `21839a4`). Range: `21839a4` (master at open) to this close-out. Fresh-clone settings verified set at open (`core.hooksPath` = `.githooks`, local `land` alias). Maxima at open: decisions 376, questions 210. Maxima now: decisions 376 (nothing ruled), questions 213.

- **One code commit, tests only, not in the brief:** `276ca7a test(phase): give the HTTP open test a review date relative to today` on `fix/phase-test-review-date-not-hardcoded` (PR #319, self-merged on green: guard, vitest and pytest passed on `276ca7a`; merge `0c04611`). Cause: `tests/test_training_phase.py::test_http_open_get_history_and_close` asserted `review_due is False` against the shared helper's fixed `review_on` of 2026-10-05, a date that became today at 00:00Z on 5 Oct, so the backend check went red on this PR (#318, governance only) and would have on every PR. Reproduced locally (`assert True is False`), fixed in the test only (the helper is unchanged), a review date of yesterday fails it, the restored test passes. The 5 Oct 00:20Z run on #318 was the first red.
- Item 1 of the brief (the phase-history read) was already landed and deployed as #314 (`bed4e57`, merge `f38ec24`), so nothing was rebuilt there.
- One governance commit, on `gov/phase-open-path-and-carried-items`: Q211, Q212, Q213; two dated notes on Q159; ROADMAP rows 37, 38 and 39 extended and two LATER rows added; the CLAUDE.md operator-scripts note and Recent-landings pointer; the BRANCHES row; this file. A file cannot name its own commit; the hash is on the branch. It is the only `gov(...)` commit of this session.
- Migration: none. No prod write. Code has no database access; every prod fact below is either read by Code from Railway or marked operator-owed.

## Pending-queue reconciliation

The 5 Oct brief, item by item.

1. **Phase-history fix — already landed; the verification is owed.** The history component read the response as a bare array while the server returns `{history: [...]}`; fixed in #314 (merge `f38ec24`) and deployed. **Not done:** the "before" read (that the decompression rows are in the ledger) and the "after" render check. Code has no database route, and the proxy returns 403 for the frontend host (re-tried once, same result), so neither the ledger nor the served bundle could be read. One query, with `PGCLIENTENCODING=UTF8` set first, serves items 1, 2 and 3 (ROADMAP row 39): `SELECT id, label, probe_posture, entered_on, closed_on, close_reason, (microcycle IS NOT NULL) AS has_microcycle, source FROM training_phases WHERE user_id = 1 ORDER BY entered_on, id;`. Then open the Phase card's history and compare. If the 4 Oct sequence was revise, direct open, Review / change, the rows should be decompression (7 Sep to 4 Oct), decompression (4 Oct to 4 Oct), aerobic base with no microcycle (4 Oct to 4 Oct), aerobic base with one (open): Likely, an inference from the code, not a read.
2. **Direct open skips quota — filed as Q211, no fix.** Verified: the backend allows no microcycle by design, the form sends one only if the Advanced JSON box is filled, and the resolver then falls back to the weekly template. **Did it also fail to close decompression? By the code, no:** direct open and the wizard both go through `_apply_open_phase`, which closes the open row in the same transaction (pinned by `test_opening_a_second_closes_the_first_in_one_txn`). The empty history was #314's read shape. What prod holds is unread. Options (a)-(d) and Code's lean are on Q211.
3. **"Recovery vehicles ranked first" under `aerobic base` — source reported, filed as Q212, nothing changed.** The note is emitted only when the open phase's stored `probe_posture` is `suppressed` (`selection.py:578-581`, `:687-691`); it is not label-derived and there is no default for an unmatched name. A Move seeds posture (and label, intent, slots) from the outgoing phase; the direct form has no default. Which one set it is a ledger read (`probe_posture` per row). While it stands, the probe is also forced off.
4. **Scheduled-sync evidence — NOT confirmed; recorded on Q159 and ROADMAP row 37.** Two corrections to the premise. (i) HRV is not phone evidence: it arrives by the 02:00 Brisbane server sweep (16:00Z) and the web app's own `garmin/refresh` on card open. (ii) The init fix is #370, not #371; #371 is the `record_sources` race, and its live proof (an overlapping pair both 200) is still owed. What the log does show: phone POSTs at 06:04Z, 12:08Z (237 s) and 18:09Z (04:09 Brisbane on 5 Oct, 8.5 s, 200; pre-fix empties took 40-42 ms), none after as of 00:14Z. The server records no trigger (no field, one user agent, an access-only deploy line), so scheduled versus app-open cannot be read from logs. The settling reads are the operator's: the `health_connect_sync_events` row for 18:09:30Z (`git_sha`, `fetch_meta`), the sleep's end time against 04:09, and whether the app was open. For the P1 brief, not ruled: a `client.trigger` label.
5. **Carried items — where each is recorded.**
   - Capture-rate query, result owed to Q202: **already recorded** (Q202, "Capture rate, OWED (operator)"; ROADMAP row 37 item 3). No change.
   - Per-second HR input-layer design: **was not recorded.** Added: **Q213** and a ROADMAP LATER row. It records only the direction the operator named; nothing is drafted or built.
   - Instrument datasheets brief: **was not recorded.** Added: a ROADMAP LATER row, UNSTARTED. **Its scope was not stated in the brief, so none is recorded; the link to Q213 is marked Guessing.** State the scope when it is drafted.
   - Q159 (HR via the Garmin read): OPEN, `OPEN_QUESTIONS.md` Q159; ROADMAP row 37. Q208: OPEN, Q208; row 37. Q205: OWED (the next Polar re-auth), Q205; ROADMAP row 36. All already present.
   - MCP `concurrent_strength` marker: **already recorded**, Q206 `State: OWED` (#367) and ROADMAP row 36.
6. **PENDING notes from the 1-4 Oct close-out.**
   - (a) CLAUDE.md operator notes: **landed** as a new bullet under Tooling (`railway run` cannot run an operator script; the `railway ssh` then `-m scripts.<name>` recipe; `PGCLIENTENCODING=UTF8`). The in-container interpreter note already existed in the "Prod psql route" bullet, left as is.
   - (b) Q202 capture-rate result owed: already recorded (item 5).
   - (c) The first live self-evaluation read (4 Oct): **landed** on Q159 and ROADMAP row 38, attributed as operator-reported, not read by Code. The 02:00 Brisbane sweep on 5 Oct ran (Code, Railway log); its self-evaluation counts were not read.
- **Not landed:** the ledger read; the served-bundle probe (#121); the sync-events read; the phase posture check; the duplicate Hevy folders; whether the phase was renamed `aerobic base` before Mon 5 Oct (today).

Provisional until merged: everything in the gov PR.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** Rows 37 (HC sync reliability), 38 (Garmin self-evaluation) and 39 (Phase-change form) extended; row 39's header now carries Q211, Q212. Two LATER rows added (the per-second HR input layer; the instrument datasheets brief). No row closed.

**State.** The gov PR self-merges on green. Nothing was ruled, so no DECISIONS entry. Q211-Q213 are OPEN with Luke.

**Single clearest next action.** The operator runs the one ledger query above and reads the `probe_posture` column first: if the open `aerobic base` row is `suppressed` and that was not intended, re-run Review / change and set `held` (a same-day correction is allowed, #317). Until then the 5 Oct coach output is recovery-first with the probe off.

**Operator actions owed.** (1) The ledger query and the Phase card's history check. (2) The sync-events read: `SELECT id, synced_at, git_sha, period_days, fetch_meta FROM health_connect_sync_events WHERE user_id = 1 ORDER BY id DESC LIMIT 6;`, and whether the app was open at 04:09 Brisbane. (3) The served-bundle probe (the PowerShell line in ROADMAP row 39; string `Kept as on file`). (4) The duplicate Aerobic Base Phase folders in the Hevy app. (5) Still open from earlier: the capture-rate query (Q202); the overlapping-sync live proof for #371; periodic manual 30-day syncs until P1 (#370) lands and is confirmed; the Polar backfill report, `--apply` and `refresh_load`; Q205 at the next Polar re-auth; the `concurrent_strength` marker build (Q206).

**Open questions by status** (OPEN_QUESTIONS.md above `## CLOSED`, counted by script): 118 OPEN, 6 OWED (Q78, Q176, Q178, Q181, Q205, Q206). This session: Q211, Q212, Q213 opened; none closed or moved.

**What was NOT touched (named so absence does not read as finished).**
- **Any fix for Q211 or Q212.** Both are filed with options; no production code changed.
- **The next date-bomb candidates.** `test_constraint_engine_arm.py`, `test_sweep_constraint_rehome.py` and `test_typed_write_shape_docs.py` hardcode `review_by: 2026-10-15` and do not pin today, and `typed_entries.py:110` tags `review due` once `review_by <= today`. Whether any assertion flips on the 15th was **not checked** (no faked clock here); `test_typed_entries_render.py` pins `TODAY` and is not in question. ROADMAP LATER carries it as a watch row.
- **The P1 phone build (#370)** and its brief: not drafted; the companion repo is read-only to Code here. The `client.trigger` suggestion is for that brief.
- **The HR input layer (Q213) and the instrument datasheets brief:** recorded, not drafted.
- **The stale-looking amber warning** on a Garmin or Samsung `load_window` slot ("deposits no load until Health Connect stage 2"): left, as at the last close-out.
- **The sRPE floor, the Garmin in-activity HR read (Q159), the sibling sync races (Q208), the Source hierarchy (Q201, Q203), the marker exposure (#367, Q206):** unmoved.
- **Know / the plan:** plan-conformance adjudication (Q197), Q27 and the Rule 1 vote counter did not move.
- **Walk in:** the lab upload pipeline, the interpretation layer's remaining increments and the appointment brief stood still.
- **Medical protocol:** CBT-I (Q46, Q48, Q55, Q170 and the gate constants) and the injury ledger (Q52, Q111, Q120, the #340 sweep) did not move.
- **Pattern to say out loud:** a third session in a row on the plan's input form and the sync plumbing, this one governance only. Walk in is where it was. The two real-use findings (a quota-less direct open, a posture carried on a Move) are the same class: a form default that quietly decides something the operator did not choose.

**v1-triage of the NOW lanes** (which test each serves; DONE rows are demotion candidates by lane momentum):
- Phase-change form: save order, placements and slot pickers (#375, #376; Q211, Q212, OWED): **Know** and **Loop**.
- Garmin self-evaluation read (#372, OWED, first live read reported 4 Oct): **Know** and **Loop**.
- HC sync reliability (#369-#371, Q159, Q202, Q208, OWED; #370 unconfirmed): **See** and **Loop**.
- Polar sport-id relabel and the H10-vs-Hevy facts (#366-#368, OWED): **Know** and **See**.
- Source hierarchy (#365, OWED to Luke): **See** and **Know**.
- HC zones (#364, OWED): **See**, **Know** and **Loop**.
- Aerobic ingest automated (#353, OWED check): **See** and **Loop**.
- Session fidelity (#354-#357, G6 OWED): **Loop** and **Know**.
- Injury clearance (OWED): **Know** and **Walk in**.
- Lab upload pipeline, Interpretation layer build, Appointment brief: **Walk in** (the hero consumer; unstarted).
- HR input layer per second (Q213) and the instrument datasheets brief (LATER, new): no v1 test; **See** if built, off the v1 path.
- Cross-repo shared-block rows: no v1 test; pinned in NOW by #112 as the canonical home of cross-repo debt, so they stay.
- DONE rows still sitting in NOW with no remaining work (#339 tag seed, #219 nap attribution, #213 PM-offer trigger, #342 typed-constraint G6, #362 Garmin repair): **serve no test now; demotion candidates**, surfaced here rather than left to ride.
