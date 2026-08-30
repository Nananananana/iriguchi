"""Conformance suites for the ports.

Subclass the mixin for the port you implemented, supply the factory, and you
inherit the contract:

    class TestMyScanner(SensitivityScannerContract):
        def make_scanner(self) -> SensitivityScanner:
            return MyScanner()

mamori's pattern, and the reason for it is that the clauses below are the ones
adapters get wrong. They are not a restatement of the protocol; they are a list
of mistakes, each of which somebody has made.

The one worth reading before writing an adapter is
``test_offsets_are_into_the_text_as_given``. Any scanner good enough to be worth
having will normalize before it matches -- `ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ` and
`tanaka@example.com` are the same address -- and a span into the normalized text
points at the wrong characters in the original. It is silent, it only shows up
in an explanation nobody checks, and it is the first thing this suite looks for.

Not a test file. There is no `test_` prefix on the module name, so pytest
collects it only through the subclasses that import it.
"""

from __future__ import annotations

import unicodedata
from abc import ABC, abstractmethod

import pytest

from iriguchi.domain.complexity import Complexity, ComplexityBand, Signal
from iriguchi.domain.sensitivity import Finding
from iriguchi.ports.estimator import ComplexityEstimator
from iriguchi.ports.scanner import SensitivityScanner

#: Inputs every implementation has to survive. The interesting half is not the
#: sensitive-looking text -- it is the empty string, the whitespace, and the
#: scripts where a naive offset goes wrong.
SAMPLE_TEXTS: tuple[str, ...] = (
    "",
    "   ",
    "\n\n\t",
    "hello",
    "Contact tanaka@example.com by Friday.",
    "田中さんに連絡してください。メールは tanaka@example.com です。",
    # Full-width. NFKC folds this to the ASCII form above, so a scanner that
    # matches on normalized text and forgets to map back reports a span that is
    # the right length and the wrong place.
    "ｔａｎａｋａ＠ｅｘａｍｐｌｅ．ｃｏｍ にご連絡ください",
    # NFKC *contracts* this one: `e` + U+0301 (five characters) composes to
    # `café` (four). Written as an escape rather than a literal because the two
    # forms are indistinguishable on screen, and an editor that helpfully
    # normalized this file would silently delete the case.
    "cafe\u0301 の請求書を確認して",
    # NFKC *expands* these: one character becomes three or four. This is the
    # direction a bounds check can catch, because a span into the normalized
    # text runs off the end of the original.
    "㍿の請求書を確認して",
    "Ⅻ章を要約して",
    # A long paste, which is where estimators start behaving differently.
    "summarise this log:\n" + ("2026-08-30 INFO request handled ok\n" * 60),
    # An emoji outside the BMP, for anything counting UTF-16 units by accident.
    "この記事を要約して 🗾 ありがとう",
)


class _PortContract(ABC):
    """Shared clauses. Both ports promise determinism and self-identification."""

    @abstractmethod
    def subject(self) -> SensitivityScanner | ComplexityEstimator:
        """The implementation under test."""

    @abstractmethod
    def call(self, text: str) -> tuple[object, ...]:
        """Run it and return what it produced, as a tuple."""

    def test_it_names_itself(self) -> None:
        name = self.subject().name
        assert name, "an implementation with no name cannot appear in an explanation"
        assert name == name.strip()

    @property
    @abstractmethod
    def element_type(self) -> type:
        """What a conforming call returns a sequence of."""

    @pytest.mark.parametrize("text", SAMPLE_TEXTS, ids=lambda t: repr(t[:24]))
    def test_it_answers_rather_than_raising(self, text: str) -> None:
        """Empty, whitespace, CJK, emoji and a long paste are all answerable.

        Reaching the assertion at all is most of the test. The assertion itself
        catches the implementation that returns something iterable but wrong --
        a list of tuples, a generator of strings -- which fails much later and
        much less legibly if nothing looks here.
        """
        produced = self.call(text)
        assert all(isinstance(item, self.element_type) for item in produced), (
            f"expected {self.element_type.__name__} values, got "
            f"{sorted({type(i).__name__ for i in produced})}"
        )

    @pytest.mark.parametrize("text", SAMPLE_TEXTS, ids=lambda t: repr(t[:24]))
    def test_the_same_text_twice_gives_identical_output(self, text: str) -> None:
        """Including the order. AGENTS.md's ordering discipline, pushed out to
        the adapters, because an unordered set reaching an output is how a
        reproducible build stops being one."""
        subject = self.subject()
        first, second = self.call(text), self.call(text)
        assert first == second
        assert repr(first) == repr(second)
        assert subject.name == self.subject().name

    @pytest.mark.parametrize("text", SAMPLE_TEXTS, ids=lambda t: repr(t[:24]))
    def test_offsets_are_into_the_text_as_given(self, text: str) -> None:
        """The clause adapters actually get wrong.

        A scanner that matches against NFKC-normalized text and returns spans
        into *that* is reporting positions in a string the caller never saw.

        **What this catches, and what it does not.** It is a bounds check, so it
        catches normalization that *expands* -- `㍿` becomes four characters, so
        a normalized offset runs off the end of the original and the assertion
        fires. It cannot catch normalization that *contracts*: `cafe` plus a
        combining acute is five characters and normalizes to four, so a span
        into the normalized text is wrong and still comfortably in bounds.

        There is no generic clause that catches contraction, because this suite
        does not know what the scanner meant to point at. Both directions are in
        `SAMPLE_TEXTS` anyway -- the contracting one because an adapter's own
        tests should assert on the *value* under its spans, and having the input
        already here is most of that work.
        """
        normalized = unicodedata.normalize("NFKC", text)
        for span in self.spans_of(self.call(text)):
            assert 0 <= span.start <= span.end <= len(text), (
                f"span {span} is outside the {len(text)}-character text it was scanned "
                f"from. If this implementation works on normalized text "
                f"({len(normalized)} characters here), it has to map back before it "
                f"reports."
            )

    @staticmethod
    def spans_of(produced: tuple[object, ...]) -> list:  # type: ignore[type-arg]
        raise NotImplementedError


class SensitivityScannerContract(_PortContract):
    """What every `SensitivityScanner` promises."""

    @abstractmethod
    def make_scanner(self) -> SensitivityScanner:
        """A fresh scanner. Called per test: a scanner that only conforms on
        its first use is not conforming."""

    element_type = Finding

    def subject(self) -> SensitivityScanner:
        return self.make_scanner()

    def call(self, text: str) -> tuple[Finding, ...]:
        return tuple(self.make_scanner().scan(text))

    @staticmethod
    def spans_of(produced: tuple[object, ...]) -> list:  # type: ignore[type-arg]
        return [f.span for f in produced if isinstance(f, Finding)]

    def test_it_is_a_scanner(self) -> None:
        assert isinstance(self.make_scanner(), SensitivityScanner)

    @pytest.mark.parametrize("text", SAMPLE_TEXTS, ids=lambda t: repr(t[:24]))
    def test_every_finding_carries_the_scanner_name(self, text: str) -> None:
        """So an explanation can say which scanner to trust how much.

        The fallback is expected to be wrong sometimes and mamori much less so.
        A finding that does not say which it came from makes that distinction
        unavailable to the person reading it.
        """
        scanner = self.make_scanner()
        for finding in scanner.scan(text):
            assert finding.source == scanner.name

    @pytest.mark.parametrize("text", SAMPLE_TEXTS, ids=lambda t: repr(t[:24]))
    def test_every_finding_names_a_namespaced_rule(self, text: str) -> None:
        """An id is what lets somebody disable one rule without disabling the
        scanner, so it has to be specific enough to name one thing."""
        for finding in self.make_scanner().scan(text):
            assert "." in finding.rule, (
                f"rule {finding.rule!r} is not namespaced. Use `scanner.what-it-found`, "
                "so that turning it off does not turn off something else."
            )

    def test_empty_text_finds_nothing(self) -> None:
        assert not self.make_scanner().scan("")


class ComplexityEstimatorContract(_PortContract):
    """What every `ComplexityEstimator` promises."""

    @abstractmethod
    def make_estimator(self) -> ComplexityEstimator:
        """A fresh estimator. Called per test."""

    element_type = Signal

    def subject(self) -> ComplexityEstimator:
        return self.make_estimator()

    def call(self, text: str) -> tuple[Signal, ...]:
        return tuple(self.make_estimator().estimate(text))

    @staticmethod
    def spans_of(produced: tuple[object, ...]) -> list:  # type: ignore[type-arg]
        return [s.span for s in produced if isinstance(s, Signal) and s.span is not None]

    def test_it_is_an_estimator(self) -> None:
        assert isinstance(self.make_estimator(), ComplexityEstimator)

    @pytest.mark.parametrize("text", SAMPLE_TEXTS, ids=lambda t: repr(t[:24]))
    def test_every_signal_names_a_namespaced_rule(self, text: str) -> None:
        for signal in self.make_estimator().estimate(text):
            assert "." in signal.rule

    @pytest.mark.parametrize("text", SAMPLE_TEXTS, ids=lambda t: repr(t[:24]))
    def test_no_rule_fires_twice_on_the_same_text(self, text: str) -> None:
        """Two signals from one rule would count the same evidence twice.

        Findings may repeat -- three email addresses are three findings -- but a
        signal is a statement about the request, and "this text is long" is
        either true or it is not.
        """
        rules = [signal.rule for signal in self.make_estimator().estimate(text)]
        duplicates = sorted({rule for rule in rules if rules.count(rule) > 1})
        assert not duplicates, f"{duplicates} fired more than once on one text"

    def test_empty_text_is_not_complicated(self) -> None:
        """Whatever else an estimator does, it must not think nothing is hard.

        Asserted through `Complexity` rather than by demanding no signals, so
        that an estimator is free to report `input-is-empty` as evidence -- as
        long as what that adds up to is the lowest band.
        """
        signals = self.make_estimator().estimate("")
        assert Complexity.from_signals(signals).band is ComplexityBand.LOW
