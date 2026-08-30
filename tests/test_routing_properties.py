"""The invariants, fuzzed.

The example-based tests in `test_routing_policy.py` say what happens for the
cases somebody thought of. These say what must hold for every case, including
the ones nobody thought of, which is the half that catches a policy edit whose
consequences the author did not follow through.

Two of them are the project:

- **A restricted prompt never leaves.** Whatever the signals, whatever the
  weights, whatever is available. This is the property the leak rate measures
  against a corpus; here it is asserted against arbitrary inputs.
- **The policy is a function.** Same inputs, identical decision. Not "equal
  enough" -- identical, including the order of every reason.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from iriguchi.domain.complexity import Complexity, Signal, SignalKind
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.policy import RoutingPolicy
from iriguchi.domain.sensitivity import Finding, Sensitivity, SensitivityLevel
from iriguchi.domain.span import Span

POLICY = RoutingPolicy()

rules = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=12
).map(lambda body: f"test.{body}")

spans = st.integers(min_value=0, max_value=5_000).flatmap(
    lambda start: st.integers(min_value=start, max_value=start + 500).map(
        lambda end: Span(start, end)
    )
)

findings = st.builds(Finding, rule=rules, source=st.just("fuzz"), span=spans)

signals = st.builds(
    Signal,
    rule=rules,
    kind=st.sampled_from(SignalKind),
    weight=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    escalating=st.booleans(),
    span=st.none(),
)

sensitivities = st.lists(findings, max_size=8).map(Sensitivity.from_findings)
complexities = st.lists(signals, max_size=8).map(Complexity.from_signals)
availabilities = st.sets(st.sampled_from(Destination), max_size=2).map(frozenset)


@given(sensitivity=sensitivities, complexity=complexities, available=availabilities)
def test_a_restricted_prompt_never_leaves(
    sensitivity: Sensitivity,
    complexity: Complexity,
    available: frozenset[Destination],
) -> None:
    """The one that matters. ADR-0002 and ADR-0003, together.

    No arrangement of signals, weights or escalating markers produces an
    external route once anything at all was found. There is nothing to tune
    that would change this, which is the point of keeping the axes apart.
    """
    decision = POLICY.decide(sensitivity, complexity, available)
    if sensitivity.level is SensitivityLevel.RESTRICTED:
        assert decision.route is not Route.EXTERNAL
        assert not decision.leaves_the_machine


@given(sensitivity=sensitivities, complexity=complexities, available=availabilities)
def test_a_route_is_only_ever_somewhere_that_was_available(
    sensitivity: Sensitivity,
    complexity: Complexity,
    available: frozenset[Destination],
) -> None:
    """A policy that invents a destination is worse than one that refuses."""
    decision = POLICY.decide(sensitivity, complexity, available)
    if decision.route is not Route.REFUSED:
        assert Destination(decision.route.value) in available


@given(sensitivity=sensitivities, complexity=complexities, available=availabilities)
def test_an_empty_machine_always_refuses(
    sensitivity: Sensitivity,
    complexity: Complexity,
    available: frozenset[Destination],
) -> None:
    if not available:
        assert POLICY.decide(sensitivity, complexity, available).route is Route.REFUSED


@given(sensitivity=sensitivities, complexity=complexities, available=availabilities)
def test_the_decision_is_a_function_of_its_inputs(
    sensitivity: Sensitivity,
    complexity: Complexity,
    available: frozenset[Destination],
) -> None:
    """Identical, not merely equivalent. AGENTS.md's ordering discipline."""
    first = POLICY.decide(sensitivity, complexity, available)
    second = POLICY.decide(sensitivity, complexity, available)
    assert first == second
    assert repr(first) == repr(second)


@given(sensitivity=sensitivities, complexity=complexities, available=availabilities)
def test_every_removal_names_a_destination_that_was_available(
    sensitivity: Sensitivity,
    complexity: Complexity,
    available: frozenset[Destination],
) -> None:
    """Removing something that was never offered would be a confusing lie."""
    decision = POLICY.decide(sensitivity, complexity, available)
    for removal in decision.removed:
        assert removal.destination in available


@given(sensitivity=sensitivities, complexity=complexities, available=availabilities)
def test_a_decision_always_accounts_for_itself(
    sensitivity: Sensitivity,
    complexity: Complexity,
    available: frozenset[Destination],
) -> None:
    """ADR-0006: there is no route without at least one reason for it."""
    decision = POLICY.decide(sensitivity, complexity, available)
    assert decision.reasons
    assert all(reason.rule and reason.detail for reason in decision.reasons)


@given(signals=st.lists(signals, max_size=40))
def test_the_complexity_score_stays_a_probability(signals: list[Signal]) -> None:
    """However many rules a long prompt trips."""
    assert 0.0 <= Complexity.from_signals(signals).score <= 1.0


@given(findings=st.lists(findings, max_size=8))
def test_sensitivity_only_ever_narrows(findings: list[Finding]) -> None:
    """A veto that grants is not a veto."""
    sensitivity = Sensitivity.from_findings(findings)
    for offered in (frozenset(), frozenset({Destination.LOCAL}), frozenset(Destination)):
        assert sensitivity.permit(offered) <= offered
