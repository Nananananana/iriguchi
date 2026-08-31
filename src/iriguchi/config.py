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
from dataclasses import dataclass, field

from .application.routing import PromptRouter
from .domain.destination import Destination
from .errors import ConfigurationError
from .infrastructure.channels.mamori_channel import MamoriChannel
from .infrastructure.estimators.rules import RulesEstimator
from .infrastructure.models.openai_compatible import OpenAICompatibleModel
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
#:
#: `LOCAL` and `EXTERNAL` say what this machine can reach and are all `route`
#: needs. The four that follow are what `ask` needs to actually send, and they
#: are separate on purpose: routing is answerable with no endpoint configured
#: at all, which is what keeps the deciding path testable with no network.
KNOWN_KEYS = frozenset(
    {
        "LOCAL",
        "EXTERNAL",
        "LOCAL_URL",
        "LOCAL_MODEL",
        "EXTERNAL_URL",
        "EXTERNAL_MODEL",
        "EXTERNAL_KEY",
    }
)

#: Settings whose values must never be printed. `describe()` reports every
#: other field; a key is the one thing here worth stealing, and a report that
#: quotes it turns "what does this configuration do" into a disclosure.
SECRET_KEYS = frozenset({"EXTERNAL_KEY"})

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

    #: Where the local model answers, and which one. No default: ollama listens
    #: on 11434 and guessing it would mean `ask` sends to whatever is on that
    #: port, which on a shared machine is not necessarily a model of yours.
    #: `LOCAL=1` still means "a local model exists" for routing, because `route`
    #: needs no endpoint -- these are only required by `ask`, and it says so.
    local_url: str = ""
    local_model: str = ""
    external_url: str = ""
    external_model: str = ""
    #: Never printed. See `SECRET_KEYS`.
    external_key: str = field(default="", repr=False)

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
            local_url=found.get("LOCAL_URL", ""),
            local_model=found.get("LOCAL_MODEL", ""),
            external_url=found.get("EXTERNAL_URL", ""),
            external_model=found.get("EXTERNAL_MODEL", ""),
            external_key=found.get("EXTERNAL_KEY", ""),
        )

    def local_answerer(self) -> OpenAICompatibleModel:
        """The local model, or a refusal naming what is missing.

        Composition root again: this is the one place allowed to name an
        adapter. A missing setting is reported as a setting rather than as a
        connection failure -- somebody who has not configured an endpoint should
        be told that, not told that a host they never named is unreachable.
        """
        return self._answerer("LOCAL", self.local_url, self.local_model, None)

    def external_answerer(self) -> OpenAICompatibleModel:
        """The external model, or a refusal naming what is missing."""
        return self._answerer(
            "EXTERNAL", self.external_url, self.external_model, self.external_key or None
        )

    @staticmethod
    def _answerer(which: str, url: str, model: str, key: str | None) -> OpenAICompatibleModel:
        missing = [
            f"{ENV_PREFIX}{which}_{name}"
            for name, value in (("URL", url), ("MODEL", model))
            if not value.strip()
        ]
        if missing:
            raise ConfigurationError(
                f"{missing} is not set, so there is nowhere to send and nothing to "
                f"ask for. `route` needs neither -- deciding where a prompt may go "
                f"does not require an endpoint -- but `ask` sends, and it will not "
                f"guess an address."
            )
        return OpenAICompatibleModel(url.strip(), model.strip(), api_key=key)

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

    @staticmethod
    def _endpoint(on: bool, url: str, model: str) -> str:
        """Three states, not two.

        "available" for a destination with nowhere to send would be the same
        defect `describe` already avoids for mamori: a true sentence that sends
        the reader to fix the wrong thing.
        """
        if not on:
            return "not configured"
        if url.strip() and model.strip():
            return f"available    {model.strip()} at {url.strip()}"
        return "available for routing, no endpoint for asking"

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
            f"local model       {self._endpoint(self.local, self.local_url, self.local_model)}",
            f"external service  "
            f"{self._endpoint(self.external, self.external_url, self.external_model)}",
            f"scanner           {scanner}",
            "",
        ]
        # A destination declared available with no endpoint behind it is a real
        # state and a confusing one: `route` says a prompt may go there and
        # `ask` refuses. Both are correct -- deciding needs no endpoint -- and a
        # person who reads only the first would reasonably think they were set
        # up. Said here rather than discovered at the moment of sending.
        half = [
            name
            for name, on, url, model in (
                ("LOCAL", self.local, self.local_url, self.local_model),
                ("EXTERNAL", self.external, self.external_url, self.external_model),
            )
            if on and not (url.strip() and model.strip())
        ]
        if half:
            lines.append(
                f"{half} can be routed to and not asked. `route` needs no endpoint and "
                f"will say a prompt may go there; `ask` needs one and will refuse. Set "
                f"{[f'{ENV_PREFIX}{name}_URL' for name in half]} and the matching "
                f"_MODEL to close the gap."
            )
            lines.append("")
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
