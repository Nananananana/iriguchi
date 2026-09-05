"""Ask twice. A model that is unsure answers differently each time.

The rules judge was measured and it does nothing. Over 42 request prompts
answered by a real 7B model it judged **0 of 42** weak, and 0 of 42 again for a
14B model. Signals fired -- `repetition` five times on the small model and once
on the large -- but never enough to cross a threshold, and lowering that
threshold to make it fire would be fitting a number to a wish.

The reason is not a bad rule set. It is the one the registry entry already
stated as the trade: **a confident wrong answer looks exactly like a confident
right one**, and an instruct-tuned model almost never says "I don't know" to an
ordinary work request. Every signal available to a rule over the answer text was
looking at the wrong surface.

## What does separate them

Sampling the same prompt twice, at a temperature that lets the model wander, and
measuring how much the two answers agree. Over the same 42 prompts and the same
7B model:

| labelled band | median agreement | escalated at the default |
|---|---:|---:|
| `low` | **0.435** | **0%** |
| `moderate` | 0.088 | 57% |
| `high` | 0.101 | 62% |

A **4.3x** separation between easy and not-easy. It does not distinguish
`moderate` from `high` -- those two are the same number -- and it does not need
to: the cascade asks *escalate or not*, which is binary, and this separates the
half that matters.

The rules judge fired on 0 of these 42. This one escalates none of the easy ones
and roughly six in ten of the rest.

This is self-consistency, the standard sampling-based way of estimating a
model's uncertainty about its own output. Nothing here is novel; what is worth
saying is that it works at 7B, locally, with one extra call.

## Three costs, stated

**It doubles local latency.** Two calls where there was one -- a 2.3s median
becomes about 4.6s. That is the price of the signal and it is why this judge is
not the default.

**It is not deterministic.** Everything else in this project answers identically
twice in a row, on purpose. This cannot: it works *because* the model wanders,
so the same prompt can be judged adequate once and weak the next time. The
decision the judge feeds -- `may_escalate` -- stays deterministic given a
quality; the quality itself is a sample. A caller who needs reproducibility
should record the `AnswerQuality` rather than expect to recompute it.

**It puts a model in the judging path.** Not the *deciding* path: ADR-0004
governs where a prompt is allowed to go, and that decision is made before any of
this runs and is untouched. This is a local model, judging a local answer, after
the fact -- the same argument ADR-0018 makes for the cascade itself, and it
holds for the same reason: nothing leaves the machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations

from ...domain.answer import AnswerSignal, Weakness
from ...errors import ConfigurationError, JudgementError, ModelError
from ...ports.model import Model

__all__ = ["DEFAULT_CONSISTENCY", "ConsistencyJudge", "ConsistencySettings"]

#: Where agreement stops looking like confidence.
#:
#: **Chosen from a curve by a stated rule, not by taste.** Agreement was
#: recorded for all 42 request prompts against a 7B model, and the escalation
#: rate computed at each threshold:
#:
#:     threshold    low   moderate   high    all
#:          0.05     0%         7%    23%    10%
#:          0.10     0%        57%    62%    38%
#:          0.15    27%        57%    92%    57%
#:          0.25    40%        86%   100%    74%
#:
#: The rule is **the highest threshold at which no `low` prompt escalates**, and
#: it picks 0.10. Not the largest gap -- 0.15 separates the bands slightly
#: better -- because the costs are not symmetric: a false *weak* sends a prompt
#: off the machine, and 0.15 does that to 27% of the easy ones for six points of
#: discrimination.
#:
#: It describes one model on 42 prompts, and the measurement is a sample rather
#: than a constant: re-running it moves these numbers by several points, because
#: the judge is non-deterministic by construction. A starting point in exactly
#: the sense `tools/calibrate.py` means -- re-derive it against your own traffic
#: before trusting it to describe yours.
DEFAULT_CONSISTENCY = 0.10


@dataclass(frozen=True, slots=True)
class ConsistencySettings:
    """The numbers this judge uses.

    Args:
        agrees_above: Agreement at or above which the answers are consistent
            enough to be called confident.
        samples: How many times to ask. Two is the cheapest thing that can
            disagree; more is a better estimate and a linear cost.
        weight: What disagreement is worth as a signal. Not decisive: a model
            can be consistently wrong, and consistency is evidence about
            confidence rather than about correctness.

    Raises:
        ConfigurationError: for a share outside [0,1] or fewer than two samples.
    """

    agrees_above: float = DEFAULT_CONSISTENCY
    samples: int = 2
    weight: float = 0.75

    def __post_init__(self) -> None:
        for name in ("agrees_above", "weight"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ConfigurationError(f"{name} is {value}, not a share in [0, 1]")
        if self.samples < 2:
            raise ConfigurationError(
                f"samples is {self.samples}; one answer cannot disagree with itself, "
                f"so this judge needs at least two"
            )


def agreement(answers: Sequence[str]) -> float:
    """How much a set of answers agree, as the mean pairwise similarity.

    `SequenceMatcher` over characters, which is crude and deliberately so: it
    needs no tokenizer, no embedding and no model, so the judge's only dependency
    is the one it already has. It is harsh on free-form prose -- two good answers
    to the same question score well under 1.0 -- and that does not matter,
    because the threshold is calibrated against the same harshness.

    Returns 1.0 for a single answer: nothing disagreed, which is the honest
    reading of one sample even though it is not evidence.
    """
    if len(answers) < 2:
        return 1.0
    scores = [SequenceMatcher(None, a, b).ratio() for a, b in combinations(answers, 2)]
    return sum(scores) / len(scores)


class ConsistencyJudge:
    """Asks the local model again and compares.

    Args:
        model: The **local** model that produced the answer. Asking a different
            one would measure the difference between two models rather than one
            model's confidence, and asking a remote one would send the prompt
            somewhere to decide whether to send the prompt somewhere.
        settings: The numbers.
    """

    name = "consistency"

    def __init__(self, model: Model, settings: ConsistencySettings | None = None) -> None:
        self._model = model
        self.settings = ConsistencySettings() if settings is None else settings

    def judge(self, prompt: str, answer: str) -> Sequence[AnswerSignal]:
        """Re-ask, and report disagreement as a signal.

        The answer already in hand counts as one of the samples, so `samples=2`
        costs exactly one extra call.

        Raises:
            JudgementError: if the model cannot be re-asked. Raised rather than
                returning nothing: no signals means *the answer looked fine*,
                and a judge that could not run has not formed that opinion.
        """
        answers = [answer]
        try:
            for _ in range(self.settings.samples - 1):
                answers.append(self._model.answer(prompt))
        except ModelError as failure:
            raise JudgementError(
                f"the local model could not be re-asked to check its own "
                f"consistency: {failure}. No opinion was formed, which is not "
                f"the same as the answer looking fine."
            ) from failure

        agreed = agreement(answers)
        if agreed >= self.settings.agrees_above:
            return ()
        return (
            AnswerSignal(
                rule="judge.inconsistent",
                kind=Weakness.SHAPE,
                weight=self.settings.weight,
            ),
        )
