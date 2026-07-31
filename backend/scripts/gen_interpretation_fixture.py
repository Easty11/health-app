"""Generate `frontend/src/fixtures/interpretationExample.json` from `build_foundation`.

WHY THIS EXISTS. The frontend fixture was **hand-transcribed** from the contract's §2 worked
example, not produced by the producer — so it drifted the moment the producer's shape moved, which
is `Q54` ("the view renders against a superseded contract"). Regenerating it by hand would
re-create the same fragility. This script makes it a build artefact instead: run it, commit the
result, and the fixture cannot silently disagree with the code that will serve the real thing.

WHAT IT DOES **NOT** TOUCH: `backend/tests/fixtures/interpretation_s2.json`. That file is the §2
**conformance oracle** — the independent statement of what the producer *should* emit. Generating
an oracle from the thing it tests makes the test self-referential and worthless. It stays
hand-maintained, and `test_interpretation_producer_foundation.py` keeps checking the producer
against it.

SYNTHETIC DATA, DELIBERATELY. The seed below reproduces the §2 worked example's readings — the
same ones `_seed_fixture` uses in the test suite. It is NOT generated from the live database: the
fixture is committed to the repo, and the live series is one real person's lab results. A dev-time
fallback is not a reason to put someone's health data in git. The live shape reaches the view
through the endpoint, not through this file.

Usage (from `backend/`):
    .venv/Scripts/python.exe scripts/gen_interpretation_fixture.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from interpretation.producer import build_foundation

_OUT = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "fixtures" / "interpretationExample.json"

_PRIOR = date(2026, 1, 7)
_CURRENT = date(2026, 5, 30)
_VITD = date(2025, 12, 27)


def _report(db, user_id, collected, panel_name):
    r = models.LabReport(
        user_id=user_id, lab_name="Example Pathology", panel_name_raw=panel_name,
        collected_date=collected, source_completeness="sonic_dx_extract",
        source="file_extraction", overall_confidence=0.99,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _result(db, report_id, raw, canonical, **kw):
    row = models.LabResult(lab_report_id=report_id, marker_name_raw=raw,
                           marker_canonical=canonical, confidence=0.99, **kw)
    db.add(row)
    db.commit()
    return row


def build() -> dict:
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    user = models.User(email="fixture@example.com", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)

    prior = _report(db, user.id, _PRIOR, "Androgens")
    current = _report(db, user.id, _CURRENT, "Gonadal Hormones")
    vitd = _report(db, user.id, _VITD, "Vitamin D")

    # §2 worked-example readings — identical to tests/_seed_fixture.
    _result(db, prior.id, "Testosterone (total)", "testosterone_total",
            value_num=22.5, unit_canonical="nmol/L", ref_low=10.0, ref_high=30.0)
    _result(db, current.id, "Testosterone (total)", "testosterone_total",
            value_num=24.0, unit_canonical="nmol/L", ref_low=10.0, ref_high=30.0)

    _result(db, prior.id, "Oestradiol", "oestradiol",
            value_num=110.0, unit_canonical="pmol/L", ref_high=165.0)
    _result(db, current.id, "Oestradiol", "oestradiol",
            value_num=141.0, unit_canonical="pmol/L", ref_high=165.0)

    _result(db, prior.id, "FSH", "fsh", value_num=0.1, value_operator="<",
            unit_canonical="IU/L", ref_low=1.5, ref_high=12.4, lab_flag="L")
    _result(db, current.id, "FSH", "fsh", value_num=0.1, value_operator="<",
            unit_canonical="IU/L", ref_low=1.5, ref_high=12.4, lab_flag="L")

    _result(db, prior.id, "AST", "ast", value_num=47.0,
            unit_canonical="U/L", ref_high=40.0, lab_flag="H")
    _result(db, current.id, "AST", "ast", value_num=32.0,
            unit_canonical="U/L", ref_high=40.0)

    _result(db, vitd.id, "25-OH Vitamin D", "vitamin_d_25oh", value_num=90.0,
            unit_canonical="nmol/L", ref_low=50.0, ref_high=150.0)

    return build_foundation(user.id, db, trigger_panel=current, prior_panel=prior)


def main() -> int:
    out = build()
    # `generated_at` is a wall-clock stamp. Left in the object (the contract carries it) but
    # pinned here, so re-running the generator produces a byte-identical file and a spurious
    # diff never masks a real shape change.
    out["meta"]["generated_at"] = "2026-01-01T00:00:00+00:00"
    _OUT.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {_OUT}")
    print(f"groups={[g['group_key'] for g in out['groups']]} "
          f"ungrouped={[r['marker_canonical'] for r in out['ungrouped']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
