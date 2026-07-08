# BRANCHES — every branch not master lives here until merged+deleted

| Branch | Purpose | Status | Why parked | Unblocks on |
|--------|---------|--------|-----------|-------------|
| `feat/hevy-exercise-template-resolver` | Hevy exercise-template synced store + title→id resolver (DECISIONS_LOG #60/#61) | **LANDED 2026-07-08** — ff-merged to `master` at `41a8998`, pushed; local branch deleted | — (prod-stamp precondition `217dce22fbc5` confirmed before land) | Code side complete. Loop closes on Luke's Railway post-apply stamp reading `3497ab483935` (`SELECT version_num FROM alembic_version`). |
