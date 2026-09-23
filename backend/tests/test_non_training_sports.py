"""#322 S1 — ONE static non-training set, imported by every consumer; no second list.

Fails if either consumer (`reads/psychological_reads.py`, `cbti/replay.py`) stops importing
`sport_classes`, or if any backend module other than `sport_classes.py` declares its own list —
detected as a literal containing two or more of the set's members (case-insensitive) in
non-test source. The metabolic transform must NOT import it (#322 S2: no sport exclusion for
the metabolic deposit).
"""
import itertools
import re
from pathlib import Path

from sport_classes import NON_TRAINING_SPORTS, is_non_training

BACKEND = Path(__file__).resolve().parents[1]
CONSUMERS = ("reads/psychological_reads.py", "cbti/replay.py")
_IMPORT_RE = re.compile(r"^from sport_classes import\b", re.M)


def test_set_is_the_ratified_four():
    assert NON_TRAINING_SPORTS == {"Walking", "Pilates", "Yoga", "Stretching"}


def test_matching_is_case_insensitive_exact():
    assert is_non_training("walking") and is_non_training("PILATES") and is_non_training("Yoga")
    for s in (None, "", "Fitness", "Other Workout", "Walk", " Walking", "Nordic walking"):
        assert not is_non_training(s), s


def test_every_consumer_imports_the_shared_set():
    for rel in CONSUMERS:
        assert _IMPORT_RE.search((BACKEND / rel).read_text(encoding="utf-8")), rel


def test_no_second_list_anywhere():
    members = [m.lower() for m in NON_TRAINING_SPORTS]
    # any two members as quoted string literals within one 200-char span = a declared list
    pats = [
        re.compile(rf"""["']{a}["'][\s\S]{{0,200}}?["']{b}["']""", re.I)
        for a, b in itertools.permutations(members, 2)
    ]
    offenders = []
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if rel == "sport_classes.py" or rel.startswith(("tests/", "migrations/")):
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if any(p.search(src) for p in pats):
            offenders.append(rel)
    assert offenders == [], f"declare non-training sports only in sport_classes.py: {offenders}"


def test_metabolic_transform_does_not_import_it():
    assert "sport_classes" not in (BACKEND / "load_events_metabolic.py").read_text(encoding="utf-8")
