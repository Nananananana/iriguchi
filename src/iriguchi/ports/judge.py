"""What an answer judge has to be.

The same shape as the other two proposers: it returns signals, and
`domain/answer.py` decides what they add up to. A judge cannot return an
adequacy, because an adequacy is a decision.

Where it differs from `ComplexityEstimator` is which way silence is safe, and
the answer is the opposite of the estimator's.

An estimator that finds nothing has legitimately concluded the prompt looks
ordinary, and the lowest band routes **local**, which is the safe direction. A
judge that finds nothing has concluded the answer is fine, and an adequate
answer means **no escalation** -- which is also local, and also the safe
direction. So silence is safe on this axis too, and for a reason worth stating
rather than inheriting: **the failure mode of this port is a wasted local
answer, never a leak.**

That holds only because of the rule in `domain/cascade.py`: escalation is gated
on the original decision having left the external destination available. A judge
cannot cause a prompt to leave that was not already permitted to. The worst a
broken judge can do is escalate something that did not need it, or fail to
escalate something that did -- quality, not safety.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..domain.answer import AnswerSignal

__all__ = ["AnswerJudge"]


@runtime_checkable
class AnswerJudge(Protocol):
    """An answer in, signals out."""

    @property
    def name(self) -> str:
        """How this judge identifies itself in an explanation."""
        ...

    def judge(self, prompt: str, answer: str) -> Sequence[AnswerSignal]:
        """Every reason this answer might not be good enough.

        Args:
            prompt: What was asked, so a judge can notice an answer that
                restates it or leaves half of it unaddressed. **Read, never
                re-scanned**: a judge is not a second scanner and must not
                return findings.
            answer: What the local model said.

        Offsets, where a signal has them, are into `answer` -- not into the
        prompt. A signal about the answer as a whole carries no span.

        The same pair twice must give identical output, in the same order.

        Raises:
            JudgementError: if it cannot answer at all. Rare by construction:
                returning no signals is a legitimate opinion that the answer
                looked fine, and the caller treats it as such.
        """
        ...
