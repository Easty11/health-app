# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`. Interruption ledger: `HANDOFF.md`._

2026-07-20 · governance view generator (#94)

## 1. Real commits this session

Session-open ref: `9ec0f2b`. Landed on `master` at **`b4e18ecc8d8cad3d8e34614a9e923c8d406c5f1d`**, pushed.

```
b4e18ec gov: DECISIONS_LOG #94 + FEEDBACK §16 — generated view supersedes the hand-assembled mirror
869fffd feat(scripts): generate the consolidated governance view from master
2cb04e9 gov(handoff): record the 10-hour timestamp error, append-only
cf03197 gov(handoff): receipt — governance view generator brief received, not started
```

Repo's own dated record (`git log --format="%ad %s" --date=short -10`):

```
2026-07-20 gov: DECISIONS_LOG #94 + FEEDBACK §16 — generated view supersedes the hand-assembled mirror
2026-07-20 feat(scripts): generate the consolidated governance view from master
2026-07-20 gov(handoff): record the 10-hour timestamp error, append-only
2026-07-20 gov(handoff): receipt — governance view generator brief received, not started
2026-07-20 chore: session close-out
2026-07-20 gov: DECISIONS_LOG #93 — adoption completes at the frame; sweeps run definition-first
2026-07-20 gov(feedback): §14 occurrence 4 (the false PASS); mint §15
2026-07-20 gov(questions): correct Q25's stale limb; mint Q33 for the deferred shared block
2026-07-20 gov(branches): mirror HCA's header frame and four-state preamble
2026-07-20 gov(ritual): strike `parked` as a status verb from the closeout gate
```

Scope fence held: 4 files — `DECISIONS_LOG.md`, `FEEDBACK.md`, `HANDOFF.md`,
`scripts/gen_governance_view.py`. Zero `backend/`, `frontend/`, `alembic/`.
Backend suite **206 passed**, unchanged from the `9ec0f2b` baseline.

## 2. Pending-queue reconciliation

| Brief item | Outcome |
|---|---|
| Step 0 — HANDOFF receipt, committed alone | **LANDED** `cf03197` |
| Step 1 — `scripts/gen_governance_view.py`, 8 stores, 2 repos, raw at master | **LANDED** `869fffd` |
| Step 2 — match the existing format | **AMENDED MID-SESSION.** The format source was unreachable from Code; a digest format was specified instead |
| Step 3 — live provenance (SHA, highest decision, timestamp) | **LANDED**, five columns |
| Step 4 — gitignored output at `build/` | **LANDED.** No `.gitignore` change was needed — `build/` was already ignored (twice, lines 10 and 30) |
| Step 5 — gitignore entry, #94, ff-merge, push, delete, `/closeout` | **DONE**. Merge `9ec0f2b..b4e18ec`, branch deleted |
| `FEEDBACK` §16 | **LANDED** `b4e18ec` |

### Deviations from the brief, all deliberate

1. **Anchors are `github.com/blob/<sha>#L<n>`, not raw URLs.** `raw.githubusercontent.com` serves
   plain text and supports no line anchors, so a raw link cannot jump to an entry. Fetching still
   uses raw, as specified; only the clickable anchor differs.
2. **Provenance carries five columns** — the brief said "same five columns" above a four-column
   example. Added **Highest decision**, which step 3 requires live.
3. **ROADMAP emits all sections and both row forms**, not `NOW`/`NEXT`/`LATER` tables. HCA uses none
   of those section names and uses bullets, not tables.
4. **334 → 337 lines, against a 800–1200 target.** One line per entry is what the digest spec
   produces. Reported rather than padded; the lever, if wanted, is a second line per decision.

### Two parser defects that passed a clean first run

Both exited 0 and printed a tidy summary. Neither crashed; both produced a confident wrong number.

- **FEEDBACK reported 52 entries for a 15-section store.** A lenient `#{2,3}` heading match swept in
  health-app's `### 1.1` / `### 2.6` subsections. Caught by checking the count against the store.
- **HCA's ROADMAP reported 4 rows.** HCA uses bullet lists where health-app uses tables; a table-only
  parser dropped its entire Now / Work queue / Phase 2 / UI debt content and kept 4 rows from an
  unrelated stats table.

The script now asserts every parser matched ≥1 entry, asserts a fetch size floor, and gates each
store's emitted line count against its parsed entry count — so this class fails loudly.

### A defect found outside the brief: Git Bash ignores `TZ` on this machine

`TZ='Australia/Brisbane' date` returns `10:44 GMT` — UTC, mislabelled — while true local is `+1000`.
Both `CHAT→CODE` receipts written this conversation are stamped **10 hours early** (`09:50` / `10:24`
should read `19:50` / `20:24`). Corrected by **appending** a `CODE` entry, not by editing: the ledger's
header says "Append-only. Never edit or delete an existing line." The in-place fix was made, then
reverted once that rule was re-read. Entries predating this session are left unmarked — this session
did not write them and cannot attest how they were produced, though any made the same way share the
error. The generator now stamps a numeric UTC offset, which neither Windows' verbose `%Z` nor Git
Bash's TZ fallback can misrender.

## 3. Cold-resume handoff

**Branch:** `master` @ `b4e18ec` (+ this close-out), pushed, clean. Untracked stray:
`.claude/launch.json` (known).

**The generated view.** `python scripts/gen_governance_view.py` → `build/CONSOLIDATED_GOVERNANCE_VIEW.md`
(gitignored, never committed). Regenerated **after** the ff-merge so its provenance names a commit that
contains the generator that produced it: `health-app master @ b4e18ec #94` / `health-connect-app master
@ 36a8444 #21`. 337 lines / UTF-8 / LF / zero CR bytes.

| Check | Result |
|---|---|
| Digest lines == parsed entries, per store | health-app 94/33/16/27; HCA 21/11/12/30 — gated in-script |
| Decision gap check (highest == count) | passes silently, both repos |
| Structure | banner runs exactly 60 `═`, 1 blank before / 3 after; 8 `─── STORE: ───` separators |
| Encoding | UTF-8, LF, 0 CR bytes |
| Backend tests | 206 passed, unchanged |
| Shared block G1 | `4243c91ce78e0331ddfa5178aa3006b8` / 155 / 10232 — untouched |

**Branch terminal-state gate — passes.** Only `gov/consolidated-view-generator` was touched this
session (ff-merged, deleted; never pushed, so no remote ref). The four pre-existing locals all carry
`+` commits and all are rowed in `BRANCHES.md`:

```
feat/checkin-injury-probe          2 +   rowed, pushed
feat/feedback-ledger               4 +   rowed, pushed
feat/interpretation-view-skeleton  3 +   rowed, pushed
feat/recovery-metrics-rhr          1 +   rowed (UNSTARTED), local-only by design
```

**Open questions by status** — 33 total: 15 UNSTARTED · 11 DONE · 5 OWED · 2 BLOCKED. None minted this
session.

**OWED, cross-repo — carried from #93, not yet discharged.** `health-connect-app` **Q11** names the two
items #93 landed and should close **`DONE → #93`** from an HCA-rooted session; its "HCA is authoritative
… in the interim" clause lapses. Still open there: HCA **Q9 item 1** (`ROADMAP.md` work queue carrying
`RESOLVED` / `parked` / `Blocked on`) and HCA **Q10** (ritual ANCHOR's declarative mood).

**OWED — Q33**, the one struck-vocabulary instance left standing: `CLAUDE.md:128` here and `:116` in
HCA, inside the G1-fingerprinted shared block. Needs its own brief with a mirror-first plan and a G1
re-fingerprint on both sides.

**OWED, unchanged, owner Luke** — both blocked on Anthropic API credit, to be run in one pass:
`probe_resolver.py` container run, and `hevy-resolver-activation` limb 2 (a live chat request naming a
nonsense movement; confirm the routine is refused and the unresolved title is named back).

**Single clearest next action:** run `python scripts/gen_governance_view.py` and replace the project-
knowledge copy of `CONSOLIDATED_GOVERNANCE_VIEW.md` wholesale from `build/`. That retires the
hand-assembled mirror in the place it actually causes harm — the project view chat reads. Until it is
replaced, the stale `#34` / `#15` copy is still what chat sees.
