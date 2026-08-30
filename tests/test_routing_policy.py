"""The only place a route is chosen, and the order it chooses in.

Four steps, and the order is the decision (ADR-0003):

1. start from the destinations this machine actually has;
2. sensitivity removes;
3. an empty set is `REFUSED` (ADR-0002);
4. complexity chooses among whatever is left.

Every test here is a statement about that order. The one that matters most is
``test_difficulty_cannot_buy_back_a_vetoed_destination``: it is the bug this
whole design exists to make unrepresentable.
"""

from __future__ import annotations

import pytest

from iriguchi.domain.complexity import Complexity, ComplexityBand, Signal, SignalKind
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.policy import RoutingPolicy
from iriguchi.domain.sensitivity import Finding, Sensitivity
from iriguchi.domain.span import Span

BOTH = frozenset(Destination)
LOCAL_ONLY = frozenset({Destination.LOCAL})
NOTHING: frozenset[Destination] = frozenset()

CLEAR = Sensitivity.from_findings(())
RESTRICTED = Sensitivity.from_findings((Finding("fallback.email-shape", "fallback", Span(4, 22)),))

EASY = Complexity.from_signals(())
HARD = Complexity.from_signals((Signal("complexity.enormous", SignalKind.LEXICAL, 0.95),))


@pytest.fixture
def policy() -> RoutingPolicy:
    return RoutingPolicy()


class TestTheOrder:
    def test_easy_and_clear_stays_local(self, policy: RoutingPolicy) -> None:
        assert policy.decide(CLEAR, EASY, BOTH).route is Route.LOCAL

    def test_hard_and_clear_escalates(self, policy: RoutingPolicy) -> None:
        assert policy.decide(CLEAR, HARD, BOTH).route is Route.EXTERNAL

    def test_difficulty_cannot_buy_back_a_vetoed_destination(self, policy: RoutingPolicy) -> None:
        """The bug this design exists to make unrepresentable. ADR-0003.

        A prompt with a finding in it is hard *and* restricted. Every weighted
        router eventually routes this outbound, because a high enough
        difficulty score outweighs a sensitivity score. Here there is no score
        to outweigh: the destination is gone before complexity is consulted.
        """
        decision = policy.decide(RESTRICTED, HARD, BOTH)
        assert decision.route is Route.LOCAL

    def test_the_veto_is_recorded_with_its_reason(self, policy: RoutingPolicy) -> None:
        decision = policy.decide(RESTRICTED, HARD, BOTH)
        removed = {removal.destination for removal in decision.removed}
        assert removed == {Destination.EXTERNAL}
        assert decision.removed[0].reason.span == Span(4, 22)
        assert decision.removed[0].reason.rule


class TestFailClosed:
    def test_no_destination_at_all_is_refused(self, policy: RoutingPolicy) -> None:
        assert policy.decide(CLEAR, EASY, NOTHING).route is Route.REFUSED

    def test_restricted_with_no_local_model_is_refused_not_sent(
        self, policy: RoutingPolicy
    ) -> None:
        """ADR-0002, and the reason the whole decision exists.

        The machine can reach the network and cannot run a model. A router that
        treats the remaining destination as "the one that is left" converts
        every outage into a leak.
        """
        external_only = frozenset({Destination.EXTERNAL})
        decision = policy.decide(RESTRICTED, HARD, external_only)
        assert decision.route is Route.REFUSED

    def test_a_refusal_says_what_was_removed_and_why(self, policy: RoutingPolicy) -> None:
        decision = policy.decide(RESTRICTED, HARD, frozenset({Destination.EXTERNAL}))
        assert decision.removed
        assert all(removal.reason.detail for removal in decision.removed)

    def test_a_refusal_with_nothing_offered_still_explains_itself(
        self, policy: RoutingPolicy
    ) -> None:
        """Nothing was removed -- nothing was ever there. Say that, do not
        return an empty account and let the reader guess."""
        decision = policy.decide(CLEAR, EASY, NOTHING)
        assert decision.reasons
        assert any("available" in reason.detail for reason in decision.reasons)


class TestWhatItAlwaysReports:
    def test_both_axes_survive_into_the_decision(self, policy: RoutingPolicy) -> None:
        """Complexity is computed and reported even when it changed nothing."""
        decision = policy.decide(RESTRICTED, HARD, LOCAL_ONLY)
        assert decision.sensitivity is RESTRICTED
        assert decision.complexity is HARD
        assert decision.complexity.band is ComplexityBand.HIGH

    def test_reasons_are_ordered_deterministically(self, policy: RoutingPolicy) -> None:
        first = policy.decide(RESTRICTED, HARD, BOTH)
        second = policy.decide(RESTRICTED, HARD, BOTH)
        assert [r.rule for r in first.reasons] == [r.rule for r in second.reasons]
        assert [r.destination for r in first.removed] == [r.destination for r in second.removed]

    def test_the_same_inputs_give_an_identical_decision(self, policy: RoutingPolicy) -> None:
        """AGENTS.md's ordering discipline, as an equality."""
        assert policy.decide(RESTRICTED, HARD, BOTH) == policy.decide(RESTRICTED, HARD, BOTH)

    def test_a_decision_never_renders_a_value(self, policy: RoutingPolicy) -> None:
        decision = policy.decide(RESTRICTED, HARD, BOTH)
        rendered = repr(decision)
        assert "tanaka@example.com" not in rendered
        assert "fallback.email-shape" in rendered


class TestThePolicyIsPure:
    def test_it_does_not_mutate_what_it_was_given(self, policy: RoutingPolicy) -> None:
        offered = frozenset(Destination)
        policy.decide(RESTRICTED, HARD, offered)
        assert offered == frozenset(Destination)

    def test_it_holds_no_state_between_decisions(self, policy: RoutingPolicy) -> None:
        policy.decide(RESTRICTED, HARD, BOTH)
        assert policy.decide(CLEAR, EASY, BOTH).route is Route.LOCAL


class TestExternalIsTheOnlyDestination:
    """A machine with no local model, and a prompt with nothing in it.

    Sending it is correct: sensitivity did not remove the external destination,
    so refusing here would protect nothing and would only stop the person
    working. This is the one case where the fail-closed rule does *not* apply,
    and the boundary is worth pinning -- ADR-0002 refuses when a *restricted*
    prompt has nowhere safe to go, not whenever the local model is missing.
    """

    EXTERNAL_ONLY = frozenset({Destination.EXTERNAL})

    def test_a_clear_easy_prompt_goes_out(self, policy: RoutingPolicy) -> None:
        decision = policy.decide(CLEAR, EASY, self.EXTERNAL_ONLY)
        assert decision.route is Route.EXTERNAL
        assert decision.leaves_the_machine

    def test_it_says_that_it_was_the_only_one_left(self, policy: RoutingPolicy) -> None:
        decision = policy.decide(CLEAR, EASY, self.EXTERNAL_ONLY)
        assert any(reason.rule == "policy.only-destination" for reason in decision.reasons)

    def test_a_restricted_prompt_in_the_same_position_is_refused(
        self, policy: RoutingPolicy
    ) -> None:
        """The contrast that makes the previous two safe."""
        decision = policy.decide(RESTRICTED, EASY, self.EXTERNAL_ONLY)
        assert decision.was_refused
        assert not decision.leaves_the_machine
