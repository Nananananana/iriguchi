"""The exception tree.

Every failure in the deciding path is one of these, and every one of them means
the same thing to a caller: no route was produced, so nothing may be sent. There
is no partial decision and no permissive mode -- see
``docs/adr/0002-fail-closed.md``.

Messages carry rule ids, spans and types. They never carry a matched value: a
router that prints the thing it was protecting has undone itself.
"""

from __future__ import annotations


class IriguchiError(Exception):
    """Base for everything this library raises."""


class RoutingError(IriguchiError):
    """A route could not be decided, so nothing may be sent."""


class ScanError(RoutingError):
    """A sensitivity scanner failed.

    This is deliberately a ``RoutingError``: a scanner that died has not
    reported "nothing sensitive", it has reported nothing at all, and the two
    are indistinguishable at the call site unless one of them raises.
    """


class EstimationError(RoutingError):
    """A complexity estimator failed."""


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
