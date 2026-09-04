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
    scanner: str | SensitivityScanner | None = None,
    estimator: str | ComplexityEstimator | None = None,
    findings: Iterable[Finding] | None = None,
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
        scanner: Which sensitivity scanner. A **name** from the registry, or a
            **scanner object** of your own -- anything satisfying
            `ports.SensitivityScanner`. `None` takes the registry's default,
            which is the built-in one **even when mamori is installed**:
            changing the scanner changes what leaves this machine, and that is
            not a thing to inherit from what happens to be on the system.

            Passing an object is how a tuned or third-party detector gets in
            without a registry entry. Names stay the CLI's vocabulary; objects
            are the library's.
        findings: Findings from somewhere else -- your own Presidio analyzer,
            your own detector -- used **instead of** running a scanner here.
            `iriguchi.interop.findings_from_presidio` converts a
            `RecognizerResult` list without importing Presidio. Passing this
            with `scanner=` is refused rather than silently preferring one:
            somebody who named a scanner and also handed over findings has two
            intentions and iriguchi cannot tell which.
        estimator: Which complexity estimator, by name or as an object. An
            object is the way to reach `RulesSettings` -- every weight and
            threshold the rules use, which were module-private constants until
            somebody would have had to fork the library to move one::

                from iriguchi.infrastructure.estimators.rules import (
                    RulesEstimator, RulesSettings,
                )
                route(text, estimator=RulesEstimator(RulesSettings(
                    long_input_at=300,
                    marker_weights={"complexity.multi-step": 0.6},
                )), local=True)
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

    if findings is not None and scanner is not None:
        from .errors import ConfigurationError

        raise ConfigurationError(
            "both `findings=` and `scanner=` were given. Findings from elsewhere "
            "replace the scan; naming a scanner as well says to run one. Pick "
            "the one you meant -- guessing here would decide what leaves the "
            "machine on a coin toss."
        )

    # A name goes to the registry; an object goes straight onto the router
    # below. Split here rather than at the call site so `IriguchiConfig` keeps
    # taking strings only -- it is the settings object, and a settings object
    # holding a live scanner is a settings object that cannot be written down.
    scanner_name = scanner if isinstance(scanner, str) else None
    estimator_name = estimator if isinstance(estimator, str) else None

    config = IriguchiConfig(
        local=local,
        external=external,
        scanner=scanner_name or "",
        estimator=estimator_name or "",
        moderate_at="" if moderate_at is None else repr(moderate_at),
        high_at="" if high_at is None else repr(high_at),
    )
    router = config.router()
    from dataclasses import replace as _replace

    if not isinstance(scanner, str) and scanner is not None:
        router = _replace(router, scanner=scanner)
    if not isinstance(estimator, str) and estimator is not None:
        router = _replace(router, estimator=estimator)
    if findings is not None:
        from .infrastructure.scanners.supplied import SuppliedScanner

        router = _replace(router, scanner=SuppliedScanner(tuple(findings)))
    return router.route(text, config.available)


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
        "Finding": ("iriguchi.domain.sensitivity", "Finding"),
        "Span": ("iriguchi.domain.span", "Span"),
        "findings_from_presidio": ("iriguchi.interop", "findings_from_presidio"),
        "to_presidio": ("iriguchi.interop", "to_presidio"),
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
        # **Every name `__getattr__` resolves, listed here too.**
        #
        # The lazy re-export is a runtime convenience and a type checker cannot
        # see through it: `__getattr__` is annotated `-> object`, so a user who
        # wrote `from iriguchi import findings_from_presidio` got a callable
        # mypy refused to call, and `from iriguchi import Finding` got a type
        # that was not one. The ergonomic spelling -- the one the README shows
        # -- was the one that did not typecheck.
        #
        # Caught by this project's own README test, which imports the way the
        # README says to. The two lists are kept in step by
        # `tests/test_the_public_surface.py`, because two lists of names in one
        # file is a pair that drifts.
        from collections.abc import Iterable

        from .domain.complexity import Thresholds
        from .domain.decision import RoutingDecision
        from .domain.destination import Destination, Route
        from .domain.reason import Reason
        from .domain.sensitivity import Finding
        from .domain.span import Span
        from .errors import ConfigurationError, IriguchiError
        from .interfaces.contract import CONTRACT, as_document, schema
        from .interop import findings_from_presidio, to_presidio
        from .ports.estimator import ComplexityEstimator
        from .ports.scanner import SensitivityScanner

__all__ = [
    "CONTRACT",
    "ConfigurationError",
    "Destination",
    "Finding",
    "IriguchiError",
    "Reason",
    "Route",
    "RoutingDecision",
    "Span",
    "Thresholds",
    "__version__",
    "as_document",
    "findings_from_presidio",
    "route",
    "schema",
    "to_presidio",
]
