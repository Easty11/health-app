"""Read-only check of stored Garmin overnight HRV against values read off the Garmin app.

    /opt/venv/bin/python -m scripts.garmin_verify --night 2026-09-27 --expect 1=39 4=31

For each `user=ms` it reads that user's `garmin` `hrv_readings.rmssd_ms` for the night and prints
PASS or FAIL against the expected value (default tolerance 0.5 ms, since the app shows whole
numbers). It also reports how many nights the listed users hold an IDENTICAL garmin value, the
signature of one Garmin account connected to two users (expect 0 after the fix).

One SELECT per read, no writes, no secrets, ASCII output. Exit 0 = every expectation PASSed,
1 = at least one FAILed (a missing reading is a FAIL, never a silent pass).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from sqlalchemy import text


def parse_expect(items: list[str]) -> dict[int, float]:
    out: dict[int, float] = {}
    for it in items:
        uid, _, ms = it.partition("=")
        if not uid.strip().isdigit() or not ms:
            raise ValueError(f"--expect wants user=ms (e.g. 1=39), got {it!r}")
        out[int(uid)] = float(ms)
    return out


def check(conn, night: date, expect: dict[int, float], tolerance: float) -> tuple[list[str], bool]:
    lines: list[str] = []
    ok = True
    values: dict[int, float | None] = {}
    for uid, want in sorted(expect.items()):
        row = conn.execute(
            text("SELECT rmssd_ms FROM hrv_readings WHERE user_id = :u AND source = 'garmin' AND captured_at = :n"),
            {"u": uid, "n": night}).first()
        got = None if row is None else row[0]
        values[uid] = got
        if got is None:
            lines.append(f"  user {uid}: expected {want:g} ms  stored: NO READING  FAIL")
            ok = False
        elif abs(float(got) - want) <= tolerance:
            lines.append(f"  user {uid}: expected {want:g} ms  stored: {float(got):g} ms  PASS")
        else:
            lines.append(f"  user {uid}: expected {want:g} ms  stored: {float(got):g} ms  FAIL")
            ok = False
    ids = sorted(expect)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            n = conn.execute(text(
                "SELECT COUNT(*) FROM hrv_readings x JOIN hrv_readings y"
                " ON y.user_id = :b AND y.source = 'garmin' AND y.captured_at = x.captured_at"
                " AND y.rmssd_ms = x.rmssd_ms WHERE x.user_id = :a AND x.source = 'garmin'"),
                {"a": a, "b": b}).scalar_one()
            lines.append(f"  nights where users {a} and {b} hold an IDENTICAL garmin value: {n}"
                         + ("" if n == 0 else "  (a copy signature; expect 0 once the mix-up is fixed)"))
    return lines, ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Read-only stored-vs-app Garmin HRV check.")
    p.add_argument("--night", required=True, help="YYYY-MM-DD (the wake-day Garmin files the night under)")
    p.add_argument("--expect", nargs="+", required=True, metavar="USER=MS")
    p.add_argument("--tolerance", type=float, default=0.5)
    args = p.parse_args(argv)
    try:
        night, expect = date.fromisoformat(args.night), parse_expect(args.expect)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    import database

    with database.engine.connect() as conn:  # SELECT only; rolls back on close
        lines, ok = check(conn, night, expect, args.tolerance)
    print("\n".join([f"Garmin overnight HRV, night {night}:", *lines, "", "READ-ONLY: nothing was written.",
                     "RESULT: " + ("ALL PASS" if ok else "FAIL")]).encode("ascii", "backslashreplace").decode("ascii"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
