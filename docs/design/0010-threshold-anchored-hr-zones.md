# 0010 — Threshold-anchored HR zones (per sport class: %LTHR for cycling, %HRR elsewhere)
**State:** discussion
**Owner:** Code   **Opened:** 2026-11-05   **Last moved:** 2026-11-05

## Context

The platform zones every `health_connect` session on one band set, `hr_zones.BAND_PCT` = 50/60/70/80/90 % of the
user's HRmax in force (`user_hrmax`, Q159 stage 2, #364). On HRmax 179 that puts Z2 at 107–124 bpm, which is recovery
intensity: a correctly paced Z2 ride (Garmin: cycling on %LTHR, LTHR 158, Friel; default on %HRR, RHR 51 / max 179,
Karvonen — both put Z2 at about 128–140) is zoned here as Z3. The operator observed this on 2026-11-05 (the Echo
bike zones review brief, `Zone Model Build - Echo Bike Zones Review`).

What exists today (read on master `66d69d3`, the brief's VERIFY block; every item asserted true):

- `hr_zones.BAND_PCT` is the only band definition and zones scale from `user_hrmax` only (`hr_zones.zone_session`
  takes one integer `hrmax`).
- `hc_zone_enrich.enrich_user` re-zones `health_connect` rows only; Polar rows (`polar_v4`, `polar_flow_export`)
  hold the zones Polar computed under its own profile (Q198).
- `load_events_metabolic` consumes `z1..z5_seconds` under `FORMULA_VERSION_METABOLIC = "metab-v1"` (Edwards).
- No LTHR or RHR *anchor* store exists. `hr_zone_config_snapshots` (SCHEMA §050) holds Garmin's own zone
  configuration (max HR, LTHR, 7-day auto RHR, method) as capture-only observation; nothing zones from it and the
  operator cannot write it. It is the "Garmin mirror" input of this design, not an anchor.
- `Settings.jsx` has no zone or HRmax section; `LoadCard.jsx` shows `hrmax_prompts` (one per arbitrated bout, #478
  family).
- Polar samples are NOT stored: `hr_samples` carries `health_connect` (every writer, including `fi.polar.polarflow`)
  and `garmin` / `personal_api` (wellness daily HR); `polar_ingest`, `import_polar` and `routers/polar` read
  `exercises[0].zones[].inZone` only (Q198 inventory, 0005 appendix). This decides the R2 branch (below).
- Sport classifier: `backend/sport_classes.py` holds two static sets (`NON_TRAINING_SPORTS`, `STRENGTH_SPORTS`) under
  the Q164 matching rule (exact on the raw `sport_name`, case-insensitive). No cycling / sport-to-basis classifier
  exists anywhere else; `engine/resolver.py` matches `device_sports` per phase slot (phase-scoped, not reusable, #302).

Consumer map of the zone data (every non-test use of `z*_seconds`, `BAND_PCT`, `zone_session`, `hrmax_in_force`):

| Consumer | Class | What it does with zones |
|---|---|---|
| `hc_zone_enrich.enrich_user` | writer (fill) | zones HC rows from `hr_samples` + HRmax in force; chain step 3 |
| `hc_zone_enrich.over_ceiling_prompts` | report | `hrmax_prompts` (LoadCard, readiness snapshot) from samples above HRmax |
| `polar_ingest._enrich_v4_zones`, `import_polar._parse_session` | writer (vendor) | write Polar's own zone seconds onto Polar rows |
| `routers/health_connect._ingest_exercise_sessions` | writer (stage 1) | HC rows land with `z*` NULL |
| `load_events_metabolic.compute_metabolic_load_events` | load | Edwards TRIMP per canonical row → `load_events` (`metab-v1`) |
| `reads/aerobic_reads._has_usable_zones` / `zone_coverage` | report | zone coverage flag (the same INV-7 predicate) |
| `engine/resolver.py` (load_window slots) | arbitration / position | per-session TRIMP shown on a counted slot (display of the same formula) |
| `aerobic_format.format_aerobic_session` | display | zone minutes on every chat / MCP session line |
| `routers/polar.AerobicSessionOut` → `WorkoutPanel.HRZoneBar` | display | the zone bar on a session detail |
| `scripts/set_hrmax.py` | operator writer | `user_hrmax` append; plans the HC rows whose HRmax in force moves |
| `scripts/trimp_weighting_projection.py`, `scripts/arbitration_flip_report.py` | report | projections over `BAND_PCT` / `hrmax_in_force` (operator reports, read-only) |
| `mcp_server._METAB_FORMULA_VERSION` (literal `"metab-v1"`), `routers/series.py`, `reads/psychological_reads.py` | load (read) | select `load_events` / `load_metrics` rows by the metabolic formula version |

Related: 0004 (load model routing), 0005 (HR input layer; Q198 and Q216 are resolved by this doc, Q213 stays open).

## Proposal

### 1. Anchors — a dated, append-only store beside `user_hrmax`

`user_hr_anchors` mirrors `user_hrmax` one-for-one in discipline and resolver, for the two new anchors:

```sql
CREATE TABLE user_hr_anchors (
    id             SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind           VARCHAR(10) NOT NULL,       -- 'lthr' | 'rhr'
    effective_from DATE NOT NULL,              -- in force from this LOCAL date; dated rows apply forward only
    bpm            INTEGER NOT NULL,
    provenance     VARCHAR(20) NOT NULL,       -- closed set below
    note           VARCHAR(1000) NOT NULL,     -- the evidence
    restates_id    INTEGER REFERENCES user_hr_anchors(id),   -- the row this one corrects; NULL = a DATED row
    rationale      VARCHAR(1000),              -- required on a restatement
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- one DATED row per user, kind and date; a row restated at most once; chains are linear
CREATE UNIQUE INDEX uq_user_hr_anchor_dated    ON user_hr_anchors (user_id, kind, effective_from) WHERE restates_id IS NULL;
CREATE UNIQUE INDEX uq_user_hr_anchor_restates ON user_hr_anchors (restates_id) WHERE restates_id IS NOT NULL;
CHECK kind IN ('lthr','rhr');  CHECK provenance IN ('tested','observed','device_estimated','stated');
CHECK restates_id IS NULL OR rationale IS NOT NULL;
```

- **Closed provenance set:** `tested` (a field test: 30-minute TT for LTHR, a supine morning read for RHR),
  `observed` (a strap reading from a session), `device_estimated` (a device's auto-detect: Garmin LTHR auto-detect,
  a watch's RHR), `stated` (the operator's figure, no artefact). `estimated` (age or population formula) does not
  exist, as for HRmax. The **retest flag** is derived, not stored: an in-force anchor whose provenance is
  `device_estimated` is shown "retest" on the card and in the MCP read.
- **Two kinds of change (#383 semantics):** a DATED change (forward only) or a RESTATEMENT (same date as the row it
  corrects, better evidence, reflows history, `rationale` required). The one resolver is `hr_zones.hrmax_in_force`,
  already generic over `(effective_from, bpm, id, restates)` entries; it is exposed under the general name
  `anchor_in_force` and applied to all three anchors.
- **HRmax stays in `user_hrmax`,** written only by `scripts/set_hrmax.py` (SCHEMA §041/§043; `tests/test_hr_zones_schema.py`
  pins the single writer). The card reads it, shows it as an anchor, and refuses to write it, naming the script.
  Nothing in this design edits or deletes a `user_hrmax` row (brief GUARD).
- **R3.** RHR is this stored, dated anchor, never the live daily Garmin RHR (`daily_physiology.resting_hr_bpm`,
  `health_connect_syncs.hr_nadir_bpm`) and never `hr_zone_config_snapshots.rhr_7d_auto_bpm`. A fitness-driven RHR
  change is a dated change the operator records.
- **R8 (pending operator OK).** Seeded anchors take `effective_from` = the user's earliest `aerobic_sessions`
  date (best current estimate) with the provenance above. Shipped as the card's DEFAULT date for a kind that has no
  entry yet; the field stays editable (seed dates configurable), and the card says the default is R8's.

### 2. Sport → basis map (R4)

`sport_classes.LTHR_SPORTS` is a static set matched by the Q164 rule (exact on the raw `sport_name`,
case-insensitive, no trimming, no fuzzy match, all sources). `zone_basis_for(sport_name)` returns `"lthr"` for a
member and `"hrr"` for everything else, including NULL and unmapped names.

| Class | Basis | Members (raw `sport_name`) | Evidence |
|---|---|---|---|
| cycling / Echo bike | `lthr` (Friel) | Polar: `Cycling`, `Indoor cycling`, `Road cycling`, `Mountain biking`, `Spinning` (`import_polar.SPORT_NAMES` ids 2/18/38/5/118). Health Connect: `Biking`, `Biking Stationary` (`sport_name_for` types 8/9) | the names the writers emit; prod rows 2026-10 to 2026-11 carry `Biking`, `Biking Stationary` (Garmin via HC) and `Indoor cycling` (Polar) for the Echo bike |
| everything else | `hrr` (Karvonen) | unmapped | R4 |

`Elliptical`, `Cross-trainer`, `Rowing` and `Indoor rowing` are NOT in the LTHR class: the LTHR anchor is a cycling
threshold (Garmin applies its cycling LTHR to cycling only; the default profile is %HRR), so a rowing or elliptical
erg zones on %HRR. Reverse-by: add the name to `LTHR_SPORTS` (two-way, see Unresolved 3).

### 3. Band tables

Integer percents, lower-inclusive, z5 open-topped, compared in integer arithmetic (no float boundary):

| Basis | z1 | z2 | z3 | z4 | z5 | Below z1 |
|---|---|---|---|---|---|---|
| `lthr` (% of LTHR, Friel) | < 81 | 81–89 | 90–93 | 94–99 | 100+ | none: z1 has no floor (Friel) |
| `hrr` (% of heart-rate reserve, Karvonen) | 50–59 | 60–69 | 70–79 | 80–89 | 90+ | < 50 % HRR is covered, uncredited (as %HRmax was) |

`%HRR` of a sample: `(bpm − RHR) × 100 ≥ pct × (HRmax − RHR)`. `%LTHR`: `bpm × 100 ≥ pct × LTHR`. Each band's lower
edge in bpm is therefore `ceil(pct × anchor / 100)` (LTHR) or `RHR + ceil(pct × (HRmax − RHR) / 100)` (HRR); the
resolver precomputes these five integers as a `ZoneSpec`, which is what the card, the preview, the provenance line
and the MCP read all show. With the brief's anchors (LTHR 158; RHR 51, HRmax 179): LTHR z2 = 128–142 bpm,
HRR z2 = 128–140 bpm; the old %HRmax z2 was 107–124.

The HRmax ceiling stays: a plausible sample above the HRmax in force still flags `over_ceiling` and still feeds
`hrmax_prompts`, under either basis. `PLAUSIBLE_BPM`, `MAX_SAMPLE_GAP_S`, `MIN_ZONE_COVERAGE` are unchanged.

### 4. Resolver and reflow

`hr_zones.resolve_zone_spec(sport_name, day, hrmax_entries, lthr_entries, rhr_entries)` is pure: basis from the
sport map, each needed anchor via `anchor_in_force` on the row's `session_date`; a missing anchor (LTHR for the
`lthr` class; RHR or HRmax for `hrr`) yields no spec and the row is withheld with reason `no_anchor` (the renamed
`no_hrmax`: a user-level precondition, checked before the samples, so the count it blocks is complete).
`zone_session` takes the `ZoneSpec` instead of an integer HRmax and is otherwise unchanged.

`hc_zone_enrich.enrich_user` zones, on every run, every row of the user:

- **`health_connect` rows** as today (same-writer samples, now per-row spec).
- **Polar rows (R2).** Polar's own samples are not stored, so the "samples exist" branch is taken through the one
  place the H10 trace of a Polar-recorded bout already lives: `hr_samples` written by `fi.polar.polarflow` through
  Health Connect (`POLAR_SAMPLE_WRITERS`). A `polar_v4` / `polar_flow_export` row whose window those samples cover
  (`MIN_ZONE_COVERAGE`) is re-zoned onto this model and its stored zones are overwritten; a Polar row they do not
  cover KEEPS its vendor zones untouched (never NULLed) and is the flagged fallback. The chain report counts
  `polar_rezoned` and `polar_vendor_fallback`. The writer identity is the arbitration's own twin evidence
  (`also_recorded_by` lists `fi.polar.polarflow` on every Polar bout since 30 Jun 2026); rows before that have no
  copy and stay vendor. Native Polar sample ingest (AccessLink `samples` feature, untested) is a separate `build`
  issue (GH#, filed with this doc) so the remaining Polar rows reach the model.
- **Per-row basis on read.** Nothing is stored: `reads.zone_reads.row_zoning(row, anchors)` derives
  `{basis: lthr|hrr|vendor, class, anchors: {...}, spec}` from `(source, sport_name, session_date, samples present)`,
  and is attached to every session the sessions API returns (`AerobicSessionOut.zoning`) and to the load event's
  provenance. A vendor row reads `basis: vendor`.

### 5. Load meaning (R1)

`FORMULA_VERSION_METABOLIC` bumps to `metab-v2`: same Edwards weights, zone seconds now from the per-class model.
The transform deletes and reinserts `(user, metab-v2)` as before and additionally removes rows of the retired
version (`RETIRED_METABOLIC_VERSIONS = ("metab-v1",)`) so no orphaned series lingers in `load_events`; every reader
of the version (`mcp_server`, `routers/series`, `reads/psychological_reads`, `load_metrics` callers) takes it from
the one constant (the `mcp_server` literal is replaced by the import). The recompute is the existing chain
(`scripts/refresh_load`, steps 3 → 5 → 7): it runs on the next Training-page open and at 02:00 after release, and the
card calls `POST /load/refresh?force=true` after a successful anchor append so a seed reflows at once. No recompute
runs against prod before the operator releases the migration (GUARD).

### 6. API, UI, MCP

- `GET /hr-zones/config` — the one read (`reads/zone_reads.zone_config`): per class the basis, members, band
  percents and today's bpm edges; per anchor (`hrmax`, `lthr`, `rhr`) the entry in force today, every entry
  (dated / restatement chain, provenance, note, `created_at`), the retest flag; `hrmax_prompts`; the R8 default date;
  the Garmin mirror (band percents as Garmin's profile states them, and the latest `hr_zone_config_snapshots` row).
- `POST /hr-zones/anchors/preview` and `POST /hr-zones/anchors` — body `{kind, bpm, effective_from, provenance,
  note, change: "dated" | "restate", rationale}`. `change` is REQUIRED (the forced choice, R6): a dated change on a
  date that already has a row, or a restatement on a date without one, is refused with the way out. Preview returns
  the bpm edges before and after for every class the anchor touches and the count of rows whose spec changes;
  append writes one row (never updates or deletes), returns the same plan, and the card then forces the refresh.
  `kind: hrmax` is refused (400) naming `scripts/set_hrmax.py`.
- **Settings → "Heart rate zones"** (`frontend/src/components/HRZonesCard.jsx`): per class the basis and bpm bands;
  the anchors (value, provenance, effective_from, retest); `hrmax_prompts`; the append form with the forced choice,
  the preview step before Save, and the R8 default date; the Garmin mirror strip.
- **WorkoutPanel:** one provenance line under `HRZoneBar` from `zoning`: "Zoned on %LTHR (cycling class) · LTHR 158
  bpm from 2026-03-01" / "… %HRR … RHR 51 · HRmax 179 …" / "Polar's own zones (not re-zoned)".
- **MCP (R7):** `get_hr_zone_config` — the same read, formatted; read-only.
- Garmin per-activity time-in-zone ingest (a display-only cross-check) is OUT of scope (R5): `build` issue GH#.

### 7. Tests

Band edges on both bases at every boundary (integer arithmetic, the brief's bpm figures); the resolver across dated
and restated anchors per kind and the `no_anchor` precondition; the sport map (Q164 exactness, unmapped → hrr); the
Polar branch (covered twin samples re-zone the Polar row; no samples keep the vendor zones; a second run changes
nothing); `metab-v2` recompute idempotence and the retired-version cleanup; the API (config, preview, dated/restate
forced choice, hrmax refusal, append-only); the MCP tool; the card (preview before commit, forced choice, R8
default) and the provenance line (vitest).

### 8. Rollout order

1. This PR (held: it carries the migration). Design doc, code, tests, governance ride together; nothing deploys.
2. Operator releases: merge → Railway runs `alembic upgrade head` → `user_hr_anchors` exists, empty.
3. Until anchors exist every row of the `hrr` class is withheld `no_anchor` (RHR missing) and every `lthr`-class row
   likewise (LTHR missing): the metabolic series is EMPTY under `metab-v2`, not wrong. The operator seeds LTHR and
   RHR through the card (R8 date default), each append forcing a refresh; the chain re-zones all history and
   deposits `metab-v2`.
4. Verify: `deploy-check` on the merge commit; `GET /hr-zones/config` shows the three anchors in force; a Z2 ride
   on the Echo bike reads as Z2 on its card.

## Alternatives considered

- **Keep one basis, swap %HRmax for %HRR everywhere.** Simpler, and Q216's original shape, but the operator's Garmin
  profile already runs cycling on %LTHR, so a single basis would still disagree with the device the operator paces
  by. Rejected by the brief's target model.
- **Store the basis / anchors on the session row.** Makes "what zoned this row" a stored fact, but the row would then
  need rewriting on every anchor change and the existing design keeps every derivation re-computable from source
  (#32, D-B). Rejected: derive on read.
- **Widen `user_hrmax` into a generic anchor table (add `kind`).** One store, but it would rewrite a table with a
  single-writer guard, a seed row and a restatement chain in prod, and the HRmax writer rule (#364 R2) would have to
  change in the same migration. Rejected: a sibling table with the same shape costs one migration and touches nothing.
- **Zone Polar rows from Polar's own per-second samples.** Not available: not stored, not fetched, the AccessLink
  `samples` feature untested (0005 appendix). Deferred to the `build` issue; the HC-twin branch covers the bouts
  since 30 Jun 2026.

## Unresolved questions

| # | Question | Proposed answer | Evidence that settles it | Door | Status |
|---|----------|-----------------|--------------------------|------|--------|
| 1 | Do a Polar row's zones come from the `fi.polar.polarflow` Health Connect samples of the same bout (R2 "samples exist" read through the HC twin)? | Yes: `POLAR_SAMPLE_WRITERS = ("fi.polar.polarflow",)`; a Polar row those samples cover is re-zoned, else vendor zones stay. | `tests/test_hc_zone_enrich.py` Polar branch; `polar_rezoned` / `polar_vendor_fallback` in the chain report on prod after release | two-way (reverse-by: empty tuple → pure vendor fallback) | resolved in-PR (ruling, this entry) |
| 2 | Does the LTHR z1 have a floor? | No: Friel z1 is "< 81 %" and Garmin's cycling profile states no floor; a sample below it is z1 time. | the brief's band table; `test_hr_zones.py` edge tests | two-way (reverse-by: `LTHR_Z1_FLOOR_PCT`) | resolved in-PR (ruling) |
| 3 | Do rowing / elliptical / cross-trainer ergs join the LTHR class? | No: the LTHR anchor is a cycling threshold; they zone on %HRR. | the operator's Garmin profile (LTHR on cycling only); `sport_classes.LTHR_SPORTS` | two-way (reverse-by: add the name) | resolved in-PR (ruling) |
| 4 | R8: seeded anchors take `effective_from` = earliest session date? | Yes, shipped as the card's default date, editable. | the operator's OK | one-way (shapes stored rows' meaning) | open (pending operator OK) |
| 5 | Does the card become a writer of `user_hrmax`? | No: the script stays the one writer; the card shows HRmax and names the script. | `tests/test_hr_zones_schema.py::test_only_the_operator_script_writes_user_hrmax` | two-way | resolved in-PR (ruling) |
| 6 | Native Polar per-second sample ingest (AccessLink `samples`)? | Build issue; the rows before 30 Jun 2026 and any bout without an HC copy stay vendor until it lands. | the `build` issue's live probe of the `samples` feature | — | filed (GH#, `build`) |

## Decisions landed

- #NEXT (resolved at merge) — the model, R1 to R8 recorded; rows 1, 2, 3, 5 as rulings under the same entry.
