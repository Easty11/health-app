# Close-out — clinical-documents: the store is live in prod (12 documents imported and read back byte-exact), the `document` door resolves, the one free-text ref is re-pointed, and the list view has labelled fallbacks (#403; Q142 closed, Q220, Q221 opened)

## Real commits this session

`git log --format="%h %ad %s" --date=short 7b09998..HEAD` (session opened at master `7b09998`; maxima at open: `DECISIONS_LOG` #402, `OPEN_QUESTIONS` Q219):

- `35ad177` 2026-10-08 feat(clinical-documents): a dedicated store for imaging reports and clinical letters; the document door resolves
- `56e8143` 2026-10-08 gov(clinical-documents): record the clinical documents store; Q142 closed; two questions opened
- `d8121db` 2026-10-08 chore: session close-out
- `8044d1f` 2026-10-08 gov(clinical-documents): land - integers resolved (#403, Q220, Q221), F1 to F3 recorded as operator-ratified
- `b07b0d5` 2026-10-08 Merge pull request #352 (the migration and the store; merged on the operator's instruction, which released the migration)
- `64e3baa` 2026-10-08 test(knowledge): pin who may rewrite a confirmed finding and what survives
- `2d75c26` 2026-10-08 Merge pull request #353 (tests only)
- `3380f96` 2026-10-08 feat(clinical-documents): the list view says something useful when a document has no conclusion
- `c1ffe52` 2026-10-08 gov(clinical-documents): record the prod import, the F2 re-point and the list-view fallbacks
- the close-out commit below this file (`chore: session close-out`), on this branch's PR (merge SHA recorded at the next close-out)

## Pending-queue reconciliation

No `PENDING` items were carried in. The chat brief's LOG block is landed: `DECISIONS_LOG` #403 (F1 to F3 operator-ratified), Q142 DONE → #403, Q220 and Q221 opened, the ROADMAP item struck. Two things were deliberately not written: the optional `FEEDBACK` note ("declare the door, land the store later"; a pattern note, not a correction), and a second CLAUDE.md Recent-landings pointer (this PR extends #403, which already has one). Nothing decided is uncommitted.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. The NEXT item "Appointment brief — imaging timeline resolves documents" is DONE except the operator's chat check below.

**State.** Master carries the store, importer, read routes, MCP tool, `imaging_timeline` resolution and the two brief renderers. In prod (operator-run, operator-reported): 12 documents imported, the rerun reported all `unchanged`, 0 verbatim mismatches, both letters match, the MCP read-back matched. The one free-text `document` ref was re-pointed to its `doc_key` in place; the follow-up appointment was marked `attended` with `imaging_timeline` added. This PR adds the labelled list-view fallbacks (a referral's `reason`, a DXA's `structured` headline) and the #403 status addendum. Backend suite and frontend suite are in the PR; 10 of 10 new mutants killed.

**Single clearest next action.** The operator asks chat for `get_appointment_brief` on the follow-up appointment and confirms its imaging section shows the resolved record (date, title, conclusion). That is the last OWED item and the end-to-end proof of the door.

**Operator actions owed.** (1) That brief check. (2) Remove the 65 PDFs from the project knowledge (the database now covers them; this is what saves the context). (3) Repo visibility (public with a scrub, or private) is a separate decision, not acted on; Q142 and #280 already hold study-level clinical content in the public repo. Carried from earlier sessions, unconfirmed here: the #348 post-deploy check, Q217 and Q218 rulings.

**Code actions owed.** None for this lane. Q220 (strict `document` validation) is the operator's call; its trigger is met for active findings. Q221 (an upload and extraction UI) is deferred. The pending knee MRI arrives later as a single-document import through the same endpoint (dry run first). Carried: Q200 to CLOSED with `DONE → #395`; the #387 shared-block propagation to `health-connect-app`.

**Open questions by status** (counted by script above `## CLOSED`): 122 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). This session: Q142 closed; Q220 and Q221 opened; Q220 gained a trigger update and stays OPEN.

**Things the next reader should know.**
- The prod facts above are operator-reported; Code had no prod access and read none of it. The F2 refs never entered the repo (operator ruling); this repo's new text carries counts and pass/fail only.
- The F2 re-point and the appointment edit were in-place SQL updates, so neither left a supersede row. Why, and the cost, are in the #403 addendum; the write-path facts are pinned in `tests/test_finding_rewrite_paths.py`.
- The headline reads `total_mass_kg`, `tissue_fat_pct` and `t_score` from a DXA's `structured`. If a future DXA names them differently the headline silently omits that part (a test pins the omission), so check the first new one.
- The full migration chain cannot run on an empty database (`e3b7c5a1f942` HALTs on zero rows by design); migration checks must build the base from the models.

**What was NOT touched (named so absence does not read as finished).**
- **Every v1 test's open leg:** the reconcile leg of Walk in (NEXT, #386) and every Loop item. This lane is a medical-protocol data foundation that serves the appointment brief (Walk in, already met); it moved no open v1 leg.
- **The ingest and dedupe lane, the `/metrics` phase-marker build (R11), Q217, Q218, Q219:** unmoved.
- **The marker exposure (#367, Q206), the Source hierarchy (Q201, Q203), the Polar re-zoning (Q198), the HC sync reliability lane (Q159, Q208, Q214), the Garmin self-evaluation read, Q216:** unmoved.
- **Decided and unbuilt from earlier sessions:** the companion RHR capture (#400), the soft exclusion and window-absence reconciliation (#399, migration HOLD), the HRV/SpO2/respiratory/distance AEST re-bucketing.
- **Lab upload pipeline, interpretation layer, CBT-I, the injury ledger:** did not move. Out of scope by the brief: an upload UI (Q221), a DEXA numeric series, creating findings or injury changes from document content, and the knee MRI.
- **Pattern to say out loud:** this whole session served the medical-protocol module's document store and its read paths. It moved no open v1 leg. The next session should go to the reconcile leg or a Loop item unless the operator wants more here.

**v1-triage of the NOW lanes** (unchanged; the NOW table was not edited):
- Source hierarchy (#365): **See** and **Know**. Polar sport-id relabel (#366-#368): **Know** and **See**. HC sync reliability (#369-#371, #377, #380): **See** and **Loop**. Garmin self-evaluation read (#372-#374): **Know** and **Loop**. Aerobic ingest automated (#353): **See** and **Loop**. Session fidelity (#354-#357): **Loop** and **Know**. Appointment brief: **Walk in**, met (#386).
- Candidates for removal from NOW, as the previous close-outs named them: the phase-change form (#389, DONE), HC zones (#364, #385, #388), Know (d) (#390-#394).
- Carrying no v1 test: the CBT-I items, the injury sweep, the typed-constraints seed, and the clinical-documents store serve the medical-protocol module; the operator should rule on whether any of them belongs in NOW.
