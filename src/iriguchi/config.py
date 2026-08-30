"""Every switch, and the factories that assemble them.

One object, no configuration file format. mamori's ADR-0012, and the reasoning
transfers: a format needs a parser, a schema, a search path and a precedence
order, and all four are surface area on a tool whose whole claim is that it is
small enough to audit.

**Availability is configuration, not a probe.** Whether this machine has a local
model is something you tell iriguchi; it does not go and look. ADR-0011 records
why, and the consequence is visible in the test suite: everything runs with the
network unavailable, including the CLI, because nothing ever reaches for it to
find out what exists.

Unknown environment keys are refused rather than ignored. A typo in a privacy
setting that silently does nothing is the worst available outcome -- the person
believes they tightened something and did not.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .application.routing import PromptRouter
from .domain.destination import Destination
from .errors import ConfigurationError
from .infrastructure.channels.mamori_channel import MamoriChannel
from .infrastructure.estimators.rules import RulesEstimator
from .infrastructure.scanners.fallback import FallbackScanner
from .infrastructure.scanners.mamori_scanner import (
    MamoriScanner,
    SiblingState,
    mamori_state,
)

__all__ = ["ENV_PREFIX", "IriguchiConfig"]

ENV_PREFIX = "IRIGUCHI_"

#: Every key this build understands. Anything else under the prefix is a typo,
#: and is refused.
KNOWN_KEYS = frozenset({"LOCAL", "EXTERNAL"})

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _flag(name: str, raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ConfigurationError(
        f"{ENV_PREFIX}{name}={raw!r} is not a yes or a no. Use one of {sorted(_TRUE | _FALSE)}."
    )


@dataclass(frozen=True, slots=True)
class IriguchiConfig:
    """What this machine can reach, and what to route with.

    Both destinations default to **off**, which is the fail-safe value. A person
    who has configured nothing gets refusals rather than a router quietly
    assuming a model exists, and a refusal says what is missing.
    """

    local: bool = False
    external: bool = False
    #: Use mamori as the scanner. Defaults to off even when mamori is
    #: installed: a change of scanner changes what leaves this machine, and
    #: that is not something to inherit from what happens to be on the
    #: system. `iriguchi doctor` says when it is available and unused.
    use_mamori: bool = False

    @property
    def available(self) -> frozenset[Destination]:
        destinations = set()
        if self.local:
            destinations.add(Destination.LOCAL)
        if self.external:
            destinations.add(Destination.EXTERNAL)
        return frozenset(destinations)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> IriguchiConfig:
        """Read `IRIGUCHI_LOCAL` and `IRIGUCHI_EXTERNAL`.

        Raises:
            ConfigurationError: for an unknown `IRIGUCHI_*` key, or a value that
                is not recognisably a yes or a no.
        """
        source = os.environ if environ is None else environ
        found = {
            key[len(ENV_PREFIX) :]: value
            for key, value in source.items()
            if key.startswith(ENV_PREFIX)
        }
        unknown = sorted(set(found) - KNOWN_KEYS)
        if unknown:
            raise ConfigurationError(
                f"unknown settings {[ENV_PREFIX + key for key in unknown]}. Known keys "
                f"are {sorted(ENV_PREFIX + key for key in KNOWN_KEYS)}. Refusing rather "
                "than ignoring: a typo that silently does nothing is worse than an "
                "error, because you would believe you had changed something."
            )
        return cls(
            local=_flag("LOCAL", found["LOCAL"]) if "LOCAL" in found else False,
            external=_flag("EXTERNAL", found["EXTERNAL"]) if "EXTERNAL" in found else False,
        )

    def router(self) -> PromptRouter:
        """The router this configuration describes.

        The one place the CLI is allowed to name an adapter. Everything above it
        takes a `PromptRouter` and does not know what is inside.

        Raises:
            ScanError: if mamori was asked for and is not installed. Refusing is
                right: somebody who passed `--scanner mamori` is relying on it
                finding what the fallback cannot, and quietly giving them the
                fallback instead would be the worst available outcome.
        """
        scanner = MamoriScanner() if self.use_mamori else FallbackScanner()
        return PromptRouter(scanner=scanner, estimator=RulesEstimator())

    def channel(self) -> MamoriChannel:
        """The escalation channel this configuration describes.

        Here rather than in the CLI for the same reason `router()` is: this is
        the composition root, and it is the one place allowed to name an
        adapter. It also keeps the `mamori-is-an-adapter` contract to a single
        ignored edge instead of one per caller -- three ignores would have left
        the contract mostly ignored on the paths that matter.

        Raises:
            EscalationRefusedError: when mamori is absent or broken. There is no
                unprotected fallback, by construction: the alternative to
                protecting an outbound prompt is not sending it.
        """
        return MamoriChannel()

    def describe(self) -> str:
        """What this configuration does with your prompts, in prose.

        A report rather than a dump. Somebody reading it should be able to
        answer "can anything leave this machine" without knowing the codebase.
        """
        # Three states, not two. `mamori_is_available()` is false both when
        # mamori is absent and when it is installed and will not import, and
        # printing "not installed" for the second tells somebody to install what
        # they already have. Same defect as `policy.prefer-local` had: a wrong
        # stated reason, sending the reader to fix the wrong thing.
        if self.use_mamori:
            scanner = "mamori"
        elif mamori_state()[0] is SiblingState.AVAILABLE:
            scanner = "built-in fallback (mamori is installed but not selected)"
        elif mamori_state()[0] is SiblingState.BROKEN:
            scanner = "built-in fallback (mamori is installed and will not import)"
        else:
            scanner = "built-in fallback (mamori is not installed)"

        lines = [
            f"local model       {'available' if self.local else 'not configured'}",
            f"external service  {'available' if self.external else 'not configured'}",
            f"scanner           {scanner}",
            "",
        ]
        if not self.available:
            lines.append(
                "Nothing is available, so every prompt is refused. Set "
                f"{ENV_PREFIX}LOCAL=1 once you have a local model running."
            )
        elif not self.external:
            lines.append("Nothing can leave this machine. Every prompt goes to the local model.")
        elif not self.local:
            lines.append(
                "There is no local model, so a prompt that must stay local is refused "
                "rather than sent. That is the intended behaviour, not a fallback."
            )
        else:
            lines.append(
                "A prompt with nothing sensitive in it may leave if it is hard enough. "
                "A prompt with a finding stays, whatever its difficulty."
            )
        return "\n".join(lines)
