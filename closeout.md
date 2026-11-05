# Close-out — 6 Nov 2026: zone coverage read (`DECISIONS_LOG` #505; PR GH#639)

## Real commits this session

Session opened at health-app master `1f77d6f` (the merge of PR GH#638, the previous close-out), the anchor the brief
named. Maxima at open: `DECISIONS_LOG` #504, no open `fork` issue. At close: #505 on the branch (resolved at master max
#504; re-resolve if master advances before the merge), still no open `fork` issue, no issue filed or touched.

One harness-assigned branch, `claude/laughing-goldberg-7i7ozv` (accepted per #387 in place of the brief's
`claude/zone-coverage-read`; the harness forbids pushing to any other name), one PR (GH#639, ready-for-review), three
commits:

| Commit | What |
|---|---|
| `dc4d861` feat(zones): MCP get_zone_coverage reads how every aerobic row is zoned, per source, derived live from row_zoning | `reads/zone_reads.zone_coverage` (every raw row classified by `row_zoning`, anchors read once, read-only), `coverage_category`, `format_zone_coverage`; the tool in `mcp_server.py`; the read-door guard's reason line for `reads/zone_reads.py`; `tests/test_zone_coverage.py` (12). |
| `d16fd01` docs(zones): SCHEMA §051 Readers and design 0010 §6 name the MCP get_zone_coverage tool | The two places the MCP zone tool was already listed; there is no single MCP tool list in the tree. |
| the `gov(zone-coverage)` commit (this file rides it; it cannot name its own hash) | `DECISIONS_LOG` #505 (ruling); the ROADMAP zone-model row; the CLAUDE.md Recent-landings pointer (the #501 pointer dropped under the cap of 3); the BRANCHES row for this branch and the `confident-shannon` row's outstanding cell; this file. |

**Verified.** Step 1 of the brief, reported before any code: (1) the chain report from `hc_zone_enrich.enrich_user` is
returned and printed only (`scripts/refresh_load.py` summary, `routers/load.py` response body, `load_sweep.py` log
brief), never stored; (2) `row_zoning` returns basis in {lthr, hrr, vendor, None} and reason in {no_anchor,
polar_vendor_fallback, withheld, None}, with the one nuance that a Polar row with no anchor reads basis `vendor` and
reason `no_anchor` (the coverage read classifies by reason first, so `vendor` equals `polar_vendor_fallback` exactly);
(3) the tool pattern is `@mcp.tool()` over `@_stamped`, `SessionLocal` plus the `zone_reads` read and its formatter.
Step 2's VERIFY: `zone_coverage` has no Polar branch of its own; a spy test pins every row, Polar included, to one
`row_zoning` call. `tests/test_zone_coverage.py` 12 passed; the full backend suite 4513 passed, 4 skipped, 1 xfailed
with `tests/test_current_state.py` excluded (the known shallow-clone `git show`); `scripts/check_governance_placeholders.py`
exit 0. No prod write by Code, no recompute, no anchor row or load data touched, no migration.

**Merge disposition.** Two-way door, no migration: the PR self-merges on green under § Merge disposition. The merge
SHA and the `deploy-check` run (#491: backend SUCCESS owed, frontend SKIPPED expected, only `backend/` changed) are
reported in the session's final message, not here (this file is written before the merge).

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief
`Zone Coverage Read - Echo Bike Zones Review`; each step against where it landed:

- **ANCHOR** — master HEAD `1f77d6f` as stated; verified before any edit. The branch is the harness-assigned name,
  not `claude/zone-coverage-read` (accepted per #387; the PR title and the BRANCHES row carry the meaning).
- **Step 1 VERIFY** — DONE, the three results reported before code (above).
- **Step 2 read function** — DONE (`dc4d861`): per source the count per category, totals, the date range, up to 20
  `vendor` / `no_anchor` / `withheld` rows (id, date, sport, source, reason, plus the basis), anchors read once, no
  writes. Classification calls `row_zoning` for every row; no second Polar implementation (the spy test).
- **Step 3 MCP tool** — DONE (`dc4d861`): `get_zone_coverage(days: int | None = None)`, formatted in the
  `get_hr_zone_config` style, ending with one line naming where the counts come from.
- **Step 4 guards** — DONE: the read-door allow-list test and the MCP stamp test are green. The guard is keyed by
  file and `reads/zone_reads.py` was already listed, so no new entry was required; its reason line said "never a
  count", which the coverage tally would have made false, so the line was extended to say why every raw row is
  fetched (the fill's own worklist, twins included).
- **Step 5 tests** — DONE: the seven listed cases plus the formatter, the category function, the spy and the MCP
  mirror of `test_mcp_recent_sessions.py`'s fixture; full backend suite green except the excluded shallow-clone test.
- **Step 6 docs** — DONE (`d16fd01`): no single MCP tool list exists in `CLAUDE.md` or `docs/`; the tool is named
  where `get_hr_zone_config` already was (SCHEMA §051 Readers, design 0010 §6). The docstring says read-only and
  derived.
- **Step 7 commits and merge** — the three concern-split commits as laid out; PR GH#639 opened ready-for-review;
  the merge, the merge commit and the `deploy-check` run id and status follow in-turn in the final message.
- **LOG entry** — landed as #505 in the ruling tier (`**Tier:** ruling`, Decision, Reverse-by), not the brief's
  five-field draft: `CLAUDE.md` says a ruling is two lines and `CLAUDE.md` wins; the Status and How-you-know content
  is folded into the Decision paragraph, as #504 did. Dated 2026-11-06 as the brief dates it.
- **Post-deploy gate** — OWED (chat): the operator asks chat to call `get_zone_coverage`; chat confirms the
  `polar_rezoned` / `polar_vendor_fallback` counts. Recorded in the ROADMAP and BRANCHES rows as chat's, not Code's.
- **Provisional:** nothing. Everything decided is committed; the merge and the deploy check follow in-turn.

## Cold-resume handoff

**Current sprint (ROADMAP NOW).** Zone model: DONE and seeded; R8 ruled (#503); the restatement guard fixed (#504);
coverage readable from chat (#505, this session). OWED (operator): the LTHR restatement to `device_estimated` and an
Echo bike Z2 ride read on its card. OWED (chat): the `get_zone_coverage` read after this deploy. Ledger UX follow-ups
(GH#622 to GH#629): PR-A and the ruling landed 5 Nov; the rest UNSTARTED. Coach ledger writes (GH#612 to GH#617):
UNSTARTED. Injury lifecycle in-app (design 0009): branches landed; its remaining rows unchanged. Wake-day capture:
DONE, three-morning gate OWED. The other NOW rows are OWED to the operator or Code as their cells say and did not move.

**v1 triage of NOW.** Zone model — See (a Z2 ride reads and deposits as Z2) and Know (the conditioning quota counts
load the device agrees with); this session instruments the See test's evidence path (coverage from chat) rather than
the ride itself. Ledger UX, coach ledger writes, injury lifecycle — Know and Walk in. Wake-day capture and lane
visibility — Loop. Missed-PM catch-up, data freshness, plan/schedule tools — Loop / See, DONE and riding for their
owed checks. RPE fallback (Q231) — See, OWED (Code once the gate opens). Source hierarchy (#365) and the Polar relabel
limbs — OWED (Luke), serving See / Know; neither moved this session and neither is a demotion candidate: each waits on
a named operator act.

**Open `fork` issues.** None.

**Design docs not in a terminal state.** 0001, 0002, 0004, 0005 (Q213 still open), 0006, 0007, 0008, 0009. 0010 is
`committed`. 0000 is the template.

**Branch gate.** `origin` holds `master` and `claude/laughing-goldberg-7i7ozv` only (the latter `+2` by `git cherry`
before the gov commit; rowed DONE in `BRANCHES.md` against PR GH#639, self-merged in-turn, branch deleted at merge). No
`BRANCHES.md` row carries OWED or BLOCKED status, so the Q138 sweep for landed-but-unflipped rows is empty.

**Not touched this session (named so it is not read as finished).** This was a read-tool session: no feature work on
the zone model itself, no anchor, no recompute. The ledger UX defects GH#623 to GH#629 and the coach ledger writes
GH#612 to GH#617 stood still; the RPE fallback (Q231), the source hierarchy ruling (#365), the Polar relabel limbs, the
appointment reconcile leg, the three-morning wake-day gate, the single-row HC bout deposit read (#384 item 4), GH#634
(Polar sample ingest) and GH#635 (Garmin time-in-zone cross-check) — all unchanged, all gated on the operator acts or
capacity their rows name. Three consecutive sessions on the zone model have now gone to the model, its governance and
its instrumentation; the instrumented thing — a Z2 ride on the Echo bike reading as Z2 on its card — is still an
operator read that has not been reported back. No companion-app (`health-connect-app`) work.

**The single clearest next action (operator).** Once GH#639's deploy check is green on the backend: ask chat to call
`get_zone_coverage` (all history, then `days=30`) and report the Polar line (`polar_rezoned` / `polar_vendor_fallback`)
and the `health_connect` line; then the standing items: the LTHR restatement to `device_estimated` through the card,
and an Echo bike Z2 ride opened on its card with what the provenance line and the bar show.
