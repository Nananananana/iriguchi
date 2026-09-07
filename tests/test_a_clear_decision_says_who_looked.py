"""`findings: []` was two different sentences rendered identically.

Sora walked the `--findings` path on a real machine and diffed what came back:

    $ echo "my card number is 4111 1111 1111 1111" | iriguchi --external route --json -
    $ ...  | iriguchi --external route --json --findings empty.json -

**Byte for byte the same document.** Both said:

    "sensitivity": {"level": "clear", "findings": []}

One of those means *the caller's analyzer looked and found nothing*. The other
means *this build's scanner looked and found nothing*, and this build's scanner
publishes a 61.7% miss rate against its own corpus. Sora's sentence for why that
matters is better than any written here: **without saying who looked, the weaker
claim wears the face of the stronger one.**

iriguchi had already insisted on this distinction in the other direction. Its
own reply to Sora said `--findings []` means *my analyzer found nothing*, not
*scan for me*, and that collapsing them turns a clean bill of health into a
request for a second opinion. Then it published a document that collapsed them.

## Why this is a reason and not a new field

`sensitivity.scanned_by` was what Sora asked for, and it would have needed
`routing-decision/2`: every object in that schema is `additionalProperties:
false`, and ADR-0016 wrote the rule down in advance -- *every field this schema
does not have is a field iriguchi cannot add without a v2*.

`reasons[]` is the extension point the design already has. `rule` and `source`
are open strings in the frozen schema, the set of rule ids is governed by
`iriguchi.rules/1-draft` which is a draft precisely so it can grow, and Sora
already runs their own vocabulary against `rules --json` in CI. So a new rule
costs a catalogue entry and breaks nobody, and ADR-0006 already says a decision
carries its reasons to the end.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from iriguchi.application.routing import PromptRouter
from iriguchi.domain.destination import Destination
from iriguchi.domain.sensitivity import Finding
from iriguchi.domain.span import Span
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.infrastructure.scanners.fallback import FallbackScanner
from iriguchi.infrastructure.scanners.supplied import SuppliedScanner
from iriguchi.interfaces.cli.main import EXIT_OK, main
from iriguchi.interfaces.contract import as_document
from iriguchi.interfaces.rules import RULES

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})

#: The number Sora used, kept for the record: the test card the whole industry
#: shares, invented in the sense that matters -- it belongs to nobody.
#:
#: **It is no longer a prompt the built-in scanner misses.** Sora's report had
#: two halves, and fixing the second one invalidated this fixture:
#: `fallback.long-digit-run` was `[0-9]{8,}` with no separators, so it caught
#: `4111111111111111` and missed the form everybody writes. It catches both now,
#: which is why the fixture below had to change and why this comment stays.
CARD = "my card number is 4111 1111 1111 1111"

#: A prompt the built-in scanner still misses, drawn from what it says about
#: itself: *it does not find names without an honorific*. That documented gap
#: is what makes `findings: []` from this scanner a weaker claim than
#: `findings: []` from somebody else's, which is this whole file's subject.
MISSED = "ask Katherine Whitfield whether the contract was signed"


def _document(scanner: Any, text: str = MISSED) -> dict[str, Any]:
    decision = PromptRouter(scanner=scanner, estimator=RulesEstimator()).route(text, BOTH)
    return as_document(decision)


def _rules_of(document: dict[str, Any]) -> list[str]:
    return [reason["rule"] for reason in document["reasons"]]


class TestTheTwoDocumentsAreNoLongerTheSame:
    def test_the_built_in_scan_says_it_looked(self) -> None:
        assert "scan.by-the-router" in _rules_of(_document(FallbackScanner()))

    def test_supplied_findings_say_the_caller_looked(self) -> None:
        assert "scan.by-the-caller" in _rules_of(_document(SuppliedScanner()))

    def test_and_they_differ(self) -> None:
        """The whole report, restated as the assertion Sora's diff would make."""
        ours = json.dumps(_document(FallbackScanner()), ensure_ascii=False)
        theirs = json.dumps(_document(SuppliedScanner()), ensure_ascii=False)
        assert ours != theirs

    def test_the_router_names_which_scanner_looked(self) -> None:
        """*Somebody here looked* is not enough on its own. Sora's screen wants
        to attach the published miss rate, and it can only do that if it knows
        which scanner -- and a future build might configure a different one."""
        [reason] = [
            r for r in _document(FallbackScanner())["reasons"] if r["rule"].startswith("scan.")
        ]
        assert "fallback" in reason["detail"]

    def test_the_caller_reason_names_no_scanner(self) -> None:
        """There is nothing here to name. iriguchi did not look, and inventing
        a scanner name for a scan that did not happen is the failure this whole
        change exists to end."""
        [reason] = [
            r for r in _document(SuppliedScanner())["reasons"] if r["rule"].startswith("scan.")
        ]
        assert "supplied" not in reason["detail"]


class TestItOnlySpeaksWhenTheSetIsEmpty:
    """When findings exist, each one carries its own `source` and the document
    already says who found it. The gap was only ever the empty set, which is
    where absence of evidence gets reported as evidence of absence."""

    #: Span(18, 37) is the card itself, checked against `len(CARD)` rather than
    #: eyeballed -- the first version used 19-38, which runs one past the end,
    #: and `SuppliedScanner` correctly refused the whole batch. That refusal is
    #: the defect fixed earlier this week, catching a fixture written here.
    FOUND = (Finding("presidio.credit_card", "presidio", Span(18, 37)),)

    def test_no_scan_reason_when_the_caller_supplied_findings(self) -> None:
        document = _document(SuppliedScanner(self.FOUND))
        assert not [r for r in _rules_of(document) if r.startswith("scan.")]
        assert document["sensitivity"]["findings"][0]["source"] == "presidio"

    def test_no_scan_reason_when_the_built_in_scanner_finds_something(self) -> None:
        document = _document(FallbackScanner(), "email tanaka@example.com about it")
        assert not [r for r in _rules_of(document) if r.startswith("scan.")]
        assert document["sensitivity"]["findings"]

    def test_a_broken_scanner_says_neither(self) -> None:
        """ADR-0002 already answers this case with `routing.scanner-failed`, and
        a decision claiming somebody looked when the look failed would be the
        same defect one door along."""
        from iriguchi.errors import ScanError

        class _Broken:
            name = "broken"

            def scan(self, text: str) -> list[Finding]:
                raise ScanError("nope")

        rules = _rules_of(_document(_Broken()))
        assert "routing.scanner-failed" in rules
        assert not [r for r in rules if r.startswith("scan.")]


class TestTheFrozenContractIsUntouched:
    def test_the_document_still_validates(self) -> None:
        """The reason this is a reason. Adding `sensitivity.scanned_by` would
        have needed a v2 -- every object in that schema is closed."""
        from jsonschema import Draft202012Validator

        from iriguchi.interfaces.contract import schema

        validator = Draft202012Validator(schema())
        for scanner in (FallbackScanner(), SuppliedScanner()):
            validator.validate(_document(scanner))

    def test_sensitivity_gained_no_field(self) -> None:
        assert set(_document(FallbackScanner())["sensitivity"]) == {"level", "findings"}

    def test_the_contract_version_did_not_move(self) -> None:
        assert _document(FallbackScanner())["contract"] == "iriguchi.routing-decision/1"


class TestSoraCanTranslateIt:
    """Their acceptance condition for the rules catalogue, applied to the two
    new ids: a rule that reaches a decision and is not in `rules --json` shows
    up on a Japanese reader's screen in raw ASCII."""

    @pytest.mark.parametrize("rule", ["scan.by-the-caller", "scan.by-the-router"])
    def test_it_is_in_the_catalogue(self, rule: str) -> None:
        assert rule in {entry[0] for entry in RULES}

    @pytest.mark.parametrize("rule", ["scan.by-the-caller", "scan.by-the-router"])
    def test_it_carries_both_sentences(self, rule: str) -> None:
        [entry] = [e for e in RULES if e[0] == rule]
        assert entry[2].strip() and entry[3].strip()
        assert entry[2] != entry[3]

    def test_the_command_publishes_them(self) -> None:
        out = io.StringIO()
        assert main(["rules"], out=out) == EXIT_OK
        published = {entry["rule"] for entry in json.loads(out.getvalue())["rules"]}
        assert {"scan.by-the-caller", "scan.by-the-router"} <= published


class TestThroughTheCommandSoraActuallyRuns:
    def _run(self, argv: list[str], stdin: bytes) -> dict[str, Any]:
        import sys

        class _Stdin(io.TextIOWrapper):
            def __init__(self, data: bytes) -> None:
                super().__init__(io.BytesIO(data), encoding="utf-8")

        monkey = pytest.MonkeyPatch()
        try:
            monkey.setenv("IRIGUCHI_EXTERNAL", "1")
            monkey.delenv("IRIGUCHI_LOCAL", raising=False)
            monkey.setattr(sys, "stdin", _Stdin(stdin))
            out = io.StringIO()
            assert main(argv, out=out) == EXIT_OK
            return json.loads(out.getvalue())  # type: ignore[no-any-return]
        finally:
            monkey.undo()

    def test_the_exact_pair_sora_diffed(self, tmp_path: Path) -> None:
        """Their two commands, run here, asserting the thing their diff showed
        is no longer true."""
        empty = tmp_path / "empty.json"
        empty.write_text("[]", encoding="utf-8")
        ours = self._run(["route", "--json", "-"], MISSED.encode())
        theirs = self._run(["route", "--json", "--findings", str(empty), "-"], CARD.encode())
        assert ours != theirs
        assert "scan.by-the-router" in _rules_of(ours)
        assert "scan.by-the-caller" in _rules_of(theirs)

    def test_neither_carries_any_of_the_prompt(self, tmp_path: Path) -> None:
        """ADR-0006 is not relaxed by a reason that talks about scanning. The
        new details name a scanner and nothing else."""
        empty = tmp_path / "empty.json"
        empty.write_text("[]", encoding="utf-8")
        for argv in (["route", "--json", "-"], ["route", "--json", "--findings", str(empty), "-"]):
            rendered = json.dumps(self._run(argv, MISSED.encode()), ensure_ascii=False)
            # Fragments distinctive to the prompt. The first draft swept for
            # "contract" and matched the document's own `"contract"` field --
            # a leak sweep that fires on the schema is a sweep that gets
            # relaxed, and a relaxed sweep is the one that misses a real leak.
            assert "Katherine" not in rendered
            assert "Whitfield" not in rendered
            assert "was signed" not in rendered
