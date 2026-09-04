"""Whether an answer is weak, from its shape and from what it says.

Rules, and no model -- the same constraint the estimator works under, for a
different reason. The estimator has no model because ADR-0004 refuses one in the
deciding path. This one has no model because **a judge that needs a large model
to decide whether to call a large model has not saved anything.**

## Why this can be measured and the estimator cannot

`docs/feasibility.md` F1 records the estimator scoring 42.9% on prompts written
to test it, and the honest caveat attached: those prompts were written by the
same hand that writes the rules, so the number diagnoses and does not validate.

This axis does not have that problem in the same degree. *"Did the model refuse?"*
and *"is this text truncated mid-word?"* are questions about an artefact rather
than predictions about a hypothetical, and two people looking at the same answer
will agree far more often than two people guessing how hard a prompt is. The
signals below are checkable by reading the answer, which is a much lower bar than
checkable by imagining a 3B model's performance.

## The signals, and what each is worth

`refusal` is **decisive** and nothing else is. A model saying "I don't know" has
answered the question about its own adequacy, and no amount of corroboration
makes that more true.

Everything else is a shape proxy that can be wrong about a terse correct answer,
so the shape weights are set by a rule rather than by taste:

    no shape signal crosses the threshold alone
    `repetition` plus any one other shape signal does
    any two shape signals that are not `repetition` do not

`repetition` sits highest because it is the one with **no innocent
explanation**. A truncated answer may be a terse answer that skipped its full
stop; an echo may be a summary task; a short answer may be the right answer. Four
identical lines is a model that has come apart, and nothing else looks like it.

The first draft had `repetition` at 0.5, which put a degenerate *and* truncated
answer at 0.675 -- adequate by two hundredths. That was arithmetic rather than a
decision, and the fix was to state the rule and derive the number from it, not to
nudge the number until an example passed.

That asymmetry is the design. The cost of a false *weak* is a prompt sent
somewhere larger that did not need to go -- and on the external route, that means
off the machine. The cost of a false *adequate* is a disappointing answer the
person can act on themselves. Those are not symmetric, so the thresholds are not.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from ...domain.answer import AnswerSignal, Weakness
from ...domain.span import Span
from ...errors import ConfigurationError

__all__ = ["DEFAULT_JUDGE_SETTINGS", "JudgeSettings", "RulesJudge"]

#: Phrases in which a model declines or disclaims. Matched case-insensitively.
#:
#: Deliberately narrow. `I'm not sure` appears in perfectly good answers that
#: then go on to be useful, and a rule that fires on ordinary hedging would
#: escalate half of everything -- so this list is only the forms where the model
#: is declining rather than qualifying.
_REFUSAL = re.compile(
    r"(?i:"
    r"\bi (?:do not|don't) know\b"
    r"|\bi (?:cannot|can't|am unable to|am not able to)\s+(?:help|assist|answer|do that)"
    r"|\bi (?:do not|don't) have (?:enough |sufficient )?(?:information|context)\b"
    r"|\bas an ai\b"
    r"|\bunable to (?:provide|determine|answer)\b"
    r")"
    r"|わかりません|分かりません|わかりかねます"
    r"|お答えできません|回答できません|情報がありません|判断できません"
)

#: An answer that stops without finishing a sentence. Checked on the last
#: non-space character, so a trailing newline does not hide it.
_TERMINAL = frozenset(".!?)]}\"'`。！？」』）】…:;")

#: Splitting for the repetition check. Lines first, because a repeating model
#: usually repeats whole lines.
_LINES = re.compile(r"[\n\r]+")


@dataclass(frozen=True, slots=True)
class JudgeSettings:
    """Every number this judge uses, reachable for the same reason the
    estimator's are: a deployment whose answers do not look like these had to
    fork the library to move one, and that is not a tuning story.

    Args:
        refusal_weight: What an explicit refusal is worth. Decisive regardless,
            so this only affects the reported score.
        truncated_weight: An answer that stops mid-sentence.
        repetition_weight: The same line repeated. A classic small-model
            failure and the least ambiguous shape signal.
        repetition_at: How many times a line must repeat before it counts. Two
            is normal in a list; this is about degeneration.
        echo_weight: The answer largely restates the prompt.
        echo_share: How much of the answer has to be prompt content.
        short_weight: A very short answer to a long request.
        short_ratio: Answer length as a share of prompt length, below which the
            answer is suspiciously brief.
        short_floor: Prompts shorter than this never trigger the length rule.
            A one-line question deserves a one-line answer, and without this the
            rule fires on every good short exchange.

    Raises:
        ConfigurationError: for a weight outside [0,1] or a non-positive count.
    """

    refusal_weight: float = 0.95
    truncated_weight: float = 0.35
    repetition_weight: float = 0.6
    repetition_at: int = 3
    echo_weight: float = 0.4
    echo_share: float = 0.6
    short_weight: float = 0.3
    short_ratio: float = 0.2
    short_floor: int = 200
    #: Per-rule overrides, by rule id, exactly as `RulesSettings` has.
    weights: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        for name in (
            "refusal_weight",
            "truncated_weight",
            "repetition_weight",
            "echo_weight",
            "echo_share",
            "short_weight",
            "short_ratio",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ConfigurationError(f"{name} is {value}, not a share in [0, 1]")
        for name in ("repetition_at", "short_floor"):
            if getattr(self, name) < 1:
                raise ConfigurationError(f"{name} is {getattr(self, name)}, which fires on nothing")
        for rule, weight in self.weights.items():
            if not 0.0 <= weight <= 1.0:
                raise ConfigurationError(f"the override for {rule!r} is {weight}, not in [0,1]")

    def weight_for(self, rule: str, default: float) -> float:
        return self.weights.get(rule, default)


DEFAULT_JUDGE_SETTINGS = JudgeSettings()


class RulesJudge:
    """The judge iriguchi ships with. Rules, and no model."""

    name = "rules"

    def __init__(self, settings: JudgeSettings | None = None) -> None:
        self.settings = DEFAULT_JUDGE_SETTINGS if settings is None else settings

    def judge(self, prompt: str, answer: str) -> Sequence[AnswerSignal]:
        """Every reason this answer might not be good enough.

        An empty or whitespace-only answer is the strongest case there is and is
        reported as a refusal: the model produced nothing, which is the same
        information as saying it could not.
        """
        settings = self.settings
        signals: list[AnswerSignal] = []

        if not answer.strip():
            return (
                AnswerSignal(
                    rule="judge.no-answer",
                    kind=Weakness.STATED,
                    weight=settings.weight_for("judge.no-answer", settings.refusal_weight),
                    decisive=True,
                ),
            )

        match = _REFUSAL.search(answer)
        if match is not None:
            signals.append(
                AnswerSignal(
                    rule="judge.refusal",
                    kind=Weakness.STATED,
                    weight=settings.weight_for("judge.refusal", settings.refusal_weight),
                    decisive=True,
                    span=Span(*match.span()),
                )
            )

        stripped = answer.rstrip()
        if stripped and stripped[-1] not in _TERMINAL:
            signals.append(
                AnswerSignal(
                    rule="judge.truncated",
                    kind=Weakness.SHAPE,
                    weight=settings.weight_for("judge.truncated", settings.truncated_weight),
                )
            )

        lines = [line.strip() for line in _LINES.split(answer) if line.strip()]
        if lines:
            most = max(lines.count(line) for line in set(lines))
            if most >= settings.repetition_at:
                signals.append(
                    AnswerSignal(
                        rule="judge.repetition",
                        kind=Weakness.SHAPE,
                        weight=settings.weight_for("judge.repetition", settings.repetition_weight),
                    )
                )

        if _echoes(prompt, answer, settings.echo_share):
            signals.append(
                AnswerSignal(
                    rule="judge.echoes-the-prompt",
                    kind=Weakness.SHAPE,
                    weight=settings.weight_for("judge.echoes-the-prompt", settings.echo_weight),
                )
            )

        if len(prompt) >= settings.short_floor and len(answer) < len(prompt) * settings.short_ratio:
            signals.append(
                AnswerSignal(
                    rule="judge.too-short-for-the-request",
                    kind=Weakness.SHAPE,
                    weight=settings.weight_for(
                        "judge.too-short-for-the-request", settings.short_weight
                    ),
                )
            )

        return tuple(signals)


def _echoes(prompt: str, answer: str, share: float) -> bool:
    """Whether the answer is mostly the prompt handed back.

    Compared over whitespace-separated tokens, which is crude and is the point:
    a model that has restated the request instead of answering it produces an
    overlap that survives any reasonable tokenisation. Japanese has no spaces,
    so this is weaker there -- recorded rather than papered over, the same gap
    `complexity.dense-vocabulary` has and for the same reason.
    """
    answer_tokens = answer.split()
    if not answer_tokens:
        return False
    prompt_tokens = {token for token in prompt.split() if len(token) > 2}
    if not prompt_tokens:
        return False
    shared = sum(1 for token in answer_tokens if token in prompt_tokens)
    return shared / len(answer_tokens) >= share
