import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models  # noqa: F401 — registers all tables on database.Base.metadata


def _enforce_sqlite_fks(dbapi_connection, _connection_record):
    """Turn ON `PRAGMA foreign_keys` for every SQLite connection.

    SQLite ships FK enforcement OFF by default, so the suite historically ran
    FK-BLIND — a child row could be inserted with no parent and pass. That masked a
    real ordering bug in the Hevy ingest path (autoflush=False + no `relationship()`
    let the unit of work emit `hevy_sets` before its parent `hevy_workouts`; on
    Postgres this is `hevy_sets_workout_id_fkey`, DECISIONS_LOG #239 follow-up).
    Enforcing FKs here makes the test substrate match Postgres so that class of bug is
    caught in CI, not on first prod run.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture()
def db_session():
    """Isolated in-memory SQLite session per test — never touches the dev/prod DB.

    Prod-faithful on both axes so referential-integrity and flush-ordering bugs surface
    here rather than in production: FK enforcement ON (see `_enforce_sqlite_fks`) and
    `autoflush=False`, mirroring `database.SessionLocal`."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enforce_sqlite_fks)
    database.Base.metadata.create_all(engine)
    session = sessionmaker(autoflush=False, bind=engine)()
    _seed_canonical_entries(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


_SEED_PATH = Path(__file__).resolve().parent / "reference" / "marker_canonical.json"


def _seed_canonical_entries(session) -> None:
    """Seed `marker_canonical_entries` exactly as the migration does (#220).

    `create_all` builds the table but not its contents, while in production the map
    arrives via the migration's seed. Without this, every confirm-path test would see an
    empty map and read as "nothing is canonical" — which is a fixture artefact, not the
    behaviour under test. Both paths therefore seed from the same JSON artefact.
    """
    entries = json.loads(_SEED_PATH.read_text(encoding="utf-8"))["entries"]
    session.add_all([
        models.MarkerCanonicalEntry(
            marker_name_raw=e["marker_name_raw"],
            marker_canonical=e.get("marker_canonical"),
            unit_established=e.get("unit_established"),
            loinc=e.get("loinc"),
            source="seed",
        )
        for e in entries
    ])
    session.commit()
