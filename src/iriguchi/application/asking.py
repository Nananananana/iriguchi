"""Route a prompt, then act on the decision.

The first thing here that does anything irreversible, and it is arranged so
that the irreversible part is the last part.

    REFUSED    nothing happens, and the reasons say why
    LOCAL      the local model answers
    ESCALATED  the channel protects, the external model answers the protected
               text, and the escalation puts the values back

**The decision is settled before any of that.** A model that answers something
unexpected is a weak model; it is not a route and it is not a leak. kiseki put
it best while shipping a producer that calls one: *the answer is settled before
it becomes a record.*

Nothing a model returns is fed back into the **routing**. It can be fed to a
judge, and that is the cascade (ADR-0018): a local answer that looks weak may be
re-asked externally -- but only where the routing decision had already left the
external destination available. The judge never touches the veto, and
`domain/cascade.py` is not even handed the prompt, so it cannot. What the
cascade changes is *which permitted destination answers*, never *which
destinations are permitted*.

**Only one branch protects, and it is the only one that leaves.** That asymmetry
is the whole design, and it is here in one function rather than inside two
adapters, so that reading this file is enough to see it.

`Asker` does not decide whether to send. `PromptRouter` did that, `available`
came from configuration, and a destination that is not configured produces
`REFUSED` before this module is reached.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..domain.answer import AnswerQuality
from ..domain.cascade import EscalationVerdict, escalation_possible, may_escalate
from ..domain.decision import RoutingDecision
from ..domain.destination import Destination
from ..domain.reason import Reason
from ..errors import EscalationRefusedError, JudgementError
from ..ports.channel import EscalationChannel
from ..ports.judge import AnswerJudge
from ..ports.model import Model
from .routing import PromptRouter

__all__ = ["Answer", "Asker"]


@dataclass(frozen=True, slots=True)
class Answer:
    """What came back, and the whole account of how it was obtained.

    Carries the decision rather than summarising it, because a caller that
    wants to explain the route already has `RoutingDecision.reasons` and a
    second, lossier copy would be the thing that drifts.

    `text` is `None` when nothing was asked. That is the honest value for a
    refusal: an empty string would print as an answer of no words, and the two
    are different events -- the same distinction the model port refuses to
    collapse one layer down.
    """

    decision: RoutingDecision
    text: str | None = None
    #: What answered, named as a person would recognise it. Empty when nothing
    #: did.
    model: str = ""
    #: What the protection noticed that the routing decision did not. Never a
    #: copy of the protection record (ADR-0013); a kind, a count, and the
    #: scanner that missed it. Empty is the ordinary case.
    missed: Sequence[Reason] = field(default_factory=tuple)
    #: What the judge thought of the **local** answer, when a judge ran. `None`
    #: means no judge was configured, which is not the same as the answer
    #: having looked fine -- the distinction `JudgementError` exists for.
    quality: AnswerQuality | None = None
    #: Whether that judgement led anywhere, and why or why not. Present whenever
    #: a judge was configured, in every branch, because *no* and *no, because
    #: the veto had removed the destination* send a reader to different places.
    escalation: EscalationVerdict | None = None
    #: The local answer that was judged weak and replaced, when one was. Kept
    #: because a person told "the local answer was poor, here is the external
    #: one" is entitled to see the poor one.
    superseded: str | None = None

    @property
    def answered(self) -> bool:
        return self.text is not None

    @property
    def cascaded(self) -> bool:
        """True when a local answer was judged weak and re-asked externally."""
        return self.superseded is not None


@dataclass(frozen=True, slots=True)
class Asker:
    """Routes a prompt and then answers it, in that order."""

    router: PromptRouter
    #: Absent when this machine has no local model configured. The router is
    #: told the same thing through `available`, so a `LOCAL` decision cannot
    #: arrive here without one -- and if it somehow did, that is a bug and the
    #: refusal below says so rather than sending anywhere else.
    local: Model | None = None
    external: Model | None = None
    channel: EscalationChannel | None = None
    #: The cascade, when one is wanted. `None` -- the default -- means a local
    #: answer is final. Opt-in because every judge measured so far either does
    #: nothing or doubles local latency (`docs/measurements.md`), and a router
    #: should not spend a second model call on somebody who did not ask for one.
    judge: AnswerJudge | None = None

    def ask(self, text: str, available: frozenset[Destination]) -> Answer:
        """Decide, then act.

        Raises:
            ModelError: if the model that was asked could not answer. Not
                converted into an empty answer: a caller cannot tell those
                apart, and only one of them means the model said nothing.
            EscalationRefusedError: if the prompt was allowed to leave and the
                protection would not let it. Every one of those leaves the
                prompt where it is; none is a degradation to sending something
                less protected.
            RestorationError: if an answer came back and could not be fully put
                back together.
        """
        decision = self.router.route(text, available)
        if decision.was_refused:
            return Answer(decision)
        # `leaves_the_machine` rather than a comparison against a route value.
        # It is the domain's own name for the question everything here exists
        # to answer correctly, and a reader should meet it in that form.
        if decision.leaves_the_machine:
            return self._outward(decision, text)
        return self._locally(decision, text, available)

    def _locally(
        self, decision: RoutingDecision, text: str, available: frozenset[Destination]
    ) -> Answer:
        if self.local is None:
            # Unreachable through the CLI, because `available` is built from
            # the same configuration. Stated rather than asserted: a router
            # asked for a destination nothing can serve is a composition bug,
            # and the fail-closed answer to one is a refusal, not a fallback to
            # the destination that does exist.
            raise EscalationRefusedError(
                "the decision was LOCAL and no local model is configured. Nothing "
                "was sent: the answer to a missing local model is not the external "
                "one, which is the destination the decision ruled out."
            )
        first = self.local.answer(text)
        if self.judge is None:
            return Answer(decision, first, self.local.name)
        return self._cascade(decision, text, first, available)

    def _cascade(
        self,
        decision: RoutingDecision,
        text: str,
        first: str,
        available: frozenset[Destination],
    ) -> Answer:
        """Judge the local answer, and re-ask externally only where permitted.

        Three things are true of every branch here, and they are the design:

        - the local answer is **always** returned or superseded, never lost;
        - the veto is never consulted again -- `may_escalate` reads the decision
          that already exists and is not given the prompt;
        - a judge that fails is reported and the local answer stands. A cascade
          that quietly stopped cascading looks exactly like one whose answers
          were all adequate, so the failure goes into the verdict's reason.
        """
        assert self.judge is not None and self.local is not None

        # Ask the cheap half of the gate first. Every refusal it can give is a
        # property of the decision and the machine rather than of the answer, so
        # none of them needs a judge -- and the judge that works costs a second
        # inference. Running it anyway and then reporting "there is nowhere to
        # escalate to" is a bill for nothing, which is what this did until it
        # was run on a machine with no external endpoint.
        impossible = escalation_possible(decision, available)
        if impossible is not None:
            return Answer(decision, first, self.local.name, escalation=impossible)

        try:
            quality = AnswerQuality.from_signals(self.judge.judge(text, first))
        except JudgementError as failure:
            # No opinion was formed. The local answer stands, and the account
            # says why rather than presenting it as adequate.
            verdict = EscalationVerdict(
                False,
                Reason(
                    rule="cascade.judge-failed",
                    source="cascade",
                    span=None,
                    detail=(
                        f"the judge {self.judge.name!r} could not run ({failure}); "
                        f"the local answer stands unjudged"
                    ),
                ),
            )
            return Answer(decision, first, self.local.name, escalation=verdict)

        verdict = may_escalate(decision, quality, available)
        if not verdict.escalate:
            return Answer(decision, first, self.local.name, quality=quality, escalation=verdict)

        # Permitted and wanted. This is the one place a local answer is replaced,
        # and it goes through exactly the same protected path a direct external
        # route would -- there is no second, lighter way out.
        outward = self._outward(decision, text)
        return Answer(
            decision,
            outward.text,
            outward.model,
            outward.missed,
            quality=quality,
            escalation=verdict,
            superseded=first,
        )

    def _outward(self, decision: RoutingDecision, text: str) -> Answer:
        if self.channel is None or self.external is None:
            raise EscalationRefusedError(
                "the decision was ESCALATED and no protected outbound path is "
                "configured. iriguchi does not send an unprotected prompt to an "
                "external service, so there is no path here that runs without both "
                "a channel and a model."
            )
        # `prepare` protects and returns; nothing has left at this point, which
        # is what `route --explain --dry-run` relies on. The send is the next
        # line, and it is the only line in this package that sends.
        escalation = self.channel.prepare(text)
        try:
            answer = self.external.answer(escalation.protected_text)
            return Answer(
                decision, escalation.restore(answer), self.external.name, escalation.findings
            )
        finally:
            # The mapping is the highest-value object in this round trip and it
            # exists for exactly as long as the round trip does -- including
            # when the model fails, which is when a caller is least likely to
            # remember.
            escalation.close()
