"""ID-keyed exercise-tag coverage audit (DECISIONS_LOG #79).

Pins the three-state classification, the title-drift case that motivated the
whole decision (a template logged under a title the catalogue no longer
carries), the window filter, and the read-only contract.
"""
from datetime import datetime, timedelta, timezone

import pytest

import audit_exercise_tag_coverage as audit
import models
from engine import selection

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def _seed_template(db, tid, title, adjudicated=False):
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=False, owner_user_id=None,
        adjudicated_at=NOW if adjudicated else None,
    ))


def _tag(db, tid, region_key):
    db.add(models.ExerciseRegionTag(
        hevy_exercise_template_id=tid, region_key=region_key,
        role="primary", source="human_confirmed",
    ))


def _workout(*exercises, days_ago=1):
    return {
        "start_time": (NOW - timedelta(days=days_ago)).isoformat(),
        "exercises": [
            {"exercise_template_id": tid, "title": title} for tid, title in exercises
        ],
    }


@pytest.fixture
def three_state(db_session):
    """One template in each coverage state.

    `bss1` is the real DECISIONS_LOG #79 case: the catalogue carries
    'Bulgarian Split Squat (Dumbbell)' but the user's history logs the movement
    as bare 'Bulgarian Split Squat'. It is TAGGED — proving the id-keyed join
    sees coverage that a title-keyed pass would score as a miss.
    """
    _seed_template(db_session, "bss1", "Bulgarian Split Squat (Dumbbell)")
    _tag(db_session, "bss1", "lunge_single_leg")
    _seed_template(db_session, "ser1", "Shoulder External Rotation", adjudicated=True)
    _seed_template(db_session, "legext1", "Leg Extension (Machine)")
    db_session.commit()
    return db_session


def test_three_states_are_classified_and_hit_rate_computed(three_state):
    workouts = [_workout(
        ("bss1", "Bulgarian Split Squat"),        # logged title != catalogue title
        ("ser1", "Shoulder External Rotation"),
        ("legext1", "Leg Extension (Machine)"),
    )]
    report = audit.audit_coverage(three_state, workouts)

    assert report["counts"] == {
        selection.COVERAGE_TAGGED: 1,
        selection.COVERAGE_ADJUDICATED_NO_PATTERN: 1,
        selection.COVERAGE_UNTAGGED: 1,
    }
    assert report["distinct_movements"] == 3
    # Only the never-adjudicated template counts as a gap — 1 of 3.
    assert report["fallback_hit_rate"] == pytest.approx(1 / 3)


def test_title_drift_is_surfaced_not_scored_as_a_miss(three_state):
    """The #79 corollary: keying on id, the drifted BSS resolves as TAGGED and
    the drift is REPORTED. A title-keyed audit would have called it untagged."""
    report = audit.audit_coverage(three_state, [_workout(("bss1", "Bulgarian Split Squat"))])

    tagged = report["movements"][selection.COVERAGE_TAGGED]
    assert [m["template_id"] for m in tagged] == ["bss1"]
    assert tagged[0]["catalogue_title"] == "Bulgarian Split Squat (Dumbbell)"
    assert tagged[0]["logged_titles"] == ["Bulgarian Split Squat"]
    assert tagged[0]["title_drift"] is True
    assert report["fallback_hit_rate"] == 0.0
    assert "logged as: Bulgarian Split Squat" in audit.render(report, days=28)


def test_no_drift_flag_when_titles_agree(three_state):
    report = audit.audit_coverage(
        three_state, [_workout(("bss1", "Bulgarian Split Squat (Dumbbell)"))]
    )
    assert report["movements"][selection.COVERAGE_TAGGED][0]["title_drift"] is False


def test_same_template_under_several_logged_titles(three_state):
    """Drift is per-window, not per-workout: the same id logged under two titles
    keeps both."""
    report = audit.audit_coverage(three_state, [
        _workout(("bss1", "Bulgarian Split Squat"), days_ago=2),
        _workout(("bss1", "Bulgarian Split Squat (Dumbbell)"), days_ago=1),
    ])
    assert report["distinct_movements"] == 1
    assert report["movements"][selection.COVERAGE_TAGGED][0]["logged_titles"] == [
        "Bulgarian Split Squat", "Bulgarian Split Squat (Dumbbell)",
    ]


def test_classification_matches_the_read_path(three_state):
    """The audit must measure what infer_loaded_regions DOES. Same fixture, both
    paths: exactly the audit's TAGGED movement contributes a region; the
    adjudicated and untagged ones contribute none (the untagged title matches no
    keyword needle, so the fallback fires and yields nothing)."""
    workouts = [_workout(
        ("bss1", "Bulgarian Split Squat"),
        ("ser1", "Shoulder External Rotation"),
        ("legext1", "Leg Extension (Machine)"),
    )]
    got = selection.infer_loaded_regions(workouts, db=three_state)
    assert got == {"lunge_single_leg"}

    report = audit.audit_coverage(three_state, workouts)
    assert report["counts"][selection.COVERAGE_UNTAGGED] == 1


def test_template_absent_from_catalogue_is_untagged_and_marked(three_state):
    """A logged template with no local catalogue row still counts as a gap and
    is not silently dropped."""
    report = audit.audit_coverage(three_state, [_workout(("ghost1", "Mystery Move"))])
    untagged = report["movements"][selection.COVERAGE_UNTAGGED]
    assert untagged[0]["template_id"] == "ghost1"
    assert untagged[0]["catalogue_title"] is None
    assert report["fallback_hit_rate"] == 1.0
    assert "<NOT IN LOCAL CATALOGUE>" in audit.render(report, days=28)


# --------------------------------------------------------------------------- #
# Window filter                                                                #
# --------------------------------------------------------------------------- #

def test_window_excludes_workouts_outside_the_window():
    inside = _workout(("bss1", "x"), days_ago=27)
    outside = _workout(("bss1", "x"), days_ago=29)
    kept = audit.workouts_in_window([inside, outside], 28, now=NOW)
    assert kept == [inside]


def test_window_excludes_unparseable_and_missing_timestamps():
    """A workout that cannot be shown to fall inside the window is excluded —
    never counted in by default."""
    kept = audit.workouts_in_window(
        [{"exercises": []}, {"start_time": "not-a-date", "exercises": []}], 28, now=NOW
    )
    assert kept == []


def test_window_falls_back_to_created_at():
    w = {"created_at": (NOW - timedelta(days=1)).isoformat(), "exercises": []}
    assert audit.workouts_in_window([w], 28, now=NOW) == [w]


def test_empty_window_rate_is_reported_as_vacuous(db_session):
    report = audit.audit_coverage(db_session, [])
    assert report["distinct_movements"] == 0
    assert report["fallback_hit_rate"] == 0.0
    assert "vacuous" in audit.render(report, days=28)


# --------------------------------------------------------------------------- #
# Read-only contract                                                           #
# --------------------------------------------------------------------------- #

def test_audit_writes_nothing(three_state):
    before_tags = three_state.query(models.ExerciseRegionTag).count()
    before_templates = three_state.query(models.HevyExerciseTemplate).count()

    audit.audit_coverage(three_state, [_workout(
        ("bss1", "Bulgarian Split Squat"),
        ("ghost1", "Mystery Move"),
    )])

    assert not three_state.new and not three_state.dirty and not three_state.deleted
    assert three_state.query(models.ExerciseRegionTag).count() == before_tags
    assert three_state.query(models.HevyExerciseTemplate).count() == before_templates
