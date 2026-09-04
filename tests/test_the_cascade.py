"""Answer locally, look at what came back, escalate only if it was poor.

The axis that does not have to guess. `docs/feasibility.md` F1 measured the
complexity estimator at **42.9%** on prompts written to test it -- eleven of the
thirteen hardest kept local, because the request did not announce its own
difficulty. That is the ceiling on predicting how hard a prompt will be *before
anybody has tried*.

A cascade sidesteps the prediction. It inspects an artefact instead of imagining
one.

## The two invariants this file exists to hold

**ADR-0004 survives because the first hop is local.** That ADR pins the router at
"before the request, always", and says a decision made after a first response is
made after the text was already sent. That objection is about text *leaving the
machine* -- and a local answer never left it. So a cascade whose first hop is
external is not a cascade, and `may_escalate` refuses one.

**The veto is not re-litigated.** A weak answer is evidence about a model, not
about sensitivity. If a finding removed the external destination it stays
removed, however disappointing the local answer was. The alternative -- "the
answer was bad enough to be worth the risk" -- is the exact trade this project
exists to refuse, and `may_escalate` is not even given the prompt, so it cannot
make it.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from iriguchi.domain.answer import (
    DEFAULT_ADEQUACY,
    Adequacy,
    AnswerQuality,
    AnswerSignal,
    Weakness,
)
from iriguchi.domain.cascade import may_escalate
from iriguchi.domain.complexity import Complexity, ComplexityBand
from iriguchi.domain.decision import RoutingDecision
from iriguchi.domain.destination import Destination, Route
from iriguchi.domain.reason import Reason, Removal
from iriguchi.domain.sensitivity import Sensitivity, SensitivityLevel
from iriguchi.infrastructure.judges import DEFAULT_JUDGE_SETTINGS, JudgeSettings, RulesJudge

BOTH = frozenset({Destination.LOCAL, Destination.EXTERNAL})
LOCAL_ONLY = frozenset({Destination.LOCAL})

WEAK = AnswerQuality.from_signals(
    [AnswerSignal(rule="judge.refusal", kind=Weakness.STATED, weight=0.95, decisive=True)]
)
FINE = AnswerQuality.from_signals([])


def _decision(
    route: Route = Route.LOCAL,
    *,
    removed_external: bool = False,
    level: SensitivityLevel = SensitivityLevel.CLEAR,
) -> RoutingDecision:
    removed: tuple[Removal, ...] = ()
    if removed_external:
        removed = (
            Removal(
                destination=Destination.EXTERNAL,
                reason=Reason(
                    rule="policy.restricted",
                    source="policy",
                    span=None,
                    detail="a finding",
                ),
            ),
        )
    return RoutingDecision(
        route=route,
        sensitivity=Sensitivity(level=level, findings=()),
        complexity=Complexity(band=ComplexityBand.LOW, score=0.0),
        reasons=(),
        removed=removed,
    )


class TestTheVetoIsNotReLitigated:
    """The invariant that matters more than the feature."""

    def test_a_weak_answer_does_not_reopen_a_removed_destination(self) -> None:
        verdict = may_escalate(_decision(removed_external=True), WEAK, BOTH)
        assert not verdict.escalate
        assert "not evidence about sensitivity" in verdict.reason.detail

    def test_it_stays_refused_however_bad_the_answer_is(self) -> None:
        """Every weakness at once, on a prompt whose external route was
        removed. There is no amount of disappointment that buys a leak."""
        everything = AnswerQuality.from_signals(
            [
                AnswerSignal("judge.refusal", Weakness.STATED, 0.95, decisive=True),
                AnswerSignal("judge.repetition", Weakness.SHAPE, 0.6),
                AnswerSignal("judge.truncated", Weakness.SHAPE, 0.35),
            ]
        )
        assert everything.is_weak
        assert not may_escalate(_decision(removed_external=True), everything, BOTH)

    def test_the_gate_is_never_given_the_prompt(self) -> None:
        """Structural, not behavioural. A function that cannot see the text
        cannot be talked into re-scanning it with a weaker scanner, and this is
        the assertion that keeps it that way."""
        import inspect

        parameters = set(inspect.signature(may_escalate).parameters)
        assert parameters == {"decision", "quality", "available"}
        assert "prompt" not in parameters and "text" not in parameters


class TestTheFirstHopMustBeLocal:
    def test_an_external_answer_does_not_cascade(self) -> None:
        """ADR-0004 survives because nothing left the machine to inform the
        second decision. A cascade from an external answer would break exactly
        that, so there is no such thing."""
        verdict = may_escalate(_decision(Route.EXTERNAL), WEAK, BOTH)
        assert not verdict.escalate
        assert "already" in verdict.reason.detail

    def test_a_refusal_has_nothing_to_escalate_from(self) -> None:
        verdict = may_escalate(_decision(Route.REFUSED), WEAK, BOTH)
        assert not verdict.escalate
        assert "no local answer" in verdict.reason.detail


class TestWhatItDoesPermit:
    def test_a_weak_answer_on_a_permitted_prompt_escalates(self) -> None:
        verdict = may_escalate(_decision(), WEAK, BOTH)
        assert verdict.escalate
        assert "judge.refusal" in verdict.reason.detail

    def test_an_adequate_answer_does_not(self) -> None:
        verdict = may_escalate(_decision(), FINE, BOTH)
        assert not verdict.escalate
        assert verdict.reason.rule == "cascade.answer-was-adequate"

    def test_a_missing_endpoint_is_not_a_refusal(self) -> None:
        """`removed` being empty means nothing was taken away, which is not the
        same as something having been there. Conflating those is the defect this
        project has found in three places, so the gate is handed `available`
        rather than left to infer it."""
        verdict = may_escalate(_decision(), WEAK, LOCAL_ONLY)
        assert not verdict.escalate
        assert "missing endpoint" in verdict.reason.detail

    def test_every_branch_carries_a_reason(self) -> None:
        """There is no branch that returns a bare False."""
        for decision, quality, available in (
            (_decision(Route.REFUSED), WEAK, BOTH),
            (_decision(Route.EXTERNAL), WEAK, BOTH),
            (_decision(), WEAK, LOCAL_ONLY),
            (_decision(removed_external=True), WEAK, BOTH),
            (_decision(), FINE, BOTH),
            (_decision(), WEAK, BOTH),
        ):
            verdict = may_escalate(decision, quality, available)
            assert verdict.reason.detail.strip()
            assert verdict.reason.source == "cascade"


class TestTheJudgeReadsTheAnswer:
    JUDGE = RulesJudge()

    def _quality(self, prompt: str, answer: str) -> AnswerQuality:
        return AnswerQuality.from_signals(self.JUDGE.judge(prompt, answer))

    @pytest.mark.parametrize(
        "answer",
        [
            "I do not know how to do that.",
            "I cannot help with that request.",
            "As an AI, I am unable to provide that.",
            "申し訳ありませんが、わかりません。",
            "その情報がありません。",
        ],
        ids=["dont know", "cannot help", "as an ai", "japanese", "no information"],
    )
    def test_a_stated_refusal_is_decisive(self, answer: str) -> None:
        """A model saying it could not help has answered the question about its
        own adequacy. Corroboration adds nothing."""
        quality = self._quality("Prove the lemma.", answer)
        assert quality.is_weak
        assert quality.decided_outright

    def test_an_empty_answer_is_the_same_information(self) -> None:
        quality = self._quality("Prove the lemma.", "   \n  ")
        assert quality.is_weak and quality.decided_outright

    def test_a_good_answer_produces_no_signals(self) -> None:
        """The floor. A judge that finds something in everything escalates
        everything, which is the same as having no local model."""
        quality = self._quality(
            "Prove the lemma.",
            "By induction on n. The base case holds trivially, and the inductive step "
            "follows from the hypothesis.",
        )
        assert quality.signals == ()
        assert quality.adequacy is Adequacy.ADEQUATE

    def test_a_terse_correct_answer_is_not_weak(self) -> None:
        """The false-weak this design is most worried about. `2` is the right
        answer to `1 + 1` and must not be escalated."""
        assert not self._quality("What is 1 + 1?", "2.").is_weak

    def test_degeneration_plus_one_other_signal_is_weak(self) -> None:
        quality = self._quality("Summarise this.", "ok ok\nok ok\nok ok\nok ok")
        assert {s.rule for s in quality.signals} >= {"judge.repetition"}
        assert quality.is_weak

    def test_an_echo_of_the_prompt_is_noticed(self) -> None:
        prompt = "Explain the difference between a process and a thread with an example."
        assert "judge.echoes-the-prompt" in {
            s.rule for s in self.JUDGE.judge(prompt, prompt + " " + prompt)
        }

    def test_a_short_answer_to_a_long_request(self) -> None:
        long_prompt = "Plan the migration in detail. " * 12
        assert "judge.too-short-for-the-request" in {
            s.rule for s in self.JUDGE.judge(long_prompt, "Do it carefully.")
        }

    def test_a_short_answer_to_a_short_request_is_fine(self) -> None:
        """Without the floor this rule fires on every good short exchange."""
        assert self.JUDGE.judge("What time is it?", "Ten past three.") == ()

    def test_it_satisfies_the_port(self) -> None:
        from iriguchi.ports.judge import AnswerJudge

        assert isinstance(self.JUDGE, AnswerJudge)

    def test_the_same_pair_twice_is_the_same_answer(self) -> None:
        pair = ("Prove it.", "I do not know.\nI do not know.")
        assert self.JUDGE.judge(*pair) == self.JUDGE.judge(*pair)

    def test_no_signal_carries_the_answer_text(self) -> None:
        """ADR-0006 applies here too: rule ids and spans, never a value."""
        answer = "I do not know, pomegranate."
        for signal in self.JUDGE.judge("Prove it.", answer):
            assert "pomegranate" not in repr(signal)


class TestTheWeightsFollowTheStatedRule:
    """The shape weights are derived from a rule, not chosen by taste.

        no shape signal crosses the threshold alone
        `repetition` plus any one other shape signal does
        any two shape signals that are not `repetition` do not

    The first draft had `repetition` at 0.5, which put a degenerate *and*
    truncated answer at 0.675 -- adequate by two hundredths. That was arithmetic
    rather than a decision. This is the test that keeps it a decision.
    """

    SHAPE: ClassVar[dict[str, float]] = {
        "repetition": DEFAULT_JUDGE_SETTINGS.repetition_weight,
        "truncated": DEFAULT_JUDGE_SETTINGS.truncated_weight,
        "echo": DEFAULT_JUDGE_SETTINGS.echo_weight,
        "short": DEFAULT_JUDGE_SETTINGS.short_weight,
    }

    @staticmethod
    def _combined(*weights: float) -> float:
        from math import prod

        return 1.0 - prod(1.0 - w for w in weights)

    @pytest.mark.parametrize("name", list(SHAPE))
    def test_no_shape_signal_decides_alone(self, name: str) -> None:
        assert self.SHAPE[name] < DEFAULT_ADEQUACY

    @pytest.mark.parametrize("other", ["truncated", "echo", "short"])
    def test_repetition_plus_any_other_crosses(self, other: str) -> None:
        assert self._combined(self.SHAPE["repetition"], self.SHAPE[other]) >= DEFAULT_ADEQUACY

    @pytest.mark.parametrize(
        "pair", [("truncated", "echo"), ("truncated", "short"), ("echo", "short")]
    )
    def test_two_milder_signals_do_not(self, pair: tuple[str, str]) -> None:
        assert self._combined(*(self.SHAPE[n] for n in pair)) < DEFAULT_ADEQUACY

    def test_repetition_is_the_highest_shape_weight(self) -> None:
        """Because it is the one with no innocent explanation."""
        assert self.SHAPE["repetition"] == max(self.SHAPE.values())


class TestItsNumbersAreReachable:
    def test_an_override_moves_a_signal(self) -> None:
        judge = RulesJudge(JudgeSettings(weights={"judge.truncated": 0.9}))
        [signal] = [s for s in judge.judge("Prove it.", "Because") if s.rule == "judge.truncated"]
        assert signal.weight == 0.9

    @pytest.mark.parametrize(
        "kwargs",
        [{"repetition_weight": 1.5}, {"short_ratio": -0.1}, {"repetition_at": 0}],
        ids=["weight above one", "negative share", "count of zero"],
    )
    def test_settings_that_cannot_mean_anything_are_refused(
        self, kwargs: dict[str, object]
    ) -> None:
        from iriguchi.errors import ConfigurationError

        with pytest.raises(ConfigurationError):
            JudgeSettings(**kwargs)  # type: ignore[arg-type]

    def test_the_defaults_are_the_shipped_ones(self) -> None:
        assert RulesJudge().settings == DEFAULT_JUDGE_SETTINGS
