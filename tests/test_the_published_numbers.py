"""The rows of a published table that can be recomputed, recomputed.

kiseki's question, arriving through manager: **when a set gains a member, how
many mechanisms go red?** If none, the set will be silently wrong at the next
one.

`docs/measurements.md` publishes a band table over the 21 generated cases. Add a
twenty-second and three things move at once — the baseline, the rules' accuracy,
and the 4.76 points a single case is worth — and **nothing said so.** The
numbers were prose, and prose is where a corpus change goes to be forgotten.

Two of the rows need no model and are checked here against the corpus as it is
now. The model rows cannot be: they are recorded observations of a particular
model on a particular day, and re-deriving them would need the model running in
CI, which is exactly what the `llm` marker exists to avoid. **Those stay
recorded, with the date and the model in the section heading.**

So the split is:

    baseline, rules, n, the per-case value   recomputed here, every run
    the eight model rows                     recorded, dated, not re-derived

The second half is a real gap and it is the honest one: a table nobody can
re-derive is a table that has to be trusted. What this file removes is the part
that never needed trusting.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from measure_router import (  # noqa: E402
    CORPUS,
    READABLE_AT_CASES,
    Judgement,
    Outcome,
    rules_band,
    score,
)

MEASUREMENTS = ROOT / "docs" / "measurements.md"


@pytest.fixture(scope="module")
def cases() -> list[dict[str, object]]:
    loaded = json.loads(CORPUS.read_text(encoding="utf-8"))["samples"]
    assert loaded, "the corpus is empty, so every figure below would be about nothing"
    return list(loaded)


@pytest.fixture(scope="module")
def published() -> str:
    text = MEASUREMENTS.read_text(encoding="utf-8")
    marker = "## The band, against a model"
    assert marker in text, "the section this file checks is gone"
    return text[text.index(marker) :]


def _row(published: str, label: str) -> list[str]:
    """One table row by its first cell, split into cells.

    Matched on the label rather than on a number, so this cannot be satisfied
    by finding the figure it is looking for somewhere else in the document.
    """
    for line in published.splitlines():
        if line.startswith("|") and label in line.split("|")[1]:
            return [cell.strip() for cell in line.strip("|").split("|")]
    raise AssertionError(f"no row labelled {label!r} in the published table")


class TestTheRowsThatCanBeRecomputed:
    def test_the_baseline_is_what_the_corpus_says(
        self, cases: list[dict[str, object]], published: str
    ) -> None:
        """Always answering the majority band. It moves whenever the corpus
        does, and it is the number every other figure has to beat."""
        counts = Counter(str(case["band"]) for case in cases)
        band, hits = counts.most_common(1)[0]
        expected = f"{100 * hits / len(cases):.1f}%"
        row = _row(published, f"always answering `{band}`")
        assert row[1] == expected, (
            f"the published baseline is {row[1]} and the corpus now gives "
            f"{expected}. Adding a case moves this, and until now nothing said so."
        )

    def test_the_rules_row_is_what_the_rules_do(
        self, cases: list[dict[str, object]], published: str
    ) -> None:
        """Recomputed through the domain, the way the tool does it, so a change
        to the estimator or to the combination rule lands here too."""
        judged = [
            Judgement(str(c["id"]), str(c["band"]), rules_band(str(c["prompt"])), Outcome.ANSWERED)
            for c in cases
        ]
        result = score(judged)
        expected = f"{100 * result['accuracy']:.1f}%"
        row = _row(published, "the rules, today")
        assert expected in row[1], (
            f"the published figure for the rules is {row[1]} and they now score {expected}."
        )

    def test_the_per_class_counts_are_the_corpus_denominators(
        self, cases: list[dict[str, object]], published: str
    ) -> None:
        """The column headers carry the denominators — `low (14)`, `mod (3)`,
        `high (4)`. Those are corpus facts and they move with it."""
        counts = Counter(str(case["band"]) for case in cases)
        header = _row(published, "")
        for band, short in (("low", "low"), ("moderate", "mod"), ("high", "high")):
            assert f"{short} ({counts[band]})" in header, (
                f"the header says {header} but the corpus has {counts[band]} {band} cases."
            )


class TestTheArithmeticInTheProse:
    def test_what_one_case_is_worth_is_derived_from_the_corpus(
        self, cases: list[dict[str, object]], published: str
    ) -> None:
        """4.76 is 100/21. Typed once into a sentence, it survives a corpus
        change and becomes the most confident wrong number on the page."""
        expected = f"{100 / len(cases):.2f} points"
        assert expected in published, (
            f"the page says one case is worth something other than {expected}, "
            f"which is what {len(cases)} cases make it."
        )

    def test_the_floor_in_the_prose_is_the_floor_the_tool_applies(
        self, cases: list[dict[str, object]], published: str
    ) -> None:
        """The sentence and `decidable()` have to agree, or the table's verdicts
        and its explanation describe different rules."""
        floor = 100.0 * READABLE_AT_CASES / len(cases)
        assert f"{floor:.1f} points" in published, (
            f"the prose names a floor other than {floor:.1f}, which is what "
            f"{READABLE_AT_CASES} cases are worth at n={len(cases)}."
        )

    def test_the_corpus_size_is_stated_correctly(
        self, cases: list[dict[str, object]], published: str
    ) -> None:
        assert f"n = {len(cases)}" in published
        assert f"the {len(cases)} generated cases" in published


class TestWhatIsNotChecked:
    """Named, so the gap is a decision rather than an omission."""

    def test_the_model_rows_carry_a_date_and_a_model(self, published: str) -> None:
        """They cannot be recomputed without a model, so they must at least say
        when and with what. A row that says neither is a number with no way
        back to its measurement."""
        assert re.search(r"20\d\d-\d\d-\d\d", published), "no date on the section"
        assert "temperature 0" in published
        assert "qwen2.5:14b-q4" in published

    def test_the_borrowed_corpus_is_still_excluded(self, published: str) -> None:
        """134 cases labelled `low` by these same rules would add 134 free
        agreements. If somebody folds them in, this figure moves a long way and
        for the wrong reason."""
        assert "134 borrowed cases" in published
        assert CORPUS.name == "generated.json"
