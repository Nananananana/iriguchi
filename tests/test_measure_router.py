"""The instrument that produced a published number.

`tools/measure_router.py` wrote the table in `docs/measurements.md`. Two of its
functions can corrupt that table silently, and neither is exercised by running
the tool — a wrong `parse` or a wrong `score` produces a plausible percentage
rather than a crash.

The `llm`-marked test at the bottom is the only one here that talks to a model.
It is deselected in CI by `addopts = "-q -m 'not llm'"`, because a build that
depends on a model having been pulled fails for reasons unrelated to the change.
The marker existed before this file did and nothing carried it: **v0.2 listed
"`llm`-marked tests, deselected in CI" and what shipped was the deselection.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from measure_router import (  # noqa: E402
    BANDS,
    CORPUS,
    READABLE_AT_CASES,
    Judgement,
    Outcome,
    caveats,
    decidable,
    parse,
    rules_band,
    score,
)


class TestParsingAModelsReply:
    """Strict about content, permissive about surroundings.

    Every reply in the published run was literally one word, so this rescued
    nothing — which is worth knowing rather than assuming. It is here for the
    reply that is not.
    """

    @pytest.mark.parametrize("band", BANDS)
    @pytest.mark.parametrize("dressing", ["{}", "{}.", "**{}**", " {} \n", "{}\n"])
    def test_a_band_with_punctuation_around_it_is_still_a_band(
        self, band: str, dressing: str
    ) -> None:
        assert parse(dressing.format(band)) == band

    @pytest.mark.parametrize(
        "reply",
        ["it depends", "", "   ", "I cannot classify this", "42"],
        ids=["a hedge", "empty", "whitespace", "a refusal", "a number"],
    )
    def test_a_reply_that_names_no_band_is_not_guessed_at(self, reply: str) -> None:
        """`None` rather than a default. A guessed band is indistinguishable
        from a judged one once it reaches a percentage."""
        assert parse(reply) is None

    def test_a_reply_naming_two_bands_is_refused(self) -> None:
        """ "between low and moderate" is a model declining to choose, and
        taking the first word would record a decision it did not make."""
        assert parse("between low and moderate") is None


class TestScoring:
    @staticmethod
    def _judgements(*pairs: tuple[str, str | None]) -> list[Judgement]:
        return [
            Judgement(
                f"case-{n}",
                label,
                predicted,
                Outcome.ANSWERED if predicted else Outcome.UNPARSEABLE,
            )
            for n, (label, predicted) in enumerate(pairs)
        ]

    def test_accuracy_is_over_every_case_not_over_the_ones_that_answered(self) -> None:
        """The trap that would have flattered every model in the table.

        A model that answers eight of twenty-one and gets all eight right has
        not scored 100%. It failed thirteen times, in a way that matters more
        than a wrong band, and a denominator of eight would have hidden that
        behind a perfect score.
        """
        result = score(self._judgements(("low", "low"), ("high", None), ("high", None)))
        assert result["correct"] == 1
        assert result["accuracy"] == pytest.approx(1 / 3)

    def test_the_ways_of_producing_no_band_stay_apart(self) -> None:
        """bench found four collapsed into one boolean in their own generator,
        where they read as "the writer redacted nothing". A timeout, an empty
        reply and a paragraph are three different findings, and only the last
        is about the model's judgement."""
        judgements = [
            Judgement("a", "low", None, Outcome.EMPTY),
            Judgement("b", "low", None, Outcome.UNPARSEABLE),
            Judgement("c", "low", None, Outcome.FAILED),
        ]
        assert score(judgements)["outcomes"] == {
            "answered": 0,
            "empty": 1,
            "unparseable": 1,
            "failed": 1,
        }

    def test_per_class_counts_denominators_from_the_labels(self) -> None:
        """Not from the predictions. A model that never says `high` must show
        0/4 rather than vanishing from the row."""
        result = score(self._judgements(("high", "low"), ("high", "low"), ("low", "low")))
        assert result["per_class"]["high"] == (0, 2)
        assert result["per_class"]["low"] == (1, 1)

    def test_an_empty_run_does_not_divide_by_zero(self) -> None:
        assert score([])["accuracy"] == 0.0


class TestWhetherADifferenceCanBeRead:
    """Three values, and the middle one is the reason it is not a `bool`.

    The version this replaced was a sentence in the caveats — *a difference
    under fourteen points is not a result* — sitting above a table, where a
    reader skips it and then reads the numbers. bench wrote the three-valued
    form and tsumugi carried it: **a note in prose leaves the reader room and a
    type does not.**

    It changed a published claim within minutes of existing. The table said two
    configurations beat the rules; both were inside the floor.
    """

    def test_a_difference_inside_the_floor_is_undecidable_not_absent(self) -> None:
        """`False` means *this run cannot say*, and the whole point of the
        three values is that nobody can read it as *no difference*."""
        assert decidable(9.5, 21) is False
        assert decidable(-9.5, 21) is False

    def test_a_difference_larger_than_the_floor_is_readable(self) -> None:
        assert decidable(14.4, 21) is True
        assert decidable(-52.4, 21) is True

    def test_the_floor_is_three_cases_at_this_size(self) -> None:
        """4.76 a case, so the boundary is 14.29 — derived, not typed."""
        floor = 100.0 * READABLE_AT_CASES / 21
        assert decidable(floor - 0.01, 21) is False
        assert decidable(floor + 0.01, 21) is True

    def test_it_is_symmetric(self) -> None:
        """A model eleven cases behind and one eleven ahead are equally
        readable. A one-sided test would have called the losses undecidable."""
        assert decidable(20.0, 21) == decidable(-20.0, 21)

    @pytest.mark.parametrize("n", [0, 1])
    def test_no_floor_exists_below_two_cases(self, n: int) -> None:
        """`None`, not `False`. With one sample there is no spread to be inside
        of, and saying "undecidable" would imply a floor was consulted."""
        assert decidable(50.0, n) is None

    def test_the_floor_moves_with_the_corpus(self) -> None:
        """If the corpus grows, the same difference becomes readable. A figure
        typed into prose would not have moved with it."""
        assert decidable(5.0, 21) is False
        assert decidable(5.0, 200) is True


class TestTheCaveatsTravelWithTheNumbers:
    def test_the_arithmetic_is_derived_and_not_typed(self) -> None:
        """4.76 is 100/21. If the corpus grows, the sentence has to move with
        it, and a figure typed in prose would not."""
        text = caveats(66.7, 21, "a-model", "temperature 0")
        assert "4.76 points" in text
        assert "n = 21" in text

    def test_it_names_the_baseline_it_was_given(self) -> None:
        assert "66.7%" in caveats(66.7, 21, "m", "temperature 0")


class TestTheRulesSide:
    def test_the_band_comes_from_the_domain_and_not_from_the_estimator(self) -> None:
        """The estimator returns signals; `Complexity.from_signals` decides.
        Reading a band off the estimator would measure something the product
        does not do."""
        assert rules_band("Refactor this and explain why, step by step.") == "high"
        assert rules_band("Fix the typo.") == "low"

    def test_it_measures_the_generated_corpus_only(self) -> None:
        """The 134 borrowed cases all carry `band: low`, assigned by these same
        rules. Including them would add 134 free agreements with the thing
        being tested."""
        assert CORPUS.name == "generated.json"


@pytest.mark.llm
@pytest.mark.network
def test_a_real_model_answers_with_one_word() -> None:
    """The end of the chain, run against something real.

    **Two markers, and this is the first use of either.** `llm` deselects it in
    CI, because a build that depends on a model having been pulled fails for
    reasons unrelated to the change. `network` opts it out of the suite's
    autouse socket poisoning -- v0.1 wrote that marker for exactly this moment
    and said so: *it exists so that v0.2's adapters make their exception visible
    per test rather than by relaxing the default.* Nothing had used it until
    now, and the default stays as strict as it was.

    Run with `pytest -m llm` and a local model pulled.

    It asserts the *shape* rather than an accuracy: which band a model picks is
    a measurement and belongs in `docs/measurements.md`, where its caveats are.
    A test that pinned a percentage would fail on a model upgrade and say
    nothing about the code.
    """
    from measure_router import PROMPTS

    from iriguchi.infrastructure.models.openai_compatible import OpenAICompatibleModel

    model = OpenAICompatibleModel(
        "http://127.0.0.1:11434/v1", "qwen2.5:7b-instruct-q8_0", temperature=0.0
    )
    reply = model.answer(PROMPTS["briefed"].format(prompt="Fix the typo in this sentence."))
    assert parse(reply) in BANDS
