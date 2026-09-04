"""Every tuned number, reachable and script-neutral.

Two questions a library gets asked the week after it ships, and iriguchi could
not answer either.

**"Our traffic is not your corpus. How do I retune this?"** You forked it. The
weights were module-private constants and `RulesEstimator` had no `__init__` at
all -- not a narrow interface, *no* interface. Every number that decides
anything was reachable only by editing the installed package.

**"Why does the Japanese version of the same prompt score lower?"** Because the
length threshold counted code points, and Japanese says the same thing in about
half of them. Measured:

    Please refactor this authentication module. (x15)    660 code points
    この認証モジュールをリファクタリングしてください。 (x15)    375 code points

Same request. The English one crossed 600 and the Japanese one did not, so a
Japanese user had to write roughly twice as much to reach the same band. In a
project written in Japanese, about Japanese prompts.

Neither is a bug in the sense of a wrong line. Both are the same defect: **a
number chosen against one sample, frozen where nobody can reach it, and assumed
to mean the same thing everywhere.** That is what does not survive release.
"""

from __future__ import annotations

import pytest

from iriguchi.domain.complexity import Complexity
from iriguchi.errors import ConfigurationError
from iriguchi.infrastructure.estimators.rules import (
    DEFAULT_SETTINGS,
    RulesEstimator,
    RulesSettings,
    display_width,
)

#: The same request, twice. Repeated to clear the default threshold in at least
#: one script -- the point is the gap between them, not either number.
ENGLISH = "Please refactor this authentication module. " * 15
JAPANESE = "この認証モジュールをリファクタリングしてください。" * 15


def _rules(text: str, settings: RulesSettings | None = None) -> set[str]:
    return {signal.rule for signal in RulesEstimator(settings).estimate(text)}


class TestTheSameRequestInTwoScripts:
    def test_the_japanese_version_really_is_shorter_in_code_points(self) -> None:
        """The premise. If these ever converge the rest of this class is
        measuring nothing."""
        assert len(JAPANESE) < len(ENGLISH) * 0.75, (len(JAPANESE), len(ENGLISH))

    def test_both_now_reach_the_long_input_signal(self) -> None:
        """The defect, stated as the behaviour that was missing. Before display
        width, only the English one fired."""
        assert "complexity.long-input" in _rules(ENGLISH)
        assert "complexity.long-input" in _rules(JAPANESE)

    def test_counting_code_points_is_what_broke_it(self) -> None:
        """The asymmetry, stated where it lives rather than simulated through
        the settings -- the first version of this test set `long_input_at` to a
        code-point count and compared it against a width, which is the same
        unit confusion the bug was made of, and it carried an `or True` that
        made half of it pass regardless.

        Under `len`, one of these clears 600 and the other does not. Under
        `display_width`, both do. That is the whole defect and the whole fix.
        """
        assert len(ENGLISH) >= 600 > len(JAPANESE), (len(ENGLISH), len(JAPANESE))
        assert display_width(ENGLISH) >= 600 and display_width(JAPANESE) >= 600

    def test_width_counts_wide_characters_as_two(self) -> None:
        assert display_width("認証") == 4
        assert display_width("auth") == 4

    def test_ambiguous_width_counts_as_one(self) -> None:
        """Their width depends on the reader's locale. Guessing East Asian for a
        string that might be Greek would break this in the other direction."""
        assert display_width("αβγ") == 3

    def test_it_is_never_shorter_than_the_string(self) -> None:
        for text in (ENGLISH, JAPANESE, "", "abc", "認証", "a認b証"):
            assert display_width(text) >= len(text)


class TestTheDenseSignalIsHonestAboutNotApplying:
    """It cannot fire on Japanese or Chinese, and now says so.

    `_ASCII_WORD` needs spaces to find words. The docstring admitted the rule
    was wrong about German and did not mention that it is *silent* on the
    language this project is written in.
    """

    def test_it_does_not_fire_on_japanese_however_technical(self) -> None:
        technical = "".join(["実装方式", "設計判断", "根拠説明", "比較検討"] * 20)
        assert "complexity.dense-vocabulary" not in _rules(technical)

    def test_it_does_fire_on_the_english_equivalent(self) -> None:
        """The floor. Without this the assertion above passes against a rule
        that was deleted."""
        technical = " ".join(["implementation", "architecture", "serialization"] * 20)
        assert "complexity.dense-vocabulary" in _rules(technical)

    def test_kanji_ratio_would_not_have_fixed_it(self) -> None:
        """The obvious counterpart, rejected with a measurement rather than an
        opinion. Chinese is ~90% hanzi whatever it is about, so a kanji-density
        signal fires on all Chinese prose -- a language detector wearing a
        density costume, and a veto-adjacent signal that fires on a whole
        language is worse than a missing one."""

        def ratio(text: str) -> float:
            return sum(1 for c in text if "一" <= c <= "鿿") / len(text)

        ordinary_chinese = "这是北京云图科技有限公司的张伟。"
        technical_english = "implementation architecture serialization"
        assert ratio(ordinary_chinese) > 0.5
        assert ratio(technical_english) == 0.0


class TestEveryNumberCanBeMoved:
    def test_the_defaults_are_what_was_hard_coded(self) -> None:
        """Adopting the settings object changed no behaviour. If this drifts,
        every published measurement was taken against different software."""
        assert DEFAULT_SETTINGS.long_input_at == 600
        assert DEFAULT_SETTINGS.long_input_weight == 0.3
        assert DEFAULT_SETTINGS.dense_word_length == 7.0
        assert DEFAULT_SETTINGS.dense_min_words == 20
        assert DEFAULT_SETTINGS.dense_weight == 0.25
        assert DEFAULT_SETTINGS.mixed_script_min_share == 0.1
        assert DEFAULT_SETTINGS.mixed_script_weight == 0.2
        assert DEFAULT_SETTINGS.escalating_weight == 0.45

    def test_an_estimator_with_no_arguments_is_the_old_one(self) -> None:
        assert RulesEstimator().settings == DEFAULT_SETTINGS

    @pytest.mark.parametrize(
        "field,value,text,rule",
        [
            ("long_input_at", 10, "a" * 20, "complexity.long-input"),
            ("dense_min_words", 1, "implementation architecture", "complexity.dense-vocabulary"),
            (
                "mixed_script_min_share",
                0.01,
                "認証 auth aaaaaaaaaaaaaaaaaaaa",
                "complexity.mixed-script",
            ),
        ],
    )
    def test_lowering_a_threshold_makes_its_signal_fire(
        self, field: str, value: float, text: str, rule: str
    ) -> None:
        """Each structural threshold, shown moving. A settings object whose
        fields are read but never used is the failure this catches."""
        assert rule not in _rules(text), f"{rule} already fires; this proves nothing"
        assert rule in _rules(text, RulesSettings(**{field: value}))  # type: ignore[arg-type]

    def test_a_weight_change_reaches_the_signal(self) -> None:
        long_text = "a" * 700
        [signal] = [
            s for s in RulesEstimator().estimate(long_text) if s.rule.endswith("long-input")
        ]
        assert signal.weight == 0.3
        louder = RulesEstimator(RulesSettings(long_input_weight=0.9))
        [changed] = [s for s in louder.estimate(long_text) if s.rule.endswith("long-input")]
        assert changed.weight == 0.9

    def test_a_weight_change_reaches_the_band(self) -> None:
        """Through the domain, not just onto the signal. A weight that is
        reported and not combined is a knob connected to the display."""
        long_text = "a" * 700
        quiet = Complexity.from_signals(
            RulesEstimator(RulesSettings(long_input_weight=0.01)).estimate(long_text)
        )
        loud = Complexity.from_signals(
            RulesEstimator(RulesSettings(long_input_weight=0.99)).estimate(long_text)
        )
        assert loud.score > quiet.score


class TestTheKnobThatMattersAfterRelease:
    """Per-rule overrides. A deployment retunes one rule, not the library."""

    MARKER = "complexity.multi-step"
    TEXT = "Compare both approaches and say which is better."

    def _weight(self, settings: RulesSettings | None = None) -> float:
        signals = RulesEstimator(settings).estimate(self.TEXT)
        matching = [s for s in signals if s.rule == self.MARKER]
        assert matching, f"{self.MARKER} did not fire; pick a marker that does"
        return matching[0].weight

    def test_the_marker_fires_at_its_table_weight(self) -> None:
        assert self._weight() > 0

    def test_an_override_replaces_it(self) -> None:
        assert self._weight(RulesSettings(marker_weights={self.MARKER: 0.05})) == 0.05

    def test_other_markers_are_untouched(self) -> None:
        """The point of a per-rule override. Retuning one rule must not be a
        way to accidentally retune twenty."""
        text = "Prove the lemma, step by step, and write the code."
        before = {s.rule: s.weight for s in RulesEstimator().estimate(text)}
        after = {
            s.rule: s.weight
            for s in RulesEstimator(RulesSettings(marker_weights={self.MARKER: 0.05})).estimate(
                text
            )
        }
        assert set(before) == set(after)
        assert [r for r in before if before[r] != after[r]] == [self.MARKER]

    def test_escalating_weight_actually_moves_escalating_markers(self) -> None:
        """It sat beside a copy of itself in the marker table for a while, which
        made it a field that reads as a knob and turns nothing."""
        text = "Prove the lemma, step by step."
        escalating = [s for s in RulesEstimator().estimate(text) if s.escalating]
        assert escalating, "no escalating marker fired; this test is guarding nothing"
        louder = RulesEstimator(RulesSettings(escalating_weight=0.9))
        assert all(s.weight == 0.9 for s in louder.estimate(text) if s.escalating)

    def test_a_per_rule_override_beats_escalating_weight(self) -> None:
        """Most specific wins, or the two settings fight and the winner depends
        on reading the source."""
        text = "Prove the lemma, step by step."
        rule = next(s.rule for s in RulesEstimator().estimate(text) if s.escalating)
        settings = RulesSettings(escalating_weight=0.9, marker_weights={rule: 0.11})
        assert (
            next(s.weight for s in RulesEstimator(settings).estimate(text) if s.rule == rule)
            == 0.11
        )


class TestItRefusesSettingsThatCannotMeanAnything:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"long_input_weight": 1.5},
            {"long_input_weight": -0.1},
            {"escalating_weight": 2.0},
            {"mixed_script_min_share": 1.1},
            {"long_input_at": 0},
            {"dense_min_words": 0},
            {"dense_word_length": 0},
            {"marker_weights": {"complexity.multi-step": 3.0}},
        ],
        ids=[
            "weight above one",
            "negative weight",
            "escalating above one",
            "share above one",
            "zero length",
            "zero words",
            "zero word length",
            "override out of range",
        ],
    )
    def test_it_is_refused_at_construction(self, kwargs: dict[str, object]) -> None:
        """Refused where it is written, not on the prompt that reveals it.
        `1 - prod(1 - w)` with a weight above one produces a negative factor and
        a score outside [0,1], which the contract's schema then rejects -- three
        layers away from the line that caused it."""
        with pytest.raises(ConfigurationError):
            RulesSettings(**kwargs)  # type: ignore[arg-type]

    def test_the_valid_case_is_accepted(self) -> None:
        """A floor. A validator that refuses everything passes every assertion
        above."""
        assert RulesSettings(long_input_weight=0.5, long_input_at=100)


class TestTheDecisionStillRecordsWhatProducedIt:
    def test_a_retuned_weight_appears_in_the_published_document(self) -> None:
        """`routing-decision/1` is frozen and carries no settings block, which
        looked like a reproducibility hole once weights became movable. It is
        not one: every signal publishes **its own weight**, so the score can be
        recomputed from the document without knowing the settings that produced
        it."""
        from iriguchi.application.routing import PromptRouter
        from iriguchi.domain.destination import Destination
        from iriguchi.infrastructure.registry import SCANNERS
        from iriguchi.interfaces.contract import as_document

        estimator = RulesEstimator(RulesSettings(long_input_weight=0.77))
        router = PromptRouter(scanner=SCANNERS.build("fallback"), estimator=estimator)
        decision = router.route("a" * 700, frozenset({Destination.LOCAL, Destination.EXTERNAL}))
        document = as_document(decision)
        weights = [s["weight"] for s in document["complexity"]["signals"]]
        assert 0.77 in weights, weights

    def test_the_score_can_be_recomputed_from_the_document_alone(self) -> None:
        """The property that makes the above sufficient. A reader with the
        document and nothing else gets the same number."""
        from math import prod

        from iriguchi.application.routing import PromptRouter
        from iriguchi.domain.destination import Destination
        from iriguchi.infrastructure.registry import SCANNERS
        from iriguchi.interfaces.contract import as_document

        estimator = RulesEstimator(RulesSettings(long_input_weight=0.42))
        router = PromptRouter(scanner=SCANNERS.build("fallback"), estimator=estimator)
        decision = router.route(
            "a" * 700 + " compare both approaches", frozenset({Destination.LOCAL})
        )
        document = as_document(decision)
        published = document["complexity"]
        recomputed = 1 - prod(1 - s["weight"] for s in published["signals"])
        assert recomputed == pytest.approx(published["score"])


class TestTheOneCallReachesThem:
    """`route()` takes an object, not only a name.

    A settings class nobody can reach from the one documented entry point is a
    settings class that exists in the tests. Names are the CLI's vocabulary --
    they have to be strings, and they have to be in a registry. Objects are the
    library's, and they are how a tuned estimator or a third-party detector gets
    in without asking for a registry entry first.
    """

    def test_an_estimator_object_is_used(self) -> None:
        from iriguchi import route

        louder = RulesEstimator(RulesSettings(long_input_weight=0.99))
        assert route("a" * 700, estimator=louder, local=True).complexity.score == 0.99

    def test_the_default_is_unchanged_by_the_new_parameter(self) -> None:
        """The floor that matters: adding an object path must not have quietly
        changed what happens when nobody passes one."""
        from iriguchi import route

        assert route("a" * 700, local=True).complexity.score == pytest.approx(0.3)

    def test_a_scanner_object_is_used(self) -> None:
        from iriguchi import route
        from iriguchi.domain.sensitivity import Finding
        from iriguchi.domain.span import Span

        class Always:
            name = "always"

            def scan(self, text: str) -> tuple[Finding, ...]:
                return (Finding(rule="mine.everything", source="mine", span=Span(0, 1)),)

        decision = route("Summarise this.", scanner=Always(), local=True, external=True)
        assert not decision.leaves_the_machine
        assert [f.source for f in decision.sensitivity.findings] == ["mine"]

    def test_a_name_still_works(self) -> None:
        from iriguchi import route

        assert route("hello", scanner="fallback", local=True).route

    def test_an_unknown_name_is_still_refused(self) -> None:
        """The object path must not have turned a typo into a silent default.
        A string is looked up; only a non-string is taken as an instance."""
        from iriguchi import route

        with pytest.raises(ConfigurationError, match="no scanner called"):
            route("hello", scanner="fallbcak", local=True)

    def test_an_object_and_findings_together_are_still_refused(self) -> None:
        """Two intentions, no way to tell which. The refusal was keyed on
        `scanner is not None`, which an object satisfies too -- worth asserting,
        because a check written for strings is exactly the kind that stops
        covering the new case."""
        from iriguchi import route

        class Quiet:
            name = "quiet"

            def scan(self, text: str) -> tuple[()]:
                return ()

        with pytest.raises(ConfigurationError, match="Pick the one you meant"):
            route("hello", scanner=Quiet(), findings=[], local=True)
