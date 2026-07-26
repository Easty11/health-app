# closeout — health-app

_Latest Code session handoff. Overwritten each `/closeout`. Canonical history:
`DECISIONS_LOG.md`. Forward work: `ROADMAP.md`._

Session date: 2026-07-26.

## Real commits this session

Session-open ref: `2662729` (#125 close-out). `git log --oneline 2662729..HEAD`:

```
7809dfe governance: DECISIONS_LOG #127 — recall-only adherence & capture; resolve Q47
c1b4cb8 feat(capture): recall-only lights_out — drop the Samsung prefill default (#127)
a00eeba feat(engine): recall-only adherence — drop the samsung_bedtime arm (#127)
2f47327 governance: DECISIONS_LOG #126 — block 3 opening-rx operator correction
5237a82 seed: operator correction to block 3 opening prescription (supersede id=10)
```

Immutable commit dates (`git log --format="%ad %s" --date=short -10`):

```
2026-07-26 governance: DECISIONS_LOG #127 — recall-only adherence & capture; resolve Q47
2026-07-26 feat(capture): recall-only lights_out — drop the Samsung prefill default (#127)
2026-07-26 feat(engine): recall-only adherence — drop the samsung_bedtime arm (#127)
2026-07-26 governance: DECISIONS_LOG #126 — block 3 opening-rx operator correction
2026-07-26 seed: operator correction to block 3 opening prescription (supersede id=10)
2026-07-25 chore: session close-out — daily notes (#125) landed and verified
2026-07-25 governance: CLAUDE.md recent-landings — prepend #125
2026-07-25 governance: DECISIONS_LOG #125 — free-text AM/PM notes on the daily record
2026-07-25 feat: free-text am_notes / pm_notes on the daily record, both check-in surfaces
2026-07-24 chore: session close-out
```

Two concern-named branches, both ff-merged to master and remote + local deleted:

- `seed/cbti-block3-rx-correction` → `5237a82`, `2f47327` (landed; deploy `8420d396` SUCCESS)
- `fix/cbti-recall-only` → `a00eeba`, `c1b4cb8`, `7809dfe` (landed; deploy `8a8d934b` SUCCESS,
  served instance content-probed — `RECALL-ONLY (#127)` present in both files, old
  `if night.samsung_bedtime:` branch absent)

**Prod DB write** (runtime effect, not in git — the committed artifact is
`backend/correct_cbti_block3_rx.py`): applied in-container via `railway ssh`, dry-run then
`--apply`. `cbti_prescriptions`: inserted **id=11** (block 2, 22:30→05:00, window 390,
`decision='adopt'`, `effective_from` 2026-07-27, `basis_*` NULL); set **id=10**
`effective_to`=2026-07-26 and `superseded_by`=11 (every other column frozen). `cbti_blocks`
id=2 unchanged (`wake_anchor` 05:45, append-only invariant upheld). Read-back confirmed all
three rows. Full backend suite 406 passed.

## Pending-queue reconciliation

No `;cc` pending-commit queue was carried into this session — it ran from a live brief, not a
chat close-out payload. The brief specified "Decisions minted at merge, not here," honoured.
Brief steps → disposition:

- **V1** (verify basis boundary before S1) — answered, no commit. Basis is cycle-windowed and
  the prescription tracks in lockstep; not block-bounded, so the GUARD did not halt.
  Corrected in-session: the clearance is narrow — safe to WRITE tonight, but the replay
  regenerates the chain from row zero and would false-HOLD a mid-cycle correction (filed Q49).
- **S1** (prescription correction) — LANDED: `5237a82` (seed script) + prod write
  (id=11 supersedes id=10) + `2f47327` (#126 governance + Q49).
- **S2** (drop samsung adherence arm) — LANDED: `a00eeba`.
- **S3** (drop lights_out prefill) — LANDED: `c1b4cb8`.
- **S4** (lag query) — read-only, no commit by design. Result (n=2 matched nights, sensor−diary
  mean +3.5 min — too thin; the export's own `bedtime_detection_delay` p50 14 / n=211 is the
  real distribution) folded into `7809dfe` (#127) and Q47's resolution.

Nothing provisional; all decided work committed. Q47 marked DONE → #127; Q49 opened UNSTARTED.

## Cold-resume handoff

**Decisions minted this session:** #126 (block-3 opening-rx operator correction, append+supersede;
block row left at 05:45), #127 (CBT-I adherence & capture are recall-only — samsung adherence arm
and the AM `lights_out` prefill default both removed; resolves Q47).

**Current sprint (ROADMAP NOW):**

- **CBT-I evaluation path — HARD-GATED by Q49 (NEW blocker, ahead of ~31 Jul):** the
  replay/evaluation must read the effective prescription per cycle from `cbti_prescriptions`
  instead of regenerating from row zero (and must take the wake anchor from the effective
  prescription, not `cbti_blocks`). Block 3's mid-cycle correction (#126) is invisible to the
  current replay, which would FALSE-HOLD cycle 1 on adherence. **This gates the ~31 Jul manual
  evaluation trigger** — running an evaluation against the current evaluator is wrong.
- **CBT-I manual witnessed evaluation trigger** (#118's PM-offer half) — DATED ~31 Jul (first
  titration cycle; block 3 opened 24 Jul). Build after / together with Q49.
- **Q45 nap day-attribution** — DATED, contaminating capture now: validate the `naps_min`
  date−1 read against the VA protocol before the engine relies on it.
- Lab upload pipeline → interpretation layer → appointment brief (medical spine; design Locked,
  build pending).
- **Cross-repo:** propagate the CLAUDE.md shared block (incl. #111 secret-rendering rule) to
  `health-connect-app` — OWED, from an HCA-rooted session.

**Open questions by status (CBT-I-relevant):**

- **UNSTARTED:** Q49 (replay reads effective prescription — blocker on first evaluation),
  Q45 (nap attribution, dated), Q46 (device-vs-diary basis provenance), Q48 (settling period —
  instrument exists, block 3 accumulating).
- **DONE this session:** Q47 → #127 (samsung adherence-lag flip, resolved on principle by
  recall-only).
- Older live items unchanged: Q3, Q4, Q42, and the rest of the OPEN_QUESTIONS live list.

**Single clearest next action:** Cut a fresh branch from master and fix **Q49** — make the
evaluation path (`cbti/replay.py`, and the forthcoming manual trigger) read the effective
prescription (window, lights-out, wake anchor) per cycle from `cbti_prescriptions`, not
regenerate from row zero. It is the hard dependency ahead of the ~31 Jul evaluation trigger;
until it lands, do NOT run a block-3 replay/evaluation — the first clean post-correction cycle
will false-HOLD on GATE 2 adherence.
