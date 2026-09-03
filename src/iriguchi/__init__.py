"""iriguchi -- a local governance router for generative AI.

It stands between a person and every model they use, and decides -- locally,
deterministically, and before a single byte leaves the machine -- where each
prompt is allowed to go.

    >>> from iriguchi import route
    >>> decision = route("Summarise this article.", local=True, external=True)
    >>> decision.leaves_the_machine
    False
    >>> [reason.detail for reason in decision.reasons]
    ['complexity band low does not call for the larger model, and a local model is permitted']

Both destinations default to **off**, which is the fail-safe value: a caller who
says nothing gets a refusal that names what is missing, rather than a router
quietly assuming a model exists.

For a machine-readable decision, `iriguchi.as_document` renders one as
`iriguchi.routing-decision/1` -- rule ids, spans and bands, and no part of the
prompt. `iriguchi schema` prints the shape, and `iriguchi route --json` writes
one from the command line.

The design is ``docs/proposals/0001-the-design.md``; the decisions it rests on
are in ``docs/adr/``.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"


def route(
    text: str,
    *,
    local: bool = False,
    external: bool = False,
    scanner: str | None = None,
    estimator: str | None = None,
    moderate_at: float | None = None,
    high_at: float | None = None,
) -> RoutingDecision:
    """Where `text` is allowed to go, and the whole account of why.

    The one call somebody should need. Everything under it is available and
    swappable -- `iriguchi.config.IriguchiConfig` for the composition root,
    `iriguchi.infrastructure.registry` for what can sit behind each port -- and
    a person evaluating whether this tool is worth adopting should not have to
    assemble three objects to find out.

    Args:
        text: The prompt, exactly as typed. Nothing here normalizes it.
        local: Whether a local model is available. **Passed in, never probed**
            (ADR-0011), which is what lets this run with no network at all.
        external: Whether an external service is reachable.
        scanner: Which sensitivity scanner, by name. `None` takes the registry's
            default, which is the built-in one **even when mamori is installed**
            -- changing the scanner changes what leaves this machine, and that
            is not a thing to inherit from what happens to be on the system.
        estimator: Which complexity estimator, by name.
        moderate_at: Where the middle band begins. `None` keeps the default;
            `python tools/calibrate.py --escalate 0.3` derives one from a target
            escalation rate rather than inventing a number.
        high_at: Where the top band begins.

    Returns:
        A `RoutingDecision`, which is a value: frozen, and carrying the reasons
        that produced it. It is never written anywhere by iriguchi (ADR-0012).

    Raises:
        ConfigurationError: for a scanner or estimator name nobody registered,
            for one that is registered and unavailable here, or for thresholds
            that would make a band unreachable. Refused rather than defaulted:
            somebody who named an algorithm is relying on it.

    Never raises for a scanner or estimator that fails at run time. A broken
    proposer yields the most restrictive route available and says so in the
    reasons (ADR-0002) -- a person with a broken scanner can still work locally.
    """
    from .config import IriguchiConfig

    config = IriguchiConfig(
        local=local,
        external=external,
        scanner=scanner or "",
        estimator=estimator or "",
        moderate_at="" if moderate_at is None else repr(moderate_at),
        high_at="" if high_at is None else repr(high_at),
    )
    return config.router().route(text, config.available)


def __getattr__(name: str) -> object:
    """Re-exports, resolved on first use.

    `route` is a function so that importing `iriguchi` costs nothing but a
    module object; the names below are the types a caller needs to annotate
    what it returns, and they are wired lazily for the same reason.

    Spelled as `__getattr__` rather than a block of imports at the top because
    the package docstring is the first thing a reader meets, and a screen of
    imports above it is a screen they scroll past.
    """
    lazy = {
        "RoutingDecision": ("iriguchi.domain.decision", "RoutingDecision"),
        "Route": ("iriguchi.domain.destination", "Route"),
        "Destination": ("iriguchi.domain.destination", "Destination"),
        "Reason": ("iriguchi.domain.reason", "Reason"),
        "Thresholds": ("iriguchi.domain.complexity", "Thresholds"),
        "as_document": ("iriguchi.interfaces.contract", "as_document"),
        "schema": ("iriguchi.interfaces.contract", "schema"),
        "CONTRACT": ("iriguchi.interfaces.contract", "CONTRACT"),
        "ConfigurationError": ("iriguchi.errors", "ConfigurationError"),
        "IriguchiError": ("iriguchi.errors", "IriguchiError"),
    }
    if name not in lazy:
        raise AttributeError(f"module 'iriguchi' has no attribute {name!r}")
    module_name, attribute = lazy[name]
    import importlib

    return getattr(importlib.import_module(module_name), attribute)


if __debug__:  # pragma: no cover - typing only
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from .domain.decision import RoutingDecision

__all__ = [
    "CONTRACT",
    "ConfigurationError",
    "Destination",
    "IriguchiError",
    "Reason",
    "Route",
    "RoutingDecision",
    "Thresholds",
    "__version__",
    "as_document",
    "route",
    "schema",
]
