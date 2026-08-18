# closeout — 2026-08-18 (canonical marker map → DB-backed, confirmation-screen bind)

## 1. Real commits this session

Session-open ref `b0093d3`. `git log --oneline b0093d3..HEAD`:

```
bef724a Merge pull request #80 from Easty11/feat/canonical-map-db-bind
3e6ffbe gov: DECISIONS_LOG #220, OPEN_QUESTIONS Q104, #50 status superseded, BRANCHES row
2c4b0fa feat(metrics): inline canonical bind on the confirmation screen
93cd187 feat(labs): canonical marker map becomes a DB table with a guarded runtime bind
```

One branch, `feat/canonical-map-db-bind`, landed via PR #80. Schema + backend + frontend
were one concern (the bind feature) split into three commits internally.

**Numbers claimed at merge:** `#NEXT` → **#220**, `Q#NEXT` → **Q104**, against master's max
re-read immediately before merging (**#219 / Q103** — unchanged between resolve and merge, so
strict mode forced no pause).

**Suites:** backend **882 → 890** (+8), frontend **41 → 47** (+6). Both baselined before edits
and re-run after; zero regressions. The interpretation-layer tests — the canary for the
step-1(b) decision — stayed green throughout.

**Deploy verified on both services (#116/#121), after SUCCESS on the deploy:**
- Backend, discriminating probe: `/openapi.json` lists `/labs/canonical/bind`, a path only
  the new image carries.
- Prod DB (read-only query via `railway run`, no secret rendered): `alembic_version` =
  `a7c3f19d5e28`, `marker_canonical_entries` holds **70 rows, all `source='seed'`**, 4 null
  units, `Cystatin C → ('cystatin_c', 'mg/L')`.
- Frontend, served bundle `assets/index-D1nSJ_7O.js`: carries `Not a known marker`,
  `canonical/bind`, `established unit` — all new-code-only strings.

## 2. Pending-queue reconciliation

**No `PENDING` items were carried in.** This session ran from a dispatch brief, not a `;cc`
pending-commit queue. Nothing decided this session is uncommitted — the three commits above
plus this close-out are the whole of it.

Two items the brief specified that landed as specified: the migration self-check on the seed
count, and the over-collapse guard at both bind-time and backfill-time.

One item the brief specified that landed **differently, on a corrected finding** — see §3's
scope note. Nothing was dropped.

## 3. Cold-resume handoff

### What landed

`#220` — the canonical marker map is a DB table, runtime-mutable. `labs.py` lost
`_CANONICAL_MAP`/`_load_canonical_map`; the confirm resolution and `GET /labs/canonical-map`
now query `marker_canonical_entries` per request (no cache: a cached dict would serve the
pre-bind map to the very confirm the operator just bound for). `POST /labs/canonical/bind`
writes an entry and promotes that marker's historical `marker_canonical IS NULL` rows.
`marker_canonical.json` survives as the migration seed. This fulfils `#50`'s
confirmation-populated half and supersedes its stale "Not implemented" status line in place.

The over-collapse unit-guard — the reason `#50` exists — is carried to both new points where
identity became mutable at runtime: bind-time (canonical already established at a disagreeing
unit) and backfill-time (a stored row carrying a disagreeing unit). A refused bind promotes
**zero** rows, asserted; a half-migrated series is harder to see and harder to undo than a
refusal. Binding stays optional — an unbound row still stores null (`#58`/`#155` retain-raw).

### The scope correction — read this before touching the interpretation layer

The brief proposed leaving `interpretation/gates.py` and `interpretation/rephrase.py` on the
JSON, on the hypothesis that interpretation only covers grouped markers so a
freshly-bound-ungrouped marker could never reach them. **That hypothesis is false**, and it was
tested rather than assumed: `producer._ungrouped()` emits every non-grouped panel marker as a
flat row and `presentation.py:237` builds rephrase fragments from those rows. A bound-ungrouped
marker *does* reach `rephrase`.

Phasing was still the right call, on a narrower mechanism, and that mechanism is what `Q104`
now carries:

- `rephrase._KNOWN_ENTITIES` is a **detector** allowlist, not a permit-list. The validator
  iterates the vocabulary and flags only a word that is IN the set and appears in
  candidate-but-not-source. A marker absent from the stale set is never tested — staleness
  narrows hallucination coverage (a missed detection) and can never cause a false rejection.
- `gates._UNIT_ESTABLISHED` is consulted only inside `_resolve_band`, reachable only when the
  marker is authored in `safety_thresholds.json`, which a freshly-bound marker is not; the
  absent case already falls back to `value_plausibility` — weaker, not wrong.
- Migration cost decided the split: `generate_plain` is called from an endpoint already holding
  a `db` and already takes a `known_entities=` param, so `rephrase` could migrate almost free.
  `_resolve_band` sits ~4 levels below `build_foundation` inside the pure `#86` producer,
  reached via two paths, with no injection param for the unit map — it needs a session threaded
  through ~6 signatures of contract-sensitive machinery.

### Open questions

- **Q104 (new, OPEN, blocks nothing).** The two readers above still load the JSON, which is now
  only a seed snapshot. The safe-degradation stops holding if `_KNOWN_ENTITIES` is inverted to a
  permit-list, or `_resolve_band` is made to hard-require `_UNIT_ESTABLISHED`. Either change must
  migrate both readers in the same stroke.
- **Q103** (`lab_results.is_derived` write-dead), **Q102** (`restrictions[]` dead data),
  **Q78** (multi-user nap attribution — unblocked by `#219`, not resolved), **Q101** closed at
  `#218`. `Q36`–`Q41` remain the 4b package.

### A control that fired, and the gate that did not

A blanket `#NEXT` → `#220` substitution corrupted **31 lines of pre-existing `#NEXT` prose in
`DECISIONS_LOG.md`, 3 in `OPEN_QUESTIONS.md`, 1 in `SCHEMA.md`** — the identical failure mode as
PR #71 (`#175`, 55 lines), in a session that had already read the ROADMAP row describing it.

It was caught **before commit**, and only by auditing the diff's REMOVED lines for `#176(c)`.
**The placeholder guard passed clean the whole time** — every corrupted line was prose that no
longer matched `^### #NEXT`, so the guard had nothing to see. Recovery: `git checkout --` on the
two stores, a one-line restore in `SCHEMA.md`, then re-applying the additions with literals;
pre-existing `#NEXT` counts were then re-verified equal to HEAD's (31 / 4).

The ROADMAP's cross-repo `#NEXT` row has been updated with this as second evidence, and with the
two lessons for the fix's shape: the count-verified scoped replace should be mandatory rather
than advisory, and the removed-line audit — the only control that actually caught this — belongs
in the close-out ritual rather than being a `#176(c)` side effect.

### What was NOT touched

This session was **feature work on the lab spine**, not instrumentation — but it moved one lane
and left the rest standing, and the standing ones are the product:

- **Interpretation layer, increments 3 and 5-follow-on.** Increment **3 (lever tap → scoped
  education thread) is UNSTARTED** and has been for several sessions. Increment 2 (rephrase)
  landed at `#202`, go-live at `#194`. Nothing in increment 3 moved today, and nothing here
  blocks it.
- **Appointment brief** — the hero consumer feature ("never waste a medical appointment again").
  Untouched. Still gated on the lab pipeline plus the interpretation layer, and today's work
  advanced the former.
- **Hub shell (`#150`)** — unblocked, operator-preferred next pick as of the 2026-08-02
  reconciliation. Untouched today. **`lab_accession`** remains the strongest small alternative.
- **CBT-I** — untouched this session. `Q78` (two over-threshold nap nights starving a cycle for
  a second user) is still OPEN and unblocked; rx 12 still stands pending Luke's decision on
  whether to correct it.
- **The four cross-repo ROADMAP rows** — three discharged 2026-08-17; the fourth (extend
  `#NEXT`/number-at-merge beyond DECISIONS entries) is **still OWED**, needs an HCA-rooted
  session for the propagation half, and this session produced fresh evidence for why it matters.
- **The junk-row operator decision** on the ten zero-result `lab_reports` (`#157`) is still owed
  and was not revisited.

Honest framing: the previous two sessions went to governance and to CBT-I; this one went to the
lab spine. The consumer-facing lanes — appointment brief, lever-tap threads, hub shell — have now
been queued and unmoved across all three.

### Single clearest next action

**Bind a real unmapped marker through the live confirmation screen**, against the next lab
upload. Every layer is proven except the operator's own path end-to-end in prod: the endpoint is
deployed, the table is seeded at 70, the guards are proven in tests, and the bundle carries the
control — but no marker has been bound through the UI against real data yet, and the backfill is
the half that touches stored history.

If no upload is due, the strongest alternative is the **hub shell (`#150`)** — unblocked,
operator-preferred, and one of the consumer-facing lanes named above as standing still.
