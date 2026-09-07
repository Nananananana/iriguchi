"""Running the router over the corpus, and what the numbers mean.

Six figures, adapted from RouterArena's dimensions. One of them is a gate and
the rest are measurements, and confusing the two is how a corpus becomes a
target.

**Leak rate is the gate, and its floor is zero.** A `MUST_STAY_LOCAL` case that
routed out is the failure this project exists to prevent, and there is no number
of correct decisions that buys one of these.

**Missed findings is the number to read first, and it exists because the leak
rate lied.** The first version of this file reported a 0% leak rate over a
corpus where the scanner was clearing two thirds of the must-stay-local cases.
Both facts were true: those prompts were easy, complexity chose local on its
own, and a miss that never became a route is invisible to an end-to-end
measurement. The same miss on a prompt that asks for a proof is a leak, with
nothing about the scanner changed. So coverage is measured at the scanner and
the end-to-end number is reported beside it, never instead of it.

**Everything else is reported and not gated**, deliberately loosely. A floor set
at today's score makes every honest experiment a build failure, and tuning to
reach a threshold is what mamori's ADR-0023 records happening.

Scored by exact match, with no model anywhere. RouterArena's follow-up found
LLM-as-judge scoring deviating from exact match by up to 10-24 points on
knowledge tasks -- larger than most of the routing gains being measured against
it. A benchmark whose noise exceeds its signal is measuring the judge.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

from ..application.routing import PromptRouter
from ..domain.complexity import Complexity, ComplexityBand
from ..domain.destination import Destination, Route
from ..domain.policy import RoutingPolicy
from ..domain.sensitivity import Finding, Sensitivity, SensitivityLevel
from ..domain.span import Span
from .case import Case, SensitivityClass

#: The name this project records as the author of text it wrote itself, in a
#: corpus file's `provenance.text.authored_by`.
#:
#: A constant rather than a literal at the comparison, because the claim it
#: supports -- *nobody else's prompts have asked this axis a question* -- is one
#: of the more consequential sentences in the repository, and a string typed
#: twice is a sentence that can quietly become true by a typo.
SELF = "iriguchi"

__all__ = ["Outcome", "Report", "run"]

#: What the corpus assumes a machine can reach. Both, because a corpus scored on
#: a machine with no local model would report refusals everywhere and measure
#: the machine rather than the router.
AVAILABLE = frozenset(Destination)

_EXPECTED = {
    SensitivityClass.MUST_STAY_LOCAL: SensitivityLevel.RESTRICTED,
    SensitivityClass.MAY_LEAVE: SensitivityLevel.CLEAR,
}


@dataclass(frozen=True, slots=True)
class Outcome:
    """One case, run."""

    case: Case
    route: Route
    expected_route: Route
    level: SensitivityLevel
    band: ComplexityBand
    #: Milliseconds for the decision alone. No model, no network, so this is
    #: string scanning and nothing else.
    latency_ms: float

    @property
    def leaked(self) -> bool:
        """Routed out something the corpus says had to stay. End to end.

        Has a floor of zero, and **is not the scanner's coverage**. See
        `missed_finding`: this is what happened, and what happened depended on
        the complexity axis independently agreeing.
        """
        return (
            self.case.sensitivity is SensitivityClass.MUST_STAY_LOCAL
            and self.route is Route.EXTERNAL
        )

    @property
    def missed_finding(self) -> bool:
        """The scanner said `CLEAR` about something that had to stay local.

        **The number that matters, and the one this file did not have at
        first.** `leaked` reported 0% while the scanner was missing two thirds
        of the corpus: those prompts were easy, so complexity chose local on its
        own and the miss never became a route.

        That is luck, not safety. The same miss on a prompt that happens to ask
        for a proof is a leak, and nothing about the scanner changed between the
        two. So coverage is measured where it happens -- at the scanner -- and
        the end-to-end number is reported beside it rather than instead of it.
        """
        return (
            self.case.sensitivity is SensitivityClass.MUST_STAY_LOCAL
            and self.level is SensitivityLevel.CLEAR
        )

    @property
    def over_cautious(self) -> bool:
        """Held back something the corpus says could have gone."""
        return (
            self.case.sensitivity is SensitivityClass.MAY_LEAVE
            and self.level is SensitivityLevel.RESTRICTED
        )

    @property
    def routed_correctly(self) -> bool:
        return self.route is self.expected_route

    @property
    def banded_correctly(self) -> bool:
        return self.band is self.case.band


@dataclass(frozen=True, slots=True)
class Report:
    """What the corpus says, and what it does not."""

    outcomes: tuple[Outcome, ...] = field(default=())

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def leaks(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.leaked)

    @property
    def leak_rate(self) -> float:
        """Of the cases that had to stay local, the share that did not.

        Denominator is the must-stay-local cases, not the whole corpus. Dividing
        by everything would let the number be improved by adding harmless cases,
        which is the easiest way to make a safety metric meaningless.
        """
        candidates = [
            o for o in self.outcomes if o.case.sensitivity is SensitivityClass.MUST_STAY_LOCAL
        ]
        return _share(self.leaks, candidates)

    @property
    def above_low(self) -> tuple[Outcome, ...]:
        """The cases that ask the complexity axis anything at all.

        A case labelled `low` is one the axis gets right by doing nothing, so a
        corpus of them measures the axis the way a corpus of empty strings
        measures a parser. 163 of iriguchi's 197 are `low`, and 134 of those are
        borrowed PII samples -- a name, a particle, an email address -- which is
        what they were written to be and not a request for work.
        """
        return tuple(o for o in self.outcomes if o.case.band is not ComplexityBand.LOW)

    @property
    def band_text_authors(self) -> dict[str, int]:
        """Who wrote the text of the cases in `above_low`, and how many each.

        **The number `band accuracy` most needs and never carried.** An
        estimator scored on prompts its own authors invented is being asked
        whether it agrees with the intuitions that produced it -- which it does,
        and which is not evidence. `docs/feasibility.md` F1 says this in prose;
        this is the same sentence attached to the number.
        """
        counted: dict[str, int] = {}
        for outcome in self.above_low:
            author = outcome.case.provenance.text.authored_by
            counted[author] = counted.get(author, 0) + 1
        return dict(sorted(counted.items(), key=lambda pair: (-pair[1], pair[0])))

    @property
    def band_is_self_scored(self) -> bool:
        """True while nobody else's text asks the axis a question.

        Measured, not assumed: it is `False` the moment a corpus arrives whose
        above-`low` cases were written by another hand, which is exactly the
        state F1 asks for and the reason `eval --corpus` exists.
        """
        return bool(self.above_low) and set(self.band_text_authors) <= {SELF}

    @property
    def missed_findings(self) -> tuple[Outcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.missed_finding)

    @property
    def missed_finding_rate(self) -> float:
        """Of the cases that had to stay local, the share the scanner cleared.

        Read this before the leak rate. A low leak rate over a corpus of easy
        prompts says the complexity axis kept them local, which it would have
        done whether or not the scanner worked at all.
        """
        candidates = [
            o for o in self.outcomes if o.case.sensitivity is SensitivityClass.MUST_STAY_LOCAL
        ]
        return _share(self.missed_findings, candidates)

    @property
    def over_caution_rate(self) -> float:
        candidates = [o for o in self.outcomes if o.case.sensitivity is SensitivityClass.MAY_LEAVE]
        held = [o for o in candidates if o.over_cautious]
        return _share(held, candidates)

    @property
    def route_accuracy(self) -> float:
        return _share([o for o in self.outcomes if o.routed_correctly], self.outcomes)

    @property
    def band_accuracy(self) -> float:
        return _share([o for o in self.outcomes if o.banded_correctly], self.outcomes)

    @property
    def median_latency_ms(self) -> float:
        return median([o.latency_ms for o in self.outcomes]) if self.outcomes else 0.0

    @property
    def slowest_latency_ms(self) -> float:
        return max((o.latency_ms for o in self.outcomes), default=0.0)

    def _band_provenance(self) -> list[str]:
        """Under `band accuracy`, whose text it was measured on.

        Two lines rather than a footnote, because a rate printed on its own is
        read as a property of the estimator and this one is partly a property of
        who wrote the corpus.
        """
        if not self.above_low:
            return ["  above `low`        nothing -- this corpus asks the axis no question"]
        listed = ", ".join(f"{author} {count}" for author, count in self.band_text_authors.items())
        lines = [f"  above `low`        {len(self.above_low)} cases, text by: {listed}"]
        if self.band_is_self_scored:
            lines.append(
                "                     all of it written here, so this rate is not yet an "
                "independent measurement (docs/feasibility.md F1)"
            )
        return lines

    def render(self) -> str:
        """A table, and the sentence that keeps it honest."""
        lines = [
            f"cases                {self.total}",
            f"missed findings      {self.missed_finding_rate:6.1%}"
            "   <- the scanner's coverage; read this first",
            f"leak rate            {self.leak_rate:6.1%}"
            "   <- end to end, floor of zero, flattered by easy prompts",
            f"over-caution rate    {self.over_caution_rate:6.1%}",
            f"route accuracy       {self.route_accuracy:6.1%}",
            f"band accuracy        {self.band_accuracy:6.1%}"
            f"   <- {self.total - len(self.above_low)} of {self.total} are labelled `low`",
            *self._band_provenance(),
            f"decision latency     {self.median_latency_ms:6.2f} ms median, "
            f"{self.slowest_latency_ms:.2f} ms slowest",
        ]
        for label, group in (("leaked", self.leaks), ("missed", self.missed_findings)):
            if group:
                lines.append("")
                lines.append(f"{label} ({len(group)}):")
                lines.extend(f"  {o.case.id}  ({o.case.trap.value})" for o in group)
        return "\n".join(lines)


def run(router: PromptRouter, cases: Sequence[Case], policy: RoutingPolicy | None = None) -> Report:
    """Route every case and collect what happened.

    `policy` is used only to work out what the *labels* imply, so that the
    expected route is derived rather than written into the fixtures. It should
    be the same policy the router holds, and is by default.
    """
    reference = policy or router.policy
    outcomes: list[Outcome] = []

    for case in cases:
        started = time.perf_counter()
        decision = router.route(case.prompt, AVAILABLE)
        elapsed = (time.perf_counter() - started) * 1000

        outcomes.append(
            Outcome(
                case=case,
                route=decision.route,
                expected_route=_expected_route(case, reference),
                level=decision.sensitivity.level,
                band=decision.complexity.band,
                latency_ms=elapsed,
            )
        )
    return Report(tuple(outcomes))


def _expected_route(case: Case, policy: RoutingPolicy) -> Route:
    """What the policy would decide if both proposers were perfect.

    Built from the labels alone. The synthetic finding exists only to produce a
    `RESTRICTED` sensitivity and never leaves this function.
    """
    findings = (
        (Finding("corpus.label", "corpus", Span(0, 0)),)
        if _EXPECTED[case.sensitivity] is SensitivityLevel.RESTRICTED
        else ()
    )
    return policy.decide(
        Sensitivity.from_findings(findings),
        _band_as_complexity(case.band),
        AVAILABLE,
    ).route


def _band_as_complexity(band: ComplexityBand) -> Complexity:
    """A `Complexity` carrying the labelled band and nothing else.

    Constructed directly rather than through `from_signals`, because the label
    *is* the band -- inventing signals that happen to add up to it would be
    reconstructing an estimator inside the scorer.
    """
    return Complexity(band=band, score=0.0, signals=(), short_circuited=False)


def _share(part: Sequence[object], whole: Sequence[object]) -> float:
    return len(part) / len(whole) if whole else 0.0
