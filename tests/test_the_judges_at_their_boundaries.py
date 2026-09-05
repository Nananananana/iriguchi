"""Every boundary the mutation run walked through untouched.

`python tools/mutate.py --target "src/iriguchi/infrastructure/judges/*.py"` left
**26 survivors** on code that had just been written and tested. Every one of them
is a change the suite could not tell from the truth, and they fall into four
groups:

    0.0 <= v <= 1.0  ->  0.0 < v < 1.0     a weight of exactly 1.0 was refused
    most >= at       ->  most > at         a line repeated exactly three times
    agreed >= cut    ->  agreed > cut      agreement landing exactly on the cut
    repetition_at 3  ->  4                 the shipped default was never pinned

None of those is exotic. They are the values a threshold is *for* -- the ones
sitting exactly on it -- and a test suite that only ever tries values comfortably
either side of a boundary is testing that the comparison exists, not that it is
the right one.

The `frozen=True -> False` and `slots=True -> False` survivors are the same gap
the domain has a sweep for (`test_what_the_mutants_survived.py`), which only
covers `domain/`. The settings objects live in `infrastructure/` and had nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

from iriguchi.domain.answer import AnswerQuality
from iriguchi.errors import ConfigurationError
from iriguchi.infrastructure.judges import (
    DEFAULT_CONSISTENCY,
    ConsistencyJudge,
    ConsistencySettings,
    JudgeSettings,
    RulesJudge,
)
from iriguchi.infrastructure.judges.consistency import agreement
from iriguchi.infrastructure.judges.rules import DEFAULT_JUDGE_SETTINGS


class _Model:
    """Returns a fixed answer. Enough to reach the agreement comparison."""

    name = "fake"

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def answer(self, prompt: str) -> str:
        return self._reply


class TestTheEndsOfTheRangeAreInside:
    """`0.0 <= v <= 1.0` and not `<`. A weight of exactly 1.0 is a certainty
    and exactly 0.0 is a rule somebody switched off; both are legitimate, and
    the mutation that refused them survived because nothing tried them."""

    @pytest.mark.parametrize("value", [0.0, 1.0])
    def test_a_rules_weight_may_sit_on_either_end(self, value: float) -> None:
        assert JudgeSettings(truncated_weight=value).truncated_weight == value

    @pytest.mark.parametrize("value", [0.0, 1.0])
    def test_an_override_may_too(self, value: float) -> None:
        assert (
            JudgeSettings(weights={"judge.truncated": value}).weight_for("judge.truncated", 0.5)
            == value
        )

    @pytest.mark.parametrize("value", [0.0, 1.0])
    def test_a_consistency_share_may_too(self, value: float) -> None:
        assert ConsistencySettings(agrees_above=value).agrees_above == value

    @pytest.mark.parametrize("value", [-0.000001, 1.000001])
    def test_and_just_outside_is_still_refused(self, value: float) -> None:
        """The floor for the three above: a validator that accepts everything
        passes them all."""
        with pytest.raises(ConfigurationError):
            JudgeSettings(truncated_weight=value)
        with pytest.raises(ConfigurationError):
            ConsistencySettings(agrees_above=value)

    @pytest.mark.parametrize("field", ["repetition_at", "short_floor"])
    def test_a_count_of_exactly_one_is_allowed(self, field: str) -> None:
        """`< 1` and not `< 2`. One is degenerate for `repetition_at` and
        perfectly sensible for `short_floor`, and the check is about zero."""
        assert getattr(JudgeSettings(**{field: 1}), field) == 1  # type: ignore[arg-type]

    @pytest.mark.parametrize("field", ["repetition_at", "short_floor"])
    def test_a_count_of_zero_is_not(self, field: str) -> None:
        with pytest.raises(ConfigurationError):
            JudgeSettings(**{field: 0})  # type: ignore[arg-type]

    def test_two_samples_is_allowed_and_one_is_not(self) -> None:
        assert ConsistencySettings(samples=2).samples == 2
        with pytest.raises(ConfigurationError):
            ConsistencySettings(samples=1)


class TestExactlyOnTheThreshold:
    """`>=` and not `>`. The value sitting precisely on a threshold is the one
    the threshold exists to classify, and every one of these mutations survived
    because the suite only tried values either side."""

    def test_a_line_repeated_exactly_the_threshold_number_of_times_fires(self) -> None:
        """`repetition_at` is 3, so three identical lines is degeneration and
        two is a list."""
        judge = RulesJudge()
        # The terminal punctuation goes on its own trailing line, or the third
        # repeat would differ from the first two by a full stop and the count
        # would be 2 -- which is what the first version of this test measured.
        three = "same line\nsame line\nsame line\ndone."
        two = "same line\nsame line\ndone."
        assert "judge.repetition" in {s.rule for s in judge.judge("q", three)}
        assert "judge.repetition" not in {s.rule for s in judge.judge("q", two)}

    def test_a_prompt_exactly_at_the_short_floor_is_eligible(self) -> None:
        """`len(prompt) >= short_floor`. At exactly 200 characters the length
        rule applies; at 199 it does not, whatever the answer looks like."""
        judge = RulesJudge()
        answer = "no."
        at = "x" * DEFAULT_JUDGE_SETTINGS.short_floor
        below = "x" * (DEFAULT_JUDGE_SETTINGS.short_floor - 1)
        assert "judge.too-short-for-the-request" in {s.rule for s in judge.judge(at, answer)}
        assert "judge.too-short-for-the-request" not in {s.rule for s in judge.judge(below, answer)}

    def test_both_halves_of_the_length_rule_are_required(self) -> None:
        """`and`, not `or`. A long prompt with a long answer must not fire, and
        neither must a short prompt with a short answer -- the `And -> Or`
        mutation makes both of those fire and nothing noticed."""
        judge = RulesJudge()
        long_prompt = "x" * 400
        long_answer = "y" * 400 + "."
        assert judge.judge(long_prompt, long_answer) == ()
        assert judge.judge("short?", "short.") == ()

    def test_agreement_exactly_on_the_cut_is_consistent(self) -> None:
        """`agreed >= agrees_above`. Landing exactly on the threshold means
        agreeing, not disagreeing -- the same direction every other comparison
        in this project takes."""
        answer = "abcd"
        exact = agreement([answer, answer])
        judge = ConsistencyJudge(_Model(answer), ConsistencySettings(agrees_above=exact))
        assert judge.judge("q", answer) == ()

    def test_and_a_hair_above_the_cut_disagrees(self) -> None:
        """The floor: a judge that never objects passes the assertion above."""
        answer = "abcd"
        judge = ConsistencyJudge(
            _Model("completely unrelated"), ConsistencySettings(agrees_above=1.0)
        )
        assert [s.rule for s in judge.judge("q", answer)] == ["judge.inconsistent"]

    def test_the_echo_share_is_inclusive(self) -> None:
        """`shared / len(answer) >= share`. An answer that is exactly the
        configured share of prompt tokens echoes."""
        judge = RulesJudge(JudgeSettings(echo_share=0.5))
        # Two of four answer tokens appear in the prompt: exactly 0.5.
        signals = {s.rule for s in judge.judge("alpha beta gamma", "alpha beta xxx yyy.")}
        assert "judge.echoes-the-prompt" in signals


class TestTheEchoCheckReturnsEarly:
    """Two `return False` lines that no test reached, so flipping them to
    `True` changed nothing observable."""

    def test_an_answer_of_only_whitespace_between_words_does_not_echo(self) -> None:
        """`answer.split()` empty. It cannot be reached through `judge` -- an
        empty answer is caught as `no-answer` first -- so it is reached here
        directly, which is the honest way to cover an internal guard."""
        from iriguchi.infrastructure.judges.rules import _echoes

        assert _echoes("a prompt with words", "   ", 0.6) is False

    def test_a_prompt_of_only_short_tokens_does_not_echo(self) -> None:
        """`prompt_tokens` empty, because every token is 3 characters or fewer.
        Without this the rule would divide by an empty set's worth of nothing
        and call every answer an echo."""
        from iriguchi.infrastructure.judges.rules import _echoes

        assert _echoes("a b c to of", "a b c to of", 0.6) is False

    def test_a_token_of_exactly_three_characters_is_ignored(self) -> None:
        """`len(token) > 2` -- so three characters counts and two does not.
        The boundary decides whether `the` and `and` drag every answer over the
        echo threshold."""
        from iriguchi.infrastructure.judges.rules import _echoes

        assert _echoes("abc", "abc abc", 0.9) is True
        assert _echoes("ab", "ab ab", 0.9) is False


class TestTheShippedDefaults:
    """Pinned, because a published measurement describes the numbers that were
    in force when it was taken. `repetition_at` and `short_floor` were the two
    the earlier test forgot, and both mutated freely."""

    def test_every_rules_default(self) -> None:
        assert DEFAULT_JUDGE_SETTINGS.refusal_weight == 0.95
        assert DEFAULT_JUDGE_SETTINGS.truncated_weight == 0.35
        assert DEFAULT_JUDGE_SETTINGS.repetition_weight == 0.6
        assert DEFAULT_JUDGE_SETTINGS.repetition_at == 3
        assert DEFAULT_JUDGE_SETTINGS.echo_weight == 0.4
        assert DEFAULT_JUDGE_SETTINGS.echo_share == 0.6
        assert DEFAULT_JUDGE_SETTINGS.short_weight == 0.3
        assert DEFAULT_JUDGE_SETTINGS.short_ratio == 0.2
        assert DEFAULT_JUDGE_SETTINGS.short_floor == 200

    def test_every_consistency_default(self) -> None:
        settings = ConsistencySettings()
        assert settings.agrees_above == DEFAULT_CONSISTENCY == 0.10
        assert settings.samples == 2
        assert settings.weight == 0.75


class TestTheSettingsAreValues:
    """The sweep `domain/` has, for the two settings objects that live in
    `infrastructure/` and had none. `frozen=True -> False` survived on both."""

    @pytest.mark.parametrize(
        "settings",
        [JudgeSettings(), ConsistencySettings()],
        ids=["JudgeSettings", "ConsistencySettings"],
    )
    def test_it_cannot_be_assigned_to(self, settings: object) -> None:
        field = next(iter(dataclasses.fields(settings)))  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(settings, field.name, getattr(settings, field.name))

    @pytest.mark.parametrize(
        "settings",
        [JudgeSettings(), ConsistencySettings()],
        ids=["JudgeSettings", "ConsistencySettings"],
    )
    def test_it_has_no_dict(self, settings: object) -> None:
        """`slots=True`. Without it a typo assigns a new attribute instead of
        raising, which is how a setting silently stops being read."""
        assert not hasattr(settings, "__dict__")

    @pytest.mark.parametrize(
        "settings",
        [JudgeSettings(), ConsistencySettings()],
        ids=["JudgeSettings", "ConsistencySettings"],
    )
    def test_two_of_the_same_are_equal(self, settings: object) -> None:
        assert settings == type(settings)()


class TestTheJudgesAgreeWithTheDomain:
    """A signal is only worth what the domain does with it, and both judges
    hand theirs to the same `AnswerQuality.from_signals`."""

    def test_a_single_inconsistency_is_weak_on_its_own(self) -> None:
        """0.75 against a 0.7 threshold. The consistency judge emits exactly one
        signal, so if it did not cross alone the judge would never escalate --
        which is the failure the rules judge was measured having."""
        # An explicit strict threshold, because two short unrelated strings
        # agree at 0.207 on `SequenceMatcher` -- they share spaces and common
        # letters, which is exactly why the shipped default is 0.10, and why a
        # test leaning on two strings falling below it would be testing the
        # strings rather than the judge.
        judge = ConsistencyJudge(
            _Model("completely different"), ConsistencySettings(agrees_above=1.0)
        )
        quality = AnswerQuality.from_signals(judge.judge("q", "an answer"))
        assert quality.is_weak

    def test_and_it_is_not_decisive(self) -> None:
        """A model can be consistently wrong, so disagreement is evidence about
        confidence rather than a verdict. `decided_outright` is reserved for a
        stated refusal."""
        judge = ConsistencyJudge(
            _Model("completely different"), ConsistencySettings(agrees_above=1.0)
        )
        quality = AnswerQuality.from_signals(judge.judge("q", "an answer"))
        assert not quality.decided_outright


class TestTheLastTwoSurvivors:
    """The two the first round of these tests still could not tell from the
    truth. 26 survivors became 2, and these are them."""

    def test_an_answer_exactly_at_the_length_ratio_is_not_too_short(self) -> None:
        """`len(answer) < len(prompt) * short_ratio`, strictly. A 200-character
        prompt puts the line at exactly 40; an answer of 40 is not below it.

        The `Lt -> LtE` mutant flips only this one case, which is why nothing
        that tried 39 or 41 could see it.
        """
        judge = RulesJudge()
        prompt = "x" * DEFAULT_JUDGE_SETTINGS.short_floor  # 200 -> boundary at 40.0
        exactly = "y" * 40
        below = "y" * 39
        assert "judge.too-short-for-the-request" not in {
            s.rule for s in judge.judge(prompt, exactly)
        }
        assert "judge.too-short-for-the-request" in {s.rule for s in judge.judge(prompt, below)}

    def test_each_shared_token_counts_once(self) -> None:
        """`sum(1 for ...)`, not 2. Counting each shared token twice doubles the
        overlap, so an answer that is genuinely half prompt-content would read
        as entirely prompt-content and echo.

        Half is the case that separates them: 0.5 is under the 0.6 default and
        1.0 is over it.
        """
        from iriguchi.infrastructure.judges.rules import _echoes

        half = _echoes("alpha beta gamma", "alpha beta xxx yyy", 0.6)
        assert half is False, "two of four tokens shared is 0.5, which is under 0.6"
        # And the floor: the same tokens against a threshold 0.5 does echo, so
        # the assertion above is about the ratio rather than about the rule
        # having been switched off.
        assert _echoes("alpha beta gamma", "alpha beta xxx yyy", 0.5) is True
