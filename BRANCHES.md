# BRANCHES — every branch not master lives here until merged+deleted

| Branch | Purpose | Status | Why parked | Unblocks on |
|--------|---------|--------|-----------|-------------|
| `feat/hevy-exercise-template-resolver` | Hevy exercise-template synced store + title→id resolver (DECISIONS_LOG #60/#61) | **LANDED 2026-07-08** — ff-merged to `master` at `41a8998`, pushed; local branch deleted | — (prod-stamp precondition `217dce22fbc5` confirmed before land) | Code side complete. Loop closes on Luke's Railway post-apply stamp reading `3497ab483935` (`SELECT version_num FROM alembic_version`). |
| `feat/hevy-create-loop` | `create_and_resolve` — app-originated custom exercise via create→sync→list-back (DECISIONS_LOG #65, resolves Q14) | **LANDED 2026-07-11** — ff-merged to `master` at `e13e3a2`, pushed; local+remote branch deleted | — (backend-only, no migration, no external precondition) | Code side complete. `create_and_resolve` is a library function; resolver-activation wiring stays dormant (unchanged this session). |
