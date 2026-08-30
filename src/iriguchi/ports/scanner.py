"""What a sensitivity scanner has to be.

A scanner proposes. It says "there is something here, and here is the rule that
thought so", and that is the whole of its authority: what a finding *means* is
`domain/sensitivity.py`'s business, and what it does to the route is
`domain/policy.py`'s. A scanner that hallucinated every finding in a document
would make this router refuse to send anything, and could not make it send
something it should not.

That is the reason the interface is this narrow. There is no method here that
returns a level, a score, a verdict, or a recommendation.

Two implementations are planned. The built-in fallback is deliberately dumb and
over-detects on purpose (ADR-0005). mamori's adapter is the one that can tell an
order number from a My Number, and installing it is what buys back the ability
to send anything at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..domain.sensitivity import Finding

__all__ = ["SensitivityScanner"]


@runtime_checkable
class SensitivityScanner(Protocol):
    """Text in, findings out."""

    @property
    def name(self) -> str:
        """How this scanner identifies itself in an explanation.

        Every `Finding` it returns carries this as its `source`, and the
        conformance suite checks that. Two scanners can fire on the same span
        for different reasons, and a person reading `--explain` needs to know
        whether they are looking at the fallback's shape heuristic or at
        mamori's rule -- because the first is expected to be wrong sometimes and
        the second much less so.
        """
        ...

    def scan(self, text: str) -> Sequence[Finding]:
        """Everything this scanner thinks is sensitive in `text`.

        Offsets are into `text` exactly as given. A scanner that works on
        normalized text -- and a good one will, because `ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ`
        and `tanaka@example.com` are the same address -- has to map back before
        it returns. The conformance suite checks this with full-width and
        Japanese input, which is where an offset silently shifts.

        Findings may overlap freely, in any number. Nothing downstream resolves
        them into one winner per character, because nothing downstream needs to:
        a route is removed by the first finding and cannot be removed twice.

        The same text twice must give identical output, in the same order.

        Raises:
            ScanError: if it cannot answer. Returning an empty sequence to
                signal failure is the one thing a scanner must never do -- at
                the call site, "I found nothing" and "I broke" are
                indistinguishable, and the first is safe while the second is
                not.
        """
        ...
