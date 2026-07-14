"""Workout history renders CATALOGUE titles, not Hevy's logged snapshot (#81).

The fixture is the real, prod-confirmed instance: template `B5D3A742` is
`Bulgarian Split Squat (Dumbbell)` in the live 494-row catalogue, and the user's
own Hevy history logs it as bare `Bulgarian Split Squat` — a title present in NO
template (DECISIONS_LOG #79, confirmed by the id-keyed coverage audit
2026-07-14).
"""
from datetime import datetime, timezone

import pytz

import context_builder
import models
from hevy_templates import catalogue_titles_by_id
from routers import chat as chat_mod

AEST = pytz.timezone("Australia/Brisbane")
NOW = AEST.localize(datetime(2026, 7, 14, 9, 30, 0))

BSS_ID = "B5D3A742"
BSS_CATALOGUE = "Bulgarian Split Squat (Dumbbell)"
BSS_LOGGED = "Bulgarian Split Squat"


def _seed(db, tid, title, is_custom=False, owner=None):
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=is_custom, owner_user_id=owner,
    ))


def _hevy_data(*exercises):
    return {
        "workout_count": 1,
        "recent_workouts": [{
            "title": "Lower A",
            "start_time": "2026-07-10T08:00:00Z",
            "end_time": "2026-07-10T09:00:00Z",
            "exercises": [
                {"exercise_template_id": tid, "title": t, "sets": []}
                for tid, t in exercises
            ],
        }],
    }


# --------------------------------------------------------------------------- #
# The join (hevy_templates.catalogue_titles_by_id)                             #
# --------------------------------------------------------------------------- #

def test_catalogue_titles_by_id_returns_current_title(db_session):
    _seed(db_session, BSS_ID, BSS_CATALOGUE)
    db_session.commit()
    assert catalogue_titles_by_id(db_session, {BSS_ID}) == {BSS_ID: BSS_CATALOGUE}


def test_catalogue_titles_by_id_omits_unknown_ids(db_session):
    """An id with no catalogue row is ABSENT, never mapped to a guessed title."""
    assert catalogue_titles_by_id(db_session, {"ghost"}) == {}
    assert catalogue_titles_by_id(db_session, set()) == {}


# --------------------------------------------------------------------------- #
# Upstream annotation (routers/chat._annotate_canonical_titles)                #
# --------------------------------------------------------------------------- #

def test_annotate_sets_canonical_title_over_drifted_logged_title(db_session):
    _seed(db_session, BSS_ID, BSS_CATALOGUE)
    db_session.commit()

    data = _hevy_data((BSS_ID, BSS_LOGGED))
    chat_mod._annotate_canonical_titles(data, db_session)

    ex = data["recent_workouts"][0]["exercises"][0]
    assert ex["canonical_title"] == BSS_CATALOGUE
    assert ex["title"] == BSS_LOGGED, "the logged title is preserved, not overwritten"


def test_annotate_leaves_uncatalogued_id_unannotated(db_session):
    data = _hevy_data(("ghost1", "Mystery Move"))
    chat_mod._annotate_canonical_titles(data, db_session)
    assert "canonical_title" not in data["recent_workouts"][0]["exercises"][0]


def test_annotate_is_noop_without_template_ids(db_session):
    data = {"workout_count": 0, "recent_workouts": []}
    assert chat_mod._annotate_canonical_titles(data, db_session) is data


# --------------------------------------------------------------------------- #
# Render (context_builder._section_hevy) — a pure formatter, no Session        #
# --------------------------------------------------------------------------- #

def test_history_renders_catalogue_title_not_logged_title(db_session):
    """The whole point: the model is shown the title the resolver can match."""
    _seed(db_session, BSS_ID, BSS_CATALOGUE)
    db_session.commit()

    data = _hevy_data((BSS_ID, BSS_LOGGED))
    chat_mod._annotate_canonical_titles(data, db_session)
    rendered = context_builder._section_hevy(
        data["workout_count"], data["recent_workouts"], NOW
    )

    assert BSS_CATALOGUE in rendered
    assert f"1. {BSS_CATALOGUE} [ID: {BSS_ID}]" in rendered
    # The drifted logged title must not be what we hand the model.
    assert f"1. {BSS_LOGGED} [ID:" not in rendered
    assert "UNCATALOGUED" not in rendered


def test_uncatalogued_id_falls_back_to_logged_title_and_is_marked(db_session):
    data = _hevy_data(("ghost1", "Mystery Move"))
    chat_mod._annotate_canonical_titles(data, db_session)
    rendered = context_builder._section_hevy(
        data["workout_count"], data["recent_workouts"], NOW
    )
    assert "Mystery Move" in rendered
    assert "[UNCATALOGUED — logged title, may not resolve]" in rendered


def test_section_hevy_takes_no_session_and_renders_annotation_only():
    """context_builder stays formatter-only (the #43 parity invariant, #80): it
    reads `canonical_title` off the payload and never queries. Passing an
    annotated dict with no DB in sight must render the catalogue title."""
    data = _hevy_data((BSS_ID, BSS_LOGGED))
    data["recent_workouts"][0]["exercises"][0]["canonical_title"] = BSS_CATALOGUE
    rendered = context_builder._section_hevy(1, data["recent_workouts"], NOW)
    assert BSS_CATALOGUE in rendered


def test_unannotated_payload_still_renders_logged_title_marked():
    """Back-compat: a caller that never annotates (no canonical_title anywhere)
    still gets a readable history — marked, not silently canonical-looking."""
    data = _hevy_data((BSS_ID, BSS_LOGGED))
    rendered = context_builder._section_hevy(1, data["recent_workouts"], NOW)
    assert BSS_LOGGED in rendered
    assert "UNCATALOGUED" in rendered
