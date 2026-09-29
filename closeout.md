# Close-out — Polar aerobic ingest automated (#353); Q154 closed; webhook filed as Q193

## Real commits this session

The session is `aerobic-ingest`, on branch `claude/focused-darwin-35yhmh`, a name the harness assigned. At open the
session carried the auto-title "Polar aerobic ingest automation"; it was renamed `aerobic-ingest` to match the
brief's address. The branch was cut from master `7155448`, the #286 merge, and restarted from master `9b3098a` for
this close-out.
- Master's maxima at open were decisions **#352** and questions **Q192**.
- They were re-read against `9b3098a` before the governance commit and were unchanged. That gives **#353** and
  **Q193**.

`git log --format="%h %ad %s" --date=short 7155448..origin/master` (before this commit):

```
9b3098a 2026-09-29 Merge pull request #287 from Easty11/claude/focused-darwin-35yhmh
1fb8650 2026-09-29 docs(polar): zones are no longer ZIP-only after v4 enrichment (#261)
49bb3c3 2026-09-29 feat(load): soft-fail polar_sync step in the load chain (Q154)
c8b544c 2026-09-29 refactor(polar): extract request-free ingest core polar_ingest.sync_user (Q154)
```

This close-out lands as one governance commit in its own PR: `gov(load): #353 aerobic ingest automated; Q154
closed; Q193 webhook; BRANCHES row; Recent landings; close-out`.

- **Tests:**
  - Backend: 2401 passed locally. One test failed, `test_context_builder_output_unchanged_pre_post_refactor`,
    because it needs commit `3360ed5`, which this shallow clone lacks; CI uses `fetch-depth: 0`.
  - CI was green on PR #287 (placeholder guard, backend pytest, frontend vitest).
  - Making `_polar_sync` re-raise fails 3 chain tests (mutation check).
  - The Sync response is byte-identical to master's router on a two-call probe.
- **Deploy:** the Railway `health-app-backend` build from `9b3098a` reached SUCCESS, and so did the frontend (it
  carries no frontend change, so no #121 grep is owed).
  - The new image answered (#116). Its startup self-heal sweep logged `polar_synced=`, a field only the new code
    emits: 3 of 3 users succeeded. User 1 `polar_synced=0` (180-day pull, one zone fetch for 2026-06-15). Users 4
    and 5 `no_polar`.
  - The 06-15 fetch is a zoneless v4 row that is re-fetched on every run inside its window (#261 target rule;
    noted in #353, not changed).

## Pending-queue reconciliation

No `;cc` queue was carried in. The brief's items (one paste block, addressed to this session) and where each
landed:

- **V1** (two-pass shape; `_valid_client(user_id, db)`): confirmed on `7155448`.
- **V2** (chain order; first failure skips the rest): confirmed.
- **V3** (both triggers reach `run_user_chain`): confirmed. `/load/refresh` passes `days=30`. The nightly sweep uses
  the default, **180**.
- **S1, extract the core** → `c8b544c` (`backend/polar_ingest.py`).
- **S2, route delegates; contract byte-identical** → `c8b544c`.
- **S3, chain step, soft-fail and window as ruled** → `49bb3c3`.
- **S4, webhook probe (report only)** → **Q193** in this commit. It is docs-only, for two reasons:
  - the official Polar docs are egress-blocked here;
  - a live probe would register against the only prod client (one webhook per client, one-time secret), which is
    unsafe.

  Recommendation: don't build.
- **S5, stale docstrings** → `1fb8650`. The brief said the `aerobic_reads` claim was in the module "header"; it is
  actually the comment above `_SOURCE_RANK`. That comment was corrected.
- **G1–G3** → `tests/test_polar_ingest.py` and `tests/test_refresh_load.py`. Met.
- **G4, prod** → **OWED (operator).** It has a ROADMAP NOW row.
- **LOG:** #353 appended; Q154 moved below `## CLOSED` as `DONE → #353`; Q193 opened.
- **GUARD:** held. No schema change or migration. Route unchanged. No arbitration, enrichment, transform or
  sport-exclusion change. No webhook.

**Divergences and calls (named in #353):**
- `polar_sync` sits directly after `hevy_sync`, which is inside the brief's "after hevy_sync, before
  load_events_metabolic".
- A hard `hevy_sync` failure still skips `polar_sync`, under the existing first-failure rule. The brief's soft-fail
  ruling covers polar's own failures only.
- The soft path calls `db.rollback()` before recording the error.
- The read-door drift guard now allow-lists `polar_ingest.py`, as the writer it moved out of `routers/polar.py`.
- Existing tests re-point their monkeypatch seam from `routers.polar` to `polar_ingest`.
- **Scope recorded, not changed:** the nightly sweep covers Hevy-keyed users only. A Polar-only user refreshes on
  page open, never nightly.

## Cold-resume handoff

**Where things stand.**
- Master is `9b3098a`, plus this PR (the close-out). Decisions max **#353**. Questions max **Q193**, which is OPEN.
- Polar sessions now reach `aerobic_sessions` on Training-page open and at 02:00 without a Sync press, pending the
  operator's G4 check.
- The appointment (`appt_20261001_aubrey`) is **Thu 1 Oct 2026**.

**NOW lanes and the v1 test each serves:**
- **Aerobic ingest operator check** (See / Loop). New; OWED (operator, G4).
- **Appointment brief** (Walk in). Still owed, all from #352's close-out:
  - one printed copy (OWED, operator);
  - the #121 greps for #348–#351 (OWED, operator);
  - PR2, post-visit transcript reconciliation (LATER, after 1 Oct).
- **Injury clearance** (Know / Walk in). Step (3) is OWED (operator).
- **Lab upload pipeline** and **Interpretation layer build** (Walk in). Untouched.
- **Cross-repo rows.** They serve no v1 test and are pinned by #112. The paste-addressing propagation to HCA is still
  owed.
- **Demotion candidates:** DONE rows still sitting in NOW (tags seed #339, CBT-I Q45 #219, eval trigger #213, G6
  #342).

**Open questions:** 105 OPEN and 4 OWED (Q78, Q176, Q178, Q181). Q154 closed and Q193 opened this session.

**OWED (operator), carried:**
- The Q192 orphan query from #352's close-out.
- The printed-copy read of the 1 Oct brief.

**What was NOT touched this session (and what gates it).**
- **Brief B** (the sport-exclusion ruling that supersedes #322 for the metabolic deposit): not touched, by design.
  It is its own brief.
- **Q190** (two devices, one session: source-wins and overlap dedupe) is adjacent to this work. It was not touched;
  its verify step is still owed.
- **Q153** (`_SOURCE_RANK` branch deletion) and **Q161** reader audit follow-ups: untouched.
- **Nightly sweep scope for Polar-only users:** recorded in #353, not changed. It needs a ruling only if such a user
  exists.
- **Appointment brief PR2**, **Q181 / brief 2**, **Q182–Q184**, **Q191**: untouched.
- **Interpretation layer increments 2, 3 and 5; lab pipeline residuals (Q104):** untouched.
- This session broke the #345–#352 run of appointment-brief sessions. It went to See / Loop freshness, which the
  brief-first sequencing does not rank above Walk in.

**Single clearest next action.** Operator: record a Polar session and do not press Sync. Open the Training page and
confirm the session appears with zones and a metabolic bar. The startup sweep has already shown `polar_synced=` in
prod; the scheduled 02:00 run is still to be seen. Before Thursday, print the 1 Oct brief.
