"""Ask both proposers, then ask the policy.

The whole use case is four steps and none of them is a decision -- the decisions
are all in `domain/`, which is what makes a hallucinating scanner or a broken
estimator unable to turn a must-stay-local prompt into an outbound request.

What this layer does own is **what happens when a proposer fails**, and that is
the only interesting thing in the file.

`SensitivityScanner` is required to raise rather than return an empty sequence,
because at the call site "I found nothing" and "I broke" are indistinguishable
and only the first is safe. So a failure arrives here as an exception, and
ADR-0002 says what to do with it: *the most restrictive route available, not the
most useful one*. A broken scanner costs you the external route. It does not
cost you your afternoon, and it does not silently cost you your privacy.

An estimator that fails is not dangerous in the same way. No signals is the
lowest band, which routes local, so the safe answer is already the default --
the asymmetry between the two ports, stated once more where it has
consequences. It is still reported, because a decision that quietly lost an axis
looks exactly like a decision where that axis had no opinion, and only one of
those means the router is working.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.complexity import Complexity
from ..domain.decision import RoutingDecision
from ..domain.destination import Destination
from ..domain.policy import RoutingPolicy
from ..domain.reason import Reason
from ..domain.sensitivity import Finding, Sensitivity
from ..domain.span import Span
from ..errors import EstimationError, ScanError
from ..ports.estimator import ComplexityEstimator
from ..ports.scanner import SensitivityScanner

__all__ = ["PromptRouter"]

_SOURCE = "routing"


@dataclass(frozen=True, slots=True)
class PromptRouter:
    """A scanner, an estimator, and the policy that decides between them."""

    scanner: SensitivityScanner
    estimator: ComplexityEstimator
    policy: RoutingPolicy = field(default_factory=RoutingPolicy)

    def route(self, text: str, available: frozenset[Destination]) -> RoutingDecision:
        """Where `text` is allowed to go, and the whole account of why.

        Args:
            text: The prompt, exactly as the person typed it. Nothing here
                normalizes it; a scanner that needs to fold it does so and maps
                its offsets back (see `infrastructure/normalization.py`).
            available: What this machine can reach. Passed in rather than
                probed for -- ADR-0011 -- which is what lets the whole test
                suite run with the network unavailable.

        Never raises for a proposer failure. A decision always comes out, and
        the failure is in its reasons.
        """
        sensitivity, scan_reasons = self._scan(text)
        complexity, estimate_reasons = self._estimate(text)
        extra = scan_reasons + estimate_reasons

        decision = self.policy.decide(sensitivity, complexity, available)
        if not extra:
            return decision

        # The policy's reasons plus ours, re-sorted as one list so the ordering
        # rule still holds. A failure has no span, so it sorts to the front,
        # which is where a reader needs it.
        reasons = tuple(sorted(decision.reasons + extra, key=lambda reason: reason.sort_key))
        return RoutingDecision(
            route=decision.route,
            sensitivity=decision.sensitivity,
            complexity=decision.complexity,
            reasons=reasons,
            removed=decision.removed,
        )

    def _scan(self, text: str) -> tuple[Sensitivity, tuple[Reason, ...]]:
        """Findings, or -- if the scanner broke -- a restriction saying so."""
        try:
            findings = tuple(self.scanner.scan(text))
        except ScanError as failure:
            return self._scanner_failed(text, str(failure))
        except Exception as failure:
            # An adapter that raises something other than `ScanError` is not
            # conforming, and it is still not a reason to send the prompt out.
            # Catching broadly here is deliberate: the alternative is that a
            # `KeyError` in somebody's regex table becomes a leak.
            return self._scanner_failed(text, f"{type(failure).__name__}: {failure}")
        return Sensitivity.from_findings(findings), ()

    def _scanner_failed(self, text: str, detail: str) -> tuple[Sensitivity, tuple[Reason, ...]]:
        """ADR-0002, at the point where it costs something.

        The synthetic finding spans the whole prompt, because that is what is
        actually true: nothing is known about any part of it. It carries the
        scanner's failure and never the text.
        """
        whole = Span(0, len(text))
        finding = Finding("routing.scanner-failed", _SOURCE, whole)
        reason = Reason(
            rule="routing.scanner-failed",
            source=_SOURCE,
            span=None,
            detail=(
                f"the sensitivity scanner {self.scanner.name!r} could not answer "
                f"({detail}), so nothing is known about this prompt and it is treated "
                f"as restricted"
            ),
        )
        return Sensitivity.from_findings((finding,)), (reason,)

    def _estimate(self, text: str) -> tuple[Complexity, tuple[Reason, ...]]:
        """Signals, or -- if the estimator broke -- none, which is the low band.

        Nothing dangerous happens when this fails, but it is still reported. A
        decision that quietly lost an axis looks exactly like a decision where
        that axis had no opinion, and ADR-0006 exists because those two are not
        the same and only one of them means the router is working.
        """
        try:
            return Complexity.from_signals(self.estimator.estimate(text)), ()
        except EstimationError as failure:
            detail = str(failure)
        except Exception as failure:
            detail = f"{type(failure).__name__}: {failure}"
        return Complexity.from_signals(()), (
            Reason(
                rule="routing.estimator-failed",
                source=_SOURCE,
                span=None,
                detail=(
                    f"the complexity estimator {self.estimator.name!r} could not answer "
                    f"({detail}), so this prompt is treated as the lowest band -- which "
                    f"routes local and costs answer quality, never privacy"
                ),
            ),
        )
