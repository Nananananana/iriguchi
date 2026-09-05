"""Whether a weak local answer may be asked again, somewhere larger.

One question, asked of the decision that already happened rather than of the
prompt. That is the whole design, and the reason it is safe.

## The rule

A cascade may escalate **only when the original decision left the external
destination on the table**. Not when it would be useful, not when the answer was
disappointing -- only when the veto had already cleared the prompt to leave and
something other than sensitivity kept it home.

`docs/proposals/0001-the-design.md` wrote the constraint before the code existed:
*escalate a weak local answer, but only where the domain says the prompt was
permitted to leave in the first place.* This module is that sentence.

## What it deliberately cannot do

**It never reads the prompt.** Everything it needs is in the `RoutingDecision`,
and taking the text would make it possible -- eventually, by someone in a hurry
-- to re-scan with a weaker scanner, or to weigh "how sensitive, really?" against
"how bad was the answer?". That trade is the one this project exists to refuse,
so the function is not given the material to make it.

**A weak answer is not evidence about sensitivity.** It is evidence about a
model. If the scanner removed the external destination, a disappointing local
answer leaves it removed -- the finding did not become less true because the 3B
model struggled.

**It is not a second chance for a refusal.** A prompt that was refused had no
destination at all; there is no local answer to judge, and nothing to escalate
from.
"""

from __future__ import annotations

from dataclasses import dataclass

from .answer import AnswerQuality
from .decision import RoutingDecision
from .destination import Destination, Route
from .reason import Reason

__all__ = ["EscalationVerdict", "escalation_possible", "may_escalate"]

#: What says the escalation is iriguchi's own decision rather than a scanner's.
SOURCE = "cascade"


@dataclass(frozen=True, slots=True)
class EscalationVerdict:
    """Whether to ask again, and the account of why.

    A value rather than a bool, for the reason every other decision here is one:
    *no* and *no, because a finding removed the destination* send a reader to
    different places, and a caller that cannot tell them apart will report the
    wrong thing to the person waiting.
    """

    escalate: bool
    reason: Reason

    def __bool__(self) -> bool:
        return self.escalate


def _reason(rule: str, detail: str) -> Reason:
    return Reason(rule=f"{SOURCE}.{rule}", source=SOURCE, span=None, detail=detail)


def escalation_possible(
    decision: RoutingDecision, available: frozenset[Destination]
) -> EscalationVerdict | None:
    """Whether escalation could happen at all, before anyone judges anything.

    Every refusal here is a property of the routing decision and the machine,
    not of the answer -- so all of them can be settled **before** a judge runs.
    That matters because judging is not free: the only judge measured to work
    re-asks the local model, and paying for a second inference to discover there
    was never anywhere to escalate to is a bill for nothing.

    Found by running it. A machine with a local model and no external endpoint
    took the second call every time and then reported *there is nowhere to
    escalate to* -- correct, and after the money.

    Returns:
        The refusal, when there is one. `None` when escalation is structurally
        possible and the only remaining question is whether the answer deserves
        it -- which is `may_escalate`'s half.
    """
    if decision.route is Route.REFUSED:
        return EscalationVerdict(
            False,
            _reason(
                "nothing-was-answered",
                "the prompt was refused, so there is no local answer to escalate from",
            ),
        )
    if decision.route is Route.EXTERNAL:
        return EscalationVerdict(
            False,
            _reason(
                "already-external",
                "this prompt was already answered externally; a cascade escalates a "
                "local answer, and there is no larger destination beyond this one",
            ),
        )
    if Destination.EXTERNAL not in available:
        return EscalationVerdict(
            False,
            _reason(
                "no-external-destination",
                "there is no external service configured, so there is nowhere to "
                "escalate to. That is a missing endpoint rather than a refusal",
            ),
        )
    if Destination.EXTERNAL in {removal.destination for removal in decision.removed}:
        return EscalationVerdict(
            False,
            _reason(
                "external-was-removed",
                "the external destination was removed for this prompt and a weak "
                "answer is not evidence about sensitivity. The finding did not "
                "become less true because the local model struggled",
            ),
        )
    return None


def may_escalate(
    decision: RoutingDecision,
    quality: AnswerQuality,
    available: frozenset[Destination],
) -> EscalationVerdict:
    """Whether a weak local answer may be re-asked externally.

    Args:
        decision: The routing decision that produced the local answer. Read for
            what it permitted, never re-derived.
        quality: What a judge concluded about the local answer.
        available: What this machine can actually reach. **Required, and not
            inferable from `decision`**: an empty `removed` means nothing was
            taken away, which is not the same as something having been there --
            a prompt with no findings on a machine with no external endpoint has
            an empty `removed` and nowhere to escalate to. Conflating those two
            is the defect this project has now found in three different places,
            so this function is given the fact rather than left to guess it.

    Returns:
        A verdict carrying the reason, in every branch. There is no branch that
        returns a bare `False`.
    """
    impossible = escalation_possible(decision, available)
    if impossible is not None:
        return impossible

    if not quality.is_weak:
        return EscalationVerdict(
            False,
            _reason(
                "answer-was-adequate",
                f"the local answer showed no weakness worth escalating (score {quality.score:.2f})",
            ),
        )

    named = ", ".join(signal.rule for signal in quality.signals) or "no named signal"
    return EscalationVerdict(
        True,
        _reason(
            "weak-answer",
            f"the local answer was weak ({named}) and the external destination was "
            f"never removed for this prompt",
        ),
    )
