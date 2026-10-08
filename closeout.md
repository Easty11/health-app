# Close-out — mcp-oauth: the MCP OAuth provider is persisted (hashed tokens, expiry, revocation); PR #355 is open and HELD for the operator's release; G4 and G5 are owed after it (Q196 closed; two questions opened)

## Real commits this session

`git log --format="%h %ad %s" --date=short 941d160..HEAD` (session opened at master `941d160`; maxima at open: `DECISIONS_LOG` #403, `OPEN_QUESTIONS` Q221):

- `df4b57f` 2026-10-08 feat(mcp-oauth): persist the MCP OAuth provider, hashed, with expiry and revocation (Q196)
- `e99648a` 2026-10-08 gov(mcp-oauth): record the persisted MCP OAuth provider, close Q196, open two questions
- the close-out commit below this file (`chore: session close-out`), on the same PR

Nothing is merged. PR #355 (ready for review, not draft) carries all three commits. The branch `claude/fervent-bardeen-6lea0k` is pushed and has a `BRANCHES.md` row (BLOCKED, owner Luke). Merge SHA is recorded at the next close-out.

## Pending-queue reconciliation

No `PENDING` items were carried in; the chat brief was the only input. Its LOG block is written: `DECISIONS_LOG ### #NEXT` (the persisted provider, F1 and F2 recorded as built to chat's marked leans), Q196 moved to CLOSED as `DONE → #NEXT`, and the brief's conditional new question (refresh-token rotation) is opened. One further question is opened that the brief did not ask for (pruning of expired and revoked rows, and the unauthenticated registration endpoint, which now writes a row per call). Raising a question needs no hold; neither is resolved. **Provisional, by design:** the integers `#NEXT`, `Q#NEXT` x2 are unclaimed until merge, and the F1/F2 confirmation and G4/G5 results are owed, not written. Nothing decided is uncommitted.

## Cold-resume handoff

**Sprint (ROADMAP NOW).** No NOW row changed. Q196 was never a NOW row (its only ROADMAP mention is historical, in the Garmin mix-up row).

**State.** PR #355 holds the work. Master is unchanged at `941d160` as far as this session knows. On the branch: tables `mcp_oauth_clients` and `mcp_oauth_tokens` (migration `295da687b02e`), a rewritten `oauth_provider.PersonalOAuthProvider`, `retire_user`'s dry run counting live tokens, a 29-test provider suite plus 3 `retire_user` tests (the pinning test is replaced by `test_mcp_tokens_survive_restart`), `SCHEMA.md` section 046. Gates G1, G2 and G3 pass; the suite is 3066 passed, 3 skipped against a 3035 / 3 baseline; 10 of 10 expiry/revocation mutants killed after one survivor exposed a test gap; the migration upgrade/downgrade/upgrade ran on a real Postgres 16 with no model drift, and the provider file also passes against it. The `placeholder guard (POSIX)` check is **red by design** until the integers are resolved.

**Single clearest next action.** The operator reviews PR #355, confirms F1 and F2 (1 h access / 90 d sliding refresh / no rotation) and says "release mcp-oauth". Code then resolves `#NEXT` and both `Q#NEXT` against master's max (re-read at that instant), confirms the guard is green, merges, and walks the operator through the release sequence in the PR body (deploy, migration check, one last re-auth, G5 redeploy survival, G4 real-client refresh with a 120 s TTL set in the Railway dashboard).

**Operator actions owed.** (1) Review and the release instruction. (2) The one last re-auth after the deploy. (3) G5 and G4 on prod, as scripted in the PR. (4) A ruling on whether a client secret held in `client_info` (the SDK compares it in plaintext) is acceptable as recorded in the pruning question.

**Things the next reader should know.**
- Code had no prod or database access here; G4, G5 and the connector's token-endpoint auth method are unverified. Nothing in the decision asserts them.
- `railway variables` is banned by #111, so the G4 TTL variable is set in the Railway dashboard, not from PowerShell. Setting `MCP_ACCESS_TOKEN_TTL_SECONDS` redeploys the backend; a short TTL applies to tokens minted after it, which is why the G4 script revokes the live access token to force a refresh.
- If G4 fails, F1 falls back to a long access TTL (30 days, `2592000`) by environment variable, not a code change.
- The full migration chain cannot run on an empty database (`e3b7c5a1f942` HALTs on zero rows by design); migration checks build the base from the models. A fresh container also needs the CI ephemeral `FERNET_KEY` and a non-shallow clone (`tests/test_constraint_engine_arm.py` reads an old SHA) for the suite to collect.
- The provider does synchronous database work inside async methods (one short session per call), like the existing MCP tool reads; it is not a concern at one user.

**What was NOT touched (named so absence does not read as finished).**
- **Every v1 test's open leg:** the reconcile leg of Walk in (NEXT, #386) and every Loop item. This session was transport infrastructure for the chat connector: it serves no v1 test directly (the connector is how chat reads `get_appointment_brief`, so it is a precondition of using Walk in from chat, not a leg of it).
- **The medical-protocol and fitness lanes:** the ingest and dedupe lane, Q217, Q218, Q219, the marker exposure (#367, Q206), the Source hierarchy (Q201, Q203), the Polar re-zoning (Q198), the HC sync reliability lane (Q159, Q208, Q214), the Garmin self-evaluation read, Q216, the clinical-documents operator check (the follow-up appointment's brief), the lab upload pipeline, the interpretation layer, CBT-I, the injury ledger: unmoved.
- **Decided and unbuilt from earlier sessions:** the companion RHR capture (#400), the soft exclusion and window-absence reconciliation (#399, migration HOLD), the HRV/SpO2/respiratory/distance AEST re-bucketing.
- **Out of scope by the brief:** MCP write tools, any change to what the tools return, and auth for the main app (`backend/auth.py`).
- **Pattern to say out loud:** the last two sessions went to infrastructure around the product (document store, connector persistence), not to an open v1 leg. The next session should go to the reconcile leg or a Loop item once #355 is released, unless the operator wants more here.

**Open questions by status.** 123 OPEN and 7 OWED above `## CLOSED` (two of the OPEN are new this session: refresh-token rotation; pruning and the registration endpoint). Q196 is now closed.

**v1-triage of the NOW lanes** (unchanged; the NOW table was not edited):
- Source hierarchy (#365): **See** and **Know**. Polar sport-id relabel (#366-#368): **Know** and **See**. HC sync reliability (#369-#371, #377, #380): **See** and **Loop**. Garmin self-evaluation read (#372-#374): **Know** and **Loop**. Aerobic ingest automated (#353): **See** and **Loop**. Session fidelity (#354-#357): **Loop** and **Know**. Appointment brief: **Walk in**, met (#386).
- Candidates for removal from NOW, as the previous close-outs named them: the phase-change form (#389, DONE), HC zones (#364, #385, #388), Know (d) (#390-#394).
- Carrying no v1 test: the CBT-I items, the injury sweep, the typed-constraints seed; the operator should rule on whether any of them belongs in NOW. This session's lane (the MCP connector) is not in NOW and is released by the operator, not by lane momentum.
