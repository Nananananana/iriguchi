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
from .domain.complexity import DEFAULT_THRESHOLDS, Thresholds
from .domain.destination import Destination
from .errors import ConfigurationError
from .infrastructure.channels.mamori_channel import MamoriChannel
from .infrastructure.models.openai_compatible import OpenAICompatibleModel
from .infrastructure.registry import ESTIMATORS, SCANNERS

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
        # Which algorithm sits behind each port. Names, validated against the
        # registry and refused when unknown with the alternatives listed -- the
        # way a modern library names an estimator rather than exposing a boolean.
        "SCANNER",
        "ESTIMATOR",
        # Where the bands begin. Numbers an operator should not have to invent:
        # `python tools/calibrate.py --escalate 0.3` derives them from a target
        # rate against the corpus, which is the shape RouteLLM argues for.
        "MODERATE_AT",
        "HIGH_AT",
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

    #: Which algorithm answers each axis. Empty means the registry's default,
    #: which is deliberately not "the best one installed" -- see `registry.py`.
    scanner: str = ""
    estimator: str = ""
    #: Where the bands begin. Empty means the domain's defaults.
    moderate_at: str = ""
    high_at: str = ""

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
            scanner=found.get("SCANNER", ""),
            estimator=found.get("ESTIMATOR", ""),
            moderate_at=found.get("MODERATE_AT", ""),
            high_at=found.get("HIGH_AT", ""),
        )

    def thresholds(self) -> Thresholds:
        """Where the bands begin, from settings or from the domain's defaults.

        A number that will not parse is refused rather than ignored, and the
        message says which setting -- the same rule as an unknown key. Somebody
        who wrote `IRIGUCHI_HIGH_AT=hight` has changed nothing and believes they
        changed something.
        """
        supplied: dict[str, float] = {}
        for name, raw in (("moderate_at", self.moderate_at), ("high_at", self.high_at)):
            if not raw.strip():
                continue
            try:
                supplied[name] = float(raw)
            except ValueError:
                raise ConfigurationError(
                    f"{ENV_PREFIX}{name.upper()}={raw!r} is not a number. Bands begin "
                    f"at a score between 0 and 1; `python tools/calibrate.py` derives "
                    f"one from a target escalation rate."
                ) from None
        try:
            # Spelled out rather than `**supplied`, because `short_circuit_at`
            # is an `int` and a `dict[str, float]` splat makes mypy right to
            # complain: the two settings here are floats and the third is not
            # configurable, and that is worth reading rather than inferring.
            return Thresholds(
                moderate_at=supplied.get("moderate_at", DEFAULT_THRESHOLDS.moderate_at),
                high_at=supplied.get("high_at", DEFAULT_THRESHOLDS.high_at),
            )
        except ValueError as bad:
            raise ConfigurationError(str(bad)) from bad

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
        # `use_mamori` predates the registry and still wins, because
        # `--scanner mamori` is a flag people already use. It is a shorthand for
        # a name now rather than a second mechanism.
        name = "mamori" if self.use_mamori else (self.scanner or SCANNERS.default)
        return PromptRouter(
            scanner=SCANNERS.build(name),
            estimator=ESTIMATORS.build(self.estimator or ESTIMATORS.default),
            thresholds=self.thresholds(),
        )

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
    def _protection() -> tuple[bool, str]:
        """Whether anything on this machine can protect an outbound prompt.

        Asked of the registry rather than of the adapter, for the reason the
        scanner line gives: one module names the sibling and everything else
        asks it, which is one fewer `ignore_imports` line rather than one more.

        The detail already separates *absent* from *installed and will not
        import*, and both are returned unchanged -- telling somebody to install
        what they already have is the same wrong-fix defect pointing the other
        way.
        """
        return SCANNERS.describe("mamori").available()

    @staticmethod
    def _endpoint(on: bool, url: str, model: str, protected: bool = True) -> str:
        """Four states, not two.

        "available" for a destination with nowhere to send would be the same
        defect `describe` already avoids for mamori: a true sentence that sends
        the reader to fix the wrong thing.

        `protected` is the fourth, and it was missing until a wheel in a clean
        venv was asked. The external service had a URL and a model and printed
        **available**, and every `ask --external` against it was refused,
        because protecting an outbound prompt needs mamori and there is no
        unprotected fallback by construction.

        The two blockers share one framing -- **available for routing**, then
        what stops the asking -- because that half is true in both: `route`
        needs no endpoint and no protection, and it works. The first version of
        this said `cannot be used` and took precedence over the endpoint
        message, which hid a gap a test was already checking for. Both are
        real, and the one with an endpoint set is the one that was lying.
        """
        if not on:
            return "not configured"
        if not (url.strip() and model.strip()):
            return "available for routing, no endpoint for asking"
        if not protected:
            return "available for routing, nothing can protect an outbound prompt"
        return f"available    {model.strip()} at {url.strip()}"

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
        # Asked once and used twice: the scanner line below says whether mamori
        # could be the scanner, and the external line says whether anything can
        # protect a prompt on the way out. Same fact, two consequences, and only
        # one of them was being reported.
        protects, protection = self._protection()
        chosen = "mamori" if self.use_mamori else (self.scanner or SCANNERS.default)
        if chosen != SCANNERS.default:
            scanner = chosen
        else:
            # Asked of the registry rather than of the adapter. This module used
            # to import `mamori_scanner` to answer it, which made `interfaces ->
            # config -> mamori_scanner -> mamori` a second path the contract had
            # to forgive. **One module names the sibling now**, and everything
            # else asks it -- which is one fewer `ignore_imports` line rather
            # than one more.
            usable, detail = SCANNERS.describe("mamori").available()
            note = "installed but not selected" if usable else detail
            scanner = f"built-in fallback ({note})"

        lines = [
            f"local model       {self._endpoint(self.local, self.local_url, self.local_model)}",
            f"external service  "
            f"{self._endpoint(self.external, self.external_url, self.external_model, protects)}",
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
        # Named before the endpoint gap for the same reason `_endpoint` reports
        # it first: this one cannot be closed by setting a variable.
        if self.external and not protects:
            lines.append(
                f"warning: the external service cannot be used: "
                f"{protection.rstrip('.')}. Protecting an "
                f"outbound prompt is what mamori does, and there is no unprotected "
                f"fallback -- the alternative to protecting a prompt is not sending it. "
                f"`route` still decides, and will say a prompt may leave; `ask --external` "
                f"refuses. Until then this machine is local-only in practice."
            )
            lines.append("")
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
