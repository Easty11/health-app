# Garmin Personal API migration — plan for operator ruling

Status: PLAN ONLY. No code, no migration, no prod write, no governance-store edit has been made. Uncommitted file.
Brief: "Garmin Personal API Migration" (chat probe 2026-10-24/25). Repo state read: master `8fd827e`; decisions max **#447**, questions max **Q238**; Alembic head **`b8f3d6a2c915`** (re-read at land).

---

## 1. S0 results

| Check | Result | Evidence |
|---|---|---|
| S0.1 user 1 `account_fingerprint` = `sha256("garmin:150823854")` | **MATCH** | Prod read-only SELECT on `user_integrations` (`railway connect health-app-DB`, piped). Row user 1 = `283aeee9…b6089`, equality test returned `t`. So `userProfilePk` is a valid fingerprint source for user 1 and the DI row's `socialProfile.profileId` is the same id. The attach guard migrates without re-linking. |
| S0.1 user 4 | **UNVERIFIED** | Row user 4 = `96ff6301…a5a35`; its pk was not in the brief, so there is nothing to compare. Checked at attach time: the personal-key `userProfilePk` digest must equal this row's digest, else STOP for that user. |
| S0.2 Railway egress to personal host | **PARTIAL — host reachable; authenticated path owed** | From the prod container (`railway ssh`, `/opt/venv/bin/python`, httpx): `POST personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token` with a deliberately invalid key returned **401** (TLS + DNS + route all fine, no Cloudflare block of httpx). Container Python is **3.12.7**. Real token exchange + one GET need a key attached (nothing to do until S1 lands + operator supplies a key). |

Nothing was written; no secret was rendered.

## 2. Prior-art evaluation: `garmin/connect-personal-api-python`

Read from its source (main, 4 commits, no release seen, Apache-2.0). The exchange is trivial: `POST {base}/personalapitoken-service/personal-api/personal-api-key/token`, header `Authorization: ApiKey <key>`, no body, response body is the bearer JWT as plain text (expiry from the JWT `exp`, unverified).

**Recommendation: do not depend on it; hand-roll ~120 lines on `httpx` (already pinned 0.28.1) and copy its endpoint map.** Reasons: (1) its token cache is a file under `~/.config/garmin/` and "cannot be disabled" — wrong for a multi-user server where the cache must be Fernet-encrypted in the DB; (2) `requests` would be a new dependency, and it has no retry/rate-limit handling we would not write anyway; (3) unreleased, 4 commits, `>=3.12` pin is fine but the supply-chain cost buys nothing. Keep its conventions: reuse a token only if > 1 h of life remains; 401 is not retried by the lib (we retry once after a forced re-exchange).

Endpoint map to adopt (from its `client.py`):

| Data | Path | Params |
|---|---|---|
| HRV (day) / range | `/hrv-service/hrv/{date}` · `/hrv-service/hrv/daily/{start}/{end}` | – |
| Sleep (day) / range | `/sleep-service/sleep/dailySleep` · `…/dailySleepSummariesByDate` | `date` · `startDate,endDate` |
| Heart rate (day) | `/wellness-service/wellness/dailyHeartRate` | `date` |
| SpO2 hourly | `/wellness-service/wellness/daily/spo2acclimation/{date}` | – |
| Body battery | `/wellness-service/wellness/bodyBattery/reports/daily` | `startDate,endDate` |
| Stress | `/usersummary-service/stats/stress/daily/{start}/{end}` | – |
| HR-zone config | `/biometric-service/heartRateZones/v2` | – |
| Activity search / detail | `/activitylist-service/activities/search/activities` · `/activity-service/activity/{id}` | `start,limit,startDate,endDate` |

Unknown, to probe before relying: server-side range caps on the three range endpoints, rate limits, and whether a fresh exchange invalidates the previous token (decides whether concurrent sweep + on-read refresh can race). Plan uses per-day calls except where a probe shows ranges are safe.

## 3. Design

### 3.1 Credentials (S1) — **ruling R1**

- New `user_integrations.provider = 'garmin_personal'` (one row per user; existing `uq_user_provider` fits). `api_key_encrypted` = Fernet(key). The DI row `provider='garmin'` stays untouched (SpO2 lane).
- Three nullable columns on `user_integrations` (migration M1): `key_expires_on DATE` (operator-entered at attach), `access_token_encrypted TEXT`, `access_token_expires_at TIMESTAMPTZ`. Token cached encrypted; reused while > 1 h remains; exchanged otherwise; one forced re-exchange on a 401. Alternative considered: a separate `garmin_personal_credentials` table — rejected, a third copy of the encrypt/rotate surface (`scripts.rotate_fernet` already walks `user_integrations.api_key_encrypted`; the token column would also need rotation support — add it to that script and its test).
- Key and token are never logged: log the exception class and endpoint name only (existing `garmin_*` idiom); a caplog test asserts neither string appears.
- Attach route `POST /integrations/garmin-personal/key` `{api_key, key_expires_on}`, plus `GET …/status` (connected, `days_to_expiry`, last exchange outcome) and `DELETE`. Operator-side helper `scripts/garmin_personal_attach.py` reads the key from a hidden prompt (never argv, never shell history).
- Fingerprint: exchange, fetch `hrv-service/hrv/{recent date}` (falling back across a few days / `dailySleep`) for `userProfilePk`; `account_fingerprint = sha256("garmin:" + pk)` — the existing `account_fingerprint()` function, unchanged. Guard identical to today: 409 if the digest is held by a different user **on either provider row**, 503 fail-closed if the pk cannot be resolved, key stored only after the guard passes. **Ruling R6:** if the user's own DI row exists and its digest differs from the personal key's, refuse (409, distinct message) — HRV and SpO2 would otherwise describe two different people. Recommended: refuse.

### 3.2 Lanes (S2) — **ruling R5 (staged)**

- `connectors/garmin_personal.py`: `PersonalClient` (exchange, cache, `get(path, params)`), fake-able at httpx transport.
- HRV: `sync_hrv_for_user` selects the personal lane when a `garmin_personal` row exists. Same `normalize_hrv_day` mapper (field names verified identical for `lastNightAvg`; **owed: confirm the personal payload also carries `hrvSummary.baseline/weeklyAvg/status` and `hrvReadings[]`** — the upsert overwrites DI-written rows, so a missing field would null stored data. Gate: first run in dry-run compares to stored rows; mapper never overwrites a non-null stored field with null from a personal payload unless ruled).
- `hrv_readings.source` stays `'garmin'` → `_WAKEDAY_SOURCE_RANK`, `_HRV_SOURCE_RANK`, `recovery_reads._SOURCE_RANK` untouched; no rank change anywhere. Transport recorded in **new nullable `hrv_readings.transport` (`personal_api` | `di`)**, M1; existing rows backfilled `'di'` (true by construction — **R4**, a prod data write, held).
- Self-eval: `garmin_selfeval.sync_user` takes the personal source (same `.get(path, params)` shape, so the body is unchanged). `session_rpe_observations.source` stays `'garmin'`, `SOURCE_SCALES`/`SOURCE_HIERARCHY` untouched; transport goes in the existing `provenance` JSON — no migration. The no-refresh seam (#361) is moot on the personal host (no refresh token exists).
- **Staging:** PR-A is additive (personal lane used per-user when a row exists; DI path remains for any user without one). PR-B removes DI from HRV and self-eval after both users are verified on the personal host. Without this, user 4 (no key yet) would lose HRV the moment the DI path is deleted. **R5.**

### 3.3 Raw landing (S3)

`garmin_raw_payloads` (new, M1; append-only): `id, user_id FK CASCADE, endpoint String(48), ref String(64)` (ISO date or activity id), `fetched_at, payload_sha256 CHAR(64), payload JSONB`; `UNIQUE (user_id, endpoint, ref, payload_sha256)`; insert-or-ignore, so an unchanged re-fetch is a no-op and a changed payload (e.g. the in-progress day) appends. "Current" = latest `fetched_at` for the key. Hash = SHA-256 of `json.dumps(sort_keys, compact, ensure_ascii=False).encode('utf-8')`. UTF-8 end to end; emoji round-trip is a test.

**R3 — identity in payloads.** `garmin_spo2.py` deliberately never stores the profile id/device id; Personal payloads carry `userProfilePk`, device ids. Recommended: scrub a closed key list (`userProfilePk`, `userProfileId`, `displayName`, `deviceId`, `ownerId`, …) from the payload **before hashing and landing**; the pk is used transiently for the fingerprint only. Cost: not byte-faithful to Garmin. Alternative: land verbatim (and accept the id in the table). Needs a ruling.

Volume estimate: ~15–30 KB/day/user/endpoint set → ≈ 10–40 MB/user/year; no retention rule proposed (Q).

### 3.4 Mappers → tables (S3) — **ruling R2**

Live-schema finding: `SCHEMA.md` specs `health_metrics` and `vendor_metrics` but **neither exists** as a model or migration, so "map into existing canonical tables" reduces to the following.

| Data | Target | New? |
|---|---|---|
| HRV nightly + 5-min samples | `hrv_readings` / `hrv_samples` | existing (+`transport`) |
| Intraday HR (~2-min) | `hr_samples`, `source='garmin'`, `source_package='personal_api'` | existing. Safe: every reader filters `source == 'health_connect'` (`hr_nadir`, `hc_zone_enrich`, `arbitration_flip_report`) — verified by grep. Skip null bpm. |
| sRPE | `session_rpe_observations` | existing |
| Sleep (stages, TST, start/end GMT, resp avg/low/high, avg+lowest SpO2, score + subs, awake count, avg sleep stress, sleep need, derived efficiency) | **`sleep_nights`** — source-neutral, `UNIQUE(user_id, captured_at(wake date), source)`, `transport`, typed columns, `efficiency_pct` + `efficiency_formula` tag | new. Not `health_connect_syncs`: that row is HC-writer-owned (#254 union logic) and mixing a second writer corrupts it. |
| Coarse nightly SpO2 | columns on `sleep_nights` (`spo2_avg_pct`, `spo2_lowest_pct`) | new columns |
| SpO2 hourly averages (24/day) | **`spo2_hourly`** (`user_id, hour_start, avg_pct, source, transport`) | new |
| Daily RHR, stress daily, body battery daily | **`daily_physiology`** (`user_id, date, source, transport`, `resting_hr_bpm`, stress avg/max + durations, body battery high/low/charged/drained). Stress and body battery are vendor composites: column comments say "display only, never an algorithm input" (SCHEMA.md `vendor_metrics` rule) | new |
| HR-zone config (max HR, LTHR, RHR, method) + change history | **`hr_zone_config_snapshots`** append-only; insert only when the tuple differs from the latest; RHR column named `rhr_7d_auto_bpm` (trap: that value is Garmin's 7-day auto value, not daily RHR) | new. Observation only — **never writes `user_hrmax`** (operator-owned, #383). |

Alternative to R2: realise SCHEMA.md `health_metrics` + `vendor_metrics` as specified. Not recommended: key `(user, source, source_ref)` and a whitelist gate fit a metric-per-row ingest nothing consumes yet; typed tables follow the established `hrv_readings` / `spo2_nights` shape. All new tables get a SCHEMA.md entry in the same commit as the migration.

Efficiency is `sleepTimeSeconds / (end − start)` tagged `garmin_window_tst_over_span_v1`. It excludes pre-sleep time in bed, so it will read higher than the diary SE; nothing in `cbti/` reads `sleep_nights` (a grep-pinned test, like `test_cbti_replay_training_not_read`). Mapper traps encoded as tests: `averageSpO2HRSleep` is a heart rate; key on GMT timestamps, never profile tz (`Pacific/Port_Moresby`); sleep/HRV `calendarDate` = wake date; RHR from `dailyHeartRate`, not the zones endpoint.

Backfill (`scripts/garmin_personal_backfill.py`, dry-run default, per user, newest → oldest, paced, stop after N consecutive all-endpoint-empty days, idempotent so resumable). Brief says "earliest date Garmin returns" — walk stops by empty-streak, not a fixed floor.

### 3.5 DI SpO2 lane (S4) — **ruling R7 (load-bearing)**

Today the SpO2 and self-eval steps run through a **no-refresh** client and rely on `sync_hrv_for_user` having already refreshed and written back the DI token ("the token it sees is fresh without this module adding a refresh"). Moving HRV to the personal host removes that refresh, so the DI blob would age out and the SpO2 lane would drift into `skipped_needs_refresh` — silently defeating the CPAP-seal evidence. Therefore S4 adds an explicit **DI keepalive** at the head of the SpO2 lane (`GarminClient.from_token` → `dump_token` → store, committed before the read — exactly what the HRV step did) and fixes the ordering so it is never skipped. Content of epoch SpO2 + breathing intervals is unchanged. The personal nightly avg/lowest and hourly averages persist regardless, as the permanent coarse substitute. `socialProfile` / `user-settings` calls remain only in this lane.

### 3.6 Observability (S5)

`integration_lane_status` (new): `UNIQUE(user_id, lane)`, `last_attempt_at, last_success_at, outcome` (`ok | empty | auth_failed | rate_limited | error | skipped_needs_refresh`), `reason` (exception class / short code only). Lanes: `personal_token`, `personal_hrv`, `personal_wellness`, `personal_selfeval`, `di_spo2`. Mutable status row (upsert), not append-only. Each step writes it in a `finally` so a failed lane is recorded, not skipped.

Staleness card (`reads/freshness_reads.py`): (a) `di_spo2` last outcome failed, **or** newest `spo2_nights.captured_at` more than 2 wake-dates behind the Brisbane wake-day → loud; (b) per user `key_expires_on − today` (proposed amber ≤ 30 d, red ≤ 7 d — **R8**; Garmin emails the key owner, not the operator); (c) `personal_token` outcome `auth_failed`. **R8 also:** is the epoch-SpO2 alert for user 4 as well, or user 1 only?

### 3.7 Migration (M1, one revision, additive only, holds under § Merge disposition)

Chains after `b8f3d6a2c915`. Creates: `garmin_raw_payloads`, `sleep_nights`, `spo2_hourly`, `daily_physiology`, `hr_zone_config_snapshots`, `integration_lane_status`; adds 3 columns to `user_integrations`, `transport` to `hrv_readings`. Data step (`hrv_readings.transport='di'`) is a separate revision M2 so it can be held independently. No drops. Downgrade drops the new objects. Verified by stamping the prior head and upgrading one step (the chain cannot replay on SQLite) plus a Postgres check via `DATABASE_PUBLIC_URL`.

## 4. Test plan

Transport-layer fake (`httpx.MockTransport`) for all personal-host tests (FEEDBACK §23 companion rule); `FERNET_KEY` throwaway env.
1. Exchange: 200 text JWT → token + `exp`; 401; network error → typed errors; cache reuse > 1 h, re-exchange < 1 h; forced re-exchange on 401; **caplog never contains key or token**.
2. Attach: fingerprint = existing function of `userProfilePk`; 409 other-user (either provider); 503 unresolvable; own-DI mismatch refused; same-user re-attach OK; store only after guard.
3. HRV: golden parity — personal fixture through `normalize_hrv_day` equals DI result; `transport` flips; null-overwrite guard; `source=='garmin'` ranks unchanged (existing rank tests green).
4. Self-eval: existing `test_garmin_selfeval*` pass against the personal source; provenance carries transport.
5. Raw landing: idempotent on same hash, appends on change, emoji round-trip, scrub list applied before hash.
6. Mappers: one test per trap (HR-not-SpO2, GMT vs profile tz, wake-date, RHR source, 7-day-auto naming), efficiency formula tag, `hr_samples` null skip, HR-zone snapshot appends only on change and never touches `user_hrmax`, `cbti/` grep guard.
7. DI lane: keepalive writes back before the read; `skipped_needs_refresh` still recorded; HRV path constructs no `garmin.Garmin` (PR-B).
8. Status/card: lane upsert in `finally`; >2-nights rule; expiry thresholds; token failure surfaces.
9. Migration: stamp prior head → upgrade one step; schema tests pin columns/unique keys; downgrade; `rotate_fernet` covers the token column.
10. Backfill: dry-run writes nothing; stop rule; resumable.

## 5. Proposed governance entries (PENDING — not written to the stores)

- **Decision #448 (migration + credentials):** M1/M2 shape, `garmin_personal` provider row, token columns, `hrv_readings.transport`, typed tables over `health_metrics`/`vendor_metrics`, hash-keyed append-only raw landing. How you know: S0.1 prod read; prior-art source read; httpx 401 probe.
- **Decision #449 (SpO2-lane ruling):** DI epoch SpO2 + breathing disruptions is the DI lane's only job, operator-ruled load-bearing; it gets its own token keepalive; personal coarse SpO2 persists as the permanent substitute. How you know: code coupling read (`garmin_sync` ordering, #361 seam).
- **Questions to open (Q239+):** raw-landing identity scrub (R3); user 4 fingerprint vs its pk (S0 owed); personal-host range caps / rate limits / token-invalidation-on-re-exchange; payload field parity for HRV (baseline, weekly, samples); key-rotation procedure at the 1-year expiry; raw-landing retention; reader brief for the new tables (out of scope here; `get_recovery_metrics` fix separate).

## 6. Rulings needed before any code/migration

| # | Ruling | Recommended |
|---|---|---|
| R1 | Credential shape | `garmin_personal` row + 3 columns on `user_integrations` |
| R2 | Canonical targets | New typed tables (§3.4), not `health_metrics`/`vendor_metrics` |
| R3 | Identity keys in raw landing | Scrub closed list before hash |
| R4 | `hrv_readings.transport` + backfill `'di'` (prod data write) | Yes, as separate held M2 |
| R5 | Cutover | Staged: PR-A additive, PR-B DI removal after both users verified |
| R6 | Personal-key fingerprint ≠ own DI fingerprint | Refuse |
| R7 | DI keepalive inside the SpO2 lane | Yes |
| R8 | Alert thresholds (30/7 d; 2 nights) and whether user 4 is in the SpO2 alert | As stated; operator names user scope |

Holds that apply regardless: M1 and M2 are schema/data migrations (hold, human review); the decisions above are un-ratified (hold until ratified). Code-only parts of PR-A that embed no new judgment would self-merge on green, but nothing should land before R1–R8 are answered.
