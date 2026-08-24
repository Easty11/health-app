# Provenance — `hc_sync_payload_canonical.json`

**Transcribed from `health-connect-app` at commit
`7a63b15f91e33f6e508302d2054d36a760486c1c`** (master, read 2026-08-24).

Field names were **machine-verified against that commit's source**, not hand-transcribed from a
chat-side table. A fixture that cannot name the commit it came from is undetectable drift, and it
is the only cross-repo anchor this contract has: chat cannot read HCA, and the backend cannot
import it.

## Transcribed from the `fetchAllData` INLINE mappers, deliberately

`src/healthConnect.js` carries the sleep and HRV mappers **twice**:

| Mapper | Standalone | Inline in `fetchAllData` | On the sync path |
|---|---|---|---|
| sleep | `fetchSleepData` (`:150–156`) | `:274–280` | **inline copy only** |
| HRV | `fetchHRVData` (`:161–165`) | `:282–285` | **inline copy only** |

`heartRateMapper` (`:174`), `stepsMapper` (`:183`) and `workoutMapper` (`:245`) are shared
functions with a single definition each, reached by both paths.

`SyncScreen.js` → `fetchAllData` → `api.js::syncHealthData` is the only sync path, so the
standalone copies are **never executed in production**. This fixture is transcribed from the
inline copies. Transcribing from the standalone functions would pin code production does not run,
and would pass every gate while doing so.

**At `7a63b15` the two copies are content-identical** — no divergence today. The duplication is a
latent hazard, not a live defect, and de-duplication is a named precondition of the E3 adapter
extraction (see the source-neutral contract decision).

## What the shipped shapes actually are

- **steps** carry `date` / `count` / `sourcePackage` only. `stepsMapper` builds a fourth field,
  `durationMs`, but `aggregateSteps` consumes it for the ≥23 h daily-aggregate test and drops it
  from the emitted record. *The mapper that builds is not the shape that ships.*
- **`sourcePackage` is the mapped writer identity.** Every mapper reads the SDK's
  `r.metadata?.dataOrigin` and emits `sourcePackage`; no record carries a top-level `dataOrigin`.
- **workouts carry `id` / `recordingMethod` / `device`** (`workoutMapper`, forwarded per HCA's
  `DECISIONS_LOG #35`). Samsung Health populates `id` with a stable UUID and leaves
  `recordingMethod` / `device` at their UNKNOWN sentinels (`0` / type `0`) — reproduced here.
- **Envelope keys, exactly:** `syncedAt`, `periodDays`, `sleep`, `hrv`, `heartRate`, `steps`,
  `workouts`, `errors`. There is **no `exercise` key**. `oxygenSaturation`, `respiratoryRate`,
  `weight`, `distance` and `mindfulness` are never posted (verified: zero occurrences across
  `src/healthConnect.js` and `src/api.js` at this commit).

## Why provenance lives here and not inside the JSON

The fixture is a **pure payload**. A `_provenance` key inside it would be an unknown top-level key,
which is inert under the current models but would be retained in `model_extra` once the payload
models set `extra="allow"` — contaminating the additive-unknown-key control that proves the
tolerance works. The fixture has to be able to stand as a clean negative for "no unknown keys
present".

## Re-verifying this fixture

```
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Easty11/health-connect-app <path>
git -C <path> rev-parse HEAD          # must equal the SHA above, or re-verify the mappers
```

If HCA master has moved, this fixture is a claim about a commit that is no longer the tip. It stays
valid as a pin of *that* commit; whether it still describes what ships is a fresh question.
