"""null forward-carried daily_records.passive_hrv_ms (user 1) — DATA ONLY, HELD

HOLD FOR OPERATOR RELEASE (CLAUDE.md § Merge disposition, hold (a)). Data correction, no
schema change.

WHY. Before the HRV recency gate (#NEXT), the AM check-in Save froze
`representative_source(hrv_deviation(for_date=today))["rmssd"]` into
`daily_records.passive_hrv_ms`. `hrv_deviation` read each source's latest reading AT OR
BEFORE `for_date`, so on a morning whose night had not landed (or whose source had died) it
froze a PRIOR night's RMSSD as that day's HRV — a forward carry. Historical readers
(`/series/readiness`, MCP `get_checkin_history`) now read `hrv_readings` by wake-day
equality and fall back to this column only for a day with NO canonical row; a forward carry
on such a day would still be drawn as that day's HRV. NULLing it makes that day a gap, which
is the truth: no reading for that night existed at Save.

WHICH ROWS. Verified in chat 2026-09-17 (prod): 12 user-1 rows. The identification criteria
as briefed — a LATERAL join finding the earlier genuine `hrv_readings` row whose `rmssd_ms`
equals the frozen value, `days_back` 1–2 — are reconstructed below (the 09-17 SQL text is
not in the repo). A row qualifies when ALL hold:
  1. user_id = 1, passive_hrv_ms IS NOT NULL;
  2. NO `hrv_readings` row ON dr.date carries rmssd_ms = passive_hrv_ms (not that day's own);
  3. the most recent EARLIER `hrv_readings` row with rmssd_ms = passive_hrv_ms is 1–2 days
     before dr.date (days_back ∈ {1, 2}).
Run `IDENTIFY_SQL` read-only against prod BEFORE releasing this (the live probe is the gate —
#166: this write cannot be undone from the data alone). The upgrade re-runs it and REFUSES
(raises, transaction rolled back, nothing written) if the count is not EXPECTED_COUNT.

Count drift: Save kept writing passive_hrv_ms until the #NEXT denorm drop deployed, so the
count may exceed 12 by the time this is released. A mismatch is a HALT, never an auto-adjust
— re-verify the extra rows and re-ratify EXPECTED_COUNT in a reviewed commit.

Scope note: carries older than 2 days (e.g. a long-dead source frozen for weeks) do NOT match
criterion 3 and are left untouched here by design; see the PR for that open point.

Irreversibility: `downgrade()` is a no-op — the NULLed values are recoverable only from the
upgrade's own log line (each row's id/date/value is printed before the UPDATE) or a backup.
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


EXPECTED_COUNT = 12
USER_ID = 1

IDENTIFY_SQL = """
SELECT dr.id, dr.date, dr.passive_hrv_ms,
       src.captured_at AS carried_from, src.source AS carried_source,
       (dr.date - src.captured_at) AS days_back
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
  AND (dr.date - src.captured_at) BETWEEN 1 AND 2
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
    rows = bind.execute(sa.text(IDENTIFY_SQL), {"user_id": USER_ID}).fetchall()
    if len(rows) != EXPECTED_COUNT:
        raise RuntimeError(
            f"forward-carry identification returned {len(rows)} rows, expected "
            f"{EXPECTED_COUNT} — HALT. Re-verify and re-ratify EXPECTED_COUNT; nothing written."
        )
    for r in rows:
        print(
            f"[e3b7c5a1f942] NULL passive_hrv_ms id={r.id} date={r.date} "
            f"was={r.passive_hrv_ms} carried_from={r.carried_from} ({r.carried_source}, "
            f"{r.days_back}d back)"
        )
    ids = [r.id for r in rows]
    result = bind.execute(
        sa.text("UPDATE daily_records SET passive_hrv_ms = NULL "
                "WHERE user_id = :user_id AND id = ANY(:ids)"),
        {"user_id": USER_ID, "ids": ids},
    )
    if result.rowcount != EXPECTED_COUNT:
        raise RuntimeError(f"UPDATE touched {result.rowcount} rows, expected {EXPECTED_COUNT}")


def downgrade() -> None:
    # Irreversible data correction — see module docstring (values are in the upgrade log).
    pass
