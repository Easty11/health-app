# Close-out — 5 Nov 2026: zone model build (design 0010; `DECISIONS_LOG` #502; GH#634, GH#635 filed; released and merged, `37bfdbd`; anchors not yet seeded)

## Real commits this session

Session opened at health-app master `66d69d3` (the merge of PR 633, the previous close-out). Maxima at open: `DECISIONS_LOG` #501, no open `fork` issue. At close: #502 on the branch (resolved at master max #501; re-resolve if master advances before the release lands), still no open `fork` issue, GH#634 and GH#635 filed (`build`).

One harness-assigned branch, `claude/confident-shannon-ch8hwv`, two PRs: PR 636 (the build; a one-way door, held until the operator said `merge`, then landed by Code end-to-end: merge `37bfdbd`, all checks green on `1d5e4c9`) and the post-merge docs-only flip from the restarted branch (this file, the BRANCHES and ROADMAP rows, the CLAUDE.md pointer).

| Commit | What |
|---|---|
| `5ad65a9` docs(design): 0010 threshold-anchored HR zones (per-class %LTHR / %HRR), R1 to R8 recorded; 0005 rows Q198, Q216 moved | the design doc (`discussion`; row 4 open on R8); 0005's Q198 and Q216 point at it |
| `345db8b` feat(schema): user_hr_anchors, the LTHR and RHR anchor store (migration e7b2a4c9d1f3, HELD for release); SCHEMA.md §051 | the sibling of `user_hrmax`: append-only, dated vs restatement, partial uniques, self-FK, closed provenance; `tests/test_hr_anchors_schema.py` (14) |
| `b3c252e` feat(hr_zones): per-class zone model, %LTHR for the cycling class and %HRR elsewhere, resolved over dated anchors | `ZoneSpec`, `zone_spec`, `resolve_zone_spec`, `anchor_in_force`, `no_anchor`; `sport_classes.LTHR_SPORTS` + `zone_basis_for`; provenance rows; `tests/test_hr_zones.py` (53) |
| `d63f531` feat(zones): the fill re-zones every row per class; Polar rows from the Polar Flow trace where it covers them, else vendor zones kept (R2) | `hc_zone_enrich` over every `aerobic_sessions` row, `POLAR_SAMPLE_WRITERS`, `polar_rezoned` / `polar_vendor_fallback` / `by_basis`; the G2 projection script takes anchors; `test_hc_zone_enrich`, `test_hrmax_prompts`, `test_hc_zone_projection` re-aimed and extended |
| `49575f2` feat(load): metab-v2, the metabolic formula version bumps with the zone model; retired-version rows removed; zoning basis in provenance (R1) | `FORMULA_VERSION_METABOLIC = "metab-v2"`, `RETIRED_METABOLIC_VERSIONS`, `zoning_basis` in each event's provenance |
| `ab6c8db` feat(api): zone config read, anchor preview and append with the forced choice, per-row zoning on sessions, MCP get_hr_zone_config (R6, R7) | `reads/zone_reads.py`, `hr_anchors.py`, `routers/hr_zones.py`, `AerobicSessionOut.zoning`, the MCP tool, the constant import in `mcp_server`; `tests/test_hr_zones_config.py` |
| `86db308` feat(settings): Heart rate zones card (bands, anchors, forced choice with bpm preview, Garmin mirror); one provenance line under the WorkoutPanel zone bar | `HRZonesCard.jsx` on Settings, `zoningLine` under `HRZoneBar`; `HRZonesCard.test.jsx` (6), `WorkoutPanel.zoning.test.jsx` (5) |
| `1d5e4c9` gov(zone-model): DECISIONS_LOG #502 (R1 to R8, rulings rows 1, 2, 3, 5); ROADMAP and BRANCHES rows; GH#634, GH#635 in design 0010; close-out | the governance batch of PR 636 |
| the post-merge `gov(zone-model-landed)` commit | the BRANCHES row to DONE, the ROADMAP row, the CLAUDE.md pointer, this file (a second PR; it cannot name its own hash) |

**Landed and verified.** PR 636 merged at `37bfdbd` (5 Nov 2026, after the operator's `merge`). `deploy-check` run 18 SUCCESS on `37bfdbd`; Railway backend deployment `4cd47a49` and frontend `c9c154c6` both SUCCESS matched on `commitHash`; the backend boot log shows `Running upgrade c4a8e2f6b190 -> e7b2a4c9d1f3`. No prod data write by Code, no recompute run by Code, no `user_hrmax` row written, edited or deleted. `user_hr_anchors` is empty. Tests: backend 4,508 passed locally with one pre-existing failure (`test_current_state` runs `git show 3360ed5:…`, which a shallow clone cannot see; CI checks out full depth), frontend 577 passed.

Tracker writes this session (outside the tree): GH#634 `build` (Polar per-second sample ingest, the R2 "samples not stored" branch), GH#635 `build` (Garmin per-activity time-in-zone ingest, R5).

## Pending-queue reconciliation

No `PENDING` item came in from a `;cc` chat close-out. The session was driven by the pasted brief `Zone Model Build - Echo Bike Zones Review`; each step against where it landed:

- **VERIFY** — every assertion held on master `66d69d3` (recorded in 0010's Context and #502's How-you-know). One nuance, not a mismatch: `hr_zone_config_snapshots` (SCHEMA §050) holds Garmin's LTHR / RHR as capture-only observation; nothing zoned from it and the operator cannot write it, so it is not an anchor store. It is now the Garmin mirror strip's input.
- **Step 1 consumer map** — in 0010's Context (writer / load / arbitration / report / display per use). The `mcp_server` literal `"metab-v1"` was a hidden consumer; it now imports the constant.
- **Step 2 classifier** — `backend/sport_classes.py` held two static sets (non-training, strength) and no cycling class; nothing else classifies sports except phase-scoped `device_sports`. `LTHR_SPORTS` added there under the same Q164 rule.
- **Step 3 Polar samples** — NOT stored (`hr_samples`: `health_connect` and `garmin` only). R2's fallback branch taken, GH#634 filed; and the "samples exist" read taken through the `fi.polar.polarflow` Health Connect trace (0010 row 1, a two-way ruling with its reverse-by in #502).
- **Step 4 design doc** — `docs/design/0010-threshold-anchored-hr-zones.md`, `discussion`.
- **Step 5 a–i** — all built, in the commits above. 5d "recompute wired to run after release": the existing chain (Training-page open, 02:00) plus the card forcing `POST /load/refresh?force=true` after each append.
- **R8** — pending the operator's OK; shipped as the card's editable default date, flagged in the card (`r8-note`), the read (`r8_pending`) and #502.
- **Gates** — no VERIFY mismatch; the migration and the recompute wait for the operator; the PR holds.
- **Not asked for, done anyway, two-way:** the G2 projection script (`arbitration_flip_report.py --hc-zones`) now resolves the per-class spec (DB anchors; `--lthr` / `--rhr` in CSV mode) so it still projects what the fill writes.
- **Provisional:** nothing. Everything decided is committed. The entry number #502 is provisional in one sense only: it was claimed at master max #501 and must be re-resolved if master advances before the release.

## Cold-resume handoff

**Current sprint (ROADMAP NOW).** Zone model: DONE (merged `37bfdbd`, deployed, migration applied); the anchors are not yet seeded, so the metabolic series is empty until the operator does. Ledger UX follow-ups (GH#622 to GH#629): PR-A and the ruling landed 5 Nov; the rest UNSTARTED. Coach ledger writes (GH#612 to GH#617): UNSTARTED. Injury lifecycle in-app (design 0009): branches landed; its remaining rows unchanged. Wake-day capture: DONE, three-morning gate OWED. The other NOW rows are OWED to the operator or Code as their cells say and did not move.

**v1 triage of NOW.** Zone model — See (a Z2 ride reads and deposits as Z2) and Know (the conditioning quota counts load the device agrees with). Ledger UX, coach ledger writes, injury lifecycle — Know and Walk in. Wake-day capture and lane visibility — Loop. Missed-PM catch-up, data freshness, plan/schedule tools — Loop / See, DONE and riding for their owed checks. RPE fallback (Q231) — See, OWED (Code once the gate opens). Source hierarchy (#365) and the Polar relabel limbs — OWED (Luke), serving See / Know; neither moved this session and neither is a demotion candidate: each waits on a named operator act.

**Open `fork` issues.** None.

**Design docs not in a terminal state.** 0001, 0002, 0004, 0005 (Q213 still open; Q198 and Q216 moved to 0010), 0006, 0007, 0008, 0009, 0010 (`discussion`: row 4, R8, awaits the operator's OK). 0000 is the template.

**Not touched this session (named so it is not read as finished).** No feature work outside the zone model: the ledger UX defects GH#623 to GH#629 and the coach ledger writes GH#612 to GH#617 stood still; the RPE fallback (Q231), the source hierarchy ruling (#365), the Polar relabel limbs, the appointment reconcile leg, the three-morning wake-day gate, the single-row HC bout deposit read (#384 item 4) — all unchanged, all gated on the operator acts their rows name. GH#634 and GH#635 are new `build` issues; neither is started. No companion-app (`health-connect-app`) work. No CLAUDE.md change: nothing landed on master this session, so the Recent-landings block is unchanged (the pointer belongs to the release session).

**The single clearest next action (operator).** Seed the anchors, through Settings → Heart rate zones: LTHR 158 `device_estimated` (Garmin auto-detect; reads "retest") and RHR 51 `stated`, each as a dated change on the R8 default date (the earliest session date) or a date of their choosing; each Save forces the chain. Then read `GET /hr-zones/config` (or the MCP `get_hr_zone_config`) and the first chain report's `polar_rezoned` / `polar_vendor_fallback` counts, and open an Echo bike Z2 ride on its card: its provenance line should read "Zoned on %LTHR (cycling class) · LTHR 158 bpm" and its bar should be Z2. Until the anchors are seeded, every row is `no_anchor` and the `metab-v2` series is empty, not wrong.

**Second action (operator).** Rule R8 (0010 row 4): if OK, the card's default date becomes the rule; if not, say what the seed date should be.
