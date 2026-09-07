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

from ..domain.complexity import Complexity, Thresholds
from ..domain.decision import RoutingDecision
from ..domain.destination import Destination
from ..domain.policy import RoutingPolicy
from ..domain.reason import Reason
from ..domain.sensitivity import Finding, Sensitivity
from ..domain.span import Span
from ..errors import EstimationError, ScanError, safe_detail
from ..ports.estimator import ComplexityEstimator
from ..ports.scanner import SensitivityScanner

__all__ = ["PromptRouter"]

_SOURCE = "routing"

#: The source on a reason that says whose look produced an empty set of
#: findings. Its own namespace rather than `routing`, because it is a statement
#: about the scan rather than about the routing that followed it -- and because
#: `rules --json` keys translations off the prefix.
_SCAN = "scan"


@dataclass(frozen=True, slots=True)
class PromptRouter:
    """A scanner, an estimator, and the policy that decides between them."""

    scanner: SensitivityScanner
    estimator: ComplexityEstimator
    policy: RoutingPolicy = field(default_factory=RoutingPolicy)
    #: Where the bands begin. A value rather than three module constants, so an
    #: operator can name a target escalation rate and have the numbers derived
    #: (`tools/calibrate.py`) instead of inventing a 0.7. The default is exactly
    #: what shipped before this field existed.
    thresholds: Thresholds = field(default_factory=Thresholds)

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
            # The port's contract, and a live branch rather than a decorative
            # one -- `tests/test_error_tree.py` asserts that difference.
            return self._scanner_failed(text, safe_detail(failure))
        except Exception as failure:
            # An adapter that raises something other than `ScanError` is not
            # conforming, and it is still not a reason to send the prompt out.
            # Catching broadly here is deliberate: the alternative is that a
            # `KeyError` in somebody's regex table becomes a leak.
            return self._scanner_failed(text, safe_detail(failure))
        return Sensitivity.from_findings(findings), self._who_looked(findings)

    def _who_looked(self, findings: tuple[Finding, ...]) -> tuple[Reason, ...]:
        """Whose look produced an empty set of findings.

        **Only when it is empty**, and that is the whole point rather than an
        economy. When findings exist, each one carries its own `source` and the
        document already says who found it. When there are none, the document
        said nothing at all -- and *the caller's analyzer looked and found
        nothing* and *this build's scanner looked and found nothing* are claims
        of very different strength that rendered byte-for-byte identically.

        Sora found it by walking the `--findings` path on a real machine and
        diffing the two documents. Their sentence for why it matters is better
        than any written here: **without saying who looked, the weaker claim
        wears the face of the stronger one.**

        iriguchi had already insisted on exactly this distinction in the other
        direction -- `--findings []` means *my analyzer found nothing*, not
        *scan for me* -- and then published a document that collapsed it.
        """
        if findings:
            return ()
        if getattr(self.scanner, "relays_the_caller", False):
            return (
                Reason(
                    rule="scan.by-the-caller",
                    source=_SCAN,
                    span=None,
                    detail=(
                        "the findings came in with the prompt and iriguchi did not scan "
                        "it, so an empty set here is the caller's clean bill of health "
                        "rather than this build's"
                    ),
                ),
            )
        return (
            Reason(
                rule="scan.by-the-router",
                source=_SCAN,
                span=None,
                detail=(
                    f"the scanner {self.scanner.name!r} looked and found nothing; what "
                    f"it misses is published, so an empty set here is only as strong as "
                    f"that scanner"
                ),
            ),
        )

    def _scanner_failed(self, text: str, kind: str) -> tuple[Sensitivity, tuple[Reason, ...]]:
        """ADR-0002, at the point where it costs something.

        The synthetic finding spans the whole prompt, because that is what is
        actually true: nothing is known about any part of it.

        **`kind` is an exception's class name, and never its message.** This
        docstring said *it carries the scanner's failure and never the text*
        while `str(failure)` went straight into a published document, and the
        two are the same string whenever a scanner quotes what it choked on --
        which is the most ordinary error message any library writes:

            regex engine gave up on 'Please email tanaka@example.com the ...'

        That reached `reasons[].detail` of `iriguchi.routing-decision/1`, the
        document ADR-0016 says is publishable *because it holds no prompt*.
        iriguchi does not write mamori's error messages or presidio's, so the
        guarantee rested on code this repository does not control.

        The remedy is the one iriguchi gave Sora for the same problem in the
        same week: **keep the name, discard the sentence.** A class name is
        written by the library author about the library; a message is
        unclassified text of unknown provenance, and ADR-0006 already said
        which of those may travel -- rule ids, spans and types, never a value.
        """
        whole = Span(0, len(text))
        finding = Finding("routing.scanner-failed", _SOURCE, whole)
        reason = Reason(
            rule="routing.scanner-failed",
            source=_SOURCE,
            span=None,
            detail=(
                f"the sensitivity scanner {self.scanner.name!r} could not answer "
                f"({kind}), so nothing is known about this prompt and it is treated "
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
            return Complexity.from_signals(self.estimator.estimate(text), self.thresholds), ()
        except EstimationError as failure:
            kind = safe_detail(failure)
        except Exception as failure:
            kind = safe_detail(failure)
        return Complexity.from_signals((), self.thresholds), (
            Reason(
                rule="routing.estimator-failed",
                source=_SOURCE,
                span=None,
                detail=(
                    f"the complexity estimator {self.estimator.name!r} could not answer "
                    f"({kind}), so this prompt is treated as the lowest band -- which "
                    f"routes local and costs answer quality, never privacy"
                ),
            ),
        )
