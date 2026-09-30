# Close-out (follow-up landed) — Garmin account mix-up repaired and guarded; test-account retirement tooling (#358–#362); PRs #290–#295

## Real commits this session

Range: `ce75ee6` (master when the session opened, PR #289) to `e66298a` (PR #295, the close-out), real `git log`, 16 commits (merge commits included). This follow-up's own commit follows it; `git log` names it once landed.

- `e66298a` 2026-09-30 Merge pull request #295 from Easty11/claude/gracious-franklin-v4khwd
- `fa83d1d` 2026-09-30 gov(retire-test-user): session close-out - DECISIONS 358-361, Q195-Q196, FEEDBACK 56-59, closeout.md
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

Session origin: harness-assigned branch `claude/gracious-franklin-v4khwd`, restarted from master after each merge (six uses); one concern-named branch, `fix/garmin-login-blob-check`, pushed with the operator's explicit permission.

## Pending-queue reconciliation

No `;cc` PENDING queue was carried in; the session ran from the `retire-test-user` brief and the operator's rulings in chat, several of which arrived out of order. **Every PENDING item from the first close-out is now resolved** (recorded in DECISIONS #362, provisional until this follow-up lands):

- **S1 inventory, users 4 and 5:** SUPERSEDED by the scope update (6, 7, 8 candidates; 1, 4, 5 real). Landed as the dry-run report (`3c61a7f`, `f0b7217`; PR #290).
- **S2 retirement mechanism:** LANDED (`3c61a7f`, `f0b7217`; PR #290, merge `a84b449`); users 1/4/5 protected; refuse-by-default `--accept-loss` gate ratified.
- **S3 operator execution:** users 6, 7 and 8 all RETIRED by the operator (1 row, 8 rows, 9 rows), users 1/4/5 asserted identical each time. **User 7 (previously HELD):** confirmed a test account; 7 knowledge entries and the user row; #362.
- **S4 sweep verification:** MOOT; users 6, 7, 8 held no integrations and were never in the sweep (#360).
- **G1 identity check:** LANDED (`72e08dd`; PR #290). **G2 purge:** LANDED (`6ce2ee2`; PR #291, merge `46e51e7`); class A executed (21 readings, 1645 samples). **Class B (previously PENDING): CONFIRMED Deb's** (her app: 31 Aug = 48 ms, 2 Sep = 39 ms); the 8 rows stay on user 4, no reassignment, ever (#362).
- **G3 (the operator's):** DONE (27 Sep: user 1 = 39 PASS, user 4 = 31 PASS, identical nights 0); tooling fixes `a77ec86` (PR #292) and `e3e0ad4` (PR #294).
- **G4 attach guard:** LANDED (`11e657a`; PR #293, merge `0ccd20d`), migration applied at boot. **Fingerprint check (previously PENDING): VERIFIED in prod**: both users recorded, prefixes `283aeee9…` and `96ff6301…`, distinct (#362). The attach path's 409/503 were not exercised in prod (no re-attach, by design).
- **LOG instruction:** DECISIONS #358–#362, OPEN_QUESTIONS Q195–Q196, FEEDBACK §56–§59: #358–#361, Q195–Q196 and §56–§59 landed in `fa83d1d` (PR #295, merge `e66298a`); **#362 is in this commit and provisional until it lands.**
- **Withdrawn rulings** (the Hevy ownership-drain rulings; the original G3 use of `deb_token.json`): superseded, recorded in #360 and #359.
- **Decided but uncommitted:** nothing beyond this follow-up commit. **No PENDING item remains from this session.**

## Cold-resume handoff

### Current sprint (ROADMAP NOW)

Live NOW lanes: injury clearance (operator), aerobic ingest automated (operator check), session fidelity G6 (operator, after deploy), the lab upload pipeline, the interpretation layer build, the appointment brief (Thu 1 Oct 2026, tomorrow at the time of writing), and the cross-repo shared-block propagation debt. The Garmin account mix-up row is now **DONE → #362**; the rest of NOW is DONE or DISCHARGED.

### Open questions, grouped by status

OPEN 107 (**Q195** the Hevy sync re-owns a workout to whichever user synced last, dormant, to be fixed before any further user joins; **Q196** the MCP OAuth provider is in-memory), OWED 4, CLOSED 84. Nothing was closed this session.

### The single clearest next action

The appointment brief for **Thu 1 Oct 2026**, the date-anchored item: the operator's owed checks are in the `BRANCHES.md` row for the appointment brief v1 (`claude/sweet-darwin-wjr851`: the served-bundle grep, POST the 1 Oct row, the phone read). After that, the next Code item is Q195: rule the option (never re-own; key by user and Hevy id; or an attach-time guard) and fix it before any further user joins.

### NOT touched this session (named on purpose)

Every product lane stood still, and none of their gating questions moved: the **lab upload pipeline** and the **interpretation layer** (both feed the appointment brief), the **appointment brief** itself (tomorrow; its owed operator checks untouched), the **weekly resolver and Know enforcement** work (#276/#307), the **surface-debt sweep** (the Loop test), the **offseason phase sequence** (#270, operator-held), and the coach/MCP surface (Q196 is new here, nothing built). The whole session went to repair and instrumentation around accounts. That was warranted by a real integrity fault and it is now finished, but it is instrument work, not the thing being instrumented: a session opened from this handoff should go to the product lanes above, not to more account tooling.

### v1-triage (which test each live NOW lane serves)

- **Injury clearance:** Know and Walk in. **Aerobic ingest automated (operator check):** See and Loop. **Session fidelity G6:** Loop and Know.
- **Lab upload pipeline, interpretation layer, appointment brief:** Walk in.
- **Garmin account mix-up:** DONE; served Know (whose HRV the engine and the coach act on). No longer a NOW lane.
- **Cross-repo shared-block propagation:** serves no v1 test. It is in NOW because `#112` names ROADMAP NOW the canonical home for cross-repo debt, not by lane momentum; the standing question is whether that debt still needs a NOW row.

### What a cold session must know

- **Real accounts are protected:** users 1, 4 and 5 are hard-refused by `scripts/retire_user.py`. User 4 is Deb's real account; user 1's Garmin account is the one that had been shared. Users 6, 7 and 8 no longer exist.
- **Prod is operator-only** (`railway ssh --service health-app-backend`, `cd /app`, `/opt/venv/bin/python -m scripts.<name>`). Code has no prod DB access; every prod write this session was the operator's own run, and the outcomes recorded here came from the operator's pasted output.
- **`scripts/garmin_login` runs on the operator's machine** (Python >= 3.12, `garminconnect==0.3.11`) and exits 1 without a usable blob.
- **Migration `a9c3e5f7b1d2` is live** and recording fingerprints; `SCHEMA.md` §040 documents it.

### Nits (batched, not gates)

64 older `BRANCHES.md` rows have a cell count other than five (literal pipes in their text), from line 45 down; not touched here.
