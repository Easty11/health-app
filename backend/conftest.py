import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
import models  # noqa: F401 — registers all tables on database.Base.metadata


@pytest.fixture()
def db_session():
    """Isolated in-memory SQLite session per test — never touches the dev/prod DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    database.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
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
