"""What a complexity estimator has to be.

The same shape as `SensitivityScanner`, and for the same reason: it proposes
signals, and `domain/complexity.py` decides what they add up to. An estimator
cannot return a band, because a band is a decision.

Estimators are held to a looser standard than scanners, deliberately. A wrong
signal costs answer quality; a missed finding costs a leak. So this port has no
equivalent of the scanner's rule against signalling failure by returning
nothing: an estimator that cannot form an opinion has legitimately formed the
opinion that there is nothing unusual here, and `Complexity.from_signals(())` is
the lowest band, which routes local. Silence is the safe answer on this axis and
the dangerous one on the other.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..domain.complexity import Signal

__all__ = ["ComplexityEstimator"]


@runtime_checkable
class ComplexityEstimator(Protocol):
    """Text in, signals out."""

    @property
    def name(self) -> str:
        """How this estimator identifies itself in an explanation."""
        ...

    def estimate(self, text: str) -> Sequence[Signal]:
        """Every reason this text might be harder than it looks.

        Offsets, where a signal has them, are into `text` exactly as given. A
        signal about the request as a whole -- its length, its script mix --
        carries no span rather than a span covering everything, because a span
        of `0-4000` in an explanation tells a reader nothing they did not
        already know.

        The same text twice must give identical output, in the same order.

        Raises:
            EstimationError: if it cannot answer at all. Rare by construction:
                most estimators can always return an empty sequence, and doing
                so is a legitimate opinion rather than a failure.
        """
        ...
