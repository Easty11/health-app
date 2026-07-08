# BRANCHES — every branch not master lives here until merged+deleted

| Branch | Purpose | Status | Why parked | Unblocks on |
|--------|---------|--------|-----------|-------------|
| `feat/hevy-exercise-template-resolver` | Hevy exercise-template synced store + title→id resolver (DECISIONS_LOG #60/#61) | Local only, 5 commits ahead of `origin/master`, all real work; unmerged, not pushed | GATE 3 prod-stamp check unmet: could not verify Railway alembic head == `217dce22fbc5` from this session, and the brief forbids pushing migration `3497ab483935` before that (local-SQLite-vs-Railway drift hazard, #56). Not landed to avoid a broken auto-deploy. | Verify Railway alembic head == `217dce22fbc5`, then `git land feat/hevy-exercise-template-resolver` (`--ff-only`) + `alembic upgrade head` on Railway. |
