"""
Garmin sync runner — the batch sweep over Garmin-connected users, reused by two callers:

  * `scripts/garmin_sync.py` CLI (this file's `main`) — ops one-shots, run in the container from /app
    (`railway ssh --service health-app-backend`, then `/opt/venv/bin/python -m scripts.garmin_sync`).
  * The in-process nightly sweep (`load_sweep._sweep`, #299) — garmin_sync as the second job
    on #297's 02:00 Brisbane rail, beside the load chain.

`sweep_garmin_hrv` is the reusable core: it sweeps every user with a Garmin Personal API key or DI token
(or one named user), pulls their HRV for a date window through the Personal API, and upserts into
hrv_readings + hrv_samples via the shared per-user core (`routers.garmin.sync_hrv_for_user`). The Personal
API is the only HRV, self-evaluation and wellness lane (#449, PR-B); the DI token keeps one job, epoch SpO2
(#450). A user with no personal key is reported `no_personal_key` and counted failed, so a missing key is
loud, and their SpO2 still runs. PER-USER ISOLATION: one user's refused key (GarminPersonalKeyError) or any
other failure is caught, rolled back, logged and skipped — it never aborts the batch. Idempotent: the upsert
keys on (user, night, source).

    /opt/venv/bin/python -m scripts.garmin_sync                 # last 7 nights, all users
    /opt/venv/bin/python -m scripts.garmin_sync --days 30
    /opt/venv/bin/python -m scripts.garmin_sync --from 2026-08-01 --to 2026-08-31
    /opt/venv/bin/python -m scripts.garmin_sync --user-id 4     # one user only
"""
import argparse
import logging
import sys
from datetime import date, timedelta
from typing import Any

import garmin_personal_lanes as gpl
import garmin_raw
import garmin_selfeval
import garmin_spo2
import garmin_wellness
from connectors.garmin import GarminClient, GarminReconnectError
from database import SessionLocal
from encryption import decrypt
import models
from routers.garmin import _store_token, garmin_wake_day, sync_hrv_for_user

logger = logging.getLogger(__name__)

# Default window when no explicit range is given — a week of nights. Enough to cover the prior
# night plus a short self-heal tail.
_DEFAULT_SWEEP_DAYS = 7


# The wellness capture re-reads only the last few days on the nightly sweep: a day's sleep and body battery
# settle within a day or two, and each day costs one call per endpoint. An explicit window (CLI --from /
# --days, a backfill) is honoured in full.
WELLNESS_SWEEP_DAYS = 3

_SELFEVAL_COUNTS = ("fetched", "rated", "unrated", "skipped_needs_refresh", "errors")


_SPO2_COUNTS = ("nights_fetched", "nights_inserted", "nights_replaced", "nights_unchanged", "nights_empty",
                "readings", "skipped_epochs", "duplicate_epochs", "skipped_needs_refresh", "errors")


def _spo2_step(db, uid: int, factory, start: date, end: date) -> dict[str, Any]:
    """The Garmin overnight SpO2 capture (Q150) for one user: soft-fail by construction, the same shape as
    `_selfeval_step`. It runs AFTER `sync_hrv_for_user`, which has refreshed the token and committed it
    back, through a client that cannot refresh (#361). Any failure -> `{"error": ...}`, session rolled
    back; it never changes the user's HRV outcome or the self-evaluation capture."""
    try:
        return garmin_spo2.sync_user(db, uid, start=start, end=end, factory=factory)
    except Exception as exc:  # noqa: BLE001 -- soft-fail: a SpO2 failure never costs the HRV sweep
        db.rollback()
        logger.warning("garmin sweep: user %s spo2 step failed: %s", uid, type(exc).__name__)
        return {"error": f"{type(exc).__name__}: {exc}"}


def _personal_selfeval_step(db, uid: int, transport=None) -> dict[str, Any]:
    """Self-evaluation capture through the Personal API (same `garmin_selfeval.sync_user` body, source
    'garmin', transport 'personal_api'). Never raises; records the `personal_selfeval` lane."""
    return gpl.run_lane(
        db, uid, garmin_raw.LANE_PERSONAL_SELFEVAL,
        lambda client: garmin_selfeval.sync_user(db, uid, source=client, transport="personal_api"),
        transport=transport)


def _wellness_step(db, uid: int, start: date, end: date, transport=None) -> dict[str, Any]:
    """Sleep, daily HR, hourly SpO2, body battery, stress and the HR-zone config (S3). Never raises."""
    return gpl.run_lane(
        db, uid, garmin_raw.LANE_PERSONAL_WELLNESS,
        lambda client: garmin_wellness.sync_user(db, uid, client, start=start, end=end),
        transport=transport)


def _di_keepalive(db, uid: int) -> str:
    """Refresh the DI token and write it back BEFORE the SpO2 read. Until the Personal API took HRV, the
    DI HRV pull did this as a side effect (`sync_hrv_for_user`), and the SpO2 read goes through a client
    that cannot refresh (#361): with no refresh, the DI blob ages out and the epoch-SpO2 lane (the CPAP
    seal evidence) silently dies. Returns 'ok', 'reconnect_required' (the DI token is dead) or 'failed'
    (a transient error; the read is still attempted with the token we hold)."""
    row = db.query(models.UserIntegration).filter_by(user_id=uid, provider="garmin").first()
    if row is None:
        return "failed"
    try:
        client = GarminClient.from_token(decrypt(row.api_key_encrypted))
        _store_token(db, row, client.dump_token())
        db.commit()
        return "ok"
    except GarminReconnectError:
        db.rollback()
        return "reconnect_required"
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("garmin sweep: user %s DI keepalive failed: %s", uid, type(exc).__name__)
        return "failed"


def _di_spo2_lane(db, uid: int, factory, start: date, end: date, *, keepalive: bool) -> dict[str, Any]:
    """The DI epoch-SpO2 lane for one user: optional keepalive, the capture, and the `di_spo2` lane status.
    A dead DI token is recorded as `auth_failed`, never skipped silently (S5)."""
    if keepalive:
        ka = _di_keepalive(db, uid)
        if ka == "reconnect_required":
            garmin_raw.record_lane(db, uid, garmin_raw.LANE_DI_SPO2, garmin_raw.AUTH_FAILED, "GarminReconnectError")
            return {"error": "GarminReconnectError: DI token cannot authenticate", "keepalive": ka}
    result = _spo2_step(db, uid, factory, start, end)
    if "error" in result:
        garmin_raw.record_lane(db, uid, garmin_raw.LANE_DI_SPO2, garmin_raw.ERROR, str(result["error"]).split(":")[0])
    elif result.get("skipped_needs_refresh"):
        garmin_raw.record_lane(db, uid, garmin_raw.LANE_DI_SPO2, garmin_raw.SKIPPED_NEEDS_REFRESH)
    elif result.get("errors"):
        garmin_raw.record_lane(db, uid, garmin_raw.LANE_DI_SPO2, garmin_raw.ERROR, f"errors={result['errors']}")
    else:
        garmin_raw.record_lane(db, uid, garmin_raw.LANE_DI_SPO2, garmin_raw.OK)
    return result


def sweep_garmin_hrv(
    db,
    *,
    only_user_id: int | None = None,
    days: int = _DEFAULT_SWEEP_DAYS,
    start: date | None = None,
    end: date | None = None,
    spo2_factory=garmin_spo2.ProbeSource,
    personal_transport=None,
) -> dict[str, Any]:
    """Pull + upsert Garmin HRV for every connected user (or just `only_user_id`) over the
    window, isolating per-user failures. Returns an aggregate summary (mirrors `refresh_load`).

    Not a route and not CLI-shaped, so it is callable from the nightly sweep. `db` is caller-owned
    (the CLI opens its own; the sweep passes its `SessionLocal()`); a per-user failure rolls the
    session back so the next user starts clean.

    After each Personal API user's HRV pull, `garmin_selfeval` reads that user's per-activity self-evaluation
    (Q209) into the source-neutral sRPE store through the user's `PersonalClient`, and `garmin_wellness` captures
    sleep, heart rate, hourly SpO2, body battery, stress and the HR-zone config. Both skip a user whose key was
    refused (`reconnect_required`), are soft-fail, and report their counts under `per_user[uid]["selfeval"]` and
    `["wellness"]`, summed under the summary keys of the same names.

    Last, `garmin_spo2` captures the user's overnight SpO2 (Q150) for the same wake-date window, raw, through
    the DI token (the DI lane's one remaining job, #450), after a keepalive that refreshes that token. It is its
    own soft-fail step: its counts sit under `per_user[uid]["spo2"]` and summed under `summary["spo2"]`, and a
    failure in it never changes the user's HRV, self-evaluation or wellness outcome."""
    today = garmin_wake_day()   # AEST wake-day, not UTC (#327 follow-up)
    end = end or today
    explicit_window = start is not None
    start = start or (end - timedelta(days=days))
    wellness_start = start if explicit_window else max(start, end - timedelta(days=WELLNESS_SWEEP_DAYS))

    # Every user with EITHER a DI token or a Personal API key. A personal-only user has no DI row.
    q = db.query(models.UserIntegration.user_id).filter(models.UserIntegration.provider.in_(("garmin", gpl.PROVIDER)))
    if only_user_id is not None:
        q = q.filter(models.UserIntegration.user_id == only_user_id)
    user_ids = sorted({uid for (uid,) in q.all()})

    per_user: dict[int, dict] = {}
    succeeded = failed = 0
    for uid in user_ids:
        try:
            result = sync_hrv_for_user(db, uid, start, end)
            succeeded += 1
            per_user[uid] = {"status": "succeeded", **result}
            logger.info(
                "garmin sweep: user %s OK — %s readings, %s samples (%s days with data)",
                uid, result["readings_upserted"], result["samples_upserted"],
                result["days_with_data"],
            )
        except GarminReconnectError as exc:
            failed += 1
            per_user[uid] = {"status": "reconnect_required", "error": str(exc)}
            logger.warning("garmin sweep: user %s reconnect needed — %s", uid, exc)
            db.rollback()
        except gpl.NoPersonalKey:
            failed += 1
            per_user[uid] = {"status": "no_personal_key", "error": "no garmin_personal key"}
            logger.warning("garmin sweep: user %s has no personal key: no HRV, self-evaluation or wellness pull", uid)
            db.rollback()
        except Exception as exc:  # noqa: BLE001 — one user's failure never aborts the sweep
            failed += 1
            per_user[uid] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            logger.exception("garmin sweep: user %s failed", uid)
            db.rollback()
        hrv_dead = per_user[uid]["status"] == "reconnect_required"
        if gpl.get_row(db, uid) is not None and not hrv_dead:
            # Personal API user: self-evaluation and wellness come from the official host, after the HRV pull.
            per_user[uid]["selfeval"] = _personal_selfeval_step(db, uid, personal_transport)
            per_user[uid]["wellness"] = _wellness_step(db, uid, wellness_start, end, personal_transport)
        if db.query(models.UserIntegration.id).filter_by(user_id=uid, provider="garmin").first() is not None:
            # The DI lane's one job: epoch SpO2 + breathing disruptions. Nothing else refreshes its token any
            # more, so it refreshes its own first.
            per_user[uid]["spo2"] = _di_spo2_lane(db, uid, spo2_factory, start, end, keepalive=True)

    selfeval_total = {k: 0 for k in _SELFEVAL_COUNTS}
    for detail in per_user.values():
        ev = detail.get("selfeval")
        if isinstance(ev, dict) and "error" not in ev:
            for k in _SELFEVAL_COUNTS:
                selfeval_total[k] += ev.get(k, 0)
        elif isinstance(ev, dict):
            selfeval_total["errors"] += 1

    spo2_total = {k: 0 for k in _SPO2_COUNTS}
    for detail in per_user.values():
        sp = detail.get("spo2")
        if isinstance(sp, dict) and "error" not in sp:
            for k in _SPO2_COUNTS:
                spo2_total[k] += sp.get(k, 0)
        elif isinstance(sp, dict):
            spo2_total["errors"] += 1

    wellness_total: dict[str, int] = {}
    for detail in per_user.values():
        w = detail.get("wellness")
        if isinstance(w, dict) and "error" not in w and "skipped" not in w:
            for k, v in w.items():
                wellness_total[k] = wellness_total.get(k, 0) + v
        elif isinstance(w, dict):
            wellness_total["errors"] = wellness_total.get("errors", 0) + 1

    return {
        "users_attempted": len(user_ids),
        "users_succeeded": succeeded,
        "users_failed": failed,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "selfeval": selfeval_total,
        "spo2": spo2_total,
        "wellness": wellness_total,
        "per_user": per_user,
    }


def _resolve_window(args) -> tuple[date, date]:
    today = garmin_wake_day()   # AEST wake-day, not UTC (#327 follow-up)
    end = date.fromisoformat(args.to) if args.to else today
    if args.from_:
        start = date.fromisoformat(args.from_)
    else:
        start = end - timedelta(days=args.days)
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull Garmin HRV into hrv_readings/hrv_samples.")
    parser.add_argument("--days", type=int, default=_DEFAULT_SWEEP_DAYS,
                        help=f"Window length ending today (default {_DEFAULT_SWEEP_DAYS}).")
    parser.add_argument("--from", dest="from_", help="Window start (YYYY-MM-DD); overrides --days.")
    parser.add_argument("--to", help="Window end (YYYY-MM-DD); default today.")
    parser.add_argument("--user-id", type=int, help="Sync only this user (default: all connected).")
    args = parser.parse_args()

    start, end = _resolve_window(args)
    if start > end:
        print("--from must not be after --to", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        summary = sweep_garmin_hrv(db, only_user_id=args.user_id, start=start, end=end)
        if summary["users_attempted"] == 0:
            print("No Garmin-connected users in scope.")
            return 0

        print(f"Syncing Garmin HRV for {summary['users_attempted']} user(s), {start}..{end}")
        for uid, detail in summary["per_user"].items():
            if detail["status"] == "succeeded":
                print(f"  user {uid}: {detail['readings_upserted']} readings, "
                      f"{detail['samples_upserted']} samples "
                      f"({detail['days_with_data']} days with data)")
                ev = detail.get("selfeval", {})
                if "error" in ev:
                    print(f"    selfeval: error ({ev['error']})", file=sys.stderr)
                elif ev:
                    print(f"    selfeval: fetched={ev['fetched']} rated={ev['rated']} unrated={ev['unrated']} "
                          f"skipped_needs_refresh={ev['skipped_needs_refresh']} "
                          f"errors={ev['errors']}")
                wl = detail.get("wellness")
                if isinstance(wl, dict):
                    print(f"    wellness: {wl.get('error') or wl}")
                sp = detail.get("spo2", {})
                if "error" in sp:
                    print(f"    spo2: error ({sp['error']})", file=sys.stderr)
                elif sp:
                    print(f"    spo2: nights fetched={sp['nights_fetched']} inserted={sp['nights_inserted']} "
                          f"replaced={sp['nights_replaced']} unchanged={sp['nights_unchanged']} "
                          f"empty={sp['nights_empty']} readings={sp['readings']} "
                          f"skipped_needs_refresh={sp['skipped_needs_refresh']} errors={sp['errors']}")
            else:
                print(f"  user {uid}: {detail['status'].upper()} — {detail.get('error', '')}",
                      file=sys.stderr)
        return 1 if summary["users_failed"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
