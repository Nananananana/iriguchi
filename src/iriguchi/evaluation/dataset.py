"""Loading the corpus.

Two kinds of file, one shape. Both are committed JSON under `data/`, and neither
needs a model, a network or a sibling library to read -- which is what lets the
corpus run in the same poisoned-network test suite as everything else.

The borrowed file deserves a note. mamori's evaluation data is exactly the
labelled sensitivity corpus this project needs, and `evaluation/` is forbidden to
import mamori (the `mamori-is-an-adapter` contract). Reaching into an installed
package's data directory would need that import, so the borrowing happens once,
offline, in `tools/borrow_mamori_cases.py`, and what is committed here is the
result. The corpus therefore works with mamori absent, which is the
configuration most people will be in.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..domain.complexity import ComplexityBand
from .case import Case, SensitivityClass, TrapKind

__all__ = ["DATA_DIR", "load_case", "load_cases", "load_corpus"]

DATA_DIR = Path(__file__).parent / "data"

#: The contract these files speak. Bumped only when a reader would break; a new
#: optional field does not need it.
FORMAT_VERSION = 1


def load_case(raw: dict[str, object], source: str) -> Case:
    """One case from its JSON form.

    Unknown keys are refused rather than ignored. A misspelled `trap` that
    silently became `PLAIN` would quietly remove an adversary from the corpus,
    and the corpus would go on reporting a number as though it still covered
    that case.
    """
    known = {"id", "prompt", "sensitivity", "band", "trap", "note"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(f"case {raw.get('id')!r} has unknown keys {unknown}")

    return Case(
        id=str(raw["id"]),
        prompt=str(raw["prompt"]),
        sensitivity=SensitivityClass(raw["sensitivity"]),
        band=ComplexityBand(raw["band"]),
        trap=TrapKind(raw.get("trap", "plain")),
        source=source,
        note=str(raw.get("note", "")),
    )


def load_cases(path: Path) -> tuple[Case, ...]:
    """Every case in one file, in file order."""
    document = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"{path.name} declares format_version {version!r}; this build reads "
            f"{FORMAT_VERSION}. Refusing rather than guessing."
        )
    source = str(document.get("source", path.stem))
    return tuple(load_case(raw, source) for raw in document["samples"])


def load_corpus(directory: Path | None = None) -> tuple[Case, ...]:
    """Every case in every file, sorted by id.

    Sorted rather than concatenated in whatever order the filesystem produced,
    because a report whose case order depends on a directory listing is a report
    that differs between machines for no reason anybody can see.
    """
    root = DATA_DIR if directory is None else directory
    cases: list[Case] = []
    for path in sorted(root.glob("*.json")):
        cases.extend(load_cases(path))

    duplicates = _duplicate_ids(cases)
    if duplicates:
        raise ValueError(f"the corpus has duplicate case ids: {duplicates}")
    return tuple(sorted(cases, key=lambda case: case.id))


def _duplicate_ids(cases: list[Case]) -> list[str]:
    seen: set[str] = set()
    twice: set[str] = set()
    for case in cases:
        (twice if case.id in seen else seen).add(case.id)
    return sorted(twice)
