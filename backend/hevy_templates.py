"""Hevy exercise-template sync + resolver (DECISIONS_LOG #60, #61).

The provisioning path must never source exercise-template ids live. This module
keeps a synced local store (`hevy_exercise_templates`) fresh and resolves a
canonical title to a Hevy id against it.

Sync is per-user by stored Hevy key, upsert-only (the Hevy API cannot delete
templates, so there is nothing to reconcile). Re-running is idempotent; defaults
re-upsert once per user (redundant, harmless — not optimised).

Re-runnable CLI:
    python backend/hevy_templates.py            # sync all users' keys, print summary
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from connectors.hevy import HevyClient
from encryption import decrypt

logger = logging.getLogger(__name__)

_PAGE_SIZE = 100          # confirmed max pageSize (GET /v1/exercise_templates)
_INTER_PAGE_DELAY = 0.2   # seconds — gentle on Hevy rate limits (prior art)
_MAX_429_RETRIES = 5
_BACKOFF_BASE = 1.0       # seconds; exponential per retry
_CREATE_RESOLVE_ATTEMPTS = 3  # sync+resolve tries after a create (create-visibility latency)


class HevyKeyMissingError(Exception):
    """No stored Hevy integration key for the user — cannot create a template."""
    pass


class HevyCreateUnresolvedError(Exception):
    """A custom template POST succeeded but the new id never surfaced via sync.

    Raised after the bounded sync+resolve retry exhausts without the title
    appearing in the user's custom subset — never return None silently.
    """
    pass


def users_with_hevy_key(db: Session) -> list[tuple[int, str]]:
    """(user_id, decrypted_api_key) for every user holding a Hevy integration.

    Reuses the exact accessor/decrypt path the request layer uses
    (models.UserIntegration provider='hevy' + encryption.decrypt).
    """
    rows = db.query(models.UserIntegration).filter_by(provider="hevy").all()
    return [(r.user_id, decrypt(r.api_key_encrypted)) for r in rows]


def user_hevy_key(db: Session, user_id: int) -> str | None:
    """Decrypted Hevy key for one user, or None. Same accessor/decrypt path as
    `users_with_hevy_key`, scoped to a single user (the create-loop needs one)."""
    row = db.query(models.UserIntegration).filter_by(provider="hevy", user_id=user_id).first()
    return decrypt(row.api_key_encrypted) if row is not None else None


async def _fetch_page_with_backoff(client: HevyClient, page: int) -> dict:
    """One page fetch with 429 exponential backoff. Non-429 errors propagate."""
    attempt = 0
    while True:
        try:
            return await client.get_exercise_templates(page=page, page_size=_PAGE_SIZE)
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 429 and attempt < _MAX_429_RETRIES:
                delay = _BACKOFF_BASE * (2 ** attempt)
                logger.warning("Hevy 429 on page %d — backing off %.1fs (attempt %d)", page, delay, attempt + 1)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise


def _upsert_template(db: Session, t: dict, owner_user_id: int | None, now: datetime) -> None:
    """Upsert one template row keyed on the Hevy id (PK). No delete reconciliation."""
    row = db.get(models.HevyExerciseTemplate, t["id"])
    if row is None:
        row = models.HevyExerciseTemplate(id=t["id"])
        db.add(row)
    row.title = t["title"]
    row.type = t.get("type")
    row.is_custom = bool(t.get("is_custom"))
    row.owner_user_id = owner_user_id
    row.primary_muscle_group = t.get("primary_muscle_group")
    row.secondary_muscle_groups = t.get("secondary_muscle_groups")
    row.synced_at = now


def _collision_report(db: Session) -> list[str]:
    """Report-only: titles present as BOTH a default row and any custom row.

    Surfaces where default-wins resolution (#60) could split exercise_history
    across two ids. Not acted on here — handled case-by-case.
    """
    Template = models.HevyExerciseTemplate
    default_titles = set(db.scalars(select(Template.title).where(Template.is_custom.is_(False))))
    custom_titles = set(db.scalars(select(Template.title).where(Template.is_custom.is_(True))))
    collisions = sorted(default_titles & custom_titles)
    for title in collisions:
        logger.warning("Hevy template title collision (default + custom): %r", title)
    return collisions


def resolve_exercise(db: Session, title: str, user_id: int) -> str | None:
    """Resolve a canonical exercise title to a Hevy id for `user_id`.

    Default wins on title collision (#60): a title present as both a global
    default and the user's own custom returns the default id. Otherwise the
    user's own custom; never another user's custom. Exact canonical-title match
    only — fuzzy/normalised matching is an explicit non-goal (note: Hevy custom
    titles can carry U+2011 non-breaking hyphens, so callers must pass the
    canonical byte-exact title). Returns None if nothing matches.
    """
    Template = models.HevyExerciseTemplate
    stmt = (
        select(Template.id)
        .where(Template.title == title)
        .where((Template.is_custom.is_(False)) | (Template.owner_user_id == user_id))
        .order_by(Template.is_custom.asc())  # default (False) sorts first -> default wins
        .limit(1)
    )
    return db.scalars(stmt).first()


def resolve_custom_exercise(db: Session, title: str, user_id: int) -> str | None:
    """Resolve a title to the user's OWN custom id — custom subset only.

    Unlike `resolve_exercise` (default-wins, #60), this restricts to
    is_custom=True AND owner_user_id=user_id, so a same-titled global default can
    never mask the user's freshly minted custom UUID. The create-loop resolves
    here after sync; never via the bare-title default-wins path.
    """
    Template = models.HevyExerciseTemplate
    stmt = (
        select(Template.id)
        .where(Template.title == title)
        .where(Template.is_custom.is_(True))
        .where(Template.owner_user_id == user_id)
        .limit(1)
    )
    return db.scalars(stmt).first()


async def sync_one_user(db: Session, user_id: int, api_key: str) -> dict:
    """Sync one user's Hevy exercise templates into the local store.

    Pages the full catalogue (defaults + this user's customs) with 429 backoff,
    upserting each row. `is_custom` rows are owned by `user_id`; defaults carry
    NULL owner. Returns per-user counts. Commits per page (unchanged behaviour).
    """
    client = HevyClient(api_key)
    rows_processed = 0
    defaults_seen = 0
    customs_seen = 0
    page = 1
    while True:
        resp = await _fetch_page_with_backoff(client, page)
        rows = resp.get("exercise_templates", [])
        if not rows:
            break
        now = datetime.now(timezone.utc)
        for t in rows:
            is_custom = bool(t.get("is_custom"))
            owner = user_id if is_custom else None
            _upsert_template(db, t, owner, now)
            rows_processed += 1
            if is_custom:
                customs_seen += 1
            else:
                defaults_seen += 1
        db.commit()

        page_count = resp.get("page_count")
        if page_count is not None and page >= page_count:
            break
        page += 1
        await asyncio.sleep(_INTER_PAGE_DELAY)

    return {
        "rows_processed": rows_processed,
        "defaults_seen": defaults_seen,
        "customs_seen": customs_seen,
    }


async def sync_exercise_templates(db: Session) -> dict:
    """Sync every keyed user's Hevy exercise templates into the local store.

    Returns a summary: users synced, rows processed (defaults re-counted per
    user), and the collision report.
    """
    users = users_with_hevy_key(db)
    rows_processed = 0
    defaults_seen = 0
    customs_seen = 0

    for user_id, api_key in users:
        counts = await sync_one_user(db, user_id, api_key)
        rows_processed += counts["rows_processed"]
        defaults_seen += counts["defaults_seen"]
        customs_seen += counts["customs_seen"]

    collisions = _collision_report(db)
    summary = {
        "users_synced": len(users),
        "rows_processed": rows_processed,
        "defaults_seen": defaults_seen,
        "customs_seen": customs_seen,
        "collision_count": len(collisions),
        "collisions": collisions,
    }
    logger.info("Hevy template sync complete: %s", summary)
    return summary


async def create_and_resolve(
    db: Session,
    user_id: int,
    title: str,
    exercise_type: str,
    equipment_category: str,
    muscle_group: str,
    other_muscles: list[str] | None = None,
) -> str:
    """Create an app-originated custom exercise on Hevy and return its canonical id.

    The canonical id is read by list-back (create -> sync -> resolve within the
    user's custom subset), never trusted from the POST response body — the create
    response carries an integer id, distinct from the canonical string UUID the
    store keys on (#NEXT / resolves Q14).

    Order is load-bearing:
      1. Idempotency pre-check (`resolve_exercise`, default-wins): a same-titled
         default (#60) or the user's own existing custom short-circuits — no create.
      2. Decrypt the user's stored Hevy key.
      3. POST the custom template.
      4-5. Refresh the store (`sync_one_user`) and resolve within the custom
         subset only (`resolve_custom_exercise`) — bounded retry over 4-5 to
         absorb create-visibility latency (assumed eventual consistency).

    Raises HevyKeyMissingError if the user has no key, HevyCreateUnresolvedError
    if the new template never surfaces after the last retry, and surfaces the
    connector's HevyCustomExerciseLimitError (403) / HevyBadRequestError (400).
    """
    # 1. Idempotency pre-check — default-wins path. Only mint when genuinely absent.
    existing = resolve_exercise(db, title, user_id)
    if existing is not None:
        return existing

    # 2. Decrypted key (reuse the shared accessor/decrypt path).
    api_key = user_hevy_key(db, user_id)
    if api_key is None:
        raise HevyKeyMissingError(f"No Hevy key for user {user_id}; cannot create {title!r}")

    # 3. Create once (outside the retry — the POST is not idempotent).
    client = HevyClient(api_key)
    await client.create_exercise_template(
        title=title,
        exercise_type=exercise_type,
        equipment_category=equipment_category,
        muscle_group=muscle_group,
        other_muscles=other_muscles,
    )

    # 4-5. Sync + resolve within the custom subset, bounded retry for visibility latency.
    for attempt in range(_CREATE_RESOLVE_ATTEMPTS):
        await sync_one_user(db, user_id, api_key)
        resolved = resolve_custom_exercise(db, title, user_id)
        if resolved is not None:
            return resolved
        if attempt < _CREATE_RESOLVE_ATTEMPTS - 1:
            delay = _BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                "Created %r for user %d but unresolved after sync — retrying in %.1fs (attempt %d/%d)",
                title, user_id, delay, attempt + 1, _CREATE_RESOLVE_ATTEMPTS,
            )
            await asyncio.sleep(delay)

    raise HevyCreateUnresolvedError(
        f"Created {title!r} for user {user_id} but it never surfaced in the custom "
        f"subset after {_CREATE_RESOLVE_ATTEMPTS} sync attempts"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from database import SessionLocal

    _db = SessionLocal()
    try:
        _result = asyncio.run(sync_exercise_templates(_db))
        print(_result)
    finally:
        _db.close()
