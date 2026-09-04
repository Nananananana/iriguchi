"""Whether an answer was any good, from the answer alone.

**This is the axis that does not have to guess.** The complexity estimator is
asked *will a small model manage this?* before anybody has tried, and
[`feasibility.md`](../../../docs/feasibility.md) F1 records how that goes: 42.9%
on prompts written to test it, against 35.7% for always saying `low`. Eleven of
the thirteen hardest were kept local because the request did not announce its own
difficulty.

The cascade sidesteps the guess. Ask the local model, look at what came back, and
escalate only if it is visibly poor. A judgement made after the fact needs no
prediction, and the thing it inspects -- an answer -- is far more legible than
the thing the estimator inspects, which is an intention.

## Why this does not contradict ADR-0004

ADR-0004 pins the router at "before the request, always", and says plainly:
*a decision made after a first response is a decision made after the text was
already sent.* That objection is exact and it is about text **leaving the
machine**.

The first hop of a cascade is **local**. The prompt went to a model on this
machine, the answer came back from this machine, and nothing crossed a boundary
to inform the second decision. The invariant ADR-0004 protects is untouched, and
the sentence that protects it stays true.

The consequence is a hard constraint rather than a preference: **a cascade whose
first hop is external is not a cascade, it is two requests.** The escalation
path only exists downhill from a local answer.

## Why the veto is not re-litigated

A weak answer is not new evidence about sensitivity. If the scanner removed the
external destination, it stays removed however disappointing the local model was
-- `escalation_permitted` reads the original decision and never the prompt again.
The alternative, "the answer was bad enough to be worth the risk", is the exact
trade this project exists to refuse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import prod
from typing import TYPE_CHECKING

from .span import Span

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "DEFAULT_ADEQUACY",
    "Adequacy",
    "AnswerQuality",
    "AnswerSignal",
    "Weakness",
]


class Weakness(Enum):
    """Which family of evidence says an answer is poor.

    Two, and the split matters for what a reader should do about it. A `STATED`
    weakness is the model telling you it could not help, which is information
    and is usually true. A `SHAPE` weakness is iriguchi inferring from the form
    of the text, which is a proxy and can be wrong about a terse correct answer.
    """

    #: The answer says so itself: a refusal, an apology, "I don't know".
    STATED = "stated"
    #: The form of the answer: truncated, repeating itself, echoing the prompt.
    SHAPE = "shape"


@dataclass(frozen=True, slots=True)
class AnswerSignal:
    """One piece of evidence that an answer is not good enough."""

    rule: str
    kind: Weakness
    #: How much this on its own suggests the answer is weak, in ``[0, 1]``.
    #: Evidence, not a vote share -- see `AnswerQuality.from_signals`.
    weight: float
    #: Whether this alone settles it. A model that said "I cannot help with
    #: that" has answered the question about its own adequacy.
    decisive: bool = False
    #: Where in the answer, when the signal is about a place in it.
    span: Span | None = None

    def __post_init__(self) -> None:
        if not self.rule:
            raise ValueError("a signal must name the rule that produced it")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"signal weight must be within [0, 1], got {self.weight}")


class Adequacy(Enum):
    """Two bands, not three.

    The complexity axis has a middle band because an explanation benefits from
    distinguishing "not obviously easy" from "actually hard". This one does not:
    the question it answers is *do we ask a bigger model*, which is a yes or a
    no, and a middle band would be a third answer to a two-answer question.
    """

    ADEQUATE = "adequate"
    WEAK = "weak"


@dataclass(frozen=True, slots=True)
class AnswerQuality:
    """What a judge concluded about an answer."""

    adequacy: Adequacy
    score: float
    signals: tuple[AnswerSignal, ...] = field(default=())
    #: True when a single decisive signal settled it rather than the score. A
    #: reader seeing `weak` beside a score of 0.4 needs to know why.
    decided_outright: bool = False

    @property
    def is_weak(self) -> bool:
        return self.adequacy is Adequacy.WEAK

    @classmethod
    def from_signals(
        cls, signals: Iterable[AnswerSignal], weak_at: float | None = None
    ) -> AnswerQuality:
        """Combine signals into an adequacy.

        The same noisy-OR the complexity axis uses -- ``1 - prod(1 - w)`` --
        for the same reasons: bounded by construction, monotonic in every
        weight, and it does not make the fortieth signal free while the fourth
        was not. Using one combination rule in both places is deliberate; two
        would be two things to get wrong and two explanations to read.

        On top sits one rule with no counterpart on the other axis: **a single
        decisive signal settles it.** There is no "two escalating markers"
        equivalent, because a model saying "I don't know" is not partial
        evidence that needs corroborating. It is the answer.
        """
        cut = DEFAULT_ADEQUACY if weak_at is None else weak_at
        if not 0.0 <= cut <= 1.0:
            raise ValueError(f"weak_at must be within [0, 1], got {cut}")
        ordered = tuple(sorted(signals, key=lambda s: (s.rule, s.kind.value)))
        score = 1.0 - prod(1.0 - signal.weight for signal in ordered)
        decided = any(signal.decisive for signal in ordered)
        weak = decided or score >= cut
        return cls(
            adequacy=Adequacy.WEAK if weak else Adequacy.ADEQUATE,
            score=score,
            signals=ordered,
            decided_outright=decided,
        )


#: Where an answer stops being good enough to keep.
#:
#: **Chosen to be hard to reach by accumulation**, on purpose. Every shape
#: signal here is a proxy that can be wrong about a terse correct answer, and
#: the cost of being wrong is sending a prompt to a bigger model that did not
#: need to go -- which on the external route means sending it off the machine.
#: Two mild shape signals should not add up to that; a stated refusal should
#: settle it on its own, and does, through `decisive`.
DEFAULT_ADEQUACY = 0.7
