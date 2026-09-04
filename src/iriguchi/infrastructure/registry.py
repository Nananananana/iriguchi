"""Choosing an algorithm by name.

Both axes have a port and more than one thing that could sit behind it, and
until now the choice was an `if` in the composition root: `MamoriScanner() if
use_mamori else FallbackScanner()`, and one estimator with no alternative at
all. That is a boolean pretending to be a choice, and it stops working at three.

**A name, a factory, and a sentence about the trade.** The sentence is the part
that matters. Every algorithm here is a different answer to the same question,
and a person picking one needs to know what it costs — which is why the registry
stores a description rather than only a callable, and why `iriguchi doctor`
prints them.

## Why this is not entry points

The obvious modern spelling is `importlib.metadata.entry_points`, so anybody can
`pip install iriguchi-something` and have it appear. **That is exactly the wrong
shape for this project.** A router that decides what leaves your machine must
not gain a scanner because something else was installed; ADR-0011 already says
availability is configuration and not a probe, and a plugin discovered from the
environment is the same defect one layer up. Registration is an import in this
file, and adding one is a commit.

## Why the default is not the best available

`fallback` stays the default even when mamori is installed, and the reason is in
ADR-0005: **changing the scanner changes what leaves this machine**, and that is
not a thing to inherit from what happens to be on the system. The registry
reports what is available; it does not select on your behalf.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass

from ..errors import ConfigurationError
from ..ports.estimator import ComplexityEstimator
from ..ports.scanner import SensitivityScanner
from .estimators.rules import RulesEstimator
from .scanners.fallback import FallbackScanner

__all__ = [
    "DEFAULT_ESTIMATOR",
    "DEFAULT_SCANNER",
    "ESTIMATORS",
    "SCANNERS",
    "Choice",
    "Registry",
]


# PEP 695 type parameters, which is the 3.12 spelling and what `ruff` asks for.
# The older `TypeVar` form works and reads as a different vintage than the rest
# of the file.
@dataclass(frozen=True, slots=True)
class Choice[T]:
    """One algorithm, and what picking it costs.

    `summary` is one line for `doctor`; `trade` is the sentence somebody needs
    before choosing. A registry entry with no trade written down is a menu item
    with no price, and this project's whole argument is that the price is the
    interesting part.
    """

    name: str
    summary: str
    trade: str
    build: Callable[[], T]
    #: Whether this choice can be built on this machine right now. A sibling
    #: that is not installed is `False` here rather than absent, because
    #: "there is no such algorithm" and "you do not have it" send a reader to
    #: fix different things.
    available: Callable[[], tuple[bool, str]] = lambda: (True, "")


class Registry[T]:
    """Names to algorithms, with a refusal that lists the alternatives."""

    def __init__(self, kind: str, choices: Mapping[str, Choice[T]], default: str) -> None:
        self._kind = kind
        self._choices = dict(choices)
        self._default = default
        assert default in self._choices, f"the default {default!r} is not registered"

    def __contains__(self, name: object) -> bool:
        return name in self._choices

    def __iter__(self) -> Iterator[Choice[T]]:
        """The choices, in registration order.

        Annotated properly rather than as `object`, which type-checked and made
        every caller's `for choice in registry` an error at the first attribute
        access. A return type wide enough to accept anything is a return type
        that has stopped describing the function.
        """
        return iter(self._choices.values())

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._choices)

    @property
    def default(self) -> str:
        return self._default

    def describe(self, name: str) -> Choice[T]:
        try:
            return self._choices[name]
        except KeyError:
            raise ConfigurationError(
                f"there is no {self._kind} called {name!r}. Available: "
                f"{sorted(self._choices)}. Refusing rather than falling back to "
                f"the default: somebody who named one is relying on it, and "
                f"quietly giving them another is the worst available outcome."
            ) from None

    def build(self, name: str) -> T:
        """The named algorithm, or a refusal that says which of two problems it is.

        A name nobody registered and a name whose algorithm is not installed are
        different sentences, and a single "could not use that" would send half
        the readers to the wrong fix.
        """
        choice = self.describe(name)
        usable, detail = choice.available()
        if not usable:
            raise ConfigurationError(
                f"the {self._kind} {name!r} is registered and cannot be used here: "
                f"{detail}. That is not the same as it not existing."
            )
        return choice.build()


def _fallback_and_presidio() -> SensitivityScanner:
    from .scanners.composite import CompositeScanner
    from .scanners.presidio_scanner import PresidioScanner

    return CompositeScanner([FallbackScanner(), PresidioScanner()])


def _presidio_scanner() -> SensitivityScanner:
    from .scanners.presidio_scanner import PresidioScanner

    return PresidioScanner()


def _presidio_state() -> tuple[bool, str]:
    from .scanners.presidio_scanner import presidio_state

    return presidio_state()


def _mamori_scanner() -> SensitivityScanner:
    from .scanners.mamori_scanner import MamoriScanner

    return MamoriScanner()


def _mamori_state() -> tuple[bool, str]:
    from .scanners.mamori_scanner import SiblingState, mamori_state

    state, detail = mamori_state()
    if state is SiblingState.AVAILABLE:
        return True, ""
    if state is SiblingState.BROKEN:
        return False, f"mamori is installed and will not import ({detail})"
    # Says *not on PyPI* rather than only naming the path, because `../mamori`
    # on its own reads as a typo for a package name that would work.
    return False, (
        "mamori is not installed and is not on PyPI; it needs a checkout beside "
        "this one (`uv pip install -e ../mamori`)"
    )


#: The sensitivity axis. A veto: whatever it finds removes destinations, and
#: nothing it finds ever adds one.
SCANNERS: Registry[SensitivityScanner] = Registry(
    "scanner",
    {
        "fallback": Choice(
            name="fallback",
            summary="built-in rules, no dependencies",
            trade=(
                "Misses 61.7% of must-stay-local cases against mamori's 1.0% "
                "(docs/measurements.md, and that 1.0% is measured on mamori's own "
                "corpus). Over-detects on purpose: a false positive costs the "
                "external route, a false negative costs a leak."
            ),
            build=FallbackScanner,
        ),
        "presidio": Choice(
            name="presidio",
            summary="Microsoft Presidio (MIT), spaCy-backed NER plus pattern recognisers",
            trade=(
                "The only scanner worth having that a user can actually install: "
                '`pip install "iriguchi[presidio]"` plus a spaCy model, which is '
                "roughly 600MB and several seconds of import. It finds the names, "
                "organisations and locations the built-in scanner misses, and it "
                "emits low-confidence guesses that are filtered by Presidio's own "
                "`score_threshold` rather than by anything here -- iriguchi has no "
                "confidence to interpret and refuses to invent one."
            ),
            build=_presidio_scanner,
            available=_presidio_state,
        ),
        "fallback+presidio": Choice(
            name="fallback+presidio",
            summary="both of the above, findings unioned -- the most detection available on PyPI",
            trade=(
                "Costs whatever Presidio costs and finds strictly more than "
                "either member, because a measurement said the obvious ranking "
                "was wrong: Presidio finds the English names the built-in "
                "scanner misses and misses the Japanese honorifics it catches. "
                "Sound only because sensitivity is a veto -- a union of findings "
                "is at least as restrictive as either half, so there is no "
                "combination rule here to get wrong."
            ),
            build=_fallback_and_presidio,
            available=_presidio_state,
        ),
        "mamori": Choice(
            name="mamori",
            summary="mamori's detectors, when it is installed",
            trade=(
                "Far better recall, and a sibling in the deciding path. Not the "
                "default even when present: changing the scanner changes what "
                "leaves this machine (ADR-0005)."
            ),
            build=_mamori_scanner,
            available=_mamori_state,
        ),
    },
    default="fallback",
)

#: The complexity axis. A preference: it can ask for the larger model and can
#: never overrule the veto.
ESTIMATORS: Registry[ComplexityEstimator] = Registry(
    "estimator",
    {
        "rules": Choice(
            name="rules",
            summary="structural and lexical markers, weighted",
            trade=(
                "81.0% band accuracy on 21 generated cases against a 66.7% "
                "always-low baseline. No model configuration measured is decidably "
                "better, and four are decidably worse (docs/measurements.md)."
            ),
            build=RulesEstimator,
        ),
    },
    default="rules",
)

DEFAULT_SCANNER = SCANNERS.default
DEFAULT_ESTIMATOR = ESTIMATORS.default
