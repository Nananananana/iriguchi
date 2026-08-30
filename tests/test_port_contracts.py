"""That the conformance suites conform to something, and can fail.

Two halves.

The first runs the suites against deliberately trivial implementations. They are
not adapters and never will be -- a scanner that flags the letter `q` is useless
-- but they exercise every clause, so a suite that has quietly stopped asserting
anything shows up here rather than in the first real adapter's green build.

The second is the half that matters. Each clause is run against an
implementation built to break exactly that clause, and asserted to fail. A
conformance suite nobody has seen fail is a suite that might be checking
nothing, and this is the cheapest way to find out.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

import pytest

from contracts import ComplexityEstimatorContract, SensitivityScannerContract
from iriguchi.domain.complexity import Signal, SignalKind
from iriguchi.domain.sensitivity import Finding
from iriguchi.domain.span import Span
from iriguchi.ports.estimator import ComplexityEstimator
from iriguchi.ports.scanner import SensitivityScanner


class LetterQScanner:
    """Flags every `q`. Conforming, and deliberately absurd.

    Absurd on purpose: a plausible-looking stand-in invites being mistaken for
    the real fallback scanner, and then for being improved rather than deleted.
    """

    name = "letter-q"

    def scan(self, text: str) -> Sequence[Finding]:
        return [
            Finding("letter-q.the-letter-q", self.name, Span(i, i + 1))
            for i, char in enumerate(text)
            if char.lower() == "q"
        ]


class NeverFindsAnythingScanner:
    """The other conforming extreme. Every clause has to hold for it too."""

    name = "never"

    def scan(self, text: str) -> Sequence[Finding]:
        return ()


class LengthEstimator:
    """One signal, on length alone. Conforming, and not the real estimator."""

    name = "length-only"

    def estimate(self, text: str) -> Sequence[Signal]:
        if len(text) < 200:
            return ()
        return [Signal("length-only.long-input", SignalKind.LEXICAL, 0.4)]


class TestLetterQScanner(SensitivityScannerContract):
    def make_scanner(self) -> SensitivityScanner:
        return LetterQScanner()


class TestNeverFindsAnythingScanner(SensitivityScannerContract):
    def make_scanner(self) -> SensitivityScanner:
        return NeverFindsAnythingScanner()


class TestLengthEstimator(ComplexityEstimatorContract):
    def make_estimator(self) -> ComplexityEstimator:
        return LengthEstimator()


# --------------------------------------------------------------------------
# The half that matters: each clause, shown failing.
# --------------------------------------------------------------------------

#: NFKC leaves the length alone: each full-width character folds to exactly
#: one ASCII character.
FULL_WIDTH = "ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ にご連絡ください"
#: NFKC contracts: `e` + U+0301 (five characters) composes to four. An escape
#: on purpose -- the two forms look identical, and this turns on which it is.
COMBINING = "cafe\u0301 の請求書を確認して"
#: NFKC expands: one character becomes four. The only direction a bounds
#: check can catch, because the span then runs off the end of the original.
EXPANDING = "㍿の請求書を確認して"


class NormalizedOffsetScanner:
    """The bug the suite exists to catch.

    Matches against NFKC-normalized text and returns spans into *that*. Every
    span after the first character that normalizes differently points at the
    wrong place, silently, and only ever surfaces in an explanation nobody
    checks.

    This is not a strawman. It is what a scanner does when somebody follows
    mamori's advice to normalize before matching and stops there.
    """

    name = "normalized-offsets"

    def scan(self, text: str) -> Sequence[Finding]:
        normalized = unicodedata.normalize("NFKC", text)
        return [Finding("normalized.whole-text", self.name, Span(0, len(normalized)))]


class MisattributingScanner:
    """Returns findings sourced to somebody else."""

    name = "honest-name"

    def scan(self, text: str) -> Sequence[Finding]:
        return [Finding("honest.rule", "mamori", Span(0, 0))] if text else []


class UnstableScanner:
    """Answers differently each time it is asked."""

    name = "unstable"

    def __init__(self) -> None:
        self._calls = 0

    def scan(self, text: str) -> Sequence[Finding]:
        self._calls += 1
        return [Finding("unstable.call-count", self.name, Span(0, self._calls % 3))]


class UnnamespacedScanner:
    name = "unnamespaced"

    def scan(self, text: str) -> Sequence[Finding]:
        return [Finding("suspicious", self.name, Span(0, 0))] if text else []


class NamelessScanner:
    name = ""

    def scan(self, text: str) -> Sequence[Finding]:
        return ()


class WrongTypeScanner:
    """Returns something iterable, and not findings."""

    name = "wrong-type"

    def scan(self, text: str) -> Sequence[Finding]:
        return ["a finding, honest"]  # type: ignore[list-item]


class RepeatingEstimator:
    """Fires one rule twice, counting the same evidence twice."""

    name = "repeating"

    def estimate(self, text: str) -> Sequence[Signal]:
        return [
            Signal("repeating.long-input", SignalKind.LEXICAL, 0.4),
            Signal("repeating.long-input", SignalKind.LEXICAL, 0.4),
        ]


class AlarmistEstimator:
    """Thinks the empty string is hard."""

    name = "alarmist"

    def estimate(self, text: str) -> Sequence[Signal]:
        return [Signal("alarmist.everything", SignalKind.LEXICAL, 0.99)]


class TestTheScannerSuiteCanFail:
    """Each clause, against something built to break it."""

    def run(self, scanner: object, method: str, *args: object) -> None:
        suite = type(
            "Subject", (SensitivityScannerContract,), {"make_scanner": lambda _: scanner}
        )()
        getattr(suite, method)(*args)

    def test_it_catches_spans_into_normalized_text(self) -> None:
        """The expanding case, which is the one a bounds check can see."""
        with pytest.raises(AssertionError, match="outside the"):
            self.run(
                NormalizedOffsetScanner(), "test_offsets_are_into_the_text_as_given", EXPANDING
            )

    def test_the_other_two_directions_would_not_have_caught_it(self) -> None:
        """Why the clause's docstring states what it misses.

        Full-width folds one character to one, so the lengths match and a
        normalized offset is accidentally correct. A combining acute *contracts*,
        so the offset is wrong and still comfortably inside the original -- a
        bounds check cannot see it, and no generic clause can, because this suite
        does not know what the scanner meant to point at.

        Both are in `SAMPLE_TEXTS` regardless. The contracting one is there so
        that an adapter writing its own test -- one that asserts on the *value*
        under the span, which is the only thing that catches this -- already has
        the input.
        """
        assert len(unicodedata.normalize("NFKC", FULL_WIDTH)) == len(FULL_WIDTH)
        assert len(unicodedata.normalize("NFKC", COMBINING)) < len(COMBINING)
        assert len(unicodedata.normalize("NFKC", EXPANDING)) > len(EXPANDING)

        self.run(NormalizedOffsetScanner(), "test_offsets_are_into_the_text_as_given", FULL_WIDTH)
        self.run(NormalizedOffsetScanner(), "test_offsets_are_into_the_text_as_given", COMBINING)

    def test_it_catches_a_finding_attributed_to_another_scanner(self) -> None:
        with pytest.raises(AssertionError):
            self.run(MisattributingScanner(), "test_every_finding_carries_the_scanner_name", "x")

    def test_it_catches_a_scanner_that_answers_differently_each_time(self) -> None:
        with pytest.raises(AssertionError):
            self.run(UnstableScanner(), "test_the_same_text_twice_gives_identical_output", "x")

    def test_it_catches_a_rule_that_is_not_namespaced(self) -> None:
        with pytest.raises(AssertionError, match="namespaced"):
            self.run(UnnamespacedScanner(), "test_every_finding_names_a_namespaced_rule", "x")

    def test_it_catches_a_scanner_with_no_name(self) -> None:
        with pytest.raises(AssertionError, match="no name"):
            self.run(NamelessScanner(), "test_it_names_itself")

    def test_it_catches_the_wrong_element_type(self) -> None:
        with pytest.raises(AssertionError, match="expected Finding"):
            self.run(WrongTypeScanner(), "test_it_answers_rather_than_raising", "x")


class TestTheEstimatorSuiteCanFail:
    def run(self, estimator: object, method: str, *args: object) -> None:
        suite = type(
            "Subject", (ComplexityEstimatorContract,), {"make_estimator": lambda _: estimator}
        )()
        getattr(suite, method)(*args)

    def test_it_catches_a_rule_firing_twice(self) -> None:
        with pytest.raises(AssertionError, match="more than once"):
            self.run(RepeatingEstimator(), "test_no_rule_fires_twice_on_the_same_text", "x")

    def test_it_catches_an_estimator_that_thinks_nothing_is_hard(self) -> None:
        with pytest.raises(AssertionError):
            self.run(AlarmistEstimator(), "test_empty_text_is_not_complicated")


class TestTheProtocolsAreStructural:
    """Nothing implements these by inheriting them, and nothing should.

    An adapter that had to import the port to satisfy it would be an adapter
    that could not exist in another package, and the whole point of a port is
    that the thing on the other side does not have to know about this one.
    """

    def test_a_class_that_never_heard_of_the_port_satisfies_it(self) -> None:
        assert isinstance(LetterQScanner(), SensitivityScanner)
        assert isinstance(LengthEstimator(), ComplexityEstimator)
        assert SensitivityScanner not in type(LetterQScanner()).__mro__

    def test_something_missing_the_method_does_not(self) -> None:
        class NotAScanner:
            name = "no"

        assert not isinstance(NotAScanner(), SensitivityScanner)
