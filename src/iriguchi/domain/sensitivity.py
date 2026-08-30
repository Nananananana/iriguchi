"""The veto axis.

Sensitivity removes destinations. It does not score them, rank them, or trade
against anything, and there is no arithmetic in this module that a complexity
signal could ever participate in (ADR-0003).

The asymmetry that forces this: routing something outbound that should have
stayed local is a leak, and it cannot be undone. Routing something local that
could safely have left costs answer quality, and the person notices immediately.
Once both are one number, a sufficiently difficult prompt out-votes a finding,
because addition has no way to express "this destination is not available at any
price".

A scanner *proposes* findings. This decides what they mean. A hallucinating
model, a broken regex or an adapter returning nonsense can therefore make this
router over-cautious, and cannot make it leak.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from .destination import Destination
from .span import Span

__all__ = ["Finding", "Sensitivity", "SensitivityLevel"]


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing a scanner thought was sensitive.

    Three fields, and there is deliberately nowhere to put a fourth holding the
    matched text. A test asserts the field set, because the failure mode is a
    field somebody adds in good faith while debugging and forgets to remove.

    There is no confidence here either. A scanner that is unsure has two honest
    options -- report it, or do not -- and a confidence float would become a
    threshold, and a threshold is a score. Filtering by confidence is the
    scanner's business, and it happens before a `Finding` exists.
    """

    #: Namespaced rule id, matching the `Reason.rule` it will produce.
    rule: str
    #: Which scanner proposed it.
    source: str
    span: Span

    def __post_init__(self) -> None:
        if not self.rule:
            raise ValueError("a finding must name the rule that produced it")


class SensitivityLevel(Enum):
    """What the findings, taken together, mean.

    Two members, and the absence of a third is the design. There is no "high"
    or "critical": a credential and an email address remove the same
    destination, because there is only one destination to remove and no way to
    remove it twice.

    A level that graded severity would invite a policy that graded response,
    and the only response above "do not send this" is "do not process this at
    all" -- which is not something a *local* model needs protecting from. Text
    that stays on the machine is text that stayed on the machine, whatever is
    in it.
    """

    #: No scanner found anything. Every offered destination survives.
    CLEAR = "clear"
    #: Something was found. Nothing may leave.
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class Sensitivity:
    """What a scan concluded, and what it permits."""

    level: SensitivityLevel
    findings: tuple[Finding, ...] = field(default=())

    @classmethod
    def from_findings(cls, findings: Iterable[Finding]) -> Sensitivity:
        """One finding is enough.

        There is no threshold and no counting, because a count is a score and a
        score is something a complexity signal could eventually be compared
        against.
        """
        ordered = tuple(sorted(findings, key=lambda f: (f.span, f.source, f.rule)))
        level = SensitivityLevel.RESTRICTED if ordered else SensitivityLevel.CLEAR
        return cls(level=level, findings=ordered)

    def permit(self, offered: frozenset[Destination]) -> frozenset[Destination]:
        """Narrow `offered`. Never widen it.

        Intersecting rather than returning a computed set is the point: this
        cannot hand back a destination the machine never offered, so a bug here
        can refuse a prompt and cannot route one somewhere that does not exist.
        """
        if self.level is SensitivityLevel.CLEAR:
            return offered
        return offered & {Destination.LOCAL}
