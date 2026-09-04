"""Speaking Presidio's vocabulary without importing Presidio.

mamori built theirs first and handed over the three rules, which are here as
tests rather than as prose:

    do not inherit their types      or the install comes back
    accept dicts as well as objects  a JSON fixture is what people hold
    swallow keywords you ignore      the constructor is the hardest line to change

And the fourth, which is not about convenience and is the one that bites:

    **the most dangerous field is not the one you cannot fill.
      It is the one you filled with something it does not mean.**

Presidio's `RecognizerResult.score` is a confidence. iriguchi has none, on
purpose. So the score is discarded coming in and stated as invented going out,
and both directions are asserted below -- because the tempting version of this
module stores the incoming number "in case somebody wants it" and then has to
decide what it means.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from iriguchi import route
from iriguchi.domain.sensitivity import Finding
from iriguchi.domain.span import Span
from iriguchi.interop import RecognizerResult, findings_from_presidio, to_presidio
from iriguchi.interop.presidio import SOURCE, InteropError


@dataclass
class _TheirResult:
    """Something shaped like Presidio's, from a library iriguchi cannot import."""

    entity_type: str
    start: int
    end: int
    score: float = 0.85


class TestItDoesNotNeedPresidio:
    def test_nothing_here_imports_it(self) -> None:
        """The whole point. A module that imports the library it is compatible
        with is not compatibility, it is a dependency with extra steps."""
        import ast
        from pathlib import Path

        source = Path(
            str(__import__("iriguchi.interop.presidio", fromlist=["presidio"]).__file__)
        ).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "presidio_analyzer" not in imported
        assert not any(name.startswith("presidio") for name in imported)

    def test_the_result_type_is_not_a_subclass_of_anything_foreign(self) -> None:
        """Subclassing would require the install. Same attributes is enough for
        anything that reads them, which is what consumers of this shape do."""
        assert RecognizerResult.__mro__[1] is object
        result = RecognizerResult(entity_type="PERSON", start=0, end=4)
        for attribute in ("entity_type", "start", "end", "score", "recognition_metadata"):
            assert hasattr(result, attribute)


class TestWhatItAccepts:
    @pytest.mark.parametrize(
        "results",
        [
            [{"entity_type": "PERSON", "start": 0, "end": 4, "score": 0.85}],
            [_TheirResult("PERSON", 0, 4)],
            [RecognizerResult(entity_type="PERSON", start=0, end=4)],
        ],
        ids=["a dict from to_dict()", "their object", "ours"],
    )
    def test_a_dict_and_an_object_are_both_read(self, results: list[Any]) -> None:
        """A fixture loaded from JSON is the commonest thing anybody holds, and
        demanding a class puts an install back in the way."""
        findings = findings_from_presidio(results)
        assert [f.rule for f in findings] == ["presidio.person"]
        assert findings[0].span == Span(0, 4)

    def test_an_empty_batch_is_an_empty_result_and_not_an_error(self) -> None:
        """An analyzer that found nothing is a normal outcome, and the caller
        should not have to special-case it before asking."""
        assert findings_from_presidio([]) == ()

    def test_the_source_says_it_came_from_elsewhere(self) -> None:
        """Not `fallback` and not `mamori`. A person reading an explanation
        needs to know the veto came from a scanner iriguchi cannot answer
        questions about."""
        assert findings_from_presidio([_TheirResult("PERSON", 0, 4)])[0].source == SOURCE


class TestWhatItRefuses:
    @pytest.mark.parametrize(
        "bad",
        [
            {"entity_type": "PERSON", "start": 0},
            {"start": 0, "end": 4},
            object(),
            {"entity_type": "PERSON", "start": "zero", "end": 4},
        ],
        ids=["no end", "no entity_type", "not a result at all", "offsets that are not numbers"],
    )
    def test_a_malformed_result_is_refused_and_named(self, bad: object) -> None:
        """Refused per item, with its index. **A batch that silently drops the
        malformed half is a batch whose veto is quietly weaker than it looks**,
        and quiet weakening is the failure this whole project is against."""
        with pytest.raises(InteropError, match="result 0"):
            findings_from_presidio([bad])

    def test_one_bad_result_does_not_pass_the_good_ones_through(self) -> None:
        """All or nothing. Returning the readable half would give a caller a
        veto built on part of their analyzer's output, with nothing saying so."""
        good = {"entity_type": "PERSON", "start": 0, "end": 4}
        with pytest.raises(InteropError, match="result 1"):
            findings_from_presidio([good, {"entity_type": "X"}])


class TestTheScoreIsNotCarriedEitherWay:
    """The trap mamori named, in both directions."""

    def test_an_incoming_score_is_discarded(self) -> None:
        """Storing it would mean either ignoring a field -- filled with
        something it does not mean -- or growing a threshold, which is the score
        this project refuses to have. A veto has no degrees."""
        findings = findings_from_presidio([_TheirResult("PERSON", 0, 4, score=0.4)])
        assert not hasattr(findings[0], "score")
        assert "0.4" not in repr(findings[0])

    def test_a_low_confidence_result_vetoes_exactly_as_hard_as_a_high_one(self) -> None:
        """The consequence, stated as behaviour. Somebody who wants to act on
        Presidio's confidence filters **before** calling this, where the number
        came from and where it means what they think."""
        weak = route(
            "Prove the lemma, step by step.",
            findings=findings_from_presidio([_TheirResult("PERSON", 0, 4, score=0.01)]),
            local=True,
            external=True,
        )
        strong = route(
            "Prove the lemma, step by step.",
            findings=findings_from_presidio([_TheirResult("PERSON", 0, 4, score=1.0)]),
            local=True,
            external=True,
        )
        assert weak.route is strong.route
        assert not weak.leaves_the_machine

    def test_the_outgoing_score_is_one(self) -> None:
        """1.0 rather than omitted, because every consumer of this shape
        requires the field and a `None` breaks arithmetic downstream."""
        [result] = to_presidio([Finding(rule="fallback.email", source="fallback", span=Span(0, 4))])
        assert result.score == 1.0

    def test_every_outgoing_score_is_the_same_number(self) -> None:
        """The behavioural version, after two attempts at grepping my own prose.

        A varying score would mean iriguchi had started computing a confidence.
        A constant one means the field is a placeholder the shape requires, and
        **that is checkable without reading English.**

        The two attempts are worth recording. The first asserted a phrase the
        source comment wraps across two lines. The second normalised whitespace
        and still failed, because **normalising whitespace does not remove
        structure**: the `#:` comment markers survived the join and landed in
        the middle of the phrase. A check keyed on the shape of reflowed prose
        is a check about formatting, and the version before both of those ended
        in `or True`.
        """
        findings = [
            Finding(rule=f"fallback.rule-{n}", source="fallback", span=Span(n, n + 2))
            for n in range(5)
        ]
        assert {result.score for result in to_presidio(findings)} == {1.0}

    def test_the_result_carries_no_second_field_that_reads_as_certainty(self) -> None:
        """One placeholder is a stated compromise. A `confidence` beside it
        would be the field filled with something it does not mean."""
        names = set(RecognizerResult.__dataclass_fields__)
        assert names == {"entity_type", "start", "end", "score", "recognition_metadata"}


class TestGoingOut:
    def test_the_rule_becomes_an_entity_type_and_keeps_its_original(self) -> None:
        """A rename, not a translation. iriguchi's rules and Presidio's entity
        vocabulary are different lists, so the original travels in the metadata
        rather than being lost to a lossy mapping."""
        [result] = to_presidio(
            [Finding(rule="fallback.japanese-honorific", source="fallback", span=Span(2, 6))]
        )
        assert result.entity_type == "JAPANESE_HONORIFIC"
        assert result.recognition_metadata["iriguchi_rule"] == "fallback.japanese-honorific"
        assert result.recognition_metadata["iriguchi_source"] == "fallback"

    def test_a_rule_with_no_dot_keeps_its_whole_name(self) -> None:
        """Rather than becoming an empty entity type. A rule id nobody
        namespaced is unusual and silently emitting `""` would be worse."""
        [result] = to_presidio([Finding(rule="something", source="s", span=Span(0, 1))])
        assert result.entity_type == "SOMETHING"

    def test_the_round_trip_keeps_the_offsets(self) -> None:
        original = findings_from_presidio([{"entity_type": "PERSON", "start": 3, "end": 7}])
        [back] = to_presidio(original)
        assert (back.start, back.end) == (3, 7)
        assert back.entity_type == "PERSON"


class TestTheScannerThatScansNothing:
    """`SuppliedScanner` is the one scanner that is not a function of the text.

    Worth its own tests rather than only being exercised through `route`,
    because the thing that makes it useful -- ignoring the prompt -- is also the
    thing that would make a bug in it invisible.
    """

    @staticmethod
    def _scanner(*findings: Finding) -> object:
        from iriguchi.infrastructure.scanners.supplied import SuppliedScanner

        return SuppliedScanner(findings)

    def test_it_returns_what_it_was_given(self) -> None:
        found = Finding(rule="presidio.person", source="presidio", span=Span(0, 4))
        assert self._scanner(found).scan("any text at all") == (found,)  # type: ignore[attr-defined]

    def test_the_text_makes_no_difference(self) -> None:
        """The property that defines it. If a future version started reading the
        prompt, this is what would notice."""
        found = Finding(rule="presidio.person", source="presidio", span=Span(0, 4))
        scanner = self._scanner(found)
        assert scanner.scan("") == scanner.scan("田中太郎 tanaka@example.com")  # type: ignore[attr-defined]

    def test_it_names_itself_for_what_it_is(self) -> None:
        """`supplied`, not `presidio`. A caller mixing two analyzers would
        otherwise get one name covering both, and the per-finding `source` is
        where that detail belongs."""
        assert self._scanner().name == "supplied"  # type: ignore[attr-defined]

    def test_it_satisfies_the_port(self) -> None:
        from iriguchi.ports.scanner import SensitivityScanner

        assert isinstance(self._scanner(), SensitivityScanner)

    def test_it_is_not_in_the_registry(self) -> None:
        """Selectable by name would be wrong: it needs its findings passed in,
        and a name somebody could choose that then reports nothing is a scanner
        that silently disables the veto."""
        from iriguchi.infrastructure.registry import SCANNERS

        assert "supplied" not in SCANNERS


class TestThroughTheFrontDoor:
    def test_foreign_findings_reach_the_veto(self) -> None:
        decision = route(
            "Prove the lemma, step by step, comparing both approaches.",
            findings=findings_from_presidio([{"entity_type": "PERSON", "start": 0, "end": 5}]),
            local=True,
            external=True,
        )
        assert not decision.leaves_the_machine
        assert [r.destination.value for r in decision.removed] == ["external"]

    def test_no_findings_at_all_still_routes(self) -> None:
        """An empty list is *this analyzer found nothing*, not *do not scan*.
        The prompt still gets a complexity band and a route."""
        decision = route(
            "Prove the lemma, step by step, comparing both approaches.",
            findings=[],
            local=True,
            external=True,
        )
        assert decision.leaves_the_machine

    def test_supplying_findings_and_naming_a_scanner_is_refused(self) -> None:
        """Two intentions and no way to tell which. Guessing here would decide
        what leaves the machine on a coin toss."""
        from iriguchi.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="Pick the one you meant"):
            route("hello", findings=[], scanner="fallback", local=True)

    def test_the_explanation_names_the_scanner_it_cannot_answer_for(self) -> None:
        decision = route(
            "hello",
            findings=findings_from_presidio([{"entity_type": "PERSON", "start": 0, "end": 5}]),
            local=True,
            external=True,
        )
        assert any(SOURCE in reason.detail for reason in decision.reasons) or any(
            f.source == SOURCE for f in decision.sensitivity.findings
        )
