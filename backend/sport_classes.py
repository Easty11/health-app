"""NON_TRAINING_SPORTS — the ONE static non-training exclusion set (#322, S1).

Sessions whose raw `aerobic_sessions.sport_name` is in this set are NOT training for the two
consumers that ask "was this a training session?":
  • `reads.psychological_reads._duration_min_by_day` — contributes no felt-load minutes and no
    session tally (Q160 → #322 S3: `session_rpe` is one whole-day RPE, so non-training minutes
    would inflate the day's felt load);
  • `cbti.replay.load_nights` (`_TRAINING_SQL`) — never sets a night's `training_end`
    (Q162 → #322 S4).
Every other session counts, including generic names ("Fitness", "Other Workout", blank, NULL).

Matching is the Q164 rule: EXACT on the raw device string, case-insensitive, no trimming, no
fuzzy/category matching, no ingest normalisation (#322 S5). Applies to ALL sources.

Deliberately STATIC — NOT derived from activity-slot `device_sports` declarations: those are
phase-scoped, so deriving from them would make a historical day's classification change when
a phase changes (breaks series invariance, #302). The metabolic load deposit has NO sport
exclusion (#322 S2) — this set must not be imported there.

Every consumer imports this module; none declares its own list
(`tests/test_non_training_sports.py` fails if one does).
"""
from __future__ import annotations

from typing import Optional

NON_TRAINING_SPORTS = frozenset({"Walking", "Pilates", "Yoga", "Stretching"})

# Lower-cased form for case-insensitive matching (Python and SQL `LOWER(sport_name)`).
NON_TRAINING_SPORTS_LOWER = frozenset(s.lower() for s in NON_TRAINING_SPORTS)


def is_non_training(sport_name: Optional[str]) -> bool:
    """True iff `sport_name` is in NON_TRAINING_SPORTS (case-insensitive exact). NULL/blank → False."""
    return sport_name is not None and sport_name.lower() in NON_TRAINING_SPORTS_LOWER
