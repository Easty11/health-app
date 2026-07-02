# closeout.md — session close-out (per-user context isolation, #42, 2 Jul 2026)

## 1. Real commits this session

Session-open ref: `504e5e5` (origin/master at open, #41 max). `git log --oneline 504e5e5..HEAD`:

```
0e5fb66 fix(context): remove hardcoded Luke identity/injuries from every user's prompt
6b4aa1b fix(mcp): bind MCP tokens to a real user, remove the user_id=1 default
d946f30 docs(decisions): #NEXT per-user context isolation — user_knowledge_entries canonical, MCP tokens bind to real user
408579b docs(decisions): claim #42 at merge for per-user context isolation entry
```

All four landed to master concern-split: `fix/chat-context-per-user` (P1) →
`git land`'d directly (`0e5fb66`, ff); `fix/mcp-oauth-identity` (P2) rebased onto the new
master then `git land`'d (`6b4aa1b`, ff); `docs/decisions-per-user-context` rebased then
`git land`'d in two commits (`d946f30` the entry, `408579b` renaming `#NEXT` → `#42` at
merge per #40's number-at-merge rule). All pushed — `origin/master` confirmed at `408579b`.
Plus this close-out commit (`chore: session close-out`, hash in `git log` after this file
lands).

## 2. Pending-queue reconciliation

No pending-commit queue was carried into this session — it opened from a direct
engineering brief (ANCHOR/OBJECTIVE/STEPS/GATES/LOG/GUARD), not a `;cc` chat close-out
paste. There was nothing flagged `PENDING` to reconcile. Nothing decided this session is
uncommitted: the one governance decision made (DECISIONS_LOG #42) landed at
`d946f30`/`408579b`, both on master.

## 3. Branch terminal-state gate (local + remote, per #41)

- **Touched:** `fix/chat-context-per-user`, `fix/mcp-oauth-identity`,
  `docs/decisions-per-user-context` — all three merged `--ff-only` to master (two required
  a rebase first, since P1 landed before P2/governance were cut) and locally deleted by
  the `land` alias. None had ever been pushed as their own remote refs, so the alias's
  final remote-delete step errored benignly ("remote ref does not exist") on all three —
  not a real failure, confirmed by `git ls-remote --heads origin` showing master only both
  before and after.
- **End state:** `git branch` = master only; `git ls-remote --heads origin` = master only
  (`408579b`); `BRANCHES.md` empty (honest, nothing parked). Gate PASSES.

## 4. Cold-resume handoff

**Master:** `408579b` + close-out commit. DECISIONS_LOG max = **#42**. Local and remote
are both master-only. Working tree clean pre-close-out-commit.

**Landed this session — #42 per-user context isolation:**
- Chat context (P1): `_section_user_profile` (backend/context_builder.py) no longer
  hardcodes Luke's identity/devices/injuries. Identity was already dynamic
  (`_section_identity`); injuries already rendered per-user (`_section_schedule` from
  `type="injury"` entries) — only the device/method mapping was orphaned, now a
  `type="preference", key="device_profile"` entry in `user_knowledge_entries`.
  Empty-profile users get a new onboarding-interview prompt section, seeded via the
  *existing* `knowledge_update` mechanism — no second store. `seed_engine.py` extended
  (not duplicated) to seed the device profile.
- MCP identity (P2): `oauth_provider.authorize()` no longer auto-approves — gated through
  a new `/mcp/login` form re-checking against `users`; every token binds to a real
  `user_id`. All six `mcp_server.py` tools had `user_id: int = 1` removed, no override
  param. Also fixed `get_readiness_snapshot`'s hardcoded injury text (found in passing).
- Verify-first (before any code) found the brief's premise wrong: `has_structured_profile`
  and `knowledge_update` writes targeted disjoint tables (`fortification_profiles` vs
  `user_knowledge_entries`) — user resolved `user_knowledge_entries` as canonical before
  design proceeded. Full "How you know" in DECISIONS_LOG #42; all four gates (G1–G4)
  exercised against real code paths on local SQLite, not mocked.

**Owed / not yet done (all logged to canonical stores this close-out):**
1. **Run `seed_engine.py` against Railway Postgres** (ROADMAP NOW) — this session only had
   local SQLite; Luke's device/injury facts are seeded locally, not in production yet.
2. **`mcp_server.get_hevy_workouts` references an unimported `Session` type** (ROADMAP
   NOW) — pre-existing bug, found not introduced this session; will `NameError` at call
   time; left untouched (Hevy endpoints out of scope for #42).
3. **OPEN_QUESTIONS Q7 (new, open)** — structured injury ledger is missing a fourth injury
   (right proximal semimembranosus) that `FEEDBACK.md` §5 documents as distinct from the
   left hamstring entry; this session's migration reused `seed_engine.py`'s existing
   three-injury seed verbatim.

**Open questions by status:**
- open: Q3 (HR sampling cadence during sleep, blocks `runDeepConfidence` calibration), Q4
  (HC date-attribution one-day shift vs scraper), Q5 (backend dual-field acceptance —
  collapse after confirming what mobile actually posts), Q6 (strength volume-load
  unverified in load path, resolves → #28 on Postgres verify), **Q7 (new — 4th injury
  missing from structured ledger)**.
- resolved: Q1 → #20, Q2 → HCA `36df9a2`.

**Single clearest next action:** Run `python seed_engine.py luke.eastlake@outlook.com`
against Railway Postgres, then verify via a direct Postgres query (not on-device UI) that
`user_knowledge_entries` now carries Luke's `device_profile` and three injury rows —
closes the loop on #42 in production.
