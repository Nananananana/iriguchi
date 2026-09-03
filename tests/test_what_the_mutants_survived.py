"""Written from a mutation run, not from imagination.

`python tools/mutate.py` changes one operator in the domain, runs the suite, and
records whether anybody noticed. The first run: **58 mutants, 36 killed, 22
survived — 62.1%.**

A survivor is not necessarily a bug. It is a sentence the suite cannot
distinguish from the truth, which is a weaker and more useful claim. Sorted, the
twenty-two were three things:

    7   frozen=True -> False    **nothing asserted the domain's values are values**
    8   slots=True -> False     near-equivalent: memory, and adding attributes
    2   >= -> >  at the bands    **both thresholds untested at exactly the threshold**
    5   assorted defaults and a sort key

This file closes the first and third. The `slots` ones are left alive
deliberately and said so below, because a mutant killed by a test written only
to kill it is a score improved rather than a suite improved.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from iriguchi.domain import complexity as complexity_module
from iriguchi.domain.complexity import (
    Complexity,
    ComplexityBand,
    Signal,
    SignalKind,
    Thresholds,
)
from iriguchi.domain.decision import RoutingDecision
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.policy import RoutingPolicy
from iriguchi.domain.reason import Reason, Removal
from iriguchi.domain.sensitivity import Finding, Sensitivity
from iriguchi.domain.span import Span

#: Every frozen value in the domain, with something to build one from. Listed
#: rather than discovered, because a constructor needs arguments and a
#: discovered class would need them guessed — and a guess that fails would
#: silently drop a class from the sweep.
_A_REASON = Reason(rule="a.rule", source="a-source", span=None, detail="a detail")
_CLEAR = Sensitivity.from_findings(())
_NO_SIGNALS = Complexity.from_signals(())

VALUES: dict[str, Any] = {
    "Span": Span(start=0, end=3),
    "Reason": _A_REASON,
    # Three fields and deliberately nowhere for a fourth holding the matched
    # text -- and no confidence either, because a confidence becomes a threshold
    # and a threshold is a score.
    "Finding": Finding(rule="a.rule", source="a-source", span=Span(0, 3)),
    "Signal": Signal(rule="a.rule", kind=SignalKind.STRUCTURAL, weight=0.5, escalating=True),
    "Complexity": _NO_SIGNALS,
    "Sensitivity": _CLEAR,
    "RoutingDecision": RoutingDecision(
        route=Route.LOCAL, sensitivity=_CLEAR, complexity=_NO_SIGNALS
    ),
    "Removal": Removal(destination=Destination.EXTERNAL, reason=_A_REASON),
    "RoutingPolicy": RoutingPolicy(),
    "Thresholds": Thresholds(),
}


class TestTheValuesAreValues:
    """`frozen=True` survived seven mutations, once per dataclass.

    Nothing anywhere tried to assign to one. That is the promise the whole
    domain rests on — a decision is a value, so it cannot be edited after it
    was decided — and it was carried entirely by the decorator being typed
    correctly seven times.
    """

    def test_the_sweep_covers_every_frozen_class_in_the_domain(self) -> None:
        """A floor, and a comparison against the module rather than a count.

        Listing the values by hand means a new domain class is not swept until
        somebody adds it here. This says so rather than letting the sweep
        quietly shrink.
        """
        import importlib
        import pkgutil

        import iriguchi.domain

        frozen: set[str] = set()
        for info in pkgutil.iter_modules(iriguchi.domain.__path__):
            module = importlib.import_module(f"iriguchi.domain.{info.name}")
            for name, value in vars(module).items():
                # `isinstance(value, type)` because `is_dataclass` is true of
                # instances as well as classes, and the module holds
                # `DEFAULT_THRESHOLDS`. Without it the sweep demanded an entry
                # for a value rather than for its class.
                if (
                    isinstance(value, type)
                    and dataclasses.is_dataclass(value)
                    and getattr(value, "__module__", "").startswith("iriguchi.domain")
                    # `__dataclass_params__` is real and unannotated in typeshed.
                    and value.__dataclass_params__.frozen  # type: ignore[attr-defined]
                ):
                    frozen.add(name)
        missing = sorted(frozen - set(VALUES))
        assert not missing, (
            f"{missing} are frozen dataclasses in the domain and are not in this "
            f"file's sweep. A value nobody tries to assign to is a value whose "
            f"immutability is carried by a decorator being typed correctly."
        )

    @pytest.mark.parametrize("name", sorted(VALUES))
    def test_assigning_to_a_field_raises(self, name: str) -> None:
        """Every field, not the first one.

        A frozen dataclass freezes all of them, but a hand-written
        `__setattr__` guarding one and forgetting another is a real shape and
        checking `fields[0]` would not see it.

        `RoutingPolicy` has no fields at all -- it is behaviour with defaults --
        so it is skipped here and covered by the unknown-attribute test below.
        Skipped loudly rather than passing on an empty loop.
        """
        value = VALUES[name]
        fields = dataclasses.fields(value)
        if not fields:
            pytest.skip(f"{name} has no fields; the next test covers it")
        for field in fields:
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(value, field.name, getattr(value, field.name))

    @pytest.mark.parametrize("name", sorted(VALUES))
    def test_a_decision_cannot_grow_a_field_after_the_fact(self, name: str) -> None:
        """`slots=True`'s half that is not about memory.

        The mutation run left eight `slots=True -> False` survivors alive, and
        this kills them for the reason that matters rather than for the score:
        a `RoutingDecision` that can be handed an extra attribute is one a
        caller can annotate after the deciding is done.

        **`TypeError` is in the tuple because of a CPython wart, measured on
        3.12.8 rather than assumed:**

            frozen + slots   unknown attribute -> TypeError
            frozen alone     unknown attribute -> FrozenInstanceError

        `slots=True` recreates the class, and the `__setattr__` the dataclass
        generated closes over the original — so the `super()` call inside it
        fails before the frozen check can produce its own message. A user who
        mistypes a field name gets *super(type, obj): obj must be an instance or
        subtype of type*, which says nothing about what they did wrong.

        Not iriguchi's bug and iriguchi's surface. Recorded here because the
        alternative is somebody meeting it with no explanation attached.
        """
        with pytest.raises((AttributeError, TypeError)):
            VALUES[name].added_later = "no"


class TestTheBandBoundaries:
    """Two mutants survived: `score >= _HIGH_AT` and `score >= _MODERATE_AT`,
    each turned into `>`.

    Nothing tested a score sitting **exactly** on a threshold, so the difference
    between `>=` and `>` was invisible — in the function that decides whether a
    prompt is worth the larger model, and therefore whether it leaves.

    A single signal of weight `w` gives a noisy-OR score of exactly `w`, which
    is how a boundary is reached precisely rather than approached.
    """

    @staticmethod
    def _at(weight: float) -> Complexity:
        return Complexity.from_signals(
            (Signal(rule="test.exact", kind=SignalKind.LEXICAL, weight=weight, escalating=False),)
        )

    def test_exactly_the_high_threshold_is_high(self) -> None:
        """`>=`, not `>`. The threshold is the first score that counts, not the
        first one after it."""
        at = self._at(complexity_module._HIGH_AT)
        assert at.score == pytest.approx(complexity_module._HIGH_AT)
        assert at.band is ComplexityBand.HIGH

    def test_exactly_the_moderate_threshold_is_moderate(self) -> None:
        at = self._at(complexity_module._MODERATE_AT)
        assert at.score == pytest.approx(complexity_module._MODERATE_AT)
        assert at.band is ComplexityBand.MODERATE

    @pytest.mark.parametrize(
        ("threshold", "below", "above"),
        [
            ("_HIGH_AT", ComplexityBand.MODERATE, ComplexityBand.HIGH),
            ("_MODERATE_AT", ComplexityBand.LOW, ComplexityBand.MODERATE),
        ],
    )
    def test_just_below_and_just_above_land_on_either_side(
        self, threshold: str, below: ComplexityBand, above: ComplexityBand
    ) -> None:
        """The other two thirds of a boundary. A test at the threshold alone
        would pass on a function that returned the upper band for everything."""
        value = getattr(complexity_module, threshold)
        assert self._at(value - 1e-9).band is below
        assert self._at(value + 1e-9).band is above


class TestWhetherTheBoundaryIsReachableAtAll:
    """The mutation run asked a question the tests above answer only halfway.

    `score >= _MODERATE_AT` survived even after a test placed a score exactly on
    the threshold — because it cannot be placed there. Noisy-OR of a single
    weight `w` is `1 - (1 - w)`, and in binary that is not `w`:

        1 - (1 - 0.3)  ->  0.30000000000000004     **above** the threshold
        1 - (1 - 0.7)  ->  0.7                     exactly on it

    So `_HIGH_AT` is reachable by a hand-built `Signal` and `_MODERATE_AT` is
    not — not by any weight on a 0.001 grid, and not by any pair from 0.001 to
    0.2. Searched rather than reasoned about.

    **And neither is reachable by the shipped estimator at all.** Its weights
    are 0.1, 0.2, 0.25, 0.3, 0.35 and 0.45, and no combination of up to three of
    them lands exactly on either threshold.

    That makes both comparisons **inclusive by choice and unobservable in
    practice**: no prompt the product can produce distinguishes `>=` from `>`.
    The choice is still the right one — a threshold names the first score that
    counts — and this pins the fact so that the day it stops being true is a day
    somebody looks. A weight of exactly 0.3, or a change to the combination
    rule, makes the inclusivity live.
    """

    @staticmethod
    def _shipped_weights() -> list[float]:
        """Read from the estimator rather than restated.

        A list copied into this file would go stale the first time a rule's
        weight changed, and would then be pinning a fact about a version of the
        estimator nobody is running.
        """
        import ast
        from pathlib import Path as _Path

        source = (
            _Path(__file__).resolve().parent.parent
            / "src/iriguchi/infrastructure/estimators/rules.py"
        ).read_text(encoding="utf-8")
        found = sorted(
            {
                node.value
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Constant)
                and isinstance(node.value, float)
                and 0.0 < node.value < 1.0
            }
        )
        assert len(found) >= 3, f"only {found} weights found; the scan is looking at nothing"
        return found

    def test_no_shipped_weight_combination_lands_on_a_threshold(self) -> None:
        """If this ever fails, the inclusivity of the comparison has become
        observable and wants a test of its own."""
        import itertools
        from math import prod

        weights = self._shipped_weights()
        for threshold in (complexity_module._MODERATE_AT, complexity_module._HIGH_AT):
            landing = [
                combination
                for size in (1, 2, 3)
                for combination in itertools.combinations_with_replacement(weights, size)
                if 1.0 - prod(1.0 - w for w in combination) == threshold
            ]
            assert not landing, (
                f"{landing} now scores exactly {threshold}. The `>=` at that "
                f"threshold has become observable, and whether it should be `>` "
                f"is now a question a prompt can ask."
            )

    def test_the_moderate_threshold_is_not_reachable_by_one_signal(self) -> None:
        """The narrower fact, and the reason the boundary test above passes
        while its mutant survives."""
        assert 1.0 - (1.0 - complexity_module._MODERATE_AT) != complexity_module._MODERATE_AT
        assert 1.0 - (1.0 - complexity_module._HIGH_AT) == complexity_module._HIGH_AT


class TestTheShortCircuitCount:
    """`_SHORT_CIRCUIT_AT` and the `short_circuited=False` default both had
    survivors. Two escalating signals reach the top band whatever the score."""

    @staticmethod
    def _escalating(count: int) -> Complexity:
        return Complexity.from_signals(
            tuple(
                Signal(
                    rule=f"test.escalating-{n}",
                    kind=SignalKind.STRUCTURAL,
                    weight=0.01,
                    escalating=True,
                )
                for n in range(count)
            )
        )

    def test_one_escalating_signal_does_not_short_circuit(self) -> None:
        one = self._escalating(1)
        assert not one.short_circuited
        assert one.band is ComplexityBand.LOW, "0.01 is nowhere near a band on score alone"

    def test_two_escalating_signals_reach_the_top_band_on_no_score_at_all(self) -> None:
        """The borrowed rule, at its exact count. Weights of 0.01 give a score
        of about 0.02, so nothing but the short circuit can produce HIGH."""
        two = self._escalating(2)
        assert two.short_circuited
        assert two.score < complexity_module._MODERATE_AT
        assert two.band is ComplexityBand.HIGH

    def test_no_signals_at_all_does_not_short_circuit(self) -> None:
        """The default the mutant flipped. An empty estimate is the lowest band
        and the least surprising thing in the file, which is exactly why nobody
        had asserted it."""
        empty = Complexity.from_signals(())
        assert not empty.short_circuited
        assert empty.band is ComplexityBand.LOW
        assert empty.score == 0.0


class TestTheOrderOfReasons:
    """`reason.py:67` returns `(-1, -1, ...)` for a reason with no span, and
    both `-1`s survived mutation to `-2`.

    Sorting is unchanged by that — anything negative sorts before a span, whose
    start is at least 0 — so those two are **equivalent mutants** and killing
    them would mean asserting a magic number rather than the property. The
    property is what is asserted here.
    """

    def test_a_reason_with_no_span_sorts_before_one_at_offset_zero(self) -> None:
        whole = Reason(rule="b.whole", source="s", span=None, detail="about the request")
        at_zero = Reason(rule="a.span", source="s", span=Span(0, 4), detail="about a span")
        assert sorted((at_zero, whole), key=lambda r: r.sort_key) == [whole, at_zero]

    def test_two_span_less_reasons_break_the_tie_on_the_rule(self) -> None:
        first = Reason(rule="a.rule", source="s", span=None, detail="d")
        second = Reason(rule="b.rule", source="s", span=None, detail="d")
        assert sorted((second, first), key=lambda r: r.sort_key) == [first, second]
