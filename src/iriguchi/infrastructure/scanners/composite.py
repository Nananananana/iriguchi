"""Several scanners, one veto.

Written because a measurement said the obvious ranking was wrong. Against the
real Presidio, on a machine with the model installed:

    "Please summarise the memo that Katherine Whitfield sent."
        presidio  -> presidio.person
        fallback  -> nothing

    "Acme Corporation の田中さんに連絡してください"
        presidio  -> nothing
        fallback  -> fallback.japanese-honorific

**They are complementary, not ranked.** Swapping the built-in scanner for
Presidio would close the English-name gap and open a Japanese one, and a user
who read *Presidio is the better scanner* and selected it would have quietly
made their own detection worse. Neither is a superset of the other, so the thing
to do is run both.

That is sound only because sensitivity is a **veto** (ADR-0003): findings remove
destinations and never add one, so a union of two scanners' findings is at least
as restrictive as either alone. There is no combination rule to get wrong, no
weight to tune, and no way for two scanners to disagree -- one of them finding
something is the whole condition. A composite over a *score* would need all of
that; a composite over a veto needs none of it.

## A failure in one member fails the whole thing

Not skipped, not degraded. If Presidio breaks, iriguchi does not know what it
would have found, and reporting the built-in scanner's findings alone would be a
veto that is quietly weaker than the one that was asked for -- with nothing in
the explanation saying so. ADR-0002 turns the raised error into the most
restrictive route with a reason, which is the honest outcome.

This is the same rule `interop.findings_from_presidio` applies to a malformed
batch, and it is the rule this project keeps arriving at: **a check that
silently covers less than it claims is worse than a check that stops.**
"""

from __future__ import annotations

from collections.abc import Sequence

from ...domain.sensitivity import Finding
from ...errors import ScanError
from ...ports.scanner import SensitivityScanner

__all__ = ["CompositeScanner"]


class CompositeScanner:
    """Every member's findings, unioned.

    Args:
        scanners: The members, in the order their findings should be attributed.
            Each keeps its own `source` on each finding, so an explanation says
            which scanner objected rather than crediting the composite.

    Raises:
        ValueError: for an empty membership. A composite of nothing is a scanner
            that finds nothing, which is a disabled veto wearing a name that
            reads like a stronger one.
    """

    def __init__(self, scanners: Sequence[SensitivityScanner]) -> None:
        if not scanners:
            raise ValueError(
                "a composite scanner needs at least one member. An empty one "
                "reports no findings, which is indistinguishable from a clean "
                "prompt and is how a veto gets turned off by accident."
            )
        self._scanners = tuple(scanners)
        self.name = "+".join(scanner.name for scanner in self._scanners)

    @property
    def members(self) -> tuple[SensitivityScanner, ...]:
        """The scanners this runs, so `doctor` can say what is actually on."""
        return self._scanners

    def scan(self, text: str) -> tuple[Finding, ...]:
        """Every member's findings, ordered by offset and de-duplicated.

        Two scanners finding the same thing at the same offset under the same
        rule is one finding, not two: the veto is identical either way, and a
        doubled entry in an explanation reads as two separate problems.

        Findings that agree on the span but not the rule are both kept -- they
        are two scanners saying different things about one stretch of text, and
        collapsing them would throw away the more specific one at random.

        Raises:
            ScanError: if any member fails, naming which. Not skipped: iriguchi
                cannot know what the broken one would have found, and a union
                missing an unknown part of itself is weaker than it claims.
        """
        found: list[Finding] = []
        for scanner in self._scanners:
            try:
                found.extend(scanner.scan(text))
            except ScanError as failure:
                raise ScanError(
                    f"the {scanner.name!r} member of {self.name!r} failed: {failure} "
                    f"The other members are not reported on their own -- a veto "
                    f"missing an unknown part of itself is not a weaker veto, it "
                    f"is one nobody can reason about."
                ) from failure

        unique = {
            (finding.span.start, finding.span.end, finding.rule): finding for finding in found
        }
        return tuple(sorted(unique.values(), key=lambda f: (f.span.start, f.span.end, f.rule)))
