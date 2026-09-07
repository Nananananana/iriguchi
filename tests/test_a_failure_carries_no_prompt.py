"""A broken proposer becomes a decision. The decision must not become the prompt.

ADR-0002 turns a scanner's failure into the most restrictive route with a reason
naming what broke. ADR-0016 says that decision is publishable **because it holds
no prompt**. Both were true; the join between them was not.

`_scanner_failed` interpolated `str(failure)` into `reasons[].detail`, and that
reason is serialised into `iriguchi.routing-decision/1` -- the document Sora
reads, stores and puts on a screen. So:

    ScanError("regex engine gave up on 'Please email tanaka@example.com ...'")

put the prompt into the published JSON. Measured on the real router before
anything was changed, not argued from the code.

**The guarantee was resting on other people's code.** iriguchi does not write
mamori's exception messages or presidio's, and *could not parse <the input>* is
the most ordinary error message any library writes. `_scanner_failed`'s own
docstring said "it carries the scanner's failure and never the text", which is
the same sentence as the bug once a scanner puts the text in its failure.

The fix is the one iriguchi gave Sora for the same problem in the same week:
**keep the name, discard the sentence.** `errors.safe_detail` quotes a message
only when whoever raised it passed `quotable=True`, which is a claim only the
author of that `raise` is in a position to make.
"""

from __future__ import annotations

import ast
import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

import pytest

from iriguchi.application.routing import PromptRouter
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.sensitivity import Finding
from iriguchi.errors import EstimationError, JudgementError, ScanError, safe_detail
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.infrastructure.scanners.fallback import FallbackScanner
from iriguchi.interfaces.cli.main import main
from iriguchi.interfaces.contract import as_document

SRC = Path(__file__).resolve().parent.parent / "src" / "iriguchi"

#: Invented, and shaped like the thing a person would most regret publishing.
SECRET = "tanaka@example.com"
PROMPT = f"Please email {SECRET} the quarterly figures and prove the bound holds."
BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})


class _Quoting:
    """A scanner that quotes the text it choked on.

    **Not a strawman.** It is what a regex engine, a tokenizer and a JSON
    parser all do by default, and iriguchi writes none of them.
    """

    name = "quoting"

    def scan(self, text: str) -> Sequence[Finding]:
        raise ScanError(f"regex engine gave up on {text!r}")


class _QuotingLoudly:
    """The same, raising something the port never mentions. Adapters do this."""

    name = "loud"

    def scan(self, text: str) -> Sequence[Finding]:
        raise RuntimeError(f"index out of range while reading {text!r}")


class _QuotingEstimator:
    name = "quoting"

    def estimate(self, text: str) -> Sequence[object]:
        raise EstimationError(f"tokenizer failed on {text!r}")


class TestTheDecisionItself:
    @pytest.mark.parametrize(
        "scanner,estimator",
        [
            (_Quoting(), RulesEstimator()),
            (_QuotingLoudly(), RulesEstimator()),
            (FallbackScanner(), _QuotingEstimator()),
        ],
        ids=["scanner-raises-scanerror", "scanner-raises-anything", "estimator-raises"],
    )
    def test_no_part_of_the_prompt_reaches_the_published_document(
        self, scanner: Any, estimator: Any
    ) -> None:
        decision = PromptRouter(scanner=scanner, estimator=estimator).route(PROMPT, BOTH)
        rendered = json.dumps(as_document(decision), ensure_ascii=False)
        assert SECRET not in rendered
        assert "quarterly figures" not in rendered

    def test_and_the_reason_still_says_what_broke(self) -> None:
        """Redaction that leaves nothing behind is not a fix. The component and
        the failure's class both survive, which is what a person needs in order
        to know where to look."""
        decision = PromptRouter(scanner=_Quoting(), estimator=RulesEstimator()).route(PROMPT, BOTH)
        [reason] = [r for r in decision.reasons if r.rule == "routing.scanner-failed"]
        assert "quoting" in reason.detail
        assert "ScanError" in reason.detail

    def test_a_non_conforming_adapter_is_named_by_its_real_class(self) -> None:
        """`RuntimeError`, not `ScanError`. A person told the scanner raised a
        `ScanError` when it raised something else is sent to the wrong place."""
        decision = PromptRouter(scanner=_QuotingLoudly(), estimator=RulesEstimator()).route(
            PROMPT, BOTH
        )
        [reason] = [r for r in decision.reasons if r.rule == "routing.scanner-failed"]
        assert "RuntimeError" in reason.detail

    def test_the_route_is_still_the_restrictive_one(self) -> None:
        """ADR-0002 has not been traded away for ADR-0016. A broken scanner
        still costs the external destination."""
        decision = PromptRouter(scanner=_Quoting(), estimator=RulesEstimator()).route(PROMPT, BOTH)
        assert decision.route is Route.LOCAL


class TestThroughTheCommands:
    """Every channel a decision leaves by, not only the document."""

    @pytest.mark.parametrize(
        "argv",
        [["route", "--json"], ["route"], ["route", "--explain"]],
        ids=["json", "plain", "explain"],
    )
    def test_nothing_a_broken_scanner_said_is_printed(
        self,
        argv: list[str],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from iriguchi.infrastructure.registry import SCANNERS, Choice

        monkeypatch.setenv("IRIGUCHI_LOCAL", "1")
        monkeypatch.setenv("IRIGUCHI_EXTERNAL", "1")
        monkeypatch.setitem(
            SCANNERS._choices,
            "quoting",
            Choice(
                name="quoting",
                summary="a scanner that quotes the text it choked on",
                trade="a test double",
                build=_Quoting,
            ),
        )
        monkeypatch.setenv("IRIGUCHI_SCANNER", "quoting")
        out = io.StringIO()
        main([*argv, PROMPT], out=out)
        printed = out.getvalue() + capsys.readouterr().err
        assert SECRET not in printed
        assert "quarterly figures" not in printed
        assert "quoting" in printed, "too much redaction: the scanner is not named anywhere"


class TestTheFlagFailsClosed:
    def test_an_ordinary_exception_is_never_quotable(self) -> None:
        """No flag, no quoting -- and that is the answer for every exception
        iriguchi did not write, which is the population that matters."""
        assert safe_detail(RuntimeError("with the prompt in it")) == "RuntimeError"

    def test_an_iriguchi_error_is_not_quotable_unless_it_says_so(self) -> None:
        assert safe_detail(ScanError("with the prompt in it")) == "ScanError"

    def test_a_vouched_message_survives(self) -> None:
        """The half that keeps iriguchi's own diagnostics. `SuppliedScanner`
        names which supplied finding was out of range, built from rule ids and
        offsets -- exactly what ADR-0006 permits to travel."""
        assert safe_detail(ScanError("rule at 0-9", quotable=True)) == "rule at 0-9"

    def test_a_judgement_failure_is_redacted_too(self) -> None:
        assert safe_detail(JudgementError("the upstream echoed the prompt")) == "JudgementError"


class TestOnlyTheAuditedSitesVouch:
    """`quotable=True` is a claim that a message holds no prompt, and it can
    only be made where somebody looked. Listing the sites makes adding one a
    deliberate act that shows up in a diff, rather than a keyword argument
    nobody notices."""

    #: file -> how the message is constructed, established by reading it.
    VOUCHED: ClassVar[dict[str, str]] = {
        "infrastructure/scanners/supplied.py": "built from rule ids, spans and a length",
        "infrastructure/scanners/mamori_scanner.py": "a module constant",
        "errors.py": "where the keyword is defined",
    }

    @staticmethod
    def _sites() -> set[str]:
        found = set()
        for path in SRC.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and any(
                    keyword.arg == "quotable" for keyword in node.keywords
                ):
                    found.add(path.relative_to(SRC).as_posix())
        return found

    def test_the_scan_finds_something(self) -> None:
        """A set difference against an empty set passes while checking nothing,
        and both tests in this class are set differences."""
        assert self._sites()

    def test_no_unlisted_site_vouches_for_itself(self) -> None:
        surprise = self._sites() - set(self.VOUCHED)
        assert not surprise, f"new `quotable=` sites nobody audited: {sorted(surprise)}"
