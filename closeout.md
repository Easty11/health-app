# Close-out — clinical-documents: a dedicated store for imaging reports and clinical letters, and the `document` door resolves (Q142); built and tested, migration HELD for the operator's release, not merged

## Real commits this session

`git log --format="%h %ad %s" --date=short 7b09998..HEAD` (session opened at master `7b09998`; maxima at open: `DECISIONS_LOG` #402, `OPEN_QUESTIONS` Q219):

- `35ad177` 2026-10-08 feat(clinical-documents): a dedicated store for imaging reports and clinical letters; the document door resolves
- `56e8143` 2026-10-08 gov(clinical-documents): record the clinical documents store; Q142 closed; two questions opened
- the close-out commit below this file (`chore: session close-out`)

Branch `claude/optimistic-johnson-69mdls`, PR https://github.com/Easty11/health-app/pull/352 (ready for review, **not merged**). Master was `7b09998` at push; it had not advanced.

## Pending-queue reconciliation

No `PENDING` items were carried in. The chat brief's LOG block was applied as follows:
- `DECISIONS_LOG ### #NEXT`: written (`56e8143`). Integer **not claimed**, per the brief; the landing session resolves it.
- `OPEN_QUESTIONS Q142`: moved below CLOSED, body verbatim, State line `DONE → #NEXT` (`56e8143`).
- New OQ, strict `document`-door validation: written as `Q#NEXT` (`56e8143`). New OQ, upload and extraction UI: written as `Q#NEXT` (`56e8143`).
- `FEEDBACK` (optional, "declare the door, land the store later"): **not written**, provisional. It is a pattern note, not a correction; add it at landing if wanted.
- CLAUDE.md Recent-landings pointer: **not written**; nothing has landed. The landing session adds it (the BRANCHES row says so).
- Provisional until merge: every decision in `#NEXT`, including F1 to F3, which are implemented to chat's lean and **not yet ratified by the operator**.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. The NEXT item "Appointment brief — imaging timeline resolves documents" is struck as built, held.

**State.** The store, importer, read routes, MCP tool and `imaging_timeline` resolution are built on PR #352. Backend 3019 passed / 3 skipped (baseline 2938 / 3 measured on master; the brief's 2370 was stale); frontend 390 passed (+3). Migration `c3e5a7d9b1f4` ran up, down, up on a real Postgres 16, and the verbatim round trip was byte-identical on JSONB. 20 of 20 mutants killed. Nothing touched prod. The `placeholder guard` check is red on the PR **by design** until `#NEXT` / `Q#NEXT` are resolved.

**Single clearest next action.** The operator reviews PR #352 and rules on F1 to F3. Then a Code session lands it: re-read master's max, resolve `#NEXT` and both `Q#NEXT`, add the Recent-landings pointer, push, wait for green, and merge on the operator's explicit release word. The release sequence is in the PR body.

**Operator actions owed, in order.** (1) Review and release PR #352. (2) After deploy: the discriminating probe (401 not 404 on `/clinical-documents`; the frontend bundle carries `brief-doc-verbatim`). (3) Dry-run the import; proceed only on 12 `would_insert`, 0 `refused`. (4) Apply, then apply again (all `unchanged`). (5) The read-back and the MCP `get_clinical_documents` check. (6) The F2 audit query (in the PR), output kept local or sent to chat, never into the repo; then re-point existing `document` refs to `doc_key`s through the normal finding rewrite. Carried from earlier sessions, unconfirmed here: the #348 post-deploy check, Q217 and Q218 rulings.

**Code actions owed.** Land #352 as above. If the first dry run refuses a document for a key the closed lists did not know, extend `LETTER_KEYS` or the `*_KEYS` tuples in `clinical_documents.py` (a code-only change that self-merges on green). Carried: Q200 to CLOSED with `DONE → #395`; the #387 shared-block propagation to `health-connect-app`.

**Open questions by status** (counted by script above `## CLOSED`): 122 OPEN, 7 OWED (Q78, Q176, Q178, Q181, Q205, Q206, Q212). This session: Q142 moved to CLOSED; two opened (`Q#NEXT`, both OPEN, not blocking).

**Things the next reader should know.**
- The closed-key lists were written from the brief, not the payload (the file was not readable here). The first dry run is where an unknown key surfaces, by name.
- `OPEN_QUESTIONS.md` Q142 and `DECISIONS_LOG` #280 already hold study-level clinical content in the public repo. Moving Q142 re-adds it to this PR's diff. Not introduced here; it needs its own decision.
- The F2 audit output was not put in the PR because Guard 1 outranks the brief's request to list the refs there.
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
