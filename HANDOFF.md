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

2026-07-19 11:20 AEST | CODE→CHAT | Q17 resolved on (A); minted #NEXT→#89 at merge (master max was #88; `feat/checkin-injury-probe` local #89–90 hardcodes renumber at their own merge). Q29 minted (PENDING). `feat/recovery-metrics-rhr` UNSTARTED. Landing `fix/q17-hrv-instrumentation` to master; SHA in closeout. **Step 5 (HCA #19→Q29 pointer) DEFERRED** to an HCA-rooted session per single-repo rule — a ready-to-paste HCA #20 entry was emitted to chat; not written here. Re-sync OPEN_QUESTIONS, BRANCHES, DECISIONS_LOG, HANDOFF from disk.
2026-07-19 11:07 AEST | CHAT→CODE | Q17 instrumentation-close brief received. Step 1 evidence adjudicated 4/4 CONFIRMED vs HCA master (`1db8833`/#19). Writing on `fix/q17-hrv-instrumentation`: resolve Q17 → (A); mint Q29 (phantom-stale reconciliation, install-segmentation prerequisite — brief's "Q5" was a stale-mirror mis-ref, real Q5 is dual-field acceptance); `feat/recovery-metrics-rhr` BLOCKED→UNSTARTED; DECISIONS #NEXT. HCA #19 pointer (step 5) HELD for confirmation — cross-repo write.
2026-07-19 10:01 AEST | CODE→CHAT | #88 governance built on gov/interruption-survival (unseeable-surface rule, state vocabulary, HANDOFF ledger, close-out git-log emission); landing to master. Re-sync CLAUDE.md ×2, FEEDBACK, DECISIONS_LOG, BRANCHES, HANDOFF from disk; master SHA in closeout.
2026-07-19 09:44 AEST | CHAT→CODE | Interruption-survival governance brief received — 4 changes, one concern (→ #88 at merge). Received, not started.
2026-07-19 09:02 AEST | CODE | #87 landed (eed3c76) — oracle fixture group display_name re-sync.
