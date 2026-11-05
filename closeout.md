# Close-out — 5 Nov 2026: R8 ruling record (design 0010 `committed`; `DECISIONS_LOG` #503, #504; PR GH#638)

## Real commits this session

Session opened at health-app master `28181dc` (the merge of PR 637, the previous close-out), the anchor the brief
named. Maxima at open: `DECISIONS_LOG` #502, no open `fork` issue. At close: #503 and #504 on the branch (resolved at
master max #502; re-resolve if master advances before the merge), still no open `fork` issue, no issue filed or touched.

One harness-assigned branch, `claude/eloquent-bardeen-lk9soc`, one PR (GH#638), three commits:

| Commit | What |
|---|---|
| `89a3154` fix(hr_anchors): the restatement no-op test is on (value, provenance), not value alone; the card previews a same-value re-evidencing | `hr_anchors.plan` takes the provenance and refuses only when both value and provenance match the row it would correct; the preview route passes it; the plan carries `provenance`; the card's preview names a same-value restatement as a re-evidencing (old → new provenance, no band change). Two new pytest cases, one new vitest case. |
| `b838d6c` ui(hr-zones): R8 is ruled; the card's seed-date helper no longer reads "pending the operator's OK"; the read drops r8_pending | the card's helper text and comment; `zone_reads.zone_config` no longer carries `r8_pending`; the read test asserts its absence; the card test mock drops it. |
| the `gov(r8)` commit (this file rides it; it cannot name its own hash) | `DECISIONS_LOG` #503 (R8 ruled, one-way, operator) and #504 (ruling: the no-op test on (value, provenance)); design 0010 row 4 resolved and the doc `discussion` → `committed`, §1 R8 reworded, Decisions landed; the BRANCHES row for this branch and the previous row's Outstanding cell; the ROADMAP zone-model row; the CLAUDE.md Recent-landings pointer; this file. |

**Verified.** Backend `tests/test_hr_zones_config.py` 24 passed and `tests/test_hr_anchors_schema.py` 14 passed locally
(CI-style env: throwaway Fernet key, `SECRET_KEY`, `ALGORITHM`); frontend `HRZonesCard.test.jsx` 7 passed;
`scripts/check_governance_placeholders.py` exit 0. The brief's premise was checked live before the guard change: the MCP
`get_hr_zone_config` read (5 Nov 2026) shows LTHR 158 and RHR 51 seeded, both `observed`, from 2026-03-01, so the
operator's planned restatement (LTHR 158 @ 2026-03-01 → `device_estimated`) is exactly the same-value case the old guard
refused. No prod write by Code, no recompute, no anchor row or load data touched, no migration.

**Merge disposition.** The one-way content of R8 (the seed-date default) landed on master in PR 636; this PR records the
operator's explicit ruling and carries the two-way guard fix, so it self-merges on green under § Merge disposition. The
merge SHA and the deploy check (#491, both services: `backend/` and `frontend/` changed) are reported in the session's
final message, not here (this file is written before the merge).

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief
`R8 Ruling Record - Echo Bike Zones Review`; each step against where it landed:

- **ANCHOR** — master HEAD `28181dc` as stated; verified before any edit.
- **Close row 4 of design 0010** — DONE (the `gov(r8)` commit): status `resolved: the operator ruled YES, 2026-11-05 (no
  earlier threshold data); #503`.
- **Move the doc state if no other rows are open** — DONE: `discussion` → `committed`. The brief says "accepted"; the
  state vocabulary in `CLAUDE.md` is ideation / discussion / committed / abandoned, and `CLAUDE.md` wins, so `committed`.
  Row 6 is a filed `build` pointer (GH#634), not an open question, so nothing else held the doc.
- **Remove the "pending the operator's OK" wording from the card** — DONE (`b838d6c`), with the `r8_pending` flag on the
  read removed in the same commit (the same pending status, one surface further back). The `r8-note` test id and the
  "R8" mention stay: the note still tells the operator where the default comes from.
- **GUARD: no change to anchor rows or load data** — held: nothing in this PR writes `user_hr_anchors`, `aerobic_sessions`
  or `load_events`; no migration.
- **Decision number resolved at merge** — #503 and #504 resolved against master max #502 at `28181dc`; re-resolve if
  master advances before the merge (the strict-mode pause, § Merge path).
- **One gov(...) commit; UI copy in its own commit** — as laid out above (three commits: fix, ui, gov).
- **ADDITIONAL STEP: the restatement guard on (value, provenance)** — DONE (`89a3154`, ruling #504). The brief says "in
  the API and the card"; the card was verified to carry no guard of its own (it relays the API's 400), so the API change
  is the whole fix and the card's change is the preview line that makes a same-value re-evidencing legible.
- **After it lands, the operator restates LTHR 158 @ 2026-03-01 as `device_estimated`** — OWED (operator), after the
  deploy check; recorded in the BRANCHES and ROADMAP rows.
- **Provisional:** nothing. Everything decided is committed; the merge and the deploy check follow in-turn.

## Cold-resume handoff

**Current sprint (ROADMAP NOW).** Zone model: DONE and seeded; R8 ruled (#503); the restatement guard fixed (#504); OWED
(operator): the LTHR restatement to `device_estimated` and an Echo bike Z2 ride read on its card; OWED (Code): the first
chain report's `polar_rezoned` / `polar_vendor_fallback` counts. Ledger UX follow-ups (GH#622 to GH#629): PR-A and the
ruling landed 5 Nov; the rest UNSTARTED. Coach ledger writes (GH#612 to GH#617): UNSTARTED. Injury lifecycle in-app
(design 0009): branches landed; its remaining rows unchanged. Wake-day capture: DONE, three-morning gate OWED. The other
NOW rows are OWED to the operator or Code as their cells say and did not move.

**v1 triage of NOW.** Zone model — See (a Z2 ride reads and deposits as Z2) and Know (the conditioning quota counts load
the device agrees with). Ledger UX, coach ledger writes, injury lifecycle — Know and Walk in. Wake-day capture and lane
visibility — Loop. Missed-PM catch-up, data freshness, plan/schedule tools — Loop / See, DONE and riding for their owed
checks. RPE fallback (Q231) — See, OWED (Code once the gate opens). Source hierarchy (#365) and the Polar relabel limbs —
OWED (Luke), serving See / Know; neither moved this session and neither is a demotion candidate: each waits on a named
operator act.

**Open `fork` issues.** None.

**Design docs not in a terminal state.** 0001, 0002, 0004, 0005 (Q213 still open), 0006, 0007, 0008, 0009. 0010 is now
`committed` (this session). 0000 is the template.

**Branch gate.** `origin` holds `master` and `claude/eloquent-bardeen-lk9soc` only (the latter `+2` by `git cherry`
before the gov commit; rowed DONE in `BRANCHES.md` against PR GH#638, self-merged in-turn, branch deleted at merge). No
`BRANCHES.md` row carries OWED or BLOCKED status, so the Q138 sweep for landed-but-unflipped rows is empty.

**Not touched this session (named so it is not read as finished).** This was a governance-and-one-fix session: no feature
work. The ledger UX defects GH#623 to GH#629 and the coach ledger writes GH#612 to GH#617 stood still; the RPE fallback
(Q231), the source hierarchy ruling (#365), the Polar relabel limbs, the appointment reconcile leg, the three-morning
wake-day gate, the single-row HC bout deposit read (#384 item 4), GH#634 (Polar sample ingest) and GH#635 (Garmin
time-in-zone cross-check) — all unchanged, all gated on the operator acts or capacity their rows name. The first chain
report after the seed (`polar_rezoned` / `polar_vendor_fallback`) has still not been read by Code: it needs the prod
container (`railway ssh`), which this cloud session does not have. Two consecutive sessions on the zone model have now
gone to the model and its governance; the instrumented thing — a Z2 ride on the Echo bike reading as Z2 on its card —
is still an operator read that has not been reported back. No companion-app (`health-connect-app`) work.

**The single clearest next action (operator).** Once GH#638's deploy check is green on both services: Settings → Heart
rate zones, LTHR, 158 bpm, date 2026-03-01, provenance device-estimated, change = Restatement, rationale naming the
Garmin auto-detect; the preview should read "0 sessions re-zone · restates the 158 bpm entry (observed)" with the
re-evidencing line "observed → device_estimated"; Save. The LTHR line then reads `device_estimated` with the retest flag,
on the card and in the MCP `get_hr_zone_config` read. Then open an Echo bike Z2 ride on its card and report what the
provenance line and the bar show.

**Second action (Code, next session with prod access).** Read the first chain report's `polar_rezoned` /
`polar_vendor_fallback` counts and record them against #502.
