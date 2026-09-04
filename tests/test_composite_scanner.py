"""Several scanners, one veto.

The composite exists because a measurement contradicted the obvious ranking.
Against the real Presidio, with the model installed:

    "Please summarise the memo that Katherine Whitfield sent."
        presidio  -> presidio.person       fallback -> nothing

    "Acme Corporation の田中さんに連絡してください"
        presidio  -> nothing               fallback -> fallback.japanese-honorific

Neither is a superset of the other, so a user who read *Presidio is better* and
selected it would have made their own detection **worse** in Japanese. The tests
here are about the union being genuinely a union, and about what happens when
one member breaks -- which is the half that decides whether this is safe.
"""

from __future__ import annotations

import pytest

from iriguchi.domain.sensitivity import Finding
from iriguchi.domain.span import Span
from iriguchi.errors import ScanError
from iriguchi.infrastructure.scanners.composite import CompositeScanner
from iriguchi.infrastructure.scanners.fallback import FallbackScanner


class _Stub:
    """A scanner that reports what it was given, or fails."""

    def __init__(self, name: str, findings: tuple[Finding, ...] | Exception) -> None:
        self.name = name
        self._findings = findings
        self.calls: list[str] = []

    def scan(self, text: str) -> tuple[Finding, ...]:
        self.calls.append(text)
        if isinstance(self._findings, Exception):
            raise self._findings
        return self._findings


def _finding(rule: str, source: str, start: int, end: int) -> Finding:
    return Finding(rule=rule, source=source, span=Span(start, end))


class TestTheUnion:
    def test_both_members_findings_come_back(self) -> None:
        english = _finding("presidio.person", "presidio", 31, 50)
        japanese = _finding("fallback.japanese-honorific", "fallback", 2, 6)
        composite = CompositeScanner(
            [_Stub("fallback", (japanese,)), _Stub("presidio", (english,))]
        )
        assert composite.scan("anything") == (japanese, english)

    def test_each_finding_keeps_the_scanner_that_proposed_it(self) -> None:
        """The composite does not put its own name on them. An explanation has
        to say which scanner objected, or a person cannot tell whether to trust
        it -- and one of the members may be somebody else's analyzer."""
        composite = CompositeScanner(
            [
                _Stub("fallback", (_finding("fallback.email-shape", "fallback", 0, 4),)),
                _Stub("presidio", (_finding("presidio.person", "presidio", 8, 11),)),
            ]
        )
        assert {f.source for f in composite.scan("x")} == {"fallback", "presidio"}

    def test_findings_are_ordered_by_offset(self) -> None:
        """Not by member. Two runs must produce the same explanation, and the
        member order is a configuration detail a reader should not have to know
        to compare two decisions."""
        composite = CompositeScanner(
            [
                _Stub("a", (_finding("a.late", "a", 40, 44),)),
                _Stub("b", (_finding("b.early", "b", 2, 6),)),
            ]
        )
        assert [f.span.start for f in composite.scan("x")] == [2, 40]

    def test_the_same_finding_from_two_members_is_one_finding(self) -> None:
        """Identical span and identical rule is one thing found twice. A doubled
        entry in an explanation reads as two separate problems."""
        same = _finding("email", "fallback", 0, 4)
        composite = CompositeScanner([_Stub("a", (same,)), _Stub("b", (same,))])
        assert len(composite.scan("x")) == 1

    def test_two_rules_over_one_span_are_both_kept(self) -> None:
        """Two scanners saying different things about the same stretch of text.
        Collapsing them would discard the more specific one at random."""
        composite = CompositeScanner(
            [
                _Stub("a", (_finding("a.person", "a", 0, 4),)),
                _Stub("b", (_finding("b.name", "b", 0, 4),)),
            ]
        )
        assert len(composite.scan("x")) == 2

    def test_every_member_sees_the_prompt(self) -> None:
        """A composite that short-circuits after the first finding would be
        cheaper and would make the explanation depend on member order."""
        first = _Stub("a", (_finding("a.rule", "a", 0, 4),))
        second = _Stub("b", ())
        CompositeScanner([first, second]).scan("the prompt")
        assert first.calls == second.calls == ["the prompt"]

    def test_it_is_at_least_as_restrictive_as_either_member(self) -> None:
        """The property that makes a composite sound over a veto and unsound
        over a score. Stated as a test because it is the whole argument."""
        alone = FallbackScanner().scan("田中さんに tanaka@example.com で連絡")
        together = CompositeScanner([FallbackScanner(), _Stub("quiet", ())]).scan(
            "田中さんに tanaka@example.com で連絡"
        )
        assert set(alone) <= set(together)
        assert alone, "the fallback found nothing here, so this proves nothing"


class TestWhenAMemberBreaks:
    def test_the_whole_scan_fails(self) -> None:
        """Not skipped, not degraded. iriguchi cannot know what the broken
        member would have found, and reporting the rest would be a veto quietly
        weaker than the one that was asked for."""
        composite = CompositeScanner(
            [
                _Stub("fallback", (_finding("fallback.email-shape", "fallback", 0, 4),)),
                _Stub("presidio", ScanError("spaCy exploded")),
            ]
        )
        with pytest.raises(ScanError, match="spaCy exploded"):
            composite.scan("x")

    def test_the_message_names_which_member(self) -> None:
        """`fallback+presidio failed` sends somebody to read two libraries."""
        composite = CompositeScanner(
            [_Stub("fallback", ()), _Stub("presidio", ScanError("no model"))]
        )
        with pytest.raises(ScanError, match="'presidio' member"):
            composite.scan("x")

    def test_the_good_members_findings_are_not_returned(self) -> None:
        """The tempting version returns what it managed to collect. That is a
        veto missing an unknown part of itself, which is not a weaker veto --
        it is one nobody can reason about."""
        found = _Stub("fallback", (_finding("fallback.email-shape", "fallback", 0, 4),))
        composite = CompositeScanner([found, _Stub("presidio", ScanError("broken"))])
        with pytest.raises(ScanError):
            composite.scan("x")
        assert found.calls, "the working member did run; its findings are dropped on purpose"


class TestItsShape:
    def test_the_name_says_what_is_running(self) -> None:
        """`fallback+presidio`, not `composite`. A person reading `doctor` needs
        to know which detectors are on."""
        assert CompositeScanner([_Stub("fallback", ()), _Stub("presidio", ())]).name == (
            "fallback+presidio"
        )

    def test_the_members_are_readable(self) -> None:
        members = [_Stub("a", ()), _Stub("b", ())]
        assert list(CompositeScanner(members).members) == members

    def test_an_empty_composite_is_refused(self) -> None:
        """It would report no findings, which is indistinguishable from a clean
        prompt -- a veto turned off while wearing a name that reads stronger."""
        with pytest.raises(ValueError, match="at least one member"):
            CompositeScanner([])

    def test_it_satisfies_the_port(self) -> None:
        from iriguchi.ports.scanner import SensitivityScanner

        assert isinstance(CompositeScanner([FallbackScanner()]), SensitivityScanner)

    def test_it_is_registered_under_the_name_it_reports(self) -> None:
        """So `--scanner fallback+presidio` and the name in an explanation are
        the same string. Two spellings of one thing is a support question."""
        from iriguchi.infrastructure.registry import SCANNERS

        assert "fallback+presidio" in SCANNERS
