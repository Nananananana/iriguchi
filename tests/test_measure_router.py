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
    Judgement,
    Outcome,
    caveats,
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
