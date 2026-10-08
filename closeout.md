# Close-out — clinical-documents: a dedicated store for imaging reports and clinical letters, and the `document` door resolves (#403, Q142 closed, Q220, Q221); landed via PR #352, the migration released with the merge, the prod import still OWED

## Real commits this session

`git log --format="%h %ad %s" --date=short 7b09998..HEAD` (session opened at master `7b09998`; maxima at open: `DECISIONS_LOG` #402, `OPEN_QUESTIONS` Q219):

- `35ad177` 2026-10-08 feat(clinical-documents): a dedicated store for imaging reports and clinical letters; the document door resolves
- `56e8143` 2026-10-08 gov(clinical-documents): record the clinical documents store; Q142 closed; two questions opened
- `d8121db` 2026-10-08 chore: session close-out
- the landing commit below (`gov(clinical-documents): land ...`): resolves the integers and records the rulings

Branch `claude/optimistic-johnson-69mdls`, PR https://github.com/Easty11/health-app/pull/352, merged on green by Code on the operator's instruction. Master was `7b09998` when the integers were resolved (max #402 / Q219), so the numbers are **#403, Q220, Q221**. The merge SHA is recorded at the next close-out.

## Pending-queue reconciliation

No `PENDING` items were carried in. The chat brief's LOG block, as landed:
- `DECISIONS_LOG` #403: written, integer claimed at merge. F1 to F3 recorded as **operator-ratified** (8 Oct 2026).
- `OPEN_QUESTIONS` Q142: moved below CLOSED, body verbatim, State `DONE → #403`.
- New OQs: Q220 (strict `document`-door validation), Q221 (upload and extraction UI).
- CLAUDE.md Recent-landings pointer: added; the R11 line rolled off.
- `FEEDBACK` (optional, "declare the door, land the store later"): **not written**, provisional. It is a pattern note, not a correction.
- Nothing decided is uncommitted.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. The NEXT item "Appointment brief — imaging timeline resolves documents" is struck as built and landed.

**State.** The store, importer, read routes, MCP tool and `imaging_timeline` resolution are on master via PR #352. Backend 3019 passed / 3 skipped (baseline 2938 / 3 measured on master); frontend 390 passed (+3). Migration `c3e5a7d9b1f4` ran up, down, up on a real Postgres 16, and the verbatim round trip was byte-identical on JSONB. 20 of 20 mutants killed. **Merging released the migration**: Railway runs `alembic upgrade head` on deploy. No prod data has been written; the 12-document import has not run.

**Single clearest next action.** The release walk-through, one step at a time, each on the operator's go: (1) confirm both services deployed and the new image answers (401 not 404 on `/clinical-documents`; the frontend bundle carries `brief-doc-verbatim`); (2) authenticate and dry-run the import, then STOP for the operator's go.

**Operator actions owed, in order.** (1) The post-deploy probe. (2) The prod dry run; proceed only on 12 `would_insert`, 0 `refused`. (3) The apply, then apply again (all `unchanged`). (4) The read-back and the MCP `get_clinical_documents` check. (5) The F2 audit query: the operator brings the refs to chat, never into the repo; then re-point existing `document` refs to `doc_key`s through the normal finding rewrite. Carried from earlier sessions, unconfirmed here: the #348 post-deploy check, Q217 and Q218 rulings.

**Code actions owed.** If the first dry run refuses a document for a key the closed lists did not know, extend `LETTER_KEYS` or the `*_KEYS` tuples in `clinical_documents.py` (a code-only change that self-merges on green). Carried: Q200 to CLOSED with `DONE → #395`; the #387 shared-block propagation to `health-connect-app`.

**Open questions by status** (counted by script above `## CLOSED` after landing): 122 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). This session: Q142 moved to CLOSED (DONE → #403); two opened (Q220, Q221, both OPEN, not blocking).

**Things the next reader should know.**
- The closed-key lists were written from the brief, not the payload (the file was not readable here). The first dry run is where an unknown key surfaces, by name.
- `OPEN_QUESTIONS.md` Q142 and `DECISIONS_LOG` #280 already hold study-level clinical content in the public repo. Moving Q142 re-added it to the PR's diff. Not introduced here; the operator acknowledged it and ruled that repo visibility is a separate decision, not acted on in PR #352.
- The F2 audit output stays out of the repo (operator ruling): the operator brings the refs to chat.
- `request.evidence[]` on an appointment also carries `document` refs and is not resolved (recorded in the strict-validation question).
- The full migration chain cannot run on an empty database (`e3b7c5a1f942` HALTs on zero rows); the Postgres check used a base built from the models.

**What was NOT touched (named so absence does not read as finished).**
- **Every v1 test's open leg:** the reconcile leg of Walk in (NEXT, #386) and every Loop item. This session built a medical-protocol store that serves the appointment brief (Walk in, already met); it moved no open v1 leg.
- **The ingest and dedupe lane, the `/metrics` phase-marker build (R11), Q217, Q218, Q219:** unmoved.
- **The marker exposure (#367, Q206), the Source hierarchy (Q201, Q203), the Polar re-zoning (Q198), the HC sync reliability lane (Q159, Q208, Q214), the Garmin self-evaluation read, Q216:** unmoved.
- **Decided and unbuilt from earlier sessions:** the companion RHR capture (#400), the soft exclusion and window-absence reconciliation (#399, migration HOLD), the HRV/SpO2/respiratory/distance AEST re-bucketing.
- **Lab upload pipeline, interpretation layer, CBT-I, the injury ledger:** did not move. Not built here, by the brief: any upload or extraction UI, a DEXA numeric series, creating findings or injury changes from documents, and the pending knee MRI.
- **Pattern to say out loud:** this is a build session after two governance and ingest sessions, which is a change of direction, but it serves the medical-protocol module's data foundation rather than an open v1 leg. The next session should still go to the reconcile leg or a Loop item.

**v1-triage of the NOW lanes** (unchanged this session; the NOW table was not edited):
- Source hierarchy (#365): **See** and **Know**. Polar sport-id relabel (#366-#368): **Know** and **See**. HC sync reliability (#369-#371, #377, #380): **See** and **Loop**. Garmin self-evaluation read (#372-#374): **Know** and **Loop**. Aerobic ingest automated (#353): **See** and **Loop**. Session fidelity (#354-#357): **Loop** and **Know**. Appointment brief: **Walk in**, met (#386).
- Candidates for removal from NOW, as the previous close-out named them: the phase-change form (#389, DONE), HC zones (#364, #385, #388), Know (d) (#390-#394).
- Carrying no v1 test: the CBT-I items, the injury sweep, the typed-constraints seed, and the clinical-documents store itself serve the medical-protocol module; the operator should rule on whether any of them belongs in NOW.
