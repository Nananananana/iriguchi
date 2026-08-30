"""The only place a route is chosen.

Four steps, and the order *is* the decision:

1. start from the destinations this machine actually has;
2. sensitivity removes (ADR-0003);
3. an empty set is a refusal, never a fall-through (ADR-0002);
4. complexity chooses among whatever is left.

Nothing in this module compares a sensitivity with a complexity, and there is no
number they both become. That is not an oversight to be tidied up later: the
whole design rests on step 2 finishing before step 4 begins, so that no
difficulty signal can buy back a destination the veto removed.

A scanner proposes. An estimator proposes. This decides. Swapping either
proposer -- for mamori, for a local model, for something not yet written --
cannot change what a proposal means, which is why a hallucinating model cannot
become a leak here. The worst it can do is withhold a finding it should have
made, and that is a detection problem rather than a routing one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .complexity import Complexity
from .decision import RoutingDecision
from .destination import Destination, Route
from .reason import Reason, Removal
from .sensitivity import Sensitivity

__all__ = ["RoutingPolicy"]

_SOURCE = "policy"


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Stateless, and deliberately so.

    Two decisions taken a second apart must be identical, so there is nothing
    here to accumulate: no cache, no history, no wall clock. A policy that
    remembered the last prompt would be a policy whose answer depended on the
    order requests arrived in, which is not something a person could reason
    about and not something a test could pin.
    """

    def decide(
        self,
        sensitivity: Sensitivity,
        complexity: Complexity,
        available: frozenset[Destination],
    ) -> RoutingDecision:
        """Choose a route, and account for it.

        Args:
            sensitivity: What a scan concluded. Removes destinations.
            complexity: What an estimator concluded. Chooses among the rest.
            available: What this machine can actually reach. A destination
                absent here is not a policy decision -- it is a missing local
                model or an unconfigured escalation channel -- so its absence is
                reported as a reason rather than as a removal.
        """
        reasons: list[Reason] = []
        removed: list[Removal] = []

        permitted = sensitivity.permit(available)

        for destination in sorted(available - permitted, key=lambda d: d.value):
            removed.append(Removal(destination, self._veto_reason(sensitivity, destination)))

        if not available:
            reasons.append(
                Reason(
                    rule="policy.no-destination-available",
                    source=_SOURCE,
                    span=None,
                    detail=(
                        "no destination is available on this machine: there is no local "
                        "model configured and no escalation channel"
                    ),
                )
            )
        elif not permitted:
            reasons.append(
                Reason(
                    rule="policy.every-destination-removed",
                    source=_SOURCE,
                    span=None,
                    detail=(
                        "every available destination was removed, so the request is "
                        "refused rather than sent to whichever one happened to be left"
                    ),
                )
            )

        route = self._choose(permitted, complexity, reasons)
        return RoutingDecision(
            route=route,
            sensitivity=sensitivity,
            complexity=complexity,
            reasons=tuple(sorted(reasons, key=lambda r: r.sort_key)),
            removed=tuple(removed),
        )

    def _choose(
        self,
        permitted: frozenset[Destination],
        complexity: Complexity,
        reasons: list[Reason],
    ) -> Route:
        """Step 4. Only ever consulted about destinations already permitted."""
        if not permitted:
            return Route.REFUSED

        if Destination.EXTERNAL in permitted and complexity.prefers_the_larger_model:
            reasons.append(
                Reason(
                    rule="policy.escalate-on-band",
                    source=_SOURCE,
                    span=None,
                    detail=(
                        f"complexity band {complexity.band.value} and the external "
                        f"destination is permitted"
                    ),
                )
            )
            return Route.EXTERNAL

        if Destination.LOCAL in permitted:
            # Two different reasons land here and they must not share a
            # sentence. Either complexity did not ask to escalate, or it did and
            # there was nowhere to escalate to -- and printing "band high does
            # not call for the larger model" in the second case is a decision
            # explaining itself wrongly, which is worse than not explaining. The
            # CLI found this on its first run.
            if complexity.prefers_the_larger_model:
                detail = (
                    f"complexity band {complexity.band.value} would have called for the "
                    f"larger model, but the external destination is not available"
                )
            else:
                detail = (
                    f"complexity band {complexity.band.value} does not call for the "
                    f"larger model, and a local model is permitted"
                )
            reasons.append(
                Reason(rule="policy.prefer-local", source=_SOURCE, span=None, detail=detail)
            )
            return Route.LOCAL

        # Permitted, not local, and complexity did not ask to escalate. The only
        # remaining destination is external, and taking it is still correct:
        # sensitivity did not remove it, so nothing here is protecting anything
        # by refusing. Answer quality is the only thing at stake.
        reasons.append(
            Reason(
                rule="policy.only-destination",
                source=_SOURCE,
                span=None,
                detail=(
                    "no local model is available and the external destination was not "
                    "removed, so it is the only one left"
                ),
            )
        )
        return Route.EXTERNAL

    @staticmethod
    def _veto_reason(sensitivity: Sensitivity, destination: Destination) -> Reason:
        """Why a destination went away.

        Points at the first finding, because a person tracing an unexpected
        refusal wants somewhere in the text to look. The rest are in
        `decision.sensitivity.findings`, in the same order.
        """
        first = sensitivity.findings[0] if sensitivity.findings else None
        if first is None:  # pragma: no cover -- only CLEAR has no findings, and it removes nothing
            raise AssertionError(
                f"{sensitivity.level} removed {destination} without producing a finding"
            )
        return Reason(
            rule="policy.finding-present",
            source=_SOURCE,
            span=first.span,
            detail=(
                f"{sensitivity.level.value}: {len(sensitivity.findings)} finding(s), the "
                f"first from {first.rule} at {first.span}; not permitted to leave"
            ),
        )
