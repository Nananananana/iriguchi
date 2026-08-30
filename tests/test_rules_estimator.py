"""The rules estimator: what it notices, and what it cannot.

Written before the estimator, and the order matters here more than usual. The
two ADR-0007 traps -- long-and-easy, short-and-hard -- are the reason this axis
has rules at all rather than a length threshold, so they are the first two tests
in the file and everything else is arranged around them.

Nothing here measures a band distribution over real prompts. That is the
corpus's job, and a number claimed before the corpus exists is exactly what this
project keeps refusing to write down.
"""

from __future__ import annotations

import pytest

from contracts import ComplexityEstimatorContract
from iriguchi.domain.complexity import Complexity, ComplexityBand
from iriguchi.infrastructure.estimators.rules import RulesEstimator
from iriguchi.ports.estimator import ComplexityEstimator

LOG_LINE = "2026-08-30 12:00:01 INFO request handled in 12ms\n"


def band(text: str) -> ComplexityBand:
    return Complexity.from_signals(RulesEstimator().estimate(text)).band


def rules(text: str) -> set[str]:
    return {signal.rule.removeprefix("complexity.") for signal in RulesEstimator().estimate(text)}


def score(text: str) -> float:
    return Complexity.from_signals(RulesEstimator().estimate(text)).score


class TestTheContract(ComplexityEstimatorContract):
    def make_estimator(self) -> ComplexityEstimator:
        return RulesEstimator()


class TestTheTwoTraps:
    """ADR-0007's pair, and the reason this is not a length threshold."""

    def test_long_and_easy_does_not_reach_the_top_band(self) -> None:
        """Four hundred lines of log, and one trivial instruction.

        Every router that scores on length sends this to the expensive model.
        The length rule fires -- it should, the input *is* long -- but its
        weight cannot reach the top band on its own, and nothing else here has
        an opinion about a log.
        """
        text = "summarise this log:\n" + LOG_LINE * 400
        assert "long-input" in rules(text)
        assert band(text) is not ComplexityBand.HIGH

    def test_short_and_hard_reaches_the_top_band(self) -> None:
        """Eleven characters, and no small model will manage it.

        This is what the escalating families exist for. A weighted score built
        from length and shape cannot see it at all.
        """
        text = "この補題を証明して、なぜ成り立つか説明して"
        assert band(text) is ComplexityBand.HIGH

    def test_the_short_circuit_is_doing_the_work_not_the_score(self) -> None:
        """The arithmetic, asserted, because it is easy to make it a coincidence.

        Two escalating signals at 0.45 combine to 1 - 0.55^2 = 0.6975, which is
        *under* the 0.7 threshold. If somebody raises those weights until the
        score reaches the band on its own, the short-circuit stops being
        testable and quietly becomes decoration.
        """
        text = "この補題を証明して、なぜ成り立つか説明して"
        complexity = Complexity.from_signals(RulesEstimator().estimate(text))
        assert complexity.band is ComplexityBand.HIGH
        assert complexity.short_circuited is True
        assert complexity.score < 0.7


class TestWhatItNotices:
    @pytest.mark.parametrize(
        ("text", "rule"),
        [
            ("```python\nprint(1)\n```", "code-block"),
            ("結果を JSON で出力してください", "output-shape"),
            ("結果を表にまとめてください", "output-shape"),
            ("What is it? Why does it matter? How do I fix it?", "several-questions"),
            ("この二つの論文を比較してください", "multi-step"),
            ("compare these two approaches", "multi-step"),
            ("計算量を証明してください", "formal-reasoning"),
            ("derive the closed form and prove it terminates", "formal-reasoning"),
        ],
    )
    def test_a_rule_fires(self, text: str, rule: str) -> None:
        assert rule in rules(text)

    def test_a_full_width_output_request_is_still_an_output_request(self) -> None:
        """It normalizes for matching, like the scanner, and for the same reason."""
        assert "output-shape" in rules("結果を ＪＳＯＮ で出力して")

    def test_a_mixed_script_prompt_is_noticed(self) -> None:
        text = "この TypeScript の generics をわかりやすく説明してください"
        assert "mixed-script" in rules(text)


class TestWhatItStaysQuietAbout:
    """No signals is the lowest band, which routes local. Being quiet is safe
    here in a way it never is on the sensitivity axis."""

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "この記事を要約してください",
            "translate this to English",
            "hello",
            "明日の天気は",
        ],
    )
    def test_an_easy_prompt_is_low(self, text: str) -> None:
        assert band(text) is ComplexityBand.LOW

    def test_it_has_no_opinion_about_an_empty_prompt(self) -> None:
        assert RulesEstimator().estimate("") == ()


class TestTheShapeOfWhatItReturns:
    def test_a_rule_about_the_whole_request_carries_no_span(self) -> None:
        """A span of `0-4000` in an explanation tells a reader nothing."""
        signals = RulesEstimator().estimate("x" * 1000)
        whole = [s for s in signals if s.rule.endswith("long-input")]
        assert whole and whole[0].span is None

    def test_a_rule_about_a_place_carries_one(self) -> None:
        text = "この二つの論文を比較してください"
        placed = [s for s in RulesEstimator().estimate(text) if s.span is not None]
        assert placed
        assert all(text[s.span.start : s.span.end] for s in placed if s.span)

    def test_a_span_points_at_the_marker_that_fired(self) -> None:
        text = "この二つの論文を比較してください"
        signal = next(s for s in RulesEstimator().estimate(text) if "multi-step" in s.rule)
        assert signal.span is not None
        assert text[signal.span.start : signal.span.end] == "比較"

    def test_no_rule_fires_twice_however_many_markers_appear(self) -> None:
        """Findings may repeat; signals may not.

        Three email addresses are three findings. "This text asks for several
        things" is either true or it is not, and counting it three times would
        let one long prompt manufacture its own escalation.
        """
        text = "比較して、対比して、検討して、比較して、評価してください"
        found = [s.rule for s in RulesEstimator().estimate(text)]
        assert len(found) == len(set(found))


class TestItIsMonotoneEnoughToReasonAbout:
    def test_adding_a_hard_request_never_lowers_the_score(self) -> None:
        easy = "この記事を要約してください"
        harder = easy + " そのうえで二つの手法を比較して、計算量を証明してください"
        assert score(harder) > score(easy)

    def test_the_same_text_twice_is_the_same_score(self) -> None:
        text = "この二つの論文を比較して JSON で出力して"
        assert RulesEstimator().estimate(text) == RulesEstimator().estimate(text)


class TestTheVocabularyProxy:
    """`dense-vocabulary` is the weakest rule here, and it says so.

    Real rare-word rate needs a frequency list, which is data this library does
    not carry (ADR-0001: zero dependencies, and a wordlist is a dependency in
    everything but the packaging). Mean ASCII token length correlates with it
    and is wrong in ways worth pinning, so that a future improvement has
    something to beat.
    """

    #: Seventeen words was not enough -- the rule has a twenty-word floor, and a
    #: sample under it tests the floor rather than the threshold.
    TECHNICAL = (
        "the authentication middleware performs deserialization before "
        "authorization, which complicates instrumentation and observability "
        "across heterogeneous infrastructure deployments, particularly where "
        "configuration orchestration requires normalization beforehand"
    )
    ORDINARY = (
        "I went to the shop today and got some bread and milk and then I came "
        "home again to make lunch for the kids before they get back from school"
    )

    def test_it_fires_on_technical_prose(self) -> None:
        assert "dense-vocabulary" in rules(self.TECHNICAL)

    def test_it_stays_quiet_on_ordinary_prose_of_the_same_length(self) -> None:
        assert "dense-vocabulary" not in rules(self.ORDINARY)

    def test_it_needs_enough_words_to_mean_anything(self) -> None:
        """Two long words in a short sentence is not a technical document."""
        assert "dense-vocabulary" not in rules("authentication deserialization")

    def test_it_is_blind_to_a_language_without_ascii_words(self) -> None:
        """The admitted gap: it counts ASCII tokens, so Japanese technical prose
        scores nothing here. `mixed-script` is what notices that case, and only
        when English terms are mixed in."""
        assert "dense-vocabulary" not in rules("認証基盤の直列化処理を非同期化する設計の検討" * 3)
