"""The exception tree.

These are how an *adapter* says it could not answer. What happens next is
`application/routing.py`'s business, and it is not what you would guess: a
proposer's failure does not become a failed request.

``docs/adr/0002-fail-closed.md`` settles it -- a failure "yields the most
restrictive route available, not the most useful one". So a `ScanError` becomes
a restriction and the prompt routes local, with a reason naming the scanner that
broke. A broken scanner costs you the external route; it does not cost you your
afternoon, and it never silently costs you your privacy.

That is why a scanner must raise rather than return an empty sequence. At the
call site "I found nothing" and "I broke" are indistinguishable, and only the
first is safe -- so the port forbids the ambiguity and these types are how it is
avoided.

Messages carry rule ids, spans and types. They never carry a matched value: a
router that prints the thing it was protecting has undone itself.
"""

from __future__ import annotations


class IriguchiError(Exception):
    """Base for everything this library raises."""


class RoutingError(IriguchiError):
    """A proposer could not answer.

    Not "no route was produced". `PromptRouter` catches these and produces a
    decision anyway -- the most restrictive one available -- because a person
    with a broken scanner should still be able to work locally. What must never
    happen is the request going *out* while one of these is in flight, and the
    use case is where that is arranged.
    """


class ScanError(RoutingError):
    """A sensitivity scanner failed.

    A scanner that died has not reported "nothing sensitive", it has reported
    nothing at all, and the two are indistinguishable at the call site unless
    one of them raises. Raising is how a scanner says the difference.

    The use case turns this into a restriction spanning the whole prompt, so the
    route becomes local and the reason names the scanner.
    """


class EstimationError(RoutingError):
    """A complexity estimator failed.

    Less serious than a `ScanError`, and the difference is worth knowing: no
    signals is already the lowest band, which routes local, so the safe answer
    is the default here rather than something that has to be arranged. It is
    still reported -- a decision that quietly lost an axis looks exactly like one
    where that axis had no opinion.
    """


class JudgementError(RoutingError):
    """An answer judge failed.

    The least serious of the three, and the reason is structural rather than a
    matter of degree. A judge that returns nothing has said the answer looked
    fine, which means no escalation, which means the prompt stays where it
    already was. **A broken judge cannot cause a prompt to leave** -- escalation
    is gated on the original decision having permitted it, and that decision was
    made before any of this ran.

    So the cost of this failing is a local answer somebody would have wanted
    escalated, which is quality. Reported anyway, because a cascade that quietly
    stopped cascading looks exactly like one whose answers were all adequate.
    """


class EscalationRefusedError(IriguchiError):
    """A prompt that was allowed to leave will not be sent after all.

    Deliberately **not** a `RoutingError`. The route was decided correctly and
    is not in doubt; what failed is the protection that the route depends on.
    Conflating the two would let a caller retry the routing decision, which
    would produce the same answer and the same refusal.

    Every one of these leaves the prompt where it is. None is a degradation to
    sending something less protected -- see
    ``docs/adr/0013-iriguchi-reads-a-protection-record-and-keeps-none.md``.
    """


class RestorationError(IriguchiError):
    """An answer came back and could not be fully restored.

    Raised rather than returning what was restored so far. A partly restored
    answer reads as complete and quotes a placeholder as though it were a fact,
    which is worse than no answer at all.
    """


class ConfigurationError(IriguchiError):
    """A setting was missing, malformed, or not recognised.

    Unknown keys are refused rather than ignored. A typo in a privacy setting
    that silently does nothing is the worst available outcome: the person
    believes they tightened something and did not.
    """


class ModelError(IriguchiError):
    """A model could not answer.

    Deliberately **not** a `RoutingError`. By the time a model is called the
    route is decided and, on the outbound path, the protection is done -- a
    caller that retried the routing would get the same decision and the same
    failure. What failed is the answering, which is the last step and the only
    one nothing else substitutes for.

    Raised rather than returning an empty answer. mamori measured what the other
    choice costs: a pass that degraded to nothing turned a model too slow for
    its timeout into silence, and three thirty-second attempts looked exactly
    like a model too large for the hardware. The same model answered in 345
    seconds once the timeout was honoured.
    """


class ContractError(IriguchiError):
    """A document did not match a contract version this build understands.

    Refusing an unrecognised contract is the same decision as refusing an
    unrecognised setting. See ``docs/adr/0009-tsumugi-is-read-as-json.md``.

    **Nothing raises this yet** -- see `NOT_YET_RAISED`. Do not write
    ``except ContractError:`` expecting it to catch the escalation channel's
    contract check; that one refuses an escalation and says so with
    `EscalationRefusedError`, because the response there is to leave the prompt
    where it is rather than to report a bad document.
    """


#: Exceptions that exist, are exported, and are raised by nothing in `src/`.
#:
#: An exported exception with a docstring is an invitation to write
#: ``except ThatError:``, and if nothing raises it the caller gets a branch
#: that looks like handling and never runs -- the same shape as a check that
#: cannot fail. So the state is declared here rather than left to be noticed.
#:
#: `tests/test_error_tree.py` enforces both directions: an undeclared one is a
#: failure, and a declared one that *is* raised is a stale declaration and also
#: a failure. A base class is exempt when something subclasses it, decided by
#: looking at the tree rather than at whether the name reads like a base.
NOT_YET_RAISED = {
    "ContractError": (
        "The reader it was written for does not exist. ADR-0009 settles that a "
        "tsumugi context package is read as JSON and an unrecognised `contract` "
        "is refused; the dashboard that would do the reading is v0.3. Until it "
        "lands this names an event nothing produces."
    ),
}


__all__ = [
    "ConfigurationError",
    "ContractError",
    "EscalationRefusedError",
    "EstimationError",
    "IriguchiError",
    "ModelError",
    "RestorationError",
    "RoutingError",
    "ScanError",
]
