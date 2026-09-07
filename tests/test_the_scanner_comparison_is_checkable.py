"""The scanner comparison table, checked as far as this machine can check it.

Two documents publish the same four-row table — the README's, which tells a user
which scanner to install, and `docs/measurements.md`'s, which is where the
numbers came from. Until now **nothing recomputed any row of either**.

The `fallback` row went stale and was corrected by hand on 2026-09-08 when
`fallback.long-digit-run` was widened. It matched afterwards because somebody
remembered, which is the weakest reason a number can be right.

## Three rows, two situations, one rule

`fallback` is recomputed from the corpus here, on every run, in CI. There was
never a reason it was not.

`presidio` and `fallback+presidio` need presidio-analyzer and a **560 MB** spaCy
model. Putting that in CI would trade a slow, flaky, network-dependent job for a
number that moves twice a year, so presidio stays an optional extra — and the
consequence is that CI cannot check two of the rows.

The rule this file applies to that:

    presidio installed      recompute both rows and require them to match
    presidio absent         require the documents to say the rows are unverified

**CI cannot verify the numbers, so CI verifies that the documents admit it.**
That is not a consolation prize. A number nothing can check is not a defect; a
number nothing can check and nothing says so about is.

## Why the composite can only have improved

`fallback+presidio` is a union of findings. Widening the fallback added findings
and removed none, so the composite's miss rate can only have fallen — `27.1%` is
a ceiling. Stated in the documents rather than here, because a reader of the
table needs it and a reader of this file already knows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from iriguchi.application.routing import PromptRouter
from iriguchi.evaluation.dataset import load_corpus
from iriguchi.evaluation.scoring import run as run_evaluation
from iriguchi.infrastructure.registry import ESTIMATORS, SCANNERS

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
MEASUREMENTS = ROOT / "docs/measurements.md"

#: A row of either table: the scanner name, then two rates. Bold markers and the
#: dagger footnote are stripped, because a number's meaning does not depend on
#: whether somebody emphasised it.
ROW = re.compile(
    r"^\|\s*\*{0,2}`(?P<name>[a-z+]+)`\*{0,2}\s*\|"
    r"\s*\*{0,2}(?P<missed>\d{1,3}\.\d)%\*{0,2}†?\s*\|"
    r"\s*\*{0,2}(?P<caution>\d{1,3}\.\d)%\*{0,2}†?\s*\|",
    re.MULTILINE,
)

#: The sentence each document must carry while the rows cannot be recomputed.
ADMISSION = "not recomputed"


def _published(document: Path) -> dict[str, tuple[float, float]]:
    rows = {
        match["name"]: (float(match["missed"]), float(match["caution"]))
        for match in ROW.finditer(document.read_text(encoding="utf-8"))
    }
    assert rows, f"{document.name} publishes no comparison rows this can parse"
    return rows


def _measure(scanner: str) -> tuple[float, float]:
    report = run_evaluation(
        PromptRouter(scanner=SCANNERS.build(scanner), estimator=ESTIMATORS.build("rules")),
        load_corpus(),
    )
    return (
        round(report.missed_finding_rate * 100, 1),
        round(report.over_caution_rate * 100, 1),
    )


def _presidio_is_here() -> bool:
    from iriguchi.infrastructure.scanners.presidio_scanner import presidio_state

    return presidio_state()[0]


@pytest.fixture(scope="module")
def documents() -> dict[str, dict[str, tuple[float, float]]]:
    return {"README.md": _published(README), "docs/measurements.md": _published(MEASUREMENTS)}


class TestTheRowThatWasAlwaysCheckable:
    """`fallback` needs nothing installed. It was corrected by hand and matched
    because somebody remembered."""

    @pytest.mark.parametrize("document", ["README.md", "docs/measurements.md"])
    def test_the_published_fallback_row_is_what_the_corpus_gives(
        self, document: str, documents: dict[str, dict[str, tuple[float, float]]]
    ) -> None:
        published = documents[document][
            "fallback"
        ]  # (missed findings, over-caution), as percentages
        assert published == _measure("fallback"), (
            f"{document} publishes {published} for `fallback` and the corpus now gives "
            f"{_measure('fallback')}."
        )

    def test_the_two_documents_agree_with_each_other(
        self, documents: dict[str, dict[str, tuple[float, float]]]
    ) -> None:
        """Both are checked against the corpus above, so this can only fail if
        the parser is reading a different table in one of them — which is the
        failure that would make every assertion here quietly vacuous."""
        assert documents["README.md"]["fallback"] == documents["docs/measurements.md"]["fallback"]

    def test_both_tables_carry_every_scanner(
        self, documents: dict[str, dict[str, tuple[float, float]]]
    ) -> None:
        for name, rows in documents.items():
            assert {"fallback", "presidio", "fallback+presidio"} <= set(rows), (
                f"{name} lost a row, so the checks below are about less than they say"
            )


class TestTheRowsThisMachineCannotCheck:
    """Two-sided, and the second side is the one that runs in CI."""

    def test_when_presidio_is_absent_the_documents_say_so(
        self, documents: dict[str, dict[str, tuple[float, float]]]
    ) -> None:
        """**The check CI actually performs.** It cannot verify two rows, so it
        verifies that both documents admit they are unverified — which is the
        difference between a number nobody can check and a number nobody can
        check that reads as though somebody had."""
        if _presidio_is_here():
            pytest.skip("presidio is installed, so the rows are recomputed below instead")
        for name, path in (("README.md", README), ("docs/measurements.md", MEASUREMENTS)):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            assert ADMISSION in flat, (
                f"{name} publishes presidio rows that nothing here can recompute and "
                f"does not say so. Either install presidio, or say the rows are "
                f"{ADMISSION!r} since the fallback was widened."
            )

    @pytest.mark.parametrize("scanner", ["presidio", "fallback+presidio"])
    def test_when_presidio_is_here_the_rows_are_recomputed(
        self, scanner: str, documents: dict[str, dict[str, tuple[float, float]]]
    ) -> None:
        """The other side. On a machine with presidio this is a real check and
        the daggered numbers have to be true — at which point the footnote is
        what should be removed, not this test."""
        if not _presidio_is_here():
            pytest.skip("presidio-analyzer and its spaCy model are not installed here")
        measured = _measure(scanner)
        for name, rows in documents.items():
            assert rows[scanner] == measured, (
                f"{name} publishes {rows[scanner]} for `{scanner}` and this machine, "
                f"which has presidio, measures {measured}."
            )

    def test_the_composite_claim_is_stated_where_a_reader_meets_it(self) -> None:
        """That `27.1%` is a ceiling rather than a measurement belongs in the
        table's own footnote. A reader choosing a scanner does not open the
        test suite."""
        for path in (README, MEASUREMENTS):
            flat = " ".join(path.read_text(encoding="utf-8").split())
            assert "ceiling rather than a measurement" in flat, path.name
