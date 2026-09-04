"""Presidio's shape, without Presidio.

Two directions, and they are not symmetric — which is the interesting part.

    findings_from_presidio   their results  ->  iriguchi findings
    to_presidio              iriguchi findings  ->  their shape

**Coming in, a score is discarded. Going out, a score is invented and labelled.**
Both are losses and both are stated, because a compatibility layer that quietly
fills a field with something it does not mean is worse than one that refuses to
fill it at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from ..domain.sensitivity import Finding
from ..domain.span import Span
from ..errors import IriguchiError

__all__ = [
    "SOURCE",
    "InteropError",
    "RecognizerResult",
    "findings_from_presidio",
    "to_presidio",
]

#: What a finding built from somebody else's analyzer says about where it came
#: from. Not `fallback` and not `mamori`: a person reading an explanation needs
#: to know the veto came from a scanner iriguchi does not control, because that
#: is the one it cannot answer questions about.
SOURCE = "presidio"


class InteropError(IriguchiError):
    """A foreign result could not be read.

    Its own type rather than `ValueError`, so a caller converting a batch can
    tell *this analyzer output is malformed* from *this program has a bug* --
    and so the message can name the item rather than the field.
    """


@dataclass(frozen=True, slots=True)
class RecognizerResult:
    """The same attributes Presidio's has, and none of its behaviour.

    Not a subclass, because subclassing would require Presidio to be installed
    and the point is that it is not. Anything reading `.entity_type`, `.start`,
    `.end` or `.score` works unchanged; anything calling a Presidio method does
    not, and should be reading these attributes anyway.

    Frozen, like every other value here.
    """

    entity_type: str
    start: int
    end: int
    #: **Always 1.0, and that is not a measurement.**
    #:
    #: Presidio's score is a confidence its recognizers produce. iriguchi has
    #: none: a scanner that is unsure has two honest options, report it or do
    #: not, and a confidence would become a threshold. So every finding iriguchi
    #: reports is one it stands behind, which is what 1.0 means here -- *this
    #: was found*, not *this is 100% certain*.
    #:
    #: Filling it with 1.0 rather than omitting it is the lesser of two evils:
    #: the field is required by every consumer of this shape, and a `None` there
    #: breaks arithmetic downstream. The docstring is the honest part.
    score: float = 1.0
    recognition_metadata: dict[str, Any] = field(default_factory=dict)


def _read(item: object) -> tuple[str, int, int]:
    """Entity, start and end, from a dict or from anything with the attributes.

    Duck-typed on purpose. **A fixture loaded from JSON is the commonest thing
    anybody actually holds**, and requiring a class here would put an install
    back in front of somebody trying to find out whether this is worth using.
    """
    if isinstance(item, dict):
        missing = {"entity_type", "start", "end"} - set(item)
        if missing:
            raise InteropError(
                f"a result is missing {sorted(missing)}: {item!r}. A Presidio "
                f"`RecognizerResult` carries all three, and a dict from "
                f"`.to_dict()` does too."
            )
        label, start, end = item["entity_type"], item["start"], item["end"]
    else:
        try:
            label, start, end = item.entity_type, item.start, item.end  # type: ignore[attr-defined]
        except AttributeError as failure:
            raise InteropError(
                f"{type(item).__name__} is neither a mapping nor an object with "
                f"`entity_type`, `start` and `end`: {failure}"
            ) from failure
    try:
        return str(label), int(start), int(end)
    except (TypeError, ValueError) as failure:
        raise InteropError(f"offsets in {item!r} are not integers: {failure}") from failure


def findings_from_presidio(results: Iterable[object]) -> tuple[Finding, ...]:
    """Somebody else's analyzer output, as findings iriguchi can veto on.

    Accepts `RecognizerResult` objects, Presidio's own, dicts from `.to_dict()`,
    or anything carrying the three attributes.

    **The incoming `score` is discarded**, and that is the decision rather than
    an oversight. iriguchi's veto has no degrees: a finding removes the external
    destination, and a finding at 0.4 confidence removing it *slightly* is not a
    thing this design has. Storing the number would mean either ignoring it --
    a field filled with something it does not mean -- or growing a threshold,
    which is the score this project refuses to have.

    Somebody who wants to act on Presidio's confidence should filter **before**
    calling this, with `score_threshold=` on their own analyzer, where the
    number came from and where it means what they think.

    Raises:
        InteropError: for a result missing the three fields, or with offsets
            that are not integers. Refused per item and named, rather than
            skipped -- a batch that silently drops the malformed half is a batch
            whose veto is quietly weaker than it looks.
    """
    findings: list[Finding] = []
    for index, item in enumerate(results):
        try:
            label, start, end = _read(item)
            findings.append(
                Finding(rule=f"{SOURCE}.{label.lower()}", source=SOURCE, span=Span(start, end))
            )
        except (InteropError, ValueError) as failure:
            raise InteropError(f"result {index}: {failure}") from failure
    return tuple(findings)


def to_presidio(findings: Iterable[Finding]) -> Iterator[RecognizerResult]:
    """iriguchi's findings, in the shape a Presidio consumer expects.

    `entity_type` is the rule id with its source prefix removed and upper-cased,
    which is the nearest honest mapping: `fallback.email` becomes `EMAIL`.
    **It is a rename and not a translation** -- iriguchi's rule set and
    Presidio's entity vocabulary are different lists, and a rule with no
    Presidio counterpart keeps its own name rather than being forced into the
    closest-looking one.

    `recognition_metadata` carries the original rule id and source, so nothing
    is lost by the rename and a consumer can tell which scanner spoke.
    """
    for finding in findings:
        _, _, tail = finding.rule.partition(".")
        yield RecognizerResult(
            entity_type=(tail or finding.rule).upper().replace("-", "_"),
            start=finding.span.start,
            end=finding.span.end,
            recognition_metadata={"iriguchi_rule": finding.rule, "iriguchi_source": finding.source},
        )
