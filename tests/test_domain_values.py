"""The routing values, and the rules they enforce by being what they are.

These are the tests that have to hold whatever the scanners and estimators
eventually look like. Every one of them describes a property of the *domain*:
what a span is, what a finding may and may not carry, and how signals become a
band. Nothing here constructs an adapter, opens a file, or knows a model exists.

The one to read first is ``TestNothingCarriesAValue``. A router that prints the
thing it was protecting has undone itself, and the only reliable way to check
that is to render the objects and look.
"""

from __future__ import annotations

import dataclasses

import pytest

from iriguchi.domain.complexity import Complexity, ComplexityBand, Signal, SignalKind
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.reason import Reason, Removal
from iriguchi.domain.sensitivity import Finding, Sensitivity, SensitivityLevel
from iriguchi.domain.span import Span


class TestSpan:
    def test_it_knows_its_length(self) -> None:
        assert Span(4, 10).length == 6

    def test_an_empty_span_is_allowed(self) -> None:
        """A rule can fire on a position rather than a run of characters."""
        assert Span(4, 4).length == 0

    @pytest.mark.parametrize(("start", "end"), [(-1, 3), (5, 4), (0, -2)])
    def test_it_refuses_to_be_nonsense(self, start: int, end: int) -> None:
        with pytest.raises(ValueError, match="span"):
            Span(start, end)

    def test_it_sorts_by_start_then_end(self) -> None:
        """Ordering has to be total, or reason lists are not reproducible."""
        spans = [Span(5, 9), Span(0, 4), Span(5, 6)]
        assert sorted(spans) == [Span(0, 4), Span(5, 6), Span(5, 9)]

    def test_it_is_hashable_and_immutable(self) -> None:
        assert len({Span(0, 4), Span(0, 4)}) == 1
        with pytest.raises(dataclasses.FrozenInstanceError):
            Span(0, 4).start = 1  # type: ignore[misc]


class TestSensitivity:
    def test_no_findings_is_clear(self) -> None:
        assert Sensitivity.from_findings(()).level is SensitivityLevel.CLEAR

    def test_any_finding_restricts(self) -> None:
        """One is enough. There is no threshold and no counting.

        A count would be a score, and a score is something a complexity signal
        could eventually be compared against. ADR-0003.
        """
        one = Sensitivity.from_findings((Finding("fallback.email-shape", "fallback", Span(0, 5)),))
        assert one.level is SensitivityLevel.RESTRICTED

    def test_it_removes_the_external_destination_and_nothing_else(self) -> None:
        restricted = Sensitivity.from_findings(
            (Finding("fallback.key-shape", "fallback", Span(0, 5)),)
        )
        assert restricted.permit(frozenset(Destination)) == frozenset({Destination.LOCAL})

    def test_clear_removes_nothing(self) -> None:
        assert Sensitivity.from_findings(()).permit(frozenset(Destination)) == frozenset(
            Destination
        )

    def test_it_cannot_add_a_destination_that_was_not_offered(self) -> None:
        """It only ever removes. A veto that grants is not a veto."""
        offered = frozenset({Destination.LOCAL})
        assert Sensitivity.from_findings(()).permit(offered) == offered

    def test_findings_are_ordered_by_span(self) -> None:
        """Same inputs, byte-identical output. AGENTS.md's ordering discipline."""
        late = Finding("b.rule", "fallback", Span(20, 24))
        early = Finding("a.rule", "fallback", Span(2, 6))
        assert Sensitivity.from_findings((late, early)).findings == (early, late)

    def test_it_is_not_comparable_with_a_complexity(self) -> None:
        """ADR-0003, asserted rather than promised.

        If these two could be ordered against each other, somebody would
        eventually order them, and the router would have one score.
        """
        sensitivity = Sensitivity.from_findings(())
        complexity = Complexity.from_signals(())
        with pytest.raises(TypeError):
            _ = sensitivity < complexity  # type: ignore[operator]


class TestComplexity:
    def test_no_signals_is_the_lowest_band(self) -> None:
        assert Complexity.from_signals(()).band is ComplexityBand.LOW

    def test_weights_accumulate_into_a_band(self) -> None:
        signals = (
            Signal("complexity.long-input", SignalKind.LEXICAL, 0.4),
            Signal("complexity.code-fence", SignalKind.STRUCTURAL, 0.3),
        )
        assert Complexity.from_signals(signals).band is ComplexityBand.MODERATE

    def test_two_escalating_signals_short_circuit_to_high(self) -> None:
        """The one borrowed rule.

        Weighted scores under-serve the case where a prompt asks for two hard
        things at once: each marker is individually cheap, and the sum lands in
        the middle band. Two escalating markers reach the top band regardless
        of the weighted score.
        """
        signals = (
            Signal("complexity.multi-step", SignalKind.STRUCTURAL, 0.05, escalating=True),
            Signal("complexity.proof-request", SignalKind.STRUCTURAL, 0.05, escalating=True),
        )
        result = Complexity.from_signals(signals)
        assert result.band is ComplexityBand.HIGH
        assert result.short_circuited is True

    def test_one_escalating_signal_does_not_short_circuit(self) -> None:
        signals = (Signal("complexity.multi-step", SignalKind.STRUCTURAL, 0.05, escalating=True),)
        result = Complexity.from_signals(signals)
        assert result.band is ComplexityBand.LOW
        assert result.short_circuited is False

    def test_a_weighted_high_band_is_not_marked_short_circuited(self) -> None:
        signals = (Signal("complexity.enormous", SignalKind.LEXICAL, 0.95),)
        result = Complexity.from_signals(signals)
        assert result.band is ComplexityBand.HIGH
        assert result.short_circuited is False

    @pytest.mark.parametrize("weight", [-0.1, 1.1])
    def test_a_signal_weight_is_bounded(self, weight: float) -> None:
        with pytest.raises(ValueError, match="weight"):
            Signal("complexity.nonsense", SignalKind.LEXICAL, weight)

    def test_the_score_is_bounded_however_many_signals_fire(self) -> None:
        """Forty signals must not produce a score of forty."""
        signals = tuple(Signal(f"complexity.rule-{i}", SignalKind.LEXICAL, 0.9) for i in range(40))
        assert Complexity.from_signals(signals).score <= 1.0

    def test_signals_are_ordered_deterministically(self) -> None:
        signals = (
            Signal("z.rule", SignalKind.LEXICAL, 0.1),
            Signal("a.rule", SignalKind.LEXICAL, 0.1),
        )
        assert [s.rule for s in Complexity.from_signals(signals).signals] == ["a.rule", "z.rule"]


class TestNothingCarriesAValue:
    """ADR-0006. A `Reason` names a rule and a span, never the matched text.

    This is checked by rendering the objects rather than by reading the class,
    because the failure mode is a field somebody added in good faith and a
    `repr` that prints it.
    """

    SECRET = "sk-live-51H8xQeMwv"

    def test_a_finding_has_nowhere_to_put_a_value(self) -> None:
        fields = {f.name for f in dataclasses.fields(Finding)}
        assert fields == {"rule", "source", "span"}

    def test_a_finding_repr_cannot_leak(self) -> None:
        finding = Finding("fallback.key-shape", "fallback", Span(0, len(self.SECRET)))
        assert self.SECRET not in repr(finding)

    def test_a_reason_detail_is_prose_about_a_rule(self) -> None:
        reason = Reason(
            rule="fallback.key-shape",
            source="fallback",
            span=Span(0, 19),
            detail="a token of 19 characters with base64 entropy above 4.5",
        )
        assert self.SECRET not in repr(reason)
        assert "entropy" in reason.detail

    def test_a_removal_says_which_destination_and_why(self) -> None:
        removal = Removal(
            destination=Destination.EXTERNAL,
            reason=Reason(
                rule="policy.finding-present",
                source="policy",
                span=Span(0, 19),
                detail="a finding at 0-19 is not permitted to leave",
            ),
        )
        assert removal.destination is Destination.EXTERNAL
        assert self.SECRET not in repr(removal)


class TestRoute:
    def test_a_route_is_not_a_destination(self) -> None:
        """`REFUSED` is what an empty permitted set renders as.

        Modelling it as a third destination would make "send it to REFUSED" a
        sentence the type system permits.
        """
        assert {d.name for d in Destination} == {"LOCAL", "EXTERNAL"}
        assert {r.name for r in Route} == {"LOCAL", "EXTERNAL", "REFUSED"}

    def test_every_destination_has_a_route(self) -> None:
        for destination in Destination:
            assert Route.for_destination(destination).name == destination.name


class TestARuleMustNameItself:
    """An id is what lets somebody disable a rule without forking the library.

    Every value that can appear in an explanation therefore refuses to be
    constructed without one. Anonymous rules are how an explanation becomes a
    list of blanks.
    """

    def test_a_finding_needs_a_rule(self) -> None:
        with pytest.raises(ValueError, match="rule"):
            Finding("", "fallback", Span(0, 4))

    def test_a_signal_needs_a_rule(self) -> None:
        with pytest.raises(ValueError, match="rule"):
            Signal("", SignalKind.LEXICAL, 0.5)

    def test_a_reason_needs_a_rule(self) -> None:
        with pytest.raises(ValueError, match="rule"):
            Reason(rule="", source="policy", span=None, detail="something happened")

    def test_a_reason_needs_to_say_something(self) -> None:
        """Naming the rule is not the same as explaining it."""
        with pytest.raises(ValueError, match="detail"):
            Reason(rule="policy.something", source="policy", span=None, detail="")


class TestReasonOrdering:
    """Reasons about the whole request come before reasons about a place in it.

    A reader wants "no local model is configured" before "a token at offset 40
    looks like a key". Sorting spanless reasons first is how that happens
    without the policy having to order its own output by hand.
    """

    def test_a_spanless_reason_sorts_before_a_spanned_one(self) -> None:
        whole = Reason(rule="policy.whole", source="policy", span=None, detail="about the request")
        placed = Reason(rule="a.placed", source="fallback", span=Span(0, 1), detail="about a span")
        assert sorted([placed, whole], key=lambda r: r.sort_key) == [whole, placed]

    def test_spanned_reasons_sort_by_position(self) -> None:
        early = Reason(rule="z.early", source="fallback", span=Span(2, 6), detail="first")
        late = Reason(rule="a.late", source="fallback", span=Span(20, 24), detail="second")
        assert sorted([late, early], key=lambda r: r.sort_key) == [early, late]
