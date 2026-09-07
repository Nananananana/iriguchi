"""Every document that publishes a number says who checks it, or when it was true.

The suite already recomputes `README.md`, `docs/measurements.md` and
`docs/feasibility.md` against the corpus. Audited on 2026-09-08, that left
**twenty-two percentages in documents no test opens** — the ADRs and the design
proposal — and three of those documents carried no date either, so a reader
could not tell a live claim from a record of one.

    3 pct   0 dates   docs/adr/0001-the-domain-depends-on-nothing.md
    4 pct   0 dates   docs/adr/0004-decide-before-the-request.md
    3 pct   0 dates   docs/adr/0018-a-cascade-whose-first-hop-is-local.md

None of them was wrong. That is the point: **the defect was not a stale number,
it was that nothing would notice when one went stale**, and one had just gone
stale by an unrelated change — widening `fallback.long-digit-run` moved the
fallback's miss rate and made ADR-0017's composite row a ceiling rather than a
measurement, in a table that reads as current advice.

## The rule

An ADR is a record of a decision, so its numbers are allowed to age. What is
not allowed is being unable to tell. So every document holding a percentage is
in exactly one of two sets:

`RECOMPUTED`   a test parses the file and checks its numbers against the corpus
`HISTORICAL`   a record, which must carry a date so a reader knows when

A document in neither fails here, which makes adding an unchecked number a
deliberate act rather than an accident.

## What this deliberately does not do

It does not recompute the ADRs. A number in a decision's *Context* was true when
the decision was made and rewriting it would falsify the record — ADR-0001's
`63.5% (66/104)` is the measurement that caused the decision, and the corpus has
since grown to 197 cases. Dating it is the honest fix; updating it would be a
lie about why the decision was taken.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

PERCENTAGE = re.compile(r"\b\d{1,3}\.\d%")
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")

#: Parsed and checked against the corpus by another test in this suite.
RECOMPUTED = {
    "README.md": "tests/test_the_readme_is_true.py",
    "docs/measurements.md": "tests/test_the_published_numbers.py",
    "docs/feasibility.md": "tests/test_the_published_numbers.py",
    "docs/adr/0019-the-external-route-needs-a-checkout-nobody-has.md": (
        "tests/test_the_published_numbers.py, via feasibility F1"
    ),
}

#: Records rather than claims. Each must carry a date, and the reason it is not
#: recomputed is stated here rather than left to be guessed.
HISTORICAL = {
    "docs/adr/0001-the-domain-depends-on-nothing.md": (
        "the 155-case measurement that caused the decision; the corpus is 197 now"
    ),
    "docs/adr/0004-decide-before-the-request.md": (
        "the band accuracy that justified deciding without a model"
    ),
    "docs/adr/0017-an-optional-dependency-is-a-scanner-you-can-actually-get.md": (
        "the scanner comparison as it stood; presidio is absent from CI so two "
        "rows cannot be recomputed anywhere"
    ),
    "docs/adr/0018-a-cascade-whose-first-hop-is-local.md": (
        "the 42.9% the cascade exists because of"
    ),
    "docs/proposals/0001-the-design.md": "the original design, kept as written",
}


def _documents_with_numbers() -> dict[str, int]:
    found = {}
    for path in [*sorted((ROOT / "docs").rglob("*.md")), ROOT / "README.md"]:
        count = len(PERCENTAGE.findall(path.read_text(encoding="utf-8")))
        if count:
            found[path.relative_to(ROOT).as_posix()] = count
    return found


@pytest.fixture(scope="module")
def documents() -> dict[str, int]:
    found = _documents_with_numbers()
    assert found, "no document publishes a percentage, so this file checks nothing"
    return found


class TestEveryDocumentIsAccountedFor:
    def test_none_is_unclassified(self, documents: dict[str, int]) -> None:
        """The whole guard. A new document with numbers, or an old one that
        grows its first, lands here rather than in a reader's lap."""
        loose = sorted(set(documents) - set(RECOMPUTED) - set(HISTORICAL))
        assert not loose, (
            f"these publish numbers and are neither recomputed nor dated: {loose}. "
            f"Add a test that checks them, or a date saying when they were true."
        )

    def test_nothing_is_classified_that_has_no_numbers(self, documents: dict[str, int]) -> None:
        """The mirror. A file listed here and since emptied of numbers makes
        both lists read as larger than the checking they describe."""
        stale = sorted((set(RECOMPUTED) | set(HISTORICAL)) - set(documents))
        assert not stale, f"listed here and publishing no numbers: {stale}"

    def test_the_two_lists_do_not_overlap(self) -> None:
        assert not set(RECOMPUTED) & set(HISTORICAL)


class TestARecomputedDocumentIsReallyRead:
    @pytest.mark.parametrize("document", sorted(RECOMPUTED), ids=sorted(RECOMPUTED))
    def test_the_named_test_opens_it(self, document: str) -> None:
        """`RECOMPUTED` is a claim about another file, and a claim about another
        file is the kind that rots quietly. This reads that file."""
        name = Path(document).name
        readers = [
            path.name
            for path in TESTS.glob("test_*.py")
            if name in path.read_text(encoding="utf-8")
        ]
        assert readers, f"{document} is listed as recomputed and no test mentions it"


class TestAHistoricalDocumentSaysWhen:
    @pytest.mark.parametrize("document", sorted(HISTORICAL), ids=sorted(HISTORICAL))
    def test_it_carries_a_date(self, document: str) -> None:
        text = (ROOT / document).read_text(encoding="utf-8")
        assert DATE.search(text), (
            f"{document} publishes {len(PERCENTAGE.findall(text))} percentage(s) and "
            f"names no date. A reader cannot tell a record from a claim."
        )

    def test_the_one_that_went_stale_says_so(self) -> None:
        """ADR-0017's composite row. Widening `fallback.long-digit-run` moved
        the fallback's miss rate, and the composite is a union of findings — so
        its published figure became a ceiling and nothing said so.

        Named on its own because it is the case this whole file was written
        after, and because `presidio` is absent from CI: those two rows cannot
        be recomputed here, by this suite, or by the wheel job.
        """
        text = (
            ROOT / "docs/adr/0017-an-optional-dependency-is-a-scanner-you-can-actually-get.md"
        ).read_text(encoding="utf-8")
        # Flattened: line wrapping puts a newline anywhere, and a prose
        # assertion that depends on where the paragraph broke is one that fails
        # the next time somebody reflows it.
        flat = " ".join(text.split())
        assert "not recomputed" in flat
        assert "ceiling rather than a measurement" in flat
