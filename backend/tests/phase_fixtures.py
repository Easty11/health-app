"""Test-side helper for seeding the phase ledger.

`engine.training_phase.open_phase` (a commit-wrapper whose only production caller was the removed
`POST /engine/phase` route, #378) is gone; the phase transition is the one production write path and
batches through `_apply_open_phase`. Tests that just need a ledger row call this instead: same
validator and close/insert mechanics (the shared core), committed.
"""
from __future__ import annotations

from typing import Any

import models
from engine import training_phase as phase_mod


def open_phase(db, user_id: int, payload: dict[str, Any]) -> models.TrainingPhase:
    phase = phase_mod._apply_open_phase(db, user_id, payload)
    db.commit()
    db.refresh(phase)
    return phase
