"""null forward-carried daily_records.passive_hrv_ms (user 1) — DATA ONLY, HELD

HOLD FOR OPERATOR RELEASE (CLAUDE.md § Merge disposition, hold (a)). Data correction, no
schema change.

WHY. Before the HRV recency gate (#327), the AM check-in Save froze
`representative_source(hrv_deviation(for_date=today))["rmssd"]` into
`daily_records.passive_hrv_ms`. `hrv_deviation` read each source's latest reading AT OR
BEFORE `for_date`, so on a morning whose night had not landed (or whose source had died) it
froze a PRIOR night's RMSSD as that day's HRV — a forward carry. Historical readers
(`/series/readiness`, MCP `get_checkin_history`) now read `hrv_readings` by wake-day
equality and fall back to this column only for a day with NO canonical row; a forward carry
on such a day would still be drawn as that day's HRV. NULLing it makes that day a gap, which
is the truth: no reading for that night existed at Save.

WHICH ROWS (rule amended by operator ruling 2026-09-24). A row qualifies when ALL hold:
  1. user_id = 1, passive_hrv_ms IS NOT NULL;
  2. NO `hrv_readings` row ON dr.date carries rmssd_ms = passive_hrv_ms (not that day's own);
  3. an EARLIER `hrv_readings` row carries exactly rmssd_ms = passive_hrv_ms — the most
     recent such row (LATERAL) is the carry source, and carry age = dr.date − its date is
     >= 1 day, with NO upper bound. (The 09-17 verification's 1–2 day bound was an artefact
     of that date: the source has been dead longer since, and every later Save carried the
     same frozen value further.)

THE COUNT IS OPERATOR-SET. `EXPECTED_CARRY_COUNT` was None until release; set to 28 on 2026-09-25.
Run the preview (`IDENTIFY_SQL` / the row listing in the PR) ONLY AFTER #327 has deployed —
until then every AM Save can add another carry, so the count is still moving. Set the
constant to the reviewed preview count in a reviewed commit, then release. The upgrade
re-runs the identification and REFUSES (raises; the transaction rolls back; nothing
written) when the constant is unset or does not equal the live count. A mismatch is a HALT,
never an auto-adjust.

Irreversibility (#166 — the live preview is the gate): `downgrade()` is a no-op — the
NULLed values are recoverable only from the upgrade's own log line (each row's id/date/value is printed before the UPDATE) or a backup.
Postgres-only (LATERAL); a no-op on any other dialect.

Revision ID: e3b7c5a1f942
Revises: d9f2a1c7e4b8
Create Date: 2026-09-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'e3b7c5a1f942'
down_revision: Union[str, Sequence[str], None] = 'd9f2a1c7e4b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# OPERATOR-SET at release (see docstring): 28, from the preview run 2026-09-25 after #327
# deployed, listing reviewed — 9 single-night sync-lag carries + runs of 32 / 87 / 113 ms
# (the 113 run = samsung 2026-09-14 frozen 2026-09-15..09-24). Mismatch → refuse, zero writes.
EXPECTED_CARRY_COUNT: int | None = 28
USER_ID = 1

IDENTIFY_SQL = """
SELECT dr.id, dr.date, dr.passive_hrv_ms,
       src.captured_at AS carried_from, src.source AS carried_source,
       (dr.date - src.captured_at) AS carry_age_days
FROM daily_records dr
CROSS JOIN LATERAL (
    SELECT h.captured_at, h.source
    FROM hrv_readings h
    WHERE h.user_id = dr.user_id
      AND h.captured_at < dr.date
      AND h.rmssd_ms = dr.passive_hrv_ms
    ORDER BY h.captured_at DESC
    LIMIT 1
) src
WHERE dr.user_id = :user_id
  AND dr.passive_hrv_ms IS NOT NULL
  AND (dr.date - src.captured_at) >= 1
  AND NOT EXISTS (
      SELECT 1 FROM hrv_readings same
      WHERE same.user_id = dr.user_id
        AND same.captured_at = dr.date
        AND same.rmssd_ms = dr.passive_hrv_ms
  )
ORDER BY dr.date
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if EXPECTED_CARRY_COUNT is None:
        raise RuntimeError(
            "EXPECTED_CARRY_COUNT is unset — run the post-deploy preview, set the constant to "
            "the reviewed count, then release. Nothing written."
        )
    rows = bind.execute(sa.text(IDENTIFY_SQL), {"user_id": USER_ID}).fetchall()
    if len(rows) != EXPECTED_CARRY_COUNT:
        raise RuntimeError(
            f"forward-carry identification returned {len(rows)} rows, expected "
            f"{EXPECTED_CARRY_COUNT} — HALT. Re-verify and re-ratify EXPECTED_CARRY_COUNT; "
            "nothing written."
        )
    for r in rows:
        print(
            f"[e3b7c5a1f942] NULL passive_hrv_ms id={r.id} date={r.date} "
            f"was={r.passive_hrv_ms} carried_from={r.carried_from} ({r.carried_source}, "
            f"{r.carry_age_days}d)"
        )
    ids = [r.id for r in rows]
    result = bind.execute(
        sa.text("UPDATE daily_records SET passive_hrv_ms = NULL "
                "WHERE user_id = :user_id AND id = ANY(:ids)"),
        {"user_id": USER_ID, "ids": ids},
    )
    if result.rowcount != EXPECTED_CARRY_COUNT:
        raise RuntimeError(
            f"UPDATE touched {result.rowcount} rows, expected {EXPECTED_CARRY_COUNT}"
        )


def downgrade() -> None:
    # Irreversible data correction — see module docstring (values are in the upgrade log).
    pass
