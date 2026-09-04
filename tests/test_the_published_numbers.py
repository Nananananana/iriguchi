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


FEASIBILITY = ROOT / "docs" / "feasibility.md"


@pytest.fixture(scope="module")
def audit() -> str:
    text = FEASIBILITY.read_text(encoding="utf-8")
    marker = "## F1."
    assert marker in text, "the section this file checks is gone"
    return text[text.index(marker) : text.index("## F2.")]


@pytest.fixture(scope="module")
def counts() -> tuple[dict[str, int], dict[str, dict[str, int]], dict[str, str]]:
    from collections import Counter
    from statistics import median

    from which_axis import ORDER, decided_by

    from iriguchi.application.routing import PromptRouter
    from iriguchi.evaluation.dataset import load_corpus
    from iriguchi.infrastructure.registry import ESTIMATORS, SCANNERS

    router = PromptRouter(scanner=SCANNERS.build("fallback"), estimator=ESTIMATORS.build("rules"))
    overall: Counter[str] = Counter()
    by_source: dict[str, Counter[str]] = {}
    lengths: dict[str, list[int]] = {}
    for case in load_corpus():
        what = decided_by(case.prompt, router)
        overall[what] += 1
        by_source.setdefault(case.source, Counter())[what] += 1
        lengths.setdefault(case.source, []).append(len(case.prompt))
    assert set(overall) <= set(ORDER), "an outcome nobody named"
    return (
        dict(overall),
        {source: dict(counter) for source, counter in by_source.items()},
        # Formatted, not truncated. The tool prints `{median:5.0f}`, and a
        # median of 33.5 is 34 there and 33 under `int()` -- a test that
        # disagrees with the instrument it cites about rounding fails on
        # arithmetic rather than on the claim it is making.
        {source: f"{median(values):.0f}" for source, values in lengths.items()},
    )


class TestTheFeasibilityAuditIsStillTrue:
    """`docs/feasibility.md` F1, recomputed.

    An audit is the document most likely to be quietly outgrown. Its whole
    argument is a set of counts -- *the second axis changes two outcomes in a
    hundred and fifty-five* -- and the day somebody adds twenty long prompts to
    the corpus, that sentence stops being true and nothing says so. A finding
    that has been fixed and still reads as open is worse than no finding: it
    sends the next reader to solve a solved problem.

    So every number in F1's two tables is derived here from the corpus as it is
    now, through `tools/which_axis.py`, which is the same instrument the
    document cites. If the corpus changes, this goes red and the audit gets
    edited -- which is the only mechanism that keeps a written measurement from
    becoming a written belief.
    """

    def test_there_is_a_table_to_check(self, audit: str) -> None:
        """A floor. Every assertion below passes against a section with no
        tables in it, which is what a rewrite would leave."""
        assert audit.count("|---") >= 2, "F1 has lost its tables"

    @pytest.mark.parametrize(
        "label", ["the veto removed external", "complexity kept it local", "complexity sent it out"]
    )
    def test_each_outcome_row_is_what_the_corpus_gives(
        self,
        label: str,
        audit: str,
        counts: tuple[dict[str, int], dict[str, dict[str, int]], dict[str, str]],
    ) -> None:
        overall, _, _ = counts
        total = sum(overall.values())
        row = _row(audit, label)
        assert row[1].strip("*") == str(overall[label]), (
            f"F1 publishes {row[1]} for {label!r} and the corpus now gives {overall[label]}."
        )
        assert row[2].strip("*") == f"{100 * overall[label] / total:.1f}%"

    @pytest.mark.parametrize("source", ["borrowed:mamori", "generated"])
    def test_each_source_row_is_what_the_corpus_gives(
        self,
        source: str,
        audit: str,
        counts: tuple[dict[str, int], dict[str, dict[str, int]], dict[str, str]],
    ) -> None:
        from which_axis import ORDER

        _, by_source, lengths = counts
        row = _row(audit, source)
        counter = by_source[source]
        published = [cell.strip("*") for cell in row[1:]]
        expected = [str(sum(counter.values()))] + [str(counter.get(w, 0)) for w in ORDER]
        assert published[:4] == expected, (
            f"F1's row for {source} publishes {published[:4]} and the corpus now gives {expected}."
        )
        assert published[4].startswith(lengths[source]), (
            f"F1 publishes a median of {published[4]} for {source} and it is now "
            f"{lengths[source]} chars. The argument that these prompts are too "
            f"short to band rests on this number."
        )

    def test_the_claim_the_argument_rests_on(
        self, counts: tuple[dict[str, int], dict[str, dict[str, int]], dict[str, str]]
    ) -> None:
        """Stated as a behaviour rather than as a row, because this is the one
        sentence somebody would act on: **the borrowed corpus cannot exercise
        the complexity axis.** The day it can, F1 is obsolete."""
        from which_axis import SENT

        _, by_source, _ = counts
        assert by_source["borrowed:mamori"].get(SENT, 0) == 0, (
            "borrowed cases now reach the external destination on complexity "
            "alone. F1 says they cannot, and F1 is now wrong -- rewrite it "
            "rather than deleting this test."
        )
