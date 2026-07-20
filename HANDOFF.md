# HANDOFF — interruption-survival ledger

One append-only ledger of session handoffs, so a session interrupted mid-crossing is
resumable from the repo alone — without reconstructing state from chat scrollback. One
ledger, not two.

**Append-only. Never edit or delete an existing line** — only add new lines, at the top of
the list below the header (newest first).

Format: `YYYY-MM-DD HH:MM AEST | LANE | one line`
Lanes: `CHAT→CODE` · `CODE→CHAT` · `CHAT` · `CODE` · `LUKE`. Code writes every entry.

The `CHAT→CODE` receipt is written before any work begins and states received-not-started —
that entry is the one that survives an interruption, so it must not wait for the work. Other
entries may ride the next substantive commit.

---

2026-07-20 20:51 AEST | CODE | **Timestamp correction, not a restatement.** The two `CHAT→CODE` receipts below stamped `09:50` and `10:24` are each **10 hours early**; true local times were `19:50` and `20:24 AEST (+1000)`. Cause: Git Bash on this machine silently ignores `TZ` — `TZ='Australia/Brisbane' date` returns UTC and mislabels it (`10:44 GMT`), while the real local zone is `+1000`. Left in place per this ledger's append-only rule; corrected here rather than edited above. Any prior entry produced the same way carries the same error — unverified for entries predating 2026-07-20 19:50, which this session did not write. `scripts/gen_governance_view.py` now stamps a numeric offset, which neither Windows' verbose `%Z` nor Git Bash's TZ fallback can misrender.
2026-07-20 10:24 AEST | CHAT→CODE | Governance view generator brief received — `scripts/gen_governance_view.py` reading 8 stores across 2 repos at master via raw.githubusercontent, live provenance block, gitignored output (→ #94 at merge; DECISIONS max #93 and FEEDBACK max §15 both verified at open). Received, not started. **Format source `/mnt/project/CONSOLIDATED_GOVERNANCE_VIEW.md` is not reachable from Code — step 2 and the Gate-4 comparison are blocked on Luke supplying it.**
2026-07-20 09:50 AEST | CHAT→CODE | Return trip 2 brief received — Q25 close, FEEDBACK §14 append, ritual line 34, BRANCHES header pair (→ #93 at merge). Received, not started.
2026-07-20 07:55 AEST | CHAT→CODE | Vocabulary reconciliation brief received — strike CLAUDE.md line-60 status clause, sweep OPEN_QUESTIONS to four states, correct #90 gate claim via #91 (→ #91 at merge; master max confirmed #90 at line 2384, FEEDBACK max §13). Received, not started.
2026-07-20 07:38 AEST | CODE→CHAT | Session closure sweep Phase 1 LANDED to master at `05f0282` — minted **#90**, not #89 (master max was already #89; brief assumed #88). BRANCHES: all 22 rows four-state (11 DONE / 10 OWED / 1 UNSTARTED); 3 branches pushed to origin with dedicated rows + renumber debt recorded. Step-4 verdicts: hevy-exercise-template-resolver DONE, hevy-resolver-activation **OWED** (limb 2 — nonsense→refused — is a distinct path, never run), connector-error-policy **OWED** (brief's "See-all verified live" had no artifact — chat asserted an unseeable surface), probe-harness-fidelity + hrv-sleep-integrity Task 3 OWED. OPEN_QUESTIONS: 18 open / 1 verifying / 10 resolved — the brief's "no unresolved entries" was WRONG. FEEDBACK §13 added. 206 tests, unchanged. **Phase 2 (HCA) NOT started** — recorded OWED in #90 rather than asserted done. **Open for decision:** CLAUDE.md contradicts itself — canonical-stores row assigns open/verifying/resolved to OPEN_QUESTIONS, #88's vocabulary section says the four states apply to it; left unresolved because that text is in the verbatim-propagated shared block. Re-sync BRANCHES, OPEN_QUESTIONS, ROADMAP, DECISIONS_LOG, FEEDBACK, HANDOFF from disk.
2026-07-19 12:08 AEST | CHAT→CODE | Session closure sweep brief received — branch terminal states, vocabulary propagation, loop adjudication (→ #90 at merge; master max already #89, brief assumed #88 — next free number taken per PRECONDITION). Received, not started.
2026-07-19 11:20 AEST | CODE→CHAT | Q17 resolved on (A); minted #NEXT→#89 at merge (master max was #88; `feat/checkin-injury-probe` local #89–90 hardcodes renumber at their own merge). Q29 minted (PENDING). `feat/recovery-metrics-rhr` UNSTARTED. Landing `fix/q17-hrv-instrumentation` to master; SHA in closeout. **Step 5 (HCA #19→Q29 pointer) DEFERRED** to an HCA-rooted session per single-repo rule — a ready-to-paste HCA #20 entry was emitted to chat; not written here. Re-sync OPEN_QUESTIONS, BRANCHES, DECISIONS_LOG, HANDOFF from disk.
2026-07-19 11:07 AEST | CHAT→CODE | Q17 instrumentation-close brief received. Step 1 evidence adjudicated 4/4 CONFIRMED vs HCA master (`1db8833`/#19). Writing on `fix/q17-hrv-instrumentation`: resolve Q17 → (A); mint Q29 (phantom-stale reconciliation, install-segmentation prerequisite — brief's "Q5" was a stale-mirror mis-ref, real Q5 is dual-field acceptance); `feat/recovery-metrics-rhr` BLOCKED→UNSTARTED; DECISIONS #NEXT. HCA #19 pointer (step 5) HELD for confirmation — cross-repo write.
2026-07-19 10:01 AEST | CODE→CHAT | #88 governance built on gov/interruption-survival (unseeable-surface rule, state vocabulary, HANDOFF ledger, close-out git-log emission); landing to master. Re-sync CLAUDE.md ×2, FEEDBACK, DECISIONS_LOG, BRANCHES, HANDOFF from disk; master SHA in closeout.
2026-07-19 09:44 AEST | CHAT→CODE | Interruption-survival governance brief received — 4 changes, one concern (→ #88 at merge). Received, not started.
2026-07-19 09:02 AEST | CODE | #87 landed (eed3c76) — oracle fixture group display_name re-sync.
