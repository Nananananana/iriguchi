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


class ConfigurationError(IriguchiError):
    """A setting was missing, malformed, or not recognised.

    Unknown keys are refused rather than ignored. A typo in a privacy setting
    that silently does nothing is the worst available outcome: the person
    believes they tightened something and did not.
    """


class ContractError(IriguchiError):
    """A document did not match a contract version this build understands.

    Refusing an unrecognised contract is the same decision as refusing an
    unrecognised setting. See ``docs/adr/0009-tsumugi-is-read-as-json.md``.
    """


__all__ = [
    "ConfigurationError",
    "ContractError",
    "EstimationError",
    "IriguchiError",
    "RoutingError",
    "ScanError",
]
