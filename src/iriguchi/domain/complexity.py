"""The preference axis.

Complexity chooses among whatever sensitivity left standing. It never restores
a destination, and it is consulted after the veto rather than alongside it
(ADR-0003).

An estimator *proposes* signals; this turns them into a band. That split is
deliberate and it is the same one sensitivity uses: the decision lives in the
domain, so a new estimator can change what is noticed and cannot change what
noticing means.

**The residual, stated plainly.** The routing literature is consistent that
semantic features dominate difficulty prediction, with lexical and structural
features as complementary indicators. Semantic features need a model, and
ADR-0004 refuses a model in the deciding path -- so this axis is built entirely
from the complementary half and is, by construction, the weaker of the two
signals. That is an accepted cost: complexity only ever picks between
destinations that are already safe, so being wrong here costs answer quality and
nothing else.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from math import prod

from .span import Span

__all__ = ["Complexity", "ComplexityBand", "Signal", "SignalKind"]

#: Score at or above which a prompt is no longer obviously easy.
_MODERATE_AT = 0.3
#: Score at or above which a prompt wants the larger model.
_HIGH_AT = 0.7
#: How many escalating signals short-circuit the weighted score. Two, not one:
#: a single marker is what an ordinary question looks like.
_SHORT_CIRCUIT_AT = 2


class SignalKind(Enum):
    """Which family of evidence a signal came from.

    Two members. A third -- `SEMANTIC` -- is deliberately absent rather than
    unimplemented: it is the family that needs a model, and ADR-0004 refuses a
    model here. Leaving the name out keeps the refusal visible, because an enum
    member nobody constructs reads as a gap rather than as a decision.
    """

    #: Properties of the words: length, rare-word rate, script mix.
    LEXICAL = "lexical"
    #: Properties of the request: code fences, requested output shape,
    #: multi-step markers, operators.
    STRUCTURAL = "structural"


@dataclass(frozen=True, slots=True)
class Signal:
    """One piece of evidence that a prompt is harder than it looks."""

    rule: str
    kind: SignalKind
    #: How much this on its own suggests difficulty, in ``[0, 1]``. It is
    #: evidence, not a vote share: see `Complexity.from_signals` for how they
    #: combine.
    weight: float
    #: Whether this signal alone marks a prompt as needing real reasoning.
    #: Two of these reach the top band whatever the weights say.
    escalating: bool = False
    #: Where, when the signal is about a place in the text rather than the
    #: whole of it.
    span: Span | None = None

    def __post_init__(self) -> None:
        if not self.rule:
            raise ValueError("a signal must name the rule that produced it")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"signal weight must be within [0, 1], got {self.weight}")


class ComplexityBand(Enum):
    """Three bands, because there are at most two destinations to choose between.

    A finer grading would be measuring something the decision cannot act on.
    The middle band exists so that "not obviously easy" and "actually hard" are
    distinguishable in an explanation, not because it routes differently from
    `LOW` today.
    """

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class Complexity:
    """What an estimator concluded."""

    band: ComplexityBand
    score: float
    signals: tuple[Signal, ...] = field(default=())
    #: True when the band came from the escalating-signal rule rather than from
    #: the score. Worth reporting: a person looking at a `HIGH` band next to a
    #: score of 0.1 needs to know why, or the explanation looks broken.
    short_circuited: bool = False

    @classmethod
    def from_signals(cls, signals: Iterable[Signal]) -> Complexity:
        """Combine signals into a band.

        Weights combine as independent evidence -- ``1 - prod(1 - w)`` -- rather
        than by adding. Adding needs a cap, and a cap makes the fortieth signal
        free while the fourth was not; this is bounded by construction,
        monotonic in every weight, and stays meaningful however many rules a
        long prompt happens to trip.

        On top of that sits one borrowed rule: **two or more escalating signals
        reach the top band regardless of the weighted score.** It exists for the
        case weighted scoring is worst at -- a prompt that asks for two hard
        things at once, where each marker is individually cheap and the sum
        lands in the middle. "Compare these two papers and prove the third's
        lemma" is two small numbers and one very hard request.
        """
        ordered = tuple(sorted(signals, key=lambda s: (s.rule, s.kind.value)))
        score = 1.0 - prod(1.0 - signal.weight for signal in ordered)

        escalating = sum(1 for signal in ordered if signal.escalating)
        short_circuited = escalating >= _SHORT_CIRCUIT_AT

        if short_circuited or score >= _HIGH_AT:
            band = ComplexityBand.HIGH
        elif score >= _MODERATE_AT:
            band = ComplexityBand.MODERATE
        else:
            band = ComplexityBand.LOW

        return cls(band=band, score=score, signals=ordered, short_circuited=short_circuited)

    @property
    def prefers_the_larger_model(self) -> bool:
        """Whether this prompt is worth an external call, if one is permitted.

        A preference, and only ever consulted about destinations sensitivity
        already allowed.
        """
        return self.band is ComplexityBand.HIGH
