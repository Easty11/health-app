# Close-out — Garmin account mix-up repaired and guarded; test-account retirement tooling (#358–#361); landed via PRs #290–#294

## Real commits this session

Range: `ce75ee6` (master when the session opened, PR #289) to `44fcf55` (PR #294), real `git log`, 14 commits (merge commits included). This close-out's own commit follows it; `git log` names it once landed.

- `44fcf55` 2026-09-30 Merge pull request #294 from Easty11/fix/garmin-login-blob-check
- `847756c` 2026-09-30 Merge remote-tracking branch 'origin/master' into fix/garmin-login-blob-check
- `0ccd20d` 2026-09-30 Merge pull request #293 from Easty11/claude/gracious-franklin-v4khwd
- `e3e0ad4` 2026-09-30 fix(scripts): garmin_login refuses to exit 0 without a usable blob; document prerequisites and a check that can fail
- `11e657a` 2026-09-30 feat(garmin): attach guard - one Garmin account, one user (G4, migration; HELD)
- `11f470c` 2026-09-30 Merge pull request #292 from Easty11/claude/gracious-franklin-v4khwd
- `a77ec86` 2026-09-30 fix(scripts): garmin_login prompts go to stderr so stdout is exactly the token blob
- `46e51e7` 2026-09-30 Merge pull request #291 from Easty11/claude/gracious-franklin-v4khwd
- `6ce2ee2` 2026-09-30 feat(scripts): garmin_purge_copies (G2) and garmin_verify - repair the Garmin account mix-up
- `a84b449` 2026-09-30 Merge pull request #290 from Easty11/claude/gracious-franklin-v4khwd
- `95b470f` 2026-09-30 gov(retire-test-user): BRANCHES row for the retire_user / garmin_identity branch (#176 (b))
- `72e08dd` 2026-09-30 feat(scripts): garmin_identity - read-only Garmin/Hevy credential identity check (G1)
- `f0b7217` 2026-09-30 feat(scripts): retire_user - protect real accounts 1/4/5; report sign-in artefacts and knowledge
- `3c61a7f` 2026-09-30 feat(scripts): retire_user - guarded dry-run/execute account retirement

Session origin: harness-assigned branch `claude/gracious-franklin-v4khwd`, restarted from master after each merge (five uses); one concern-named branch, `fix/garmin-login-blob-check`, pushed with the operator's explicit permission.

## Pending-queue reconciliation

No `;cc` PENDING queue was carried in; the session ran from the `retire-test-user` brief and the operator's rulings in chat, several of which arrived out of order (the G3 amendment reached me before the G3 it amended). Each brief step and ruling, against the commit that landed it or the reason it did not:

- **S1 inventory, users 4 and 5:** SUPERSEDED. The operator's scope update made 6, 7, 8 the candidates and 1, 4, 5 real. The dry run built for it reports what S1 asked for (`3c61a7f`, `f0b7217`; PR #290).
- **S2 retirement mechanism:** LANDED. `scripts/retire_user.py`, dry-run default, users 1/4/5 protected, refuse-by-default `--accept-loss` gate ratified (`3c61a7f`, `f0b7217`; PR #290, merge `a84b449`).
- **S3 operator execution:** user 8 RETIRED (9 rows / 3 tables), user 6 RETIRED (1 row; Deb confirmed not required), both operator-run with users 1/4/5 asserted identical. **User 7 HELD** (its 2 injury entries and the connector check). PENDING follow-up.
- **S4 sweep verification:** MOOT. Users 6, 7, 8 held no integrations, so none was in the sweep; retiring them changes no API pull (#360).
- **LOG instruction (FEEDBACK or DECISIONS):** in THIS commit: DECISIONS #358–#361, OPEN_QUESTIONS Q195–Q196, FEEDBACK §56–§59. **Provisional until this commit lands.**
- **G1 identity check:** LANDED (`72e08dd`; PR #290). Users 1 and 4: `cbe***`, profile id `...3854` both, different digests.
- **G2 purge:** LANDED (`6ce2ee2`; PR #291, merge `46e51e7`). Class A executed by the operator (21 readings, 1645 samples; user 4's garmin disconnected; user 1 asserted identical). **Class B (8 rows) PENDING** Deb's confirmation; no `--reassign-b`. Class C = 0.
- **G3 (the operator's; amended: no `deb_token.json`):** DONE by the operator: Deb re-minted with her email, 7 readings / 656 samples, `garmin_verify` 27 Sep user 1 = 39 PASS, user 4 = 31 PASS, identical nights 0. Tooling fixes it needed: `a77ec86` (PR #292, stdout was the prompts) and `e3e0ad4` (PR #294, refuses an empty blob, documents the prerequisites).
- **G4 attach guard (migration; held, then released):** LANDED (`11e657a`; PR #293, merge `0ccd20d`). Migration applied at boot (boot log), both services SUCCESS. **Fingerprint check in prod PENDING** (two syncs, two read-only queries).
- **Withdrawn rulings:** the Hevy ownership-drain rulings (user 4 is not a duplicate of user 1) and the original G3 use of `deb_token.json`: superseded, recorded in #360 and #359.
- **Decided but uncommitted:** nothing beyond this close-out commit. **PENDING follow-up commit (do not hold this one):** the fingerprint check result (#358), class B (#359), user 7 (#360).

## Cold-resume handoff

### Current sprint (ROADMAP NOW)

Live NOW lanes: injury clearance (operator), aerobic ingest automated (operator check), session fidelity G6 (operator, after deploy), the new **Garmin account mix-up** row (three operator follow-ups), the lab upload pipeline, the interpretation layer build, the appointment brief (Thu 1 Oct 2026, tomorrow at the time of writing), and the cross-repo shared-block propagation debt. The rest of NOW is DONE or DISCHARGED.

### Open questions, grouped by status

OPEN 107 (105 before this session, plus **Q195** the Hevy sync re-owns a workout to whichever user synced last, dormant but to be fixed before any further user joins; and **Q196** the MCP OAuth provider is in-memory, so tokens never expire, outlive a deleted user until restart, and are lost on every redeploy). OWED 4. CLOSED 84. Nothing was closed this session.

### The single clearest next action

The operator runs the G4 fingerprint check in prod (`garmin_sync --user-id 1 --days 1` and `--user-id 4 --days 1` in the container, then the two read-only queries against `user_integrations`) and pastes the result; a follow-up commit records it in #358 together with the class B ruling (#359) and the user 7 decision (#360).

### NOT touched this session (named on purpose)

Every product lane stood still, and none of their gating questions moved: the **lab upload pipeline** and the **interpretation layer** (both feed the appointment brief), the **appointment brief** itself (the 1 Oct appointment is tomorrow; its owed operator checks are in BRANCHES rows, untouched), the **weekly resolver and Know enforcement** work (#276/#307), the **surface-debt sweep** (the Loop test), the **offseason phase sequence** (#270, operator-held), and the coach/MCP surface (Q196 is new here, nothing built). The session's whole output is repair and instrumentation around accounts (retirement, identity, purge, guard tooling). That is warranted by the integrity fault it repaired, but it is instrument work, not the thing being instrumented: a session opened from this handoff should not read the governance and tooling written down here as the queue.

### v1-triage (which test each live NOW lane serves)

- **Injury clearance:** Know and Walk in.
- **Aerobic ingest automated (operator check):** See and Loop.
- **Session fidelity G6:** Loop and Know.
- **Garmin account mix-up (new):** Know (restores whose HRV the engine and the coach act on). It is a correctness repair rather than a v1 feature and sits in NOW for its date-anchored operator follow-ups; a demotion candidate once the fingerprint check, class B and user 7 land.
- **Lab upload pipeline, interpretation layer, appointment brief:** Walk in.
- **Cross-repo shared-block propagation:** serves no v1 test. It is in NOW because `#112` names ROADMAP NOW the canonical home for cross-repo debt, not by lane momentum; the standing question is whether that debt still needs a NOW row.

### What a cold session must know

- **Real accounts are protected:** users 1, 4 and 5 are hard-refused by `scripts/retire_user.py` and asserted identical in-transaction. User 4 is Deb's real account; user 1's Garmin account is the one that had been shared.
- **Prod is operator-only** (`railway ssh --service health-app-backend`, then `cd /app` and `/opt/venv/bin/python -m scripts.<name>`). Code has no prod DB access; every prod write this session was the operator's own run.
- **`scripts/garmin_login` runs on the operator's machine** and needs Python >= 3.12 and `garminconnect==0.3.11`; it now exits 1 without a usable blob.
- **The dry runs are the source for the retirement and purge outcomes recorded in #359 and #360;** they were pasted into chat, not stored in the repo.
- **The migration `a9c3e5f7b1d2` is live;** `SCHEMA.md` §040 documents it.

### Nits (batched, not gates)

64 older `BRANCHES.md` rows have a cell count other than five (literal pipes in their text), from line 45 down; not touched here. The class B `daily_records.passive_hrv_ms` check covered one record only.
